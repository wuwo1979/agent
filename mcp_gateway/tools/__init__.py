"""MCP 工具注册模块"""
from mcp_gateway.tools.database import DatabaseToolProvider
from mcp_gateway.tools.filesystem import FilesystemToolProvider
from mcp_gateway.tools.llm import LLMToolProvider
from mcp_gateway.tools.terminal import TerminalToolProvider
from mcp_gateway.tools.web import WebToolProvider

__all__ = [
    "DatabaseToolProvider",
    "FilesystemToolProvider",
    "LLMToolProvider",
    "TerminalToolProvider",
    "WebToolProvider",
]
