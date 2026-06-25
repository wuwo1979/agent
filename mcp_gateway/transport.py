"""
MCP Gateway - 传输层
实现 Streamable HTTP 传输（MCP 2025 推荐方案）
支持 SSE 回退和 STDIO 模式

参考: https://spec.modelcontextprotocol.io/specification/2025-03-26/basic/transports/
"""

import asyncio
import json
import uuid
import time
from typing import Any, Callable, Dict, Optional, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger("mcp_gateway.transport")


class TransportType(str, Enum):
    STREAMABLE_HTTP = "streamable-http"
    SSE = "sse"
    STDIO = "stdio"


@dataclass
class MCPSession:
    """MCP 会话"""
    session_id: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    capabilities: Dict[str, Any] = field(default_factory=dict)


class SessionManager:
    """
    MCP 会话管理器
    管理客户端会话生命周期，支持过期清理
    """

    def __init__(self, session_timeout: int = 300):
        self._sessions: Dict[str, MCPSession] = {}
        self._timeout = session_timeout
        self._cleanup_task: Optional[asyncio.Task] = None

    def create_session(self, metadata: Dict[str, Any] = None) -> MCPSession:
        """创建新会话"""
        session_id = f"mcp-{uuid.uuid4().hex[:16]}"
        session = MCPSession(
            session_id=session_id,
            metadata=metadata or {},
        )
        self._sessions[session_id] = session
        logger.info(f"Session created: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[MCPSession]:
        """获取会话"""
        session = self._sessions.get(session_id)
        if session:
            session.last_activity = time.time()
        return session

    def remove_session(self, session_id: str):
        """移除会话"""
        self._sessions.pop(session_id, None)
        logger.info(f"Session removed: {session_id}")

    def cleanup_expired(self):
        """清理过期会话"""
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.last_activity > self._timeout
        ]
        for sid in expired:
            self.remove_session(sid)
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")

    async def start_cleanup_loop(self, interval: int = 60):
        """启动定期清理"""
        while True:
            await asyncio.sleep(interval)
            self.cleanup_expired()

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)


class StreamableHTTPTransport:
    """
    Streamable HTTP 传输层
    MCP 2025-03-26 规范推荐方案

    核心特性：
    - 单端点 /mcp 处理所有请求
    - Content-Type 协商：application/json 或 text/event-stream
    - 显式会话管理（Mcp-Session-Id Header）
    - 无状态模式支持（stateless）
    - 支持 Server-Sent Events 流式响应
    """

    def __init__(
        self,
        protocol_handler: Callable,
        session_manager: Optional[SessionManager] = None,
        stateless: bool = False,
    ):
        self.protocol_handler = protocol_handler
        self.session_manager = session_manager or SessionManager()
        self.stateless = stateless

    async def handle_streamable_http(
        self,
        method: str,
        body: str,
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        处理 Streamable HTTP 请求
        Returns:
            {
                "status": 200,
                "headers": {...},
                "body": "...",
                "content_type": "application/json" | "text/event-stream",
                "is_stream": False
            }
        """
        # 1. 会话管理
        session_id = headers.get("mcp-session-id", "")
        session = None

        if not self.stateless and session_id:
            session = self.session_manager.get_session(session_id)

        # 2. 解析 JSON-RPC 请求
        try:
            request_data = json.loads(body)
        except json.JSONDecodeError as e:
            return self._error_response(None, -32700, f"Parse error: {e}")

        request_id = request_data.get("id")
        method_name = request_data.get("method", "")
        params = request_data.get("params", {})

        # 3. initialize 特殊处理 → 创建会话
        response_headers = {}
        if method_name == "initialize":
            if not self.stateless:
                session = self.session_manager.create_session()
                response_headers["Mcp-Session-Id"] = session.session_id

        # 4. 处理请求
        try:
            result = await self.protocol_handler(method_name, params, session)
            return self._success_response(
                request_id, result, response_headers,
                stream=isinstance(result, dict) and result.get("_stream", False)
            )
        except Exception as e:
            logger.exception(f"Handler error for {method_name}")
            return self._error_response(request_id, -32000, str(e), response_headers)

    def _success_response(
        self, request_id: Any, result: Any,
        headers: Dict[str, str] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """构建成功响应"""
        response_headers = headers or {}
        response_headers["Content-Type"] = "application/json"

        response_body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }

        return {
            "status": 200,
            "headers": response_headers,
            "body": json.dumps(response_body, ensure_ascii=False, default=str),
            "content_type": "application/json",
            "is_stream": False,
        }

    def _error_response(
        self, request_id: Any, code: int, message: str,
        headers: Dict[str, str] = None,
    ) -> Dict[str, Any]:
        """构建错误响应"""
        response_headers = headers or {}
        response_headers["Content-Type"] = "application/json"

        response_body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

        return {
            "status": 200,
            "headers": response_headers,
            "body": json.dumps(response_body, ensure_ascii=False),
            "content_type": "application/json",
            "is_stream": False,
        }


class SSETransport:
    """
    SSE (Server-Sent Events) 传输层
    MCP 2024-11-05 规范（已 deprecated，保留兼容）
    """

    def __init__(self, protocol_handler: Callable):
        self.protocol_handler = protocol_handler

    async def handle_sse(self, request: str) -> AsyncGenerator[str, None]:
        """处理 SSE 请求，生成事件流"""
        try:
            request_data = json.loads(request)
        except json.JSONDecodeError:
            yield f"event: error\ndata: {json.dumps({'error': 'Parse error'})}\n\n"
            return

        request_id = request_data.get("id")
        method = request_data.get("method", "")
        params = request_data.get("params", {})

        # 发送开始事件
        yield f"event: start\ndata: {json.dumps({'id': request_id})}\n\n"

        try:
            result = await self.protocol_handler(method, params, None)

            # 如果是生成器，逐块发送
            if hasattr(result, '__aiter__'):
                async for chunk in result:
                    chunk_data = json.dumps({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"chunk": chunk},
                    })
                    yield f"event: message\ndata: {chunk_data}\n\n"
            else:
                result_data = json.dumps({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": result,
                })
                yield f"event: message\ndata: {result_data}\n\n"

        except Exception as e:
            error_data = json.dumps({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(e)},
            })
            yield f"event: error\ndata: {error_data}\n\n"

        # 结束事件
        yield f"event: done\ndata: {json.dumps({'id': request_id})}\n\n"


class STDIOTransport:
    """
    STDIO 传输层
    用于本地进程间通信（如 Claude Desktop 集成）
    """

    def __init__(self, protocol_handler: Callable):
        self.protocol_handler = protocol_handler

    async def serve(self):
        """启动 STDIO 服务"""
        import sys

        logger.info("MCP Gateway starting in STDIO mode...")
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            try:
                line = await reader.readline()
                if not line:
                    break

                request = line.decode().strip()
                if not request:
                    continue

                result = await self.protocol_handler(request, {}, None)
                if isinstance(result, dict):
                    response = json.dumps({
                        "jsonrpc": "2.0",
                        "id": result.get("id", ""),
                        "result": result.get("result", result),
                    })
                else:
                    response = json.dumps({
                        "jsonrpc": "2.0",
                        "result": str(result),
                    })

                sys.stdout.write(response + "\n")
                sys.stdout.flush()

            except Exception as e:
                error_response = json.dumps({
                    "jsonrpc": "2.0",
                    "error": {"code": -32000, "message": str(e)},
                })
                sys.stdout.write(error_response + "\n")
                sys.stdout.flush()


# ============================================================
# Unified MCP Transport (Facade)
# ============================================================

class MCPTransport:
    """
    Unified MCP transport layer.

    Routes between Streamable HTTP, SSE, and STDIO transports
    based on server configuration.
    """

    def __init__(self, protocol_handler: Callable):
        self.protocol_handler = protocol_handler
        self.session_manager = SessionManager()
        self.http_transport = StreamableHTTPTransport(
            protocol_handler, self.session_manager
        )
        self.sse_transport = SSETransport(protocol_handler)
        self.stdio_transport = STDIOTransport(protocol_handler)

    async def http_serve(self, host: str = "0.0.0.0", port: int = 9090):
        """Start HTTP server with Streamable HTTP support."""
        try:
            from aiohttp import web
        except ImportError:
            logger.error("aiohttp is required for HTTP mode. Install with: pip install aiohttp")
            return

        async def mcp_handler(request: web.Request) -> web.Response:
            """Handle incoming MCP requests."""
            body = await request.text()
            headers = dict(request.headers)
            method = request.method

            result = await self.http_transport.handle_streamable_http(
                method=method, body=body, headers=headers
            )

            return web.Response(
                status=result["status"],
                text=result["body"],
                headers=result["headers"],
                content_type=result["content_type"],
            )

        app = web.Application()
        app.router.add_post("/mcp", mcp_handler)
        app.router.add_get("/mcp", mcp_handler)
        app.router.add_get("/health", lambda r: web.json_response({"status": "ok"}))
        app.router.add_get("/stats", lambda r: web.json_response(
            self.session_manager.active_sessions
        ))

        logger.info(f"MCP Gateway starting on {host}:{port}")
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

        # Keep running
        await asyncio.Event().wait()

    async def stdio_serve(self):
        """Start STDIO server."""
        await self.stdio_transport.serve()
