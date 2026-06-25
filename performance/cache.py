"""
性能优化层 - 增量上下文缓存
工具返回结果自动去重压缩，减少 Token 消耗
目标：对比全量回传 Token 减少 35%+
"""

import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("performance.cache")


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    content: str
    hash: str
    timestamp: float = field(default_factory=time.time)
    hit_count: int = 0
    token_count: int = 0


class IncrementalContextCache:
    """
    增量上下文缓存
    核心策略：
    1. 内容哈希去重：相同结果的工具调用不重复传回
    2. 增量压缩：只传回与上次不同的部分
    3. LRU 淘汰：限制缓存大小
    4. 语义摘要：超长结果自动压缩为摘要
    """

    def __init__(
        self,
        max_entries: int = 1000,
        max_content_length: int = 8000,
        compression_threshold: int = 2000,
    ):
        self.max_entries = max_entries
        self.max_content_length = max_content_length
        self.compression_threshold = compression_threshold

        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._content_hashes: Dict[str, str] = {}

        # 统计
        self.total_calls: int = 0
        self.cache_hits: int = 0
        self.tokens_saved: int = 0
        self.total_tokens: int = 0

    def _compute_key(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """计算缓存键"""
        args_str = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        raw = f"{tool_name}:{args_str}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def _compute_content_hash(self, content: str) -> str:
        """计算内容哈希"""
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def get(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Tuple[str, int]]:
        """
        获取缓存结果
        Returns:
            (content, token_count) 或 None
        """
        key = self._compute_key(tool_name, arguments)
        self.total_calls += 1

        if key in self._cache:
            entry = self._cache[key]
            entry.hit_count += 1
            self.cache_hits += 1

            # 移动到末尾（LRU）
            self._cache.move_to_end(key)

            logger.debug(f"Cache HIT: {tool_name} (hit count: {entry.hit_count})")
            return entry.content, entry.token_count

        logger.debug(f"Cache MISS: {tool_name}")
        return None

    def set(self, tool_name: str, arguments: Dict[str, Any],
            content: str, token_count: int = 0) -> int:
        """
        设置缓存
        Returns:
            实际存储的 token 数（压缩后）
        """
        key = self._compute_key(tool_name, arguments)
        content_hash = self._compute_content_hash(content)

        # 检查内容是否与之前相同
        if content_hash in self._content_hashes:
            # 内容完全重复，存储引用
            existing_key = self._content_hashes[content_hash]
            if existing_key in self._cache:
                self._cache[key] = self._cache[existing_key]
                self._cache.move_to_end(key)
                self.tokens_saved += token_count
                logger.debug(f"Content dedup: {tool_name} → saved {token_count} tokens")
                return 0

        # 压缩内容
        compressed, compressed_tokens = self._compress(content)
        saved = token_count - compressed_tokens
        self.tokens_saved += saved
        self.total_tokens += token_count

        entry = CacheEntry(
            key=key,
            content=compressed,
            hash=content_hash,
            token_count=compressed_tokens,
        )
        self._cache[key] = entry
        self._content_hashes[content_hash] = key

        # LRU 淘汰
        if len(self._cache) > self.max_entries:
            oldest_key, _ = self._cache.popitem(last=False)
            logger.debug(f"LRU evicted: {oldest_key}")

        logger.debug(f"Cached: {tool_name} | {token_count} → {compressed_tokens} tokens (saved {saved})")
        return compressed_tokens

    def _compress(self, content: str) -> Tuple[str, int]:
        """智能压缩内容"""
        if len(content) <= self.compression_threshold:
            return content, self._estimate_tokens(content)

        # 策略 1：截断 + 摘要
        truncated = content[:self.max_content_length]
        if len(content) > self.max_content_length:
            truncated += f"\n\n[... 已截断 {len(content) - self.max_content_length} 字符 ...]"

        return truncated, self._estimate_tokens(truncated)

    def _estimate_tokens(self, text: str) -> int:
        """估算 Token 数（粗略：4 字符 ≈ 1 token）"""
        return max(1, len(text) // 4)

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        hit_rate = self.cache_hits / max(self.total_calls, 1) * 100
        save_rate = self.tokens_saved / max(self.total_tokens, 1) * 100

        return {
            "cache_size": len(self._cache),
            "total_calls": self.total_calls,
            "cache_hits": self.cache_hits,
            "hit_rate": f"{hit_rate:.1f}%",
            "tokens_saved": self.tokens_saved,
            "total_tokens": self.total_tokens,
            "token_save_rate": f"{save_rate:.1f}%",
            "unique_hashes": len(self._content_hashes),
        }

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._content_hashes.clear()
        self.total_calls = 0
        self.cache_hits = 0
        self.tokens_saved = 0
        self.total_tokens = 0


class ContextCompressor:
    """
    上下文压缩器
    将工具返回结果压缩为 LLM 友好的紧凑格式
    """

    @staticmethod
    def compress_json_result(data: Any, max_length: int = 2000) -> str:
        """压缩 JSON 结果"""
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return data[:max_length]

        if isinstance(data, list):
            if len(data) > 10:
                # 大批量：只返回前 5 条 + 统计
                sample = data[:5]
                summary = json.dumps({
                    "total": len(data),
                    "sample": sample,
                    "truncated": True
                }, ensure_ascii=False, indent=2)
                return summary[:max_length]
            return json.dumps(data, ensure_ascii=False, indent=2)[:max_length]

        if isinstance(data, dict):
            # 展平深层嵌套
            flat = ContextCompressor._flatten_dict(data, max_depth=3)
            return json.dumps(flat, ensure_ascii=False, indent=2)[:max_length]

        return str(data)[:max_length]

    @staticmethod
    def _flatten_dict(d: dict, max_depth: int = 3, current_depth: int = 0) -> dict:
        """展平嵌套字典"""
        if current_depth >= max_depth:
            return {"...": f"[{len(str(d))} chars truncated]"}

        result = {}
        for k, v in d.items():
            if isinstance(v, dict):
                for sub_k, sub_v in ContextCompressor._flatten_dict(v, max_depth, current_depth + 1).items():
                    result[f"{k}.{sub_k}"] = sub_v
            elif isinstance(v, list) and len(v) > 5:
                result[k] = f"[{len(v)} items]"
            else:
                result[k] = str(v)[:200]
        return result

    @staticmethod
    def compute_diff(old_content: str, new_content: str) -> str:
        """
        计算增量差异
        只返回变化的部分，大幅减少重复内容传输
        """
        import difflib

        if old_content == new_content:
            return "[UNCHANGED]"

        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()

        diff = list(difflib.unified_diff(
            old_lines, new_lines,
            lineterm="",
            n=1  # 只显示上下文 1 行
        ))

        if not diff:
            return "[UNCHANGED]"

        # 如果差异太大，直接返回完整内容
        if len(diff) > 50:
            return new_content

        return "\n".join(diff)


# ================================================================
# Decorator: @cached(ttl=300)
# ================================================================
# Usage:
#     @cached(ttl=300)
#     async def expensive_function(arg1, arg2) -> str:
#         ...

_cached_decorator_cache: Dict[str, Tuple[Any, float]] = {}


def cached(ttl: int = 300):
    """Decorator: cache function return value with TTL (seconds).

    Cache key = function_name + repr(args). Useful for memoizing
    repetitive tool calls that return deterministic results.
    """
    def decorator(func):
        import functools
        import inspect

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                key = f"{func.__name__}:{args}:{kwargs}"
                now = time.time()
                if key in _cached_decorator_cache:
                    value, expire = _cached_decorator_cache[key]
                    if now < expire:
                        logger.debug(f"[cached] HIT: {func.__name__}")
                        return value
                    logger.debug(f"[cached] EXPIRED: {func.__name__}")
                value = await func(*args, **kwargs)
                _cached_decorator_cache[key] = (value, now + ttl)
                return value
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                key = f"{func.__name__}:{args}:{kwargs}"
                now = time.time()
                if key in _cached_decorator_cache:
                    value, expire = _cached_decorator_cache[key]
                    if now < expire:
                        logger.debug(f"[cached] HIT: {func.__name__}")
                        return value
                    logger.debug(f"[cached] EXPIRED: {func.__name__}")
                value = func(*args, **kwargs)
                _cached_decorator_cache[key] = (value, now + ttl)
                return value
            return sync_wrapper
    return decorator


def clear_cached_decorator_cache():
    """Clear all cached decorator results."""
    _cached_decorator_cache.clear()
