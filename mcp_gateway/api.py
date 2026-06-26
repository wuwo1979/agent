"""
外部 REST API 层 — 为 Dify / Trae / Ollama / 任何 HTTP 客户端提供统一接口。

设计原则：
- 与现有 MCP JSON-RPC 协议完全解耦，互不影响
- 所有端点复用现有 ToolRegistry 和 SecurityMiddleware
- 自动记录审计日志到 AuditLogger
- CORS 全开（开发友好）+ API Key 鉴权

端点：
    POST /api/v1/tools/list       → 列出所有工具（Dify 兼容格式）
    POST /api/v1/tools/call       → 调用指定工具
    GET  /api/v1/health           → 健康检查 + 组件状态
    GET  /api/v1/logs             → 审计日志查询
    GET  /api/v1/stats            → 调用统计
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Optional

from mcp_gateway.audit import AuditEntry, get_audit_logger
from mcp_gateway.tenancy import TenancyManager, get_tenancy


def _cors_headers() -> Dict[str, str]:
    """CORS 头 — 允许所有来源（开发环境）。"""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-API-Key, Authorization",
        "Access-Control-Max-Age": "86400",
    }


def _json_response(data: Any, status: int = 200) -> Dict[str, Any]:
    """构建 JSON 响应。"""
    return {
        "status": status,
        "headers": {**_cors_headers(), "Content-Type": "application/json"},
        "body": json.dumps(data, ensure_ascii=False, default=str),
    }


def _error_response(message: str, status: int = 400) -> Dict[str, Any]:
    """构建错误响应。"""
    return _json_response({"error": True, "message": message}, status)


class ExternalAPIHandler:
    """
    外部 REST API 处理器。

    为 Dify / Trae / Ollama 等平台提供与 MCP 协议无关的 HTTP 接口。
    集成多租户权限隔离：每个 API Key 对应一个租户，拥有独立的文件白名单和工具策略。

    用法:
        handler = ExternalAPIHandler(
            registry=server.registry,
            security=server.security,
            platform="dify",
        )
        result = await handler.handle_tools_list()
        result = await handler.handle_tools_call({"name": "sysinfo", "arguments": {}})
    """

    def __init__(
        self,
        registry,            # ToolRegistry
        security,            # SecurityMiddleware
        platform: str = "api",
    ):
        self.registry = registry
        self.security = security
        self.platform = platform
        self.audit = get_audit_logger()
        self.tenancy: TenancyManager = get_tenancy()

    def _auth(self, headers: Dict[str, str]) -> tuple[bool, str, str]:
        """
        多租户 API Key 鉴权。
        返回 (通过, 调用方标识, tenant_id)。
        """
        api_key = headers.get("X-API-Key", headers.get("x-api-key", ""))

        if not api_key:
            return False, "anonymous", ""

        auth_context = self.tenancy.authenticate(headers)
        if auth_context.authenticated:
            caller = f"key_{api_key[:8]}" if len(api_key) >= 8 else api_key
            tenant_id = auth_context.metadata.get("tenant_id", "")
            return True, caller, tenant_id
        return False, "anonymous", ""

    # ── tools/list ─────────────────────────────────────────────────

    async def handle_tools_list(self, headers: Dict[str, str]) -> Dict[str, Any]:
        """
        GET/POST /api/v1/tools/list

        返回 Dify 兼容格式的工具列表。
        根据租户权限过滤工具列表（仅返回该租户有权使用的工具）。
        """
        authenticated, _, tenant_id = self._auth(headers)
        if not authenticated:
            return _error_response("Unauthorized: invalid or missing X-API-Key", 401)

        all_tools = self.registry.list_tools()
        tenant = self.tenancy.get_tenant(tenant_id)

        # 根据租户权限过滤工具
        dify_tools = []
        for tool in all_tools:
            tool_name = tool.get("name", "")

            # 如果租户有工具白名单，过滤
            if tenant and tenant.allowed_tools:
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

        return _json_response({
            "tools": dify_tools,
            "count": len(dify_tools),
            "tenant_id": tenant_id,
            "platform": self.platform,
        })

    # ── tools/call ─────────────────────────────────────────────────

    async def handle_tools_call(self, body: dict, headers: Dict[str, str]) -> Dict[str, Any]:
        """
        POST /api/v1/tools/call

        请求体：
        {
            "name": "sysinfo",
            "arguments": {}
        }

        返回：
        {
            "success": true,
            "tool_name": "sysinfo",
            "result": "...",
            "duration_ms": 12.5
        }
        """
        authenticated, caller, tenant_id = self._auth(headers)
        if not authenticated:
            return _error_response("Unauthorized: invalid or missing X-API-Key", 401)

        tool_name = body.get("name", "")
        arguments = body.get("arguments", {})

        if not tool_name:
            return _error_response("Missing required field: 'name'")

        # 多租户工具权限检查
        if tenant_id:
            from mcp_gateway.security import AuthResult
            access_result = self.tenancy.check_tool_access(tenant_id, tool_name)
            if access_result == AuthResult.DENY:
                await self.audit.record(
                    tool_name=tool_name,
                    arguments=arguments,
                    platform=self.platform,
                    caller=caller,
                    is_error=True,
                    permission="deny",
                )
                return _error_response(f"Permission denied: tenant '{tenant_id}' not allowed to use '{tool_name}'", 403)

        # 安全检查
        try:
            self.security.check_tool_permission(tool_name)
        except Exception as e:
            await self.audit.record(
                tool_name=tool_name,
                arguments=arguments,
                platform=self.platform,
                caller=caller,
                is_error=True,
                permission="deny",
            )
            return _error_response(f"Permission denied: {e}", 403)

        # 执行工具
        start = time.perf_counter()
        try:
            result = await self.registry.call_tool(tool_name, arguments)
            duration_ms = (time.perf_counter() - start) * 1000

            # 提取文本结果
            text_result = ""
            if result.content:
                for item in result.content:
                    if item.get("type") == "text":
                        text_result += item.get("text", "")

            await self.audit.record(
                tool_name=tool_name,
                arguments=arguments,
                platform=self.platform,
                caller=caller,
                result_summary=text_result,
                is_error=result.is_error,
                duration_ms=duration_ms,
                permission="allow",
                token_count=result.token_count,
            )

            return _json_response({
                "success": not result.is_error,
                "tool_name": tool_name,
                "result": text_result if text_result else str(result.content),
                "duration_ms": round(duration_ms, 2),
                "is_error": result.is_error,
            })

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            await self.audit.record(
                tool_name=tool_name,
                arguments=arguments,
                platform=self.platform,
                caller=caller,
                is_error=True,
                duration_ms=duration_ms,
            )
            return _error_response(f"Tool execution error: {e}", 500)

    # ── health ─────────────────────────────────────────────────────

    async def handle_health(self) -> Dict[str, Any]:
        """GET /api/v1/health"""
        stats = self.registry.get_stats()
        return _json_response({
            "status": "healthy",
            "server": "MCP Agent Gateway",
            "version": "3.0.0",
            "tools": stats.get("tools", 0),
            "providers": stats.get("providers", 0),
        })

    # ── logs ───────────────────────────────────────────────────────

    async def handle_logs(self, query_params: Dict[str, str]) -> Dict[str, Any]:
        """
        GET /api/v1/logs?platform=dify&tool=sysinfo&limit=50

        查询审计日志。
        """
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

        entries = await self.audit.query(
            platform=platform,
            tool_name=tool_name,
            limit=min(limit, 200),
            offset=offset,
            error_only=error_only,
        )
        return _json_response({
            "entries": entries,
            "count": len(entries),
            "filters": {
                "platform": platform,
                "tool": tool_name,
                "error_only": error_only,
            },
        })

    # ── stats ──────────────────────────────────────────────────────

    async def handle_stats(self) -> Dict[str, Any]:
        """GET /api/v1/stats"""
        audit_stats = await self.audit.get_stats()
        registry_stats = self.registry.get_stats()
        return _json_response({
            "audit": audit_stats,
            "registry": registry_stats,
        })

    # ── tenants ────────────────────────────────────────────────────

    async def handle_tenants_list(self) -> Dict[str, Any]:
        """GET /api/v1/tenants — 列出所有租户"""
        return _json_response({
            "tenants": self.tenancy.list_tenants(),
            "count": len(self.tenancy._tenants),
        })


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