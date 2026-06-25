"""
MCP Gateway Server - Production-grade entry point.

Architecture:
    MCPServer
    ├── ToolRegistry (plugin-based, IToolProvider pattern)
    │   ├── FilesystemToolProvider
    │   ├── TerminalToolProvider
    │   └── DatabaseToolProvider
    ├── MCPProtocolHandler (JSON-RPC 2.0)
    ├── SecurityMiddleware (auth + rate limit + policy)
    └── MCPTransport (HTTP/SSE/STDIO)
"""

import asyncio
import argparse
import logging
import sys
import os
import json
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_gateway.protocol import (
    MCPProtocolHandler,
    ToolRegistry,
    SecurityMiddleware,
)
from mcp_gateway.transport import MCPTransport
from mcp_gateway.tools.filesystem import FilesystemToolProvider
from mcp_gateway.tools.terminal import TerminalToolProvider
from mcp_gateway.tools.database import DatabaseToolProvider
from core.types import JSONRPCRequest
from config.loader import ConfigLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("mcp_gateway.server")


class MCPServer:
    """
    Production-grade MCP Gateway Server.

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
            server_name="MCP-Gateway",
            server_version="3.0.0"
        )
        self.registry = ToolRegistry()
        self.security = SecurityMiddleware()
        self.config = self._load_config(config_path)

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

    def setup_handlers(self):
        """Set up MCP protocol handlers linked to registry."""

        # tools/list
        async def handle_list_tools(params: dict) -> dict:
            category = params.get("category")
            tools = self.registry.list_tools(category=category)
            return {"tools": tools}

        # tools/call
        async def handle_call_tool(params: dict) -> dict:
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            # Security check
            self.security.check_tool_permission(tool_name)

            result = await self.registry.call_tool(tool_name, arguments)
            return {
                "content": result.content,
                "isError": result.is_error,
                "executionTimeMs": result.execution_time_ms,
            }

        # resources/list
        async def handle_list_resources(params: dict) -> dict:
            return {"resources": self.registry.list_resources()}

        # prompts/list
        async def handle_list_prompts(params: dict) -> dict:
            return {"prompts": self.registry.list_prompts()}

        # stats
        async def handle_stats(params: dict) -> dict:
            return self.registry.get_stats()

        self.protocol.register_handler("tools/list", handle_list_tools)
        self.protocol.register_handler("tools/call", handle_call_tool)
        self.protocol.register_handler("resources/list", handle_list_resources)
        self.protocol.register_handler("prompts/list", handle_list_prompts)
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

        # Set up protocol handlers
        self.setup_handlers()

        # Configure security
        self.configure_security()

        # Create transport with protocol handler bridge
        async def protocol_handler(method: str, params: dict, session) -> dict:
            """Bridge between transport layer and protocol handler."""
            request = JSONRPCRequest(
                jsonrpc="2.0",
                id="req",
                method=method,
                params=params,
            )
            response = await self.protocol.handle_request(request)
            if response is None:
                return {}
            return {"result": response.result} if response.error is None else {"error": response.error}

        transport = MCPTransport(protocol_handler)

        if mode == "stdio":
            logger.info("Starting MCP Gateway in STDIO mode...")
            await transport.stdio_serve()
        else:
            logger.info(f"Starting MCP Gateway in HTTP mode on {host}:{port}")
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