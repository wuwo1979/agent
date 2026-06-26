"""
外部 REST 适配器层 — 为 Dify 等 HTTP 客户端提供 REST-to-MCP-JSON-RPC 桥接。

架构设计（v2.0.0）：
    此模块是「纯适配器」，不包含任何工具执行逻辑。
    所有工具操作通过 JSON-RPC 委托给 MCPProtocolHandler.handle_request()。
    MCPProtocolHandler 是系统唯一的工具执行入口。

职责边界：
    ┌─ ExternalAPIHandler ──────────────────────────────────────┐
    │  工具相关: /api/v1/tools/list, /api/v1/tools/call        │
    │    → 组装 JSON-RPC 请求 → protocol_handler.handle_request() │
    │    → 将 JSON-RPC 响应包装为 Dify 友好的 REST 格式        │
    │  运维相关: /api/v1/health, /api/v1/logs, /api/v1/stats   │
    │    → 直接从协议内核取数，不走 JSON-RPC（非 MCP 概念）    │
    │  Ollama 代理: /api/v1/ollama/proxy/*                     │
    │    → 纯 HTTP 转发，与 MCP 协议无关                      │
    └──────────────────────────────────────────────────────────┘

端点：
    POST /api/v1/tools/list       → REST-to-MCP 桥（JSON-RPC → Dify 格式）
    POST /api/v1/tools/call       → REST-to-MCP 桥（JSON-RPC → REST 格式）
    GET  /api/v1/health           → 原生 REST（协议内核统计）
    GET  /api/v1/logs             → 原生 REST（审计日志查询）
    GET  /api/v1/stats            → 原生 REST（指标统计）
    GET  /api/v1/tenants          → 原生 REST（租户列表）
    /*   /api/v1/ollama/proxy/*   → 纯 HTTP 转发

Dify 集成配置:
  http://host.docker.internal:9090/api/v1/tools/call  (X-API-Key 头)
  http://host.docker.internal:9090/api/v1/ollama/proxy (模型供应商)

Trae/Cursor 集成:
  通过标准 MCP STDIO 协议接入，不走此 REST 层
  python scripts/setup_mcp.py --ide trae
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict

from core.types import JSONRPCRequest, JSONRPCResponse


def _cors_headers() -> Dict[str, str]:
    """CORS 头 — 允许所有来源（开发环境）。"""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-API-Key, Authorization",
        "Access-Control-Max-Age": "86400",
    }


class ExternalAPIHandler:
    """
    REST 适配器 — 将 HTTP REST 请求转为 MCP JSON-RPC 协议。

    不包含任何工具执行逻辑，所有工具操作委托给 protocol_handler。
    鉴权、多租户过滤在适配层完成（这些是 REST API 的职责，非 MCP 协议概念）。

    用法:
        handler = ExternalAPIHandler(
            protocol_handler=server.protocol,  # MCPProtocolHandler
            tenancy=tenancy_manager,
            platform="dify",
        )
        # tools/list 和 tools/call 内部走 JSON-RPC
        result = await handler.handle_tools_list(headers)
        result = await handler.handle_tools_call(body, headers)
    """

    def __init__(
        self,
        protocol_handler,  # MCPProtocolHandler
        platform: str = "api",
    ):
        self.protocol = protocol_handler
        self.platform = platform

    def _auth(self, headers: Dict[str, str]) -> tuple[bool, str, str]:
        """
        多租户 API Key 鉴权。
        返回 (通过, 调用方标识, tenant_id)。
        """
        from mcp_gateway.tenancy import get_tenancy
        tenancy = get_tenancy()
        api_key = headers.get("X-API-Key", headers.get("x-api-key", ""))
        if not api_key:
            return False, "anonymous", ""
        auth_context = tenancy.authenticate(headers)
        if auth_context.authenticated:
            caller = f"key_{api_key[:8]}" if len(api_key) >= 8 else api_key
            tenant_id = auth_context.metadata.get("tenant_id", "")
            return True, caller, tenant_id
        return False, "anonymous", ""

    # ── 通用响应封装 ──────────────────────────────────────────────

    def _rest_response(self, data: Any, status: int = 200) -> Dict[str, Any]:
        return {
            "status": status,
            "headers": {**_cors_headers(), "Content-Type": "application/json"},
            "body": json.dumps(data, ensure_ascii=False, default=str),
        }

    def _rest_error(self, message: str, status: int = 400) -> Dict[str, Any]:
        return self._rest_response({"error": True, "message": message}, status)

    def _jsonrpc_to_rest(self, rpc_resp: JSONRPCResponse) -> Dict[str, Any]:
        """将 JSON-RPC 响应转为 REST 格式。"""
        if rpc_resp.error:
            return self._rest_error(
                rpc_resp.error.get("message", "Unknown error"),
                _jsonrpc_code_to_http(rpc_resp.error.get("code", -32603)),
            )
        return self._rest_response(rpc_resp.result)

    # ── tools/list — REST → JSON-RPC → Dify 格式 ────────────────

    async def handle_tools_list(self, headers: Dict[str, str]) -> Dict[str, Any]:
        """
        GET/POST /api/v1/tools/list

        流程：REST 请求 → JSON-RPC {"method":"tools/list"} → MCPProtocolHandler
              → JSON-RPC 响应 → Dify 兼容格式 (扁平参数列表)
        """
        authenticated, _, tenant_id = self._auth(headers)
        if not authenticated:
            return self._rest_error("Unauthorized: invalid or missing X-API-Key", 401)

        # 通过协议内核获取工具列表
        req = JSONRPCRequest(id="api-tools-list", method="tools/list", params={})
        resp = await self.protocol.handle_request(req)

        if resp.error:
            return self._jsonrpc_to_rest(resp)

        all_tools = resp.result.get("tools", [])

        # 多租户过滤（仅 REST 层关心）
        if tenant_id:
            from mcp_gateway.tenancy import get_tenancy
            tenancy = get_tenancy()
            tenant = tenancy.get_tenant(tenant_id)
        else:
            tenant = None

        dify_tools = []
        for tool in all_tools:
            tool_name = tool.get("name", "")
            if tenant and getattr(tenant, 'allowed_tools', None):
                if tool_name not in tenant.allowed_tools:
                    continue

            params = []
            schema = tool.get("inputSchema", {})
            for prop_name, prop_info in schema.get("properties", {}).items():
                params.append({
                    "name": prop_name,
                    "type": prop_info.get("type", "string"),
                    "description": prop_info.get("description", ""),
                    "required": prop_name in schema.get("required", []),
                })

            dify_tools.append({
                "name": tool_name,
                "description": tool.get("description", ""),
                "parameters": params,
            })

        return self._rest_response({
            "tools": dify_tools,
            "count": len(dify_tools),
            "tenant_id": tenant_id,
            "platform": self.platform,
        })

    # ── tools/call — REST → JSON-RPC → 执行 → REST ─────────────

    async def handle_tools_call(self, body: dict, headers: Dict[str, str]) -> Dict[str, Any]:
        """
        POST /api/v1/tools/call

        流程：REST 请求 → JSON-RPC {"method":"tools/call","params":{...}}
              → MCPProtocolHandler.handle_request() → 中间件管道 → 工具执行
              → JSON-RPC 响应 → REST 格式

        完全复用协议内核的：安全校验、超时、错误码标准化、可观测性埋点。
        """
        authenticated, caller, tenant_id = self._auth(headers)
        if not authenticated:
            return self._rest_error("Unauthorized: invalid or missing X-API-Key", 401)

        tool_name = body.get("name", "")
        arguments = body.get("arguments", {})
        if not tool_name:
            return self._rest_error("Missing required field: 'name'")

        # 多租户权限检查（REST 层职责）
        if tenant_id:
            from mcp_gateway.tenancy import get_tenancy
            from mcp_gateway.security import AuthResult
            tenancy = get_tenancy()
            access_result = tenancy.check_tool_access(tenant_id, tool_name)
            if access_result == AuthResult.DENY:
                return self._rest_error(
                    f"Permission denied: tenant '{tenant_id}' not allowed to use '{tool_name}'", 403)

        # 通过协议内核执行工具调用
        start = time.perf_counter()
        req = JSONRPCRequest(
            id="api-tools-call",
            method="tools/call",
            params={"name": tool_name, "arguments": arguments},
        )
        resp = await self.protocol.handle_request(req)

        if resp.error:
            http_status = _jsonrpc_code_to_http(resp.error.get("code", -32603))
            return self._rest_error(
                resp.error.get("message", "Tool execution failed"),
                http_status,
            )

        # 提取文本结果
        content = resp.result.get("content", [])
        text_result = "".join(item.get("text", "") for item in content if item.get("type") == "text")

        duration_ms = (time.perf_counter() - start) * 1000
        return self._rest_response({
            "success": not resp.result.get("isError", False),
            "tool_name": tool_name,
            "result": text_result or str(content),
            "duration_ms": round(duration_ms, 2),
            "is_error": resp.result.get("isError", False),
        })

    # ── health — 直接从协议内核取数 ─────────────────────────────

    async def handle_health(self) -> Dict[str, Any]:
        """GET /api/v1/health — 直接从协议内核取数。"""
        stats = self.protocol.get_stats()
        return self._rest_response({
            "status": "healthy",
            "server": "MCP 本地工具网关",
            "version": "2.0.0",
            "protocol_handlers": stats.get("protocol", {}).get("handlers", 0),
            "tools": stats.get("registry", {}).get("tools", 0),
            "providers": stats.get("registry", {}).get("providers", 0),
            "active_sessions": stats.get("protocol", {}).get("active_sessions", 0),
        })

    # ── logs ─────────────────────────────────────────────────────

    async def handle_logs(self, query_params: Dict[str, str]) -> Dict[str, Any]:
        """GET /api/v1/logs"""
        from mcp_gateway.audit import get_audit_logger
        audit = get_audit_logger()

        platform = query_params.get("platform")
        tool_name = query_params.get("tool")
        try:
            limit = int(query_params.get("limit", "50"))
        except ValueError:
            limit = 50
        try:
            offset = int(query_params.get("offset", "0"))
        except ValueError:
            offset = 0
        error_only = query_params.get("error_only", "false").lower() == "true"

        entries = await audit.query(
            platform=platform,
            tool_name=tool_name,
            limit=min(limit, 200),
            offset=offset,
            error_only=error_only,
        )
        return self._rest_response({
            "entries": entries,
            "count": len(entries),
            "filters": {"platform": platform, "tool": tool_name, "error_only": error_only},
        })

    # ── stats — 直接从协议内核取数 ──────────────────────────────

    async def handle_stats(self) -> Dict[str, Any]:
        """GET /api/v1/stats — 协议内核 + 审计日志统计。"""
        from mcp_gateway.audit import get_audit_logger
        audit = get_audit_logger()
        return self._rest_response({
            "protocol": self.protocol.get_stats(),
            "audit": await audit.get_stats(),
        })

    # ── tenants ──────────────────────────────────────────────────

    async def handle_tenants_list(self) -> Dict[str, Any]:
        """GET /api/v1/tenants"""
        from mcp_gateway.tenancy import get_tenancy
        tenancy = get_tenancy()
        return self._rest_response({
            "tenants": tenancy.list_tenants(),
            "count": len(tenancy._tenants),
        })


# ── JSON-RPC 错误码 → HTTP 状态码 ─────────────────────────────

_RPC_TO_HTTP = {
    -32700: 400,   # Parse error
    -32600: 400,   # Invalid Request
    -32601: 404,   # Method not found
    -32602: 422,   # Invalid params
    -32603: 500,   # Internal error
    -32001: 403,   # Permission denied
    -32002: 500,   # Tool execution error
    -32003: 504,   # Tool timeout
    -32004: 404,   # Resource not found
    -32005: 401,   # Auth required
    -32006: 429,   # Rate limited
    -32007: 401,   # Session expired
}


def _jsonrpc_code_to_http(rpc_code: int) -> int:
    """将 JSON-RPC 错误码映射到 HTTP 状态码。"""
    return _RPC_TO_HTTP.get(rpc_code, 500)


# ── Ollama API Proxy ──────────────────────────────────────────────

_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
_OLLAMA_PROXY_PREFIX = "/api/v1/ollama/proxy"


# ── 标准化错误码 ──────────────────────────────────────────────

OLLAMA_ERROR_MAP = {
    "not found": {"code": "MODEL_NOT_FOUND", "status": 404, "message": "请求的模型不存在，请检查模型名称"},
    "does not support tools": {"code": "TOOLS_NOT_SUPPORTED", "status": 400, "message": "当前模型不支持工具调用"},
    "does not support vision": {"code": "VISION_NOT_SUPPORTED", "status": 400, "message": "当前模型不支持视觉识别"},
    "context length": {"code": "CONTEXT_OVERFLOW", "status": 413, "message": "输入超过模型最大上下文长度"},
    "timeout": {"code": "TIMEOUT", "status": 504, "message": "模型生成超时，请稍后重试"},
    "llama server error": {"code": "LLAMA_SERVER_CRASH", "status": 502, "message": "模型推理引擎异常，请检查 GPU/CPU 状态"},
    "CUDA error": {"code": "GPU_CRASH", "status": 502, "message": "GPU 推理异常，可能为显卡驱动或显存不足导致"},
    "out of memory": {"code": "OOM", "status": 507, "message": "显存/内存不足，请尝试更小的模型或量化版本"},
    "load failed": {"code": "MODEL_LOAD_FAILED", "status": 502, "message": "模型加载失败，请检查模型文件是否完整"},
    "connection refused": {"code": "OLLAMA_DOWN", "status": 503, "message": "Ollama 服务未运行或无法连接"},
}


def _standardize_ollama_error(status: int, body: str) -> Dict[str, Any]:
    """
    将 Ollama 原始错误转换为标准化格式，Dify 侧可以识别并优雅降级。

    返回：
    {
        "error": {
            "code": "GPU_CRASH",
            "message": "GPU 推理异常...",
            "ollama_raw": "CUDA error: device kernel image is invalid",
            "proxy_status": 502
        }
    }
    """
    error_data = {"code": "UNKNOWN", "status": status, "message": f"Ollama 返回错误 (HTTP {status})"}

    try:
        raw = json.loads(body)
        raw_msg = raw.get("error", body) if isinstance(raw, dict) else body
    except json.JSONDecodeError:
        raw_msg = body

    if isinstance(raw_msg, str):
        raw_lower = raw_msg.lower()
        for keyword, info in OLLAMA_ERROR_MAP.items():
            if keyword.lower() in raw_lower:
                error_data.update(info)
                break

    error_data["ollama_raw"] = str(raw_msg)[:500]
    return {"error": error_data}


class OllamaProxyResponse:
    """Response from Ollama proxy — wraps raw HTTP response."""
    def __init__(self, status: int, body: str, content_type: str = "application/json"):
        self.status = status
        self.body = body
        self.content_type = content_type
        self.is_error = status >= 400
        self.error_body: str = ""


async def _forward_ollama_request(
    method: str, path: str, request_body: str = "",
) -> OllamaProxyResponse:
    """
    Forward a request to Ollama and return the response.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: The remaining URL path to forward (e.g. /api/tags, /api/chat)
        request_body: Raw request body string

    Returns:
        OllamaProxyResponse with status, body, content_type
    """
    target_url = f"{_OLLAMA_BASE_URL}{path}"

    try:
        req = urllib.request.Request(
            target_url,
            data=request_body.encode("utf-8") if request_body else None,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            content_type = resp.headers.get("Content-Type", "application/json")
            return OllamaProxyResponse(
                status=resp.status,
                body=body,
                content_type=content_type,
            )
    except urllib.error.HTTPError as e:
        raw_body = e.read().decode("utf-8") if e.fp else str(e)
        # 标准化错误码
        standardized = _standardize_ollama_error(e.code, raw_body)
        return OllamaProxyResponse(
            status=standardized.get("error", {}).get("status", e.code),
            body=json.dumps(standardized, ensure_ascii=False),
            content_type="application/json",
        )
    except urllib.error.URLError as e:
        error_body = json.dumps(
            _standardize_ollama_error(502, str(e.reason)),
            ensure_ascii=False,
        )
        return OllamaProxyResponse(
            status=502,
            body=error_body,
            content_type="application/json",
        )
    except Exception as e:
        error_body = json.dumps(
            _standardize_ollama_error(502, str(e)),
            ensure_ascii=False,
        )
        return OllamaProxyResponse(
            status=502,
            body=error_body,
            content_type="application/json",
        )


async def _forward_ollama_streaming(
    method: str, path: str, request_body: str,
) -> OllamaProxyResponse:
    """
    检测是否为流式请求。如果 stream=true，返回 SSE 流标记。
    否则退回普通代理。
    """
    # 解析请求体判断是否流式
    try:
        body_data = json.loads(request_body) if request_body else {}
        is_stream = body_data.get("stream", False)
    except json.JSONDecodeError:
        is_stream = False

    if not is_stream:
        # 非流式 — 走普通代理
        return await _forward_ollama_request(method, path, request_body)

    # 流式 — 返回标记，由传输层处理 SSE 转发
    return OllamaProxyResponse(
        status=200,
        body=json.dumps({"_stream": True, "_target": f"{_OLLAMA_BASE_URL}{path}"}),
        content_type="application/json",
    )


def create_ollama_proxy_routes() -> Dict[str, Callable]:
    """
    Create Ollama API proxy routes.

    Dify uses these endpoints to talk to Ollama through the MCP Gateway.
    Proxy all requests: /api/v1/ollama/proxy/api/* → http://127.0.0.1:11434/api/*

    Returns:
        {("*", "/api/v1/ollama/proxy/{tail:.*}"): handler}
    """
    routes = {}

    async def _ollama_proxy_handler(request) -> Dict[str, Any]:
        """
        Catch-all handler for Ollama proxy.
        Extracts the path after /api/v1/ollama/proxy/ and forwards to Ollama.
        """
        # Get the full path from the request
        full_path = request.path if hasattr(request, 'path') else str(request.url)

        # Extract the path after the proxy prefix
        if _OLLAMA_PROXY_PREFIX in full_path:
            idx = full_path.index(_OLLAMA_PROXY_PREFIX)
            remaining = full_path[idx + len(_OLLAMA_PROXY_PREFIX):]
        else:
            remaining = ""

        if not remaining:
            remaining = "/"

        method = request.method
        body = ""
        if method in ("POST", "PUT", "PATCH"):
            body = await request.text() if hasattr(request, 'text') else ""

        # 检查是否为流式请求
        try:
            body_data = json.loads(body) if body else {}
            is_stream = body_data.get("stream", False)
        except json.JSONDecodeError:
            is_stream = False

        if is_stream:
            # 流式 SSE 转发 — 由传输层处理
            return {
                "_stream": True,
                "_stream_url": f"http://127.0.0.1:11434{remaining}",
                "_stream_body": body,
                "status": 200,
                "headers": {
                    **_cors_headers(),
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
                "body": "",
            }

        proxy_resp = await _forward_ollama_request(method, remaining, body)

        # 如果代理返回错误但 body 未标准化，补一层标准化
        response_body = proxy_resp.body
        if proxy_resp.is_error:
            try:
                parsed = json.loads(response_body)
                if "error" not in parsed or "code" not in parsed.get("error", {}):
                    standardized = _standardize_ollama_error(proxy_resp.status, response_body)
                    response_body = json.dumps(standardized, ensure_ascii=False)
            except json.JSONDecodeError:
                standardized = _standardize_ollama_error(proxy_resp.status, response_body)
                response_body = json.dumps(standardized, ensure_ascii=False)

        return {
            "status": proxy_resp.status,
            "headers": {
                **_cors_headers(),
                "Content-Type": proxy_resp.content_type,
            },
            "body": response_body,
        }

    # Catch-all route for any HTTP method under the proxy prefix
    routes[("*", _OLLAMA_PROXY_PREFIX)] = _ollama_proxy_handler
    routes[("*", f"{_OLLAMA_PROXY_PREFIX}/{{tail:.*}}")] = _ollama_proxy_handler

    return routes


def create_api_routes(
    api_handler: ExternalAPIHandler,
) -> Dict[str, Callable]:
    """
    创建 API 路由映射表。

    Returns:
        {
            ("POST", "/api/v1/tools/list"): handler_func,
            ("POST", "/api/v1/tools/call"): handler_func,
            ("GET", "/api/v1/health"): handler_func,
            ("GET", "/api/v1/logs"): handler_func,
            ("GET", "/api/v1/stats"): handler_func,
        }
    """
    routes = {}

    async def _tools_list(request) -> Dict[str, Any]:
        return await api_handler.handle_tools_list(dict(request.headers))

    async def _tools_call(request) -> Dict[str, Any]:
        body = await request.json() if hasattr(request, 'json') else json.loads(await request.text())
        return await api_handler.handle_tools_call(body, dict(request.headers))

    async def _health(request) -> Dict[str, Any]:
        return await api_handler.handle_health()

    async def _logs(request) -> Dict[str, Any]:
        return await api_handler.handle_logs(dict(request.query))

    async def _stats(request) -> Dict[str, Any]:
        return await api_handler.handle_stats()

    async def _tenants_list(request) -> Dict[str, Any]:
        return await api_handler.handle_tenants_list()

    # CORS preflight
    async def _cors_preflight(request) -> Dict[str, Any]:
        return {
            "status": 204,
            "headers": _cors_headers(),
            "body": "",
        }

    routes[("POST", "/api/v1/tools/list")] = _tools_list
    routes[("GET", "/api/v1/tools/list")] = _tools_list
    routes[("POST", "/api/v1/tools/call")] = _tools_call
    routes[("GET", "/api/v1/health")] = _health
    routes[("GET", "/api/v1/logs")] = _logs
    routes[("GET", "/api/v1/stats")] = _stats
    routes[("GET", "/api/v1/tenants")] = _tenants_list
    routes[("OPTIONS", "/api/v1/tools/list")] = _cors_preflight
    routes[("OPTIONS", "/api/v1/tools/call")] = _cors_preflight

    return routes
