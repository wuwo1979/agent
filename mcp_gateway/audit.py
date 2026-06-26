"""
统一审计日志 — 记录所有平台（Dify/Trae/Ollama/API）的工具调用。

特性：
- 内存环形缓冲区（默认 1000 条），不依赖外部数据库
- 记录：时间戳、平台、调用方、工具名、参数、结果、耗时、权限
- 支持按平台/工具名/时间范围查询
- 线程安全（asyncio.Lock）
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class AuditEntry:
    """单条审计记录。"""
    timestamp: str = ""
    platform: str = "unknown"       # dify / trae / ollama / api / curl
    caller: str = "anonymous"       # API Key 前缀或 client_id
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    result_summary: str = ""        # 结果摘要（前 200 字符）
    is_error: bool = False
    duration_ms: float = 0.0
    permission: str = "allow"       # allow / deny / require_elevation
    token_count: int = 0


class AuditLogger:
    """
    统一审计日志器。

    用法：
        logger = AuditLogger(max_entries=1000)
        logger.record(entry)
        entries = logger.query(platform="dify", limit=50)
    """

    def __init__(self, max_entries: int = 1000):
        self._buffer: deque[AuditEntry] = deque(maxlen=max_entries)
        self._lock = asyncio.Lock()
        self._total_calls = 0
        self._error_count = 0
        self._start_time = time.time()

    async def record(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        platform: str = "api",
        caller: str = "anonymous",
        result_summary: str = "",
        is_error: bool = False,
        duration_ms: float = 0.0,
        permission: str = "allow",
        token_count: int = 0,
    ):
        """记录一条审计日志。"""
        entry = AuditEntry(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            platform=platform,
            caller=caller,
            tool_name=tool_name,
            arguments=arguments,
            result_summary=result_summary[:200],
            is_error=is_error,
            duration_ms=round(duration_ms, 2),
            permission=permission,
            token_count=token_count,
        )
        async with self._lock:
            self._buffer.append(entry)
            self._total_calls += 1
            if is_error:
                self._error_count += 1

    async def query(
        self,
        platform: Optional[str] = None,
        tool_name: Optional[str] = None,
        caller: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        error_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        查询审计日志。

        Args:
            platform: 按平台过滤（dify/trae/ollama/api）
            tool_name: 按工具名过滤
            caller: 按调用方过滤
            limit: 返回条数（默认 50）
            offset: 偏移量
            error_only: 仅返回错误记录
        """
        async with self._lock:
            entries = list(self._buffer)

        # 过滤
        if platform:
            entries = [e for e in entries if e.platform == platform]
        if tool_name:
            entries = [e for e in entries if e.tool_name == tool_name]
        if caller:
            entries = [e for e in entries if e.caller == caller]
        if error_only:
            entries = [e for e in entries if e.is_error]

        # 排序（最新在前）
        entries = sorted(entries, key=lambda e: e.timestamp, reverse=True)

        # 分页
        page = entries[offset:offset + limit]

        return [asdict(e) for e in page]

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计摘要。"""
        async with self._lock:
            entries = list(self._buffer)

        total = self._total_calls
        errors = self._error_count
        uptime = time.time() - self._start_time

        # 按平台统计
        platform_counts: Dict[str, int] = {}
        for e in entries:
            platform_counts[e.platform] = platform_counts.get(e.platform, 0) + 1

        # 按工具统计
        tool_counts: Dict[str, int] = {}
        for e in entries:
            tool_counts[e.tool_name] = tool_counts.get(e.tool_name, 0) + 1

        # 平均延迟
        durations = [e.duration_ms for e in entries if e.duration_ms > 0]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total_calls": total,
            "error_count": errors,
            "error_rate": f"{errors / total * 100:.1f}%" if total > 0 else "0%",
            "uptime_seconds": round(uptime, 0),
            "buffer_size": len(entries),
            "by_platform": platform_counts,
            "by_tool": tool_counts,
            "avg_duration_ms": round(avg_duration, 2),
        }

    async def clear(self):
        """清空日志缓冲区。"""
        async with self._lock:
            self._buffer.clear()


# 全局单例
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """获取全局审计日志器单例。"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger