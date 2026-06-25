"""MCP Gateway 主模块"""
from mcp_gateway.protocol import (
    MCPProtocolHandler,
    ToolRegistry,
    BaseToolProvider,
    SecurityMiddleware,
)
from mcp_gateway.transport import (
    MCPTransport,
    StreamableHTTPTransport,
    SSETransport,
    STDIOTransport,
    SessionManager,
    TransportType,
)
from core.types import (
    ToolDefinition,
    ToolCallResult,
    JSONRPCRequest,
    JSONRPCResponse,
    ResourceDefinition,
    PromptDefinition,
)

__all__ = [
    # Protocol
    "MCPProtocolHandler",
    "ToolRegistry",
    "BaseToolProvider",
    "SecurityMiddleware",
    # Transport
    "MCPTransport",
    "StreamableHTTPTransport",
    "SSETransport",
    "STDIOTransport",
    "SessionManager",
    "TransportType",
    # Types
    "ToolDefinition",
    "ToolCallResult",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "ResourceDefinition",
    "PromptDefinition",
]