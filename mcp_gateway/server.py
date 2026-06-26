"""
MCP 本地工具网关 - 服务入口
提供 HTTP + STDIO 双模传输，支持 Dify / Trae / Ollama 全链路工具调度。

Architecture:
    MCPServer
        +-- ToolRegistry (plugin-based, IToolProvider pattern)
        |   +-- FilesystemToolProvider  (5 tools)
        |   +-- TerminalToolProvider    (2 tools)
        |   +-- DatabaseToolProvider    (4 tools)
        |   +-- WebToolProvider         (3 tools)
        |   +-- LLMToolProvider         (2 tools)
        +-- ExternalAPIHandler (REST API for Dify/Trae/Ollama)
        +-- MCPProtocolHandler (JSON-RPC 2.0)
        +-- SecurityMiddleware (auth + rate limit + policy)
        +-- AuditLogger (unified call logging)
        +-- MCPTransport (HTTP/SSE/STDIO)
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.loader import ConfigLoader
from core.types import JSONRPCRequest
from mcp_gateway.api import ExternalAPIHandler, create_api_routes
from mcp_gateway.audit import AuditLogger
from mcp_gateway.protocol import (
    MCPProtocolHandler,
    ToolRegistry,
    create_audit_middleware,
    create_auth_middleware,
)
from mcp_gateway.security import SecurityMiddleware
from mcp_gateway.tools.database import DatabaseToolProvider
from mcp_gateway.tools.filesystem import FilesystemToolProvider
from mcp_gateway.tools.llm import LLMToolProvider
from mcp_gateway.tools.terminal import TerminalToolProvider
from mcp_gateway.tools.web import WebToolProvider
from mcp_gateway.transport import MCPTransport
from mcp_gateway.workspace import (
    BUILTIN_PROMPTS,
    get_prompt_content,
    get_workspace,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("mcp_gateway.server")


class MCPServer:
    """
    MCP 本地工具网关服务端

    - HTTP 传输：对接 Dify Agent / Ollama 代理 / 自定义 REST 客户端
    - STDIO 传输：对接 Trae IDE / Claude Desktop 等本地 MCP 客户端
    - 统一工具注册、安全校验、缓存、并行调度

    Features:
    - Plugin-based tool provider architecture
    - JSON-RPC 2.0 protocol compliance
    - Streamable HTTP transport (MCP 2025 spec)
    - Security middleware (auth, rate limit, tool policy)
    - Dynamic tool registration
    - Observability (stats endpoint)
    """

    def __init__(self, config_path: Optional[str] = None):
        self.protocol = MCPProtocolHandler(
            server_name="mcp-tool-gateway",
            server_version="2.0.0"
        )
        self.registry = ToolRegistry()
        self.security = SecurityMiddleware()
        self.config = self._load_config(config_path)
        self.api_handler: Optional[ExternalAPIHandler] = None
        self.workspace = None

    def _load_config(self, config_path: Optional[str] = None):
        """Load configuration from YAML file."""
        try:
            loader = ConfigLoader(config_path)
            config = loader.load()
            # Convert AppConfig to dict for easier access
            if hasattr(config, '__dataclass_fields__'):
                return {
                    "mcp": getattr(config, "mcp", None),
                    "security": getattr(config, "security", None),
                    "agent": getattr(config, "agent", None),
                    "performance": getattr(config, "performance", None),
                }
            return config
        except Exception as e:
            logger.warning(f"Config load failed, using defaults: {e}")
            return {}

    def register_providers(self):
        """Register all built-in tool providers."""
        providers = [
            FilesystemToolProvider(),
            TerminalToolProvider(),
            DatabaseToolProvider(),
            WebToolProvider(),
            LLMToolProvider(),
        ]

        for provider in providers:
            prefix = ""
            mcp_config = self.config.get("mcp", {}) if self.config else {}
            mappings = getattr(mcp_config, "tool_prefix", {}) if hasattr(mcp_config, 'tool_prefix') else {}
            if isinstance(mappings, dict):
                prefix = mappings.get(provider.name, "")
            self.registry.register_provider(provider, prefix)

        logger.info(
            f"Registered {len(providers)} tool providers "
            f"({self.registry.get_stats()['tools']} tools total)"
        )

    def register_custom_provider(self, provider, prefix: str = ""):
        """Dynamically register a custom tool provider."""
        self.registry.register_provider(provider, prefix)
        logger.info(f"Registered custom provider: {provider.name}")

    def _register_resource_prompt_handlers(self):
        """
        注册 workspace 资源 + 提示词模板处理器到协议内核。

        这些处理器覆盖并扩展 protocol.py 中默认的 registry-based 实现，
        提供真正的文件扫描和提示词模板能力。
        """
        workspace = get_workspace()

        # resources/list - scan workspace files
        async def handle_list_resources(params: dict) -> dict:
            return {"resources": workspace.scan_resources()}

        # resources/read - read actual file contents
        async def handle_read_resource(params: dict) -> dict:
            uri = params.get("uri", "")
            try:
                contents = workspace.read_resource(uri)
                return {"contents": [contents]}
            except FileNotFoundError:
                from core.exceptions import ResourceNotFoundError
                raise ResourceNotFoundError(uri)

        # resources/templates/list
        async def handle_resource_templates_list(params: dict) -> dict:
            return {
                "resourceTemplates": [
                    {
                        "uriTemplate": "file://{path}",
                        "name": "Any file in workspace",
                        "description": "Read any file within the workspace directory",
                        "mimeType": "text/plain",
                    }
                ]
            }

        # prompts/list
        async def handle_list_prompts(params: dict) -> dict:
            return {"prompts": BUILTIN_PROMPTS}

        # prompts/get - return template with arguments
        async def handle_get_prompt(params: dict) -> dict:
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            return get_prompt_content(name, arguments)

        # stats (运维接口，非 MCP 标准方法)
        async def handle_stats(params: dict) -> dict:
            return self.registry.get_stats()

        # 只注册 resources/prompts/stats 处理器
        # tools/* 由 protocol.py 的 _register_tool_handlers 自动注册
        self.protocol.register_handler("resources/list", handle_list_resources)
        self.protocol.register_handler("resources/read", handle_read_resource)
        self.protocol.register_handler("resources/templates/list", handle_resource_templates_list)
        self.protocol.register_handler("prompts/list", handle_list_prompts)
        self.protocol.register_handler("prompts/get", handle_get_prompt)
        self.protocol.register_handler("stats", handle_stats)

    def configure_security(self):
        """Configure security middleware from config."""
        if self.config:
            self.security.configure(self.config.get("security", {}))

    async def start(
        self,
        host: str = "0.0.0.0",
        port: int = 9090,
        mode: str = "http",
    ):
        """Start the MCP gateway server."""
        # Register providers first
        self.register_providers()

        # Setup default tenants (admin, dify, ollama)
        from mcp_gateway.tenancy import get_tenancy
        get_tenancy().setup_default_tenants()
        logger.info("Default tenants configured")

        # Wire registry into protocol kernel (激活协议内置工具处理器)
        self.protocol.set_registry(self.registry)

        # Register workspace-based resource/prompt handlers (覆盖协议默认实现)
        self._register_resource_prompt_handlers()

        # Configure security
        self.configure_security()

        # 注册中间件管道 — 审计日志、速率限制等横切能力
        audit_logger = AuditLogger()
        self.protocol.middleware.use(create_audit_middleware(audit_logger), position="after")
        if self.security.authenticator or self.security.rate_limiter:
            self.protocol.middleware.use(create_auth_middleware(self.security), position="before")

        # Create external API handler — 纯适配器，不持工具执行逻辑
        self.api_handler = ExternalAPIHandler(
            protocol_handler=self.protocol,
            platform="api",
        )
        api_routes = create_api_routes(self.api_handler)

        # Create transport bridge — 统一通过协议内核 handle_request 入口
        async def protocol_handler(method: str, params: dict, session) -> dict:
            """桥接层：传输层 → 协议内核 handle_request()（唯一执行入口）。"""
            request = JSONRPCRequest(
                jsonrpc="2.0",
                id="req",
                method=method,
                params=params,
            )
            response = await self.protocol.handle_request(request)
            if response is None:
                return {}
            if response.error is not None:
                return {"error": response.error}
            return response.result

        transport = MCPTransport(protocol_handler, api_routes=api_routes)

        if mode == "stdio":
            logger.info("=" * 50)
            logger.info("MCP Gateway v2.0 - STDIO mode")
            logger.info(f"  Tools:     {self.registry.get_stats()['tools']} registered")
            logger.info(f"  Prompts:   {len(BUILTIN_PROMPTS)} built-in")
            logger.info(f"  Workspace: {get_workspace().workspace_dir}")
            logger.info("=" * 50)
            await transport.stdio_serve()
        else:
            logger.info("=" * 50)
            logger.info(f"MCP Gateway v2.0 - HTTP mode on {host}:{port}")
            logger.info(f"  MCP endpoint:    http://{host}:{port}/mcp")
            logger.info(f"  REST API:        http://{host}:{port}/api/v1/")
            logger.info(f"  Health:          http://{host}:{port}/api/v1/health")
            logger.info(f"  Audit Logs:      http://{host}:{port}/api/v1/logs")
            logger.info(f"  Tenants:         http://{host}:{port}/api/v1/tenants")
            logger.info(f"  Tools:           {self.registry.get_stats()['tools']} registered")
            logger.info(f"  Prompts:         {len(BUILTIN_PROMPTS)} built-in")
            logger.info(f"  Workspace:       {get_workspace().workspace_dir}")
            logger.info("=" * 50)
            await transport.http_serve(host, port)


def main():
    parser = argparse.ArgumentParser(
        description="MCP Gateway Server - Production-grade MCP implementation"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=9090, help="Bind port")
    parser.add_argument(
        "--mode", choices=["http", "stdio"], default="http",
        help="Transport mode"
    )
    parser.add_argument("--config", default=None, help="Path to config YAML")
    args = parser.parse_args()

    server = MCPServer(config_path=args.config)
    asyncio.run(server.start(host=args.host, port=args.port, mode=args.mode))


if __name__ == "__main__":
    main()
