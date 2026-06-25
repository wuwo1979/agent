"""MCP 工具注册模块"""
from mcp_gateway.tools.filesystem import FilesystemToolProvider
from mcp_gateway.tools.terminal import TerminalToolProvider
from mcp_gateway.tools.database import DatabaseToolProvider

__all__ = [
    "FilesystemToolProvider",
    "TerminalToolProvider",
    "DatabaseToolProvider",
]