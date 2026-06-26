"""
MCP 本地工具网关 - 协议内核 (v2.0.0)
统一的 MCP JSON-RPC 2.0 协议实现 + 可插拔中间件管道。

架构：
    MCPProtocolHandler (协议内核 — 唯一工具执行入口)
        +-- MiddlewarePipeline (可插拔中间件: 鉴权→限流→审计→缓存)
        +-- ToolRegistry (工具注册中心)
        +-- SessionContext (会话上下文管理)
        +-- MetricsCollector (可观测性埋点)

设计原则：
- 所有工具调用必须通过 handle_request()，无一例外
- 中间件在管道中按序执行，before_request → handler → after_request
- 错误码严格对齐 JSON-RPC 2.0 标准
- 会话上下文跨传输层共享（HTTP/STDIO 同一 session_id 共享状态）

References:
- MCP Specification: https://spec.modelcontextprotocol.io/
- JSON-RPC 2.0: https://www.jsonrpc.org/specification
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback
import uuid
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from core.exceptions import (
    InvalidRequestError,
    MethodNotFoundError,
    PermissionDeniedError,
    PromptNotFoundError,
    ResourceNotFoundError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolTimeoutError,
)
from core.interfaces import IToolProvider, IToolRegistry
from core.types import (
    JSONRPCRequest,
    JSONRPCResponse,
    PromptDefinition,
    ResourceDefinition,
    ToolCallResult,
    ToolDefinition,
)

logger = logging.getLogger("mcp_gateway.protocol")


# ============================================================
# JSON-RPC 2.0 Error Codes (标准 + MCP 扩展)
# ============================================================

class JSONRPCErrorCode:
    """
    JSON-RPC 2.0 标准错误码 + MCP 扩展。
    所有错误码严格对齐规范，不容混淆。
    """
    # ---- 标准 JSON-RPC 2.0 错误码 ----
    PARSE_ERROR = -32700         # 无效 JSON
    INVALID_REQUEST = -32600     # 请求结构非法
    METHOD_NOT_FOUND = -32601    # 方法不存在
    INVALID_PARAMS = -32602      # 参数校验失败
    INTERNAL_ERROR = -32603      # 内部错误

    # ---- MCP 服务器错误码 (-32000 ~ -32099) ----
    PERMISSION_DENIED = -32001   # 权限不足
    TOOL_EXECUTION_ERROR = -32002  # 工具执行异常
    TOOL_TIMEOUT = -32003        # 工具执行超时
    RESOURCE_NOT_FOUND = -32004  # 资源未找到
    AUTH_REQUIRED = -32005       # 需要认证
    RATE_LIMITED = -32006        # 请求限流
    SESSION_EXPIRED = -32007     # 会话过期

    # 错误码 → 描述映射
    DESCRIPTIONS = {
        PARSE_ERROR: "Parse error",
        INVALID_REQUEST: "Invalid Request",
        METHOD_NOT_FOUND: "Method not found",
        INVALID_PARAMS: "Invalid params",
        INTERNAL_ERROR: "Internal error",
        PERMISSION_DENIED: "Permission denied",
        TOOL_EXECUTION_ERROR: "Tool execution error",
        TOOL_TIMEOUT: "Tool timeout",
        RESOURCE_NOT_FOUND: "Resource not found",
        AUTH_REQUIRED: "Authentication required",
        RATE_LIMITED: "Rate limited",
        SESSION_EXPIRED: "Session expired",
    }


# ============================================================
# 中间件管道 — 可插拔的执行链路拦截器
# ============================================================

@dataclass
class MiddlewareContext:
    """中间件执行上下文，贯穿整个请求生命周期。"""
    request: JSONRPCRequest
    session_id: str = ""
    client_id: str = "anonymous"
    tenant_id: str = ""
    transport: str = "http"          # http / stdio
    start_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MiddlewareResult:
    """中间件结果：继续执行或中断。"""
    proceed: bool = True
    response: Optional[JSONRPCResponse] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MiddlewarePipeline:
    """
    可插拔中间件管道。

    用法：
        pipeline = MiddlewarePipeline()
        pipeline.use(AuthMiddleware())
        pipeline.use(RateLimitMiddleware())

        # 执行
        ctx = MiddlewareContext(request=req)
        ctx = await pipeline.run_before(ctx)
        if not ctx.should_stop:
            result = await handler(req)
            await pipeline.run_after(ctx, result)
    """

    def __init__(self):
        self._before: List[Callable] = []
        self._after: List[Callable] = []

    def use(self, middleware: Callable, position: str = "before"):
        """注册中间件。middleware 签名: async (ctx: MiddlewareContext) -> MiddlewareResult。"""
        if position == "before":
            self._before.append(middleware)
        elif position == "after":
            self._after.append(middleware)

    async def run_before(self, ctx: MiddlewareContext) -> MiddlewareContext:
        """依次执行所有前置中间件。"""
        for mw in self._before:
            result = await mw(ctx)
            if not result.proceed:
                ctx.metadata["interrupted"] = True
                ctx.metadata["interrupt_response"] = result.response
                break
            ctx.metadata.update(result.metadata)
        return ctx

    async def run_after(self, ctx: MiddlewareContext, response: JSONRPCResponse):
        """依次执行所有后置中间件。"""
        for mw in self._after:
            await mw(ctx, response)


# ============================================================
# 会话上下文管理器
# ============================================================

@dataclass
class SessionContext:
    """
    会话上下文 — 跨传输层共享状态。

    无论 HTTP 还是 STDIO，同一 session_id 共享:
    - 终端工作目录
    - 文件路径缓存
    - 认证信息
    """
    session_id: str
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    client_id: str = "anonymous"
    transport: str = "http"
    metadata: Dict[str, Any] = field(default_factory=dict)


class SessionManager:
    """会话管理器 — 生命周期管理 + 过期清理。"""

    def __init__(self, timeout: int = 300):
        self._sessions: Dict[str, SessionContext] = {}
        self._timeout = timeout

    def get_or_create(self, session_id: str = "", transport: str = "http",
                      client_id: str = "anonymous") -> SessionContext:
        """获取或创建会话。"""
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            session.last_active = time.time()
            return session

        session = SessionContext(
            session_id=session_id or f"mcp-{uuid.uuid4().hex[:16]}",
            transport=transport,
            client_id=client_id,
        )
        self._sessions[session.session_id] = session
        return session

    def remove(self, session_id: str):
        self._sessions.pop(session_id, None)

    def cleanup_expired(self):
        now = time.time()
        expired = [sid for sid, s in self._sessions.items()
                   if now - s.last_active > self._timeout]
        for sid in expired:
            self.remove(sid)


# ============================================================
# 可观测性收集器
# ============================================================

@dataclass
class MetricsCollector:
    """统一指标收集 — 在协议内核埋点，确保统计口径一致。"""
    total_requests: int = 0
    total_errors: int = 0
    total_duration_ms: float = 0.0
    method_counts: Dict[str, int] = field(default_factory=dict)
    error_counts: Dict[str, int] = field(default_factory=dict)
    transport_counts: Dict[str, int] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)

    def record(self, method: str, duration_ms: float, is_error: bool = False,
               transport: str = "http", error_code: str = ""):
        self.total_requests += 1
        self.total_duration_ms += duration_ms
        self.method_counts[method] = self.method_counts.get(method, 0) + 1
        self.transport_counts[transport] = self.transport_counts.get(transport, 0) + 1
        if is_error:
            self.total_errors += 1
            self.error_counts[error_code] = self.error_counts.get(error_code, 0) + 1

    def get_stats(self) -> Dict[str, Any]:
        elapsed = time.time() - self.start_time
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "avg_duration_ms": round(self.total_duration_ms / max(self.total_requests, 1), 2),
            "error_rate": f"{self.total_errors / max(self.total_requests, 1) * 100:.1f}%",
            "uptime_seconds": round(elapsed, 1),
            "requests_per_second": round(self.total_requests / max(elapsed, 1), 2),
            "methods": self.method_counts,
            "errors": self.error_counts,
            "transports": self.transport_counts,
        }


# ============================================================
# 内置中间件工厂函数
# ============================================================

def create_auth_middleware(security_middleware) -> Callable:
    """
    认证 + 速率限制前置中间件工厂。

    从 MiddlewareContext.metadata["headers"] 提取凭证，
    委托给 SecurityMiddleware 进行认证、限流、权限检查。

    使用方式:
        mw = create_auth_middleware(security)
        pipeline.use(mw, position="before")
    """
    from mcp_gateway.security import RateLimitExceededError

    async def _auth_middleware(ctx: MiddlewareContext) -> MiddlewareResult:
        headers = ctx.metadata.get("headers", {})
        method = ctx.request.method if ctx.request else ""
        try:
            auth_context = await security_middleware.check_request(method, headers)
            ctx.client_id = auth_context.client_id
            ctx.metadata["auth_context"] = auth_context
            return MiddlewareResult(proceed=True)
        except RateLimitExceededError:
            return MiddlewareResult(
                proceed=False,
                response=JSONRPCResponse(
                    jsonrpc="2.0",
                    id=ctx.request.id if ctx.request else None,
                    error={"code": -32001, "message": "Rate limit exceeded"},
                ),
            )
        except PermissionDeniedError as e:
            return MiddlewareResult(
                proceed=False,
                response=JSONRPCResponse(
                    jsonrpc="2.0",
                    id=ctx.request.id if ctx.request else None,
                    error={"code": -32001, "message": str(e)},
                ),
            )

    return _auth_middleware


def create_audit_middleware(audit_logger) -> Callable:
    """
    审计日志后置中间件工厂。

    自动记录所有 tools/call 请求的调用结果，
    包括耗时、是否成功等信息。

    使用方式:
        mw = create_audit_middleware(audit_logger)
        pipeline.use(mw, position="after")
    """
    async def _audit_middleware(ctx: MiddlewareContext, response: JSONRPCResponse):
        method = ctx.request.method if ctx.request else ""
        if method != "tools/call":
            return
        is_error = response.error is not None if response else True
        duration = (time.perf_counter() - ctx.start_time) * 1000 if ctx.start_time else 0
        await audit_logger.record(
            tool_name=method,
            arguments=ctx.request.params if ctx.request else {},
            caller=ctx.client_id,
            is_error=is_error,
            duration_ms=round(duration, 2),
        )

    return _audit_middleware


# ============================================================
# MCP 协议内核 — 唯一工具执行入口
# ============================================================

class MCPProtocolHandler:
    """
    MCP 协议内核 — 系统的唯一工具执行入口。

    无论请求来自 STDIO（Trae）还是 HTTP（Dify），都必须经过:
        handle_request() → 中间件管道 → 方法分发 → 中间件后置处理

    设计要点：
    - 不持有任何传输层概念，纯协议级处理
    - 中间件可插拔：鉴权、限流、审计、缓存均作为中间件注入
    - 错误码严格对齐 JSON-RPC 2.0 标准
    - 可观测性在协议内核统一埋点
    """

    def __init__(self, server_name: str = "MCP 本地工具网关", server_version: str = "2.0.0"):
        self.server_name = server_name
        self.server_version = server_version

        # 协议组件
        self._handlers: Dict[str, Callable] = {}
        self._notification_handlers: Dict[str, Callable] = {}

        # 中间件管道
        self.middleware = MiddlewarePipeline()

        # 会话管理
        self.sessions = SessionManager()

        # 可观测性
        self.metrics = MetricsCollector()

        # 工具注册中心（由外部注入）
        self._registry: Optional[ToolRegistry] = None

        # 注册核心生命周期处理器
        self._register_core_handlers()

    # ── 配置 ──────────────────────────────────────────────────────

    def set_registry(self, registry: ToolRegistry):
        """注入工具注册中心。"""
        self._registry = registry
        self._register_tool_handlers()

    def use_middleware(self, fn: Callable, position: str = "before"):
        """注册中间件。"""
        self.middleware.use(fn, position)

    # ── 处理器注册 ────────────────────────────────────────────────

    def _register_core_handlers(self):
        self.register_handler("initialize", self._handle_initialize)
        self.register_handler("ping", self._handle_ping)
        self.register_notification("notifications/initialized", self._handle_initialized)
        self.register_notification("notifications/cancelled", self._handle_cancelled)

    def _register_tool_handlers(self):
        """注册工具相关处理器（需要 registry 就绪后调用）。"""
        self.register_handler("tools/list", self._handle_tools_list)
        self.register_handler("tools/call", self._handle_tools_call)
        self.register_handler("tools/get", self._handle_tools_get)
        self.register_handler("resources/list", self._handle_resources_list)
        self.register_handler("resources/read", self._handle_resources_read)
        self.register_handler("resources/templates/list", self._handle_resource_templates_list)
        self.register_handler("prompts/list", self._handle_prompts_list)
        self.register_handler("prompts/get", self._handle_prompts_get)

    def register_handler(self, method: str, handler: Callable):
        self._handlers[method] = handler

    def register_notification(self, method: str, handler: Callable):
        self._notification_handlers[method] = handler

    # ── 核心生命周期处理器 ──────────────────────────────────────────

    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._client_capabilities = params.get("capabilities", {})
        protocol_version = params.get("protocolVersion", "2025-03-26")
        return {
            "protocolVersion": protocol_version,
            "serverInfo": {"name": self.server_name, "version": self.server_version},
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"subscribe": True, "listChanged": True},
                "prompts": {"listChanged": True},
                "logging": {},
            },
        }

    async def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {}

    async def _handle_initialized(self, params: Dict[str, Any]):
        logger.info("Client initialized (session negotiated)")

    async def _handle_cancelled(self, params: Dict[str, Any]):
        logger.info(f"Request cancelled: {params}")

    # ── 工具处理器 ──────────────────────────────────────────────────

    async def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._registry:
            return {"tools": []}
        category = params.get("category")
        return {"tools": self._registry.list_tools(category=category)}

    async def _handle_tools_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._registry:
            raise MethodNotFoundError("tools/get")
        name = params.get("name", "")
        tool = self._registry.get_tool(name)
        if not tool:
            raise ToolNotFoundError(name)
        return {"tool": tool.to_mcp_format()}

    async def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具调用 — 这是系统的核心路径。"""
        if not self._registry:
            raise MethodNotFoundError("tools/call")
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = await self._registry.call_tool(name, arguments)
        return result.to_mcp_format()

    async def _handle_resources_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._registry:
            return {"resources": []}
        return {"resources": self._registry.list_resources()}

    async def _handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._registry:
            raise MethodNotFoundError("resources/read")
        uri = params.get("uri", "")
        resources = self._registry.list_resources()
        for r in resources:
            if r["uri"] == uri:
                return {
                    "contents": [{
                        "uri": r["uri"],
                        "mimeType": r.get("mimeType", "text/plain"),
                        "text": f"Resource: {r['name']}\n{r.get('description', '')}",
                    }]
                }
        raise ResourceNotFoundError(uri)

    async def _handle_resource_templates_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"resourceTemplates": []}

    async def _handle_prompts_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._registry:
            return {"prompts": []}
        return {"prompts": self._registry.list_prompts()}

    async def _handle_prompts_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._registry:
            raise MethodNotFoundError("prompts/get")
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        prompts = self._registry.list_prompts()
        for p in prompts:
            if p["name"] == name:
                return {
                    "description": p.get("description", ""),
                    "messages": [{
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": f"Using prompt: {name}\n"
                                    + "\n".join(f"{k}: {v}" for k, v in arguments.items())
                        }
                    }]
                }
        raise PromptNotFoundError(name)

    # ── 统一请求入口 ──────────────────────────────────────────────

    async def handle_request(
        self,
        request: JSONRPCRequest,
        context: Optional[MiddlewareContext] = None,
    ) -> JSONRPCResponse:
        """
        统一的请求处理入口 — 所有传输层（HTTP / STDIO）必须经过此方法。

        流程：
            1. 创建中间件上下文（或复用传入的）
            2. 执行前置中间件管道（鉴权、限流、审计等）
            3. 如果中间件中断，直接返回中断响应
            4. 分发到对应方法处理器
            5. 执行后置中间件管道
            6. 记录可观测性指标
            7. 返回 JSON-RPC 响应

        Args:
            request: JSON-RPC 2.0 请求
            context: 可选的中间件上下文，由传输层传入

        Returns:
            JSONRPCResponse — 对通知返回 None
        """
        start = time.perf_counter()

        # 1. 初始化中间件上下文
        ctx = context or MiddlewareContext(
            request=request,
            transport="http",
            start_time=start,
        )

        # 2. 前置中间件管道
        ctx = await self.middleware.run_before(ctx)
        if ctx.metadata.get("interrupted"):
            response = ctx.metadata["interrupt_response"]
            elapsed = (time.perf_counter() - start) * 1000
            self.metrics.record(request.method, elapsed, is_error=True,
                                transport=ctx.transport,
                                error_code=str(response.error.get("code", "")) if response.error else "")
            return response

        # 3. 处理通知（无返回值）
        if request.method in self._notification_handlers:
            try:
                await self._notification_handlers[request.method](request.params)
            except Exception as e:
                logger.error(f"Notification handler error: {e}")
            return None

        # 4. 方法分发
        try:
            if request.method in self._handlers:
                result = await self._handlers[request.method](request.params)
                response = JSONRPCResponse.success(request.id, result)
            else:
                raise MethodNotFoundError(request.method)
        except MethodNotFoundError as e:
            response = JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.METHOD_NOT_FOUND, str(e), e.to_dict()
            )
        except InvalidRequestError as e:
            response = JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.INVALID_REQUEST, str(e), e.to_dict()
            )
        except ToolNotFoundError as e:
            response = JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.METHOD_NOT_FOUND, str(e), e.to_dict()
            )
        except ToolExecutionError as e:
            response = JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.TOOL_EXECUTION_ERROR, str(e), e.to_dict()
            )
        except ToolTimeoutError as e:
            response = JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.TOOL_TIMEOUT, str(e), e.to_dict()
            )
        except PermissionDeniedError as e:
            response = JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.PERMISSION_DENIED, str(e), e.to_dict()
            )
        except Exception as e:
            logger.error(f"Unhandled error in {request.method}: {traceback.format_exc()}")
            response = JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.INTERNAL_ERROR, f"Internal error: {str(e)}"
            )

        # 5. 后置中间件管道
        try:
            await self.middleware.run_after(ctx, response)
        except Exception as e:
            logger.warning(f"After-middleware error: {e}")

        # 6. 可观测性埋点
        elapsed = (time.perf_counter() - start) * 1000
        is_error = response is not None and response.error is not None
        error_code = ""
        if is_error and response.error:
            error_code = str(response.error.get("code", ""))
        self.metrics.record(request.method, elapsed, is_error=is_error,
                            transport=ctx.transport, error_code=error_code)

        return response

    # ── 工具方法 ──────────────────────────────────────────────────

    def parse_request(self, raw: Union[str, bytes]) -> JSONRPCRequest:
        """解析原始 JSON-RPC 请求字符串。"""
        try:
            data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
            return JSONRPCRequest.from_dict(data)
        except json.JSONDecodeError as e:
            raise InvalidRequestError(f"Invalid JSON: {e}")
        except Exception as e:
            raise InvalidRequestError(f"Invalid request format: {e}")

    def get_handler_names(self) -> List[str]:
        """获取所有已注册的处理器方法名。"""
        return list(self._handlers.keys())

    def get_stats(self) -> Dict[str, Any]:
        """获取协议内核统计。"""
        registry_stats = self._registry.get_stats() if self._registry else {}
        return {
            "protocol": {
                "server": self.server_name,
                "version": self.server_version,
                "handlers": len(self._handlers),
                "middleware": {
                    "before": len(self.middleware._before),
                    "after": len(self.middleware._after),
                },
                "active_sessions": len(self.sessions._sessions),
            },
            "metrics": self.metrics.get_stats(),
            "registry": registry_stats,
        }


# ============================================================
# Tool Registry (Plugin-based)
# ============================================================

class ToolRegistry(IToolRegistry):
    """
    Central tool registry with plugin-based architecture.

    Features:
    - Multi-provider support with tool name prefixes
    - Tool discovery and listing
    - Tool invocation with timeout and error handling
    - Resource and prompt management
    - Tool metadata (category, version, tags)
    """

    def __init__(self):
        self._providers: Dict[str, IToolProvider] = {}
        self._tools: Dict[str, ToolDefinition] = {}
        self._tool_to_provider: Dict[str, str] = {}
        self._resources: Dict[str, ResourceDefinition] = {}
        self._prompts: Dict[str, PromptDefinition] = {}
        self._prefix_mappings: Dict[str, str] = {}  # provider_name -> prefix

        # Statistics
        self._total_calls: int = 0
        self._total_errors: int = 0
        self._total_time_ms: float = 0.0

    def register_provider(self, provider: IToolProvider, prefix: str = "") -> None:
        """Register a tool provider with optional name prefix."""
        if provider.name in self._providers:
            logger.warning(f"Provider '{provider.name}' already registered, replacing")

        self._providers[provider.name] = provider
        if prefix:
            self._prefix_mappings[provider.name] = prefix

        # Register tools from this provider
        for tool in provider.list_tools():
            full_name = f"{prefix}__{tool.name}" if prefix else tool.name
            self._tools[full_name] = tool
            self._tool_to_provider[full_name] = provider.name

        # Register resources
        for resource in provider.get_resources():
            self._resources[resource.uri] = resource

        # Register prompts
        for prompt in provider.get_prompts():
            self._prompts[prompt.name] = prompt

        logger.info(
            f"Registered provider '{provider.name}' "
            f"with {len(provider.list_tools())} tools"
            + (f" (prefix: '{prefix}')" if prefix else "")
        )

    def unregister_provider(self, provider_name: str) -> None:
        """Remove a tool provider and all its tools."""
        if provider_name not in self._providers:
            raise ToolNotFoundError(f"Provider '{provider_name}' not found")

        provider = self._providers.pop(provider_name)

        # Remove tools
        for tool in provider.list_tools():
            prefix = self._prefix_mappings.get(provider_name, "")
            full_name = f"{prefix}__{tool.name}" if prefix else tool.name
            self._tools.pop(full_name, None)
            self._tool_to_provider.pop(full_name, None)

        self._prefix_mappings.pop(provider_name, None)
        logger.info(f"Unregistered provider '{provider_name}'")

    def register_tool(self, tool: ToolDefinition, provider_name: str = "builtin") -> None:
        """Register a single tool directly."""
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, replacing")
        self._tools[tool.name] = tool
        self._tool_to_provider[tool.name] = provider_name

    # ================================================================
    # Decorator API: @registry.tool(name, ...)
    # ================================================================
    # Usage:
    #     @registry.tool("my_tool", description="Does X")
    #     async def my_tool(args: dict) -> ToolCallResult:
    #         ...

    def tool(self, name: str, description: str = "", input_schema: dict = None, category: str = "custom"):
        """Decorator: register a function as an MCP tool."""
        import inspect

        def decorator(func):
            is_async = inspect.iscoroutinefunction(func)

            tool_def = ToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema or {"type": "object", "properties": {}},
                category=category,
            )
            self._tools[name] = tool_def
            self._tool_to_provider[name] = "_decorator_"

            if is_async:
                async def handler(args: dict) -> ToolCallResult:
                    result = await func(args)
                    return result if isinstance(result, ToolCallResult) else ToolCallResult.text_result(str(result))
            else:
                async def handler(args: dict) -> ToolCallResult:
                    result = func(args)
                    return result if isinstance(result, ToolCallResult) else ToolCallResult.text_result(str(result))

            tool_def._handler = handler
            return func
        return decorator

    def list_tools(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all tools in MCP-compatible format."""
        tools = []
        for tool in self._tools.values():
            if category and tool.category != category:
                continue
            tools.append(tool.to_mcp_format())
        return tools

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get a specific tool definition."""
        return self._tools.get(name)

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolCallResult:
        """
        Execute a registered tool.

        Handles:
        - Tool lookup with prefix resolution
        - Timeout enforcement
        - Error handling
        - Execution timing
        """
        self._total_calls += 1
        start_time = time.perf_counter()

        tool = self._tools.get(name)
        if not tool:
            self._total_errors += 1
            raise ToolNotFoundError(name)

        provider_name = self._tool_to_provider.get(name)
        if not provider_name or provider_name not in self._providers:
            self._total_errors += 1
            raise ToolExecutionError(name, f"Provider '{provider_name}' not found")

        provider = self._providers[provider_name]

        try:
            # Apply timeout
            timeout = tool.timeout_ms / 1000.0
            result = await asyncio.wait_for(
                provider.call_tool(name, arguments),
                timeout=timeout,
            )
            elapsed = (time.perf_counter() - start_time) * 1000
            self._total_time_ms += elapsed

            if isinstance(result, ToolCallResult):
                result.execution_time_ms = elapsed
                return result
            elif isinstance(result, str):
                return ToolCallResult.text_result(name, result, elapsed)
            elif isinstance(result, dict):
                return ToolCallResult(
                    tool_name=name,
                    content=[{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                    execution_time_ms=elapsed,
                )
            else:
                return ToolCallResult.text_result(name, str(result), elapsed)

        except asyncio.TimeoutError:
            self._total_errors += 1
            raise ToolTimeoutError(name, tool.timeout_ms)
        except (ToolNotFoundError, ToolExecutionError, ToolTimeoutError):
            self._total_errors += 1
            raise
        except Exception as e:
            self._total_errors += 1
            logger.error(f"Tool '{name}' execution error: {traceback.format_exc()}")
            raise ToolExecutionError(name, str(e))

    def get_all_providers(self) -> Dict[str, IToolProvider]:
        return dict(self._providers)

    def list_resources(self) -> List[Dict[str, Any]]:
        """List all resources in MCP format."""
        return [
            {
                "uri": r.uri,
                "name": r.name,
                "description": r.description,
                "mimeType": r.mime_type,
            }
            for r in self._resources.values()
        ]

    def list_prompts(self) -> List[Dict[str, Any]]:
        """List all prompts in MCP format."""
        return [
            {
                "name": p.name,
                "description": p.description,
                "arguments": p.arguments,
            }
            for p in self._prompts.values()
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            "providers": len(self._providers),
            "tools": len(self._tools),
            "resources": len(self._resources),
            "prompts": len(self._prompts),
            "total_calls": self._total_calls,
            "total_errors": self._total_errors,
            "avg_time_ms": self._total_time_ms / max(self._total_calls, 1),
            "error_rate": f"{self._total_errors / max(self._total_calls, 1) * 100:.1f}%",
        }

    def get_server_instructions(self) -> str:
        """Generate comprehensive server instructions for LLM."""
        sections = []
        for provider in self._providers.values():
            sections.append(provider.get_server_instructions())
        return "\n\n".join(sections)


# ============================================================
# Tool Provider Base Class
# ============================================================

class BaseToolProvider(IToolProvider):
    """
    Base class for tool providers.

    Provides common functionality:
    - Tool registration helpers
    - Resource and prompt management
    - Server instructions generation
    """

    def __init__(self, name: str, description: str = ""):
        self._name = name
        self._description = description
        self._tools: Dict[str, ToolDefinition] = {}
        self._resources: List[ResourceDefinition] = []
        self._prompts: List[PromptDefinition] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def get_resources(self) -> List[ResourceDefinition]:
        return self._resources

    def get_prompts(self) -> List[PromptDefinition]:
        return self._prompts

    def _register_tool(self, tool: ToolDefinition):
        """Register a tool in this provider."""
        self._tools[tool.name] = tool

    def _register_resource(self, resource: ResourceDefinition):
        """Register a resource."""
        self._resources.append(resource)

    def _register_prompt(self, prompt: PromptDefinition):
        """Register a prompt template."""
        self._prompts.append(prompt)

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool. Must be implemented by subclasses."""
        ...


# SecurityMiddleware has been moved to mcp_gateway/security.py
# Import from mcp_gateway.security instead.
