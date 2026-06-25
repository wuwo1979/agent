"""
Agent 调度层 - 重试与自愈机制
实现指数退避重试、失败降级、熔断保护
"""

import asyncio
import random
import time
from typing import Any, Callable, Dict, Optional, TypeVar
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger("agent_scheduler.retry")

T = TypeVar("T")


class ErrorCategory(str, Enum):
    """错误分类"""
    TRANSIENT = "transient"      # 临时错误（网络超时等）→ 可重试
    PERMANENT = "permanent"      # 永久错误（参数错误等）→ 不可重试
    DEGRADED = "degraded"        # 降级错误（服务不可用）→ 使用降级策略
    CIRCUIT_OPEN = "circuit_open"  # 熔断打开 → 快速失败


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0  # 基础延迟（秒）
    max_delay: float = 30.0  # 最大延迟（秒）
    exponential_base: float = 2.0  # 指数退避基数
    jitter: bool = True  # 是否添加随机抖动
    retryable_exceptions: tuple = (TimeoutError, ConnectionError, asyncio.TimeoutError)


@dataclass
class CircuitBreaker:
    """熔断器"""
    failure_threshold: int = 5  # 连续失败次数阈值
    recovery_timeout: float = 60.0  # 恢复超时（秒）
    half_open_max_calls: int = 3  # 半开状态最大试探调用数

    failure_count: int = 0
    last_failure_time: float = 0.0
    state: str = "closed"  # closed, open, half_open
    half_open_calls: int = 0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"Circuit breaker OPENED after {self.failure_count} failures")

    def record_success(self):
        if self.state == "half_open":
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = "closed"
                self.failure_count = 0
                self.half_open_calls = 0
                logger.info("Circuit breaker CLOSED (recovered)")
        else:
            self.failure_count = 0

    def allow_request(self) -> bool:
        """检查是否允许请求"""
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "half_open"
                self.half_open_calls = 0
                logger.info("Circuit breaker HALF_OPEN (recovery attempt)")
                return True
            return False
        return True  # half_open


class RetryManager:
    """
    重试管理器
    支持指数退避、抖动、熔断保护
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self.circuit_breaker = CircuitBreaker()
        self._retry_stats: Dict[str, int] = {}

    def classify_error(self, error: Exception) -> ErrorCategory:
        """分类错误类型"""
        if isinstance(error, self.config.retryable_exceptions):
            return ErrorCategory.TRANSIENT
        if isinstance(error, (ValueError, TypeError, KeyError)):
            return ErrorCategory.PERMANENT
        if isinstance(error, RuntimeError):
            return ErrorCategory.DEGRADED
        return ErrorCategory.TRANSIENT

    async def execute_with_retry(
        self,
        func: Callable[..., T],
        *args,
        fallback: Optional[Callable[..., T]] = None,
        tool_name: str = "unknown",
        **kwargs,
    ) -> T:
        """
        带重试的函数执行
        Args:
            func: 要执行的函数
            fallback: 降级函数
            tool_name: 工具名称（用于统计）
        Returns:
            函数返回值
        Raises:
            所有重试耗尽后的最终异常
        """
        # 检查熔断器
        if not self.circuit_breaker.allow_request():
            logger.error(f"Circuit breaker OPEN for {tool_name}")
            if fallback:
                return await self._call_fallback(fallback, *args, **kwargs)
            raise RuntimeError(f"Circuit breaker open for {tool_name}")

        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result

                # 成功：记录
                self.circuit_breaker.record_success()
                if attempt > 0:
                    logger.info(f"Retry succeeded for {tool_name} on attempt {attempt}")
                return result

            except Exception as e:
                last_error = e
                error_category = self.classify_error(e)

                if error_category == ErrorCategory.PERMANENT:
                    logger.error(f"Permanent error for {tool_name}: {e}")
                    raise

                if attempt >= self.config.max_retries:
                    logger.error(f"Max retries ({self.config.max_retries}) exhausted for {tool_name}")
                    break

                # 计算延迟
                delay = self._calculate_delay(attempt)
                logger.warning(
                    f"Retry {attempt + 1}/{self.config.max_retries} for {tool_name} "
                    f"after {delay:.1f}s. Error: {e}"
                )
                await asyncio.sleep(delay)

        # 所有重试失败
        self.circuit_breaker.record_failure()
        self._retry_stats[tool_name] = self._retry_stats.get(tool_name, 0) + 1

        if fallback:
            logger.info(f"Using fallback for {tool_name}")
            return await self._call_fallback(fallback, *args, **kwargs)

        raise last_error

    def _calculate_delay(self, attempt: int) -> float:
        """计算指数退避延迟"""
        delay = self.config.base_delay * (self.config.exponential_base ** attempt)
        delay = min(delay, self.config.max_delay)

        if self.config.jitter:
            delay *= 0.5 + random.random()  # 50%-150% 抖动

        return delay

    async def _call_fallback(self, fallback: Callable, *args, **kwargs) -> Any:
        """调用降级函数"""
        try:
            result = fallback(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as e:
            logger.error(f"Fallback also failed: {e}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """获取重试统计"""
        return {
            "retry_counts": self._retry_stats,
            "circuit_breaker_state": self.circuit_breaker.state,
            "circuit_breaker_failures": self.circuit_breaker.failure_count,
        }


# ============================================================
# 快捷重试装饰器
# ============================================================

def retryable(
    max_retries: int = 3,
    base_delay: float = 1.0,
    fallback_func: Optional[Callable] = None,
):
    """重试装饰器"""
    config = RetryConfig(max_retries=max_retries, base_delay=base_delay)
    manager = RetryManager(config)

    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            return await manager.execute_with_retry(
                func, *args, fallback=fallback_func, tool_name=func.__name__, **kwargs
            )
        return wrapper
    return decorator
