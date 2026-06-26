"""
MCP Gateway layer unit tests.
Uses MockTestProvider pattern for proper IToolProvider-based testing.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.types import JSONRPCRequest, JSONRPCResponse, ToolCallResult, ToolDefinition
from mcp_gateway.protocol import (
    BaseToolProvider,
    MCPProtocolHandler,
    ToolRegistry,
)

# ============================================================
# Mock Test Provider
# ============================================================

class MockTestProvider(BaseToolProvider):
    """Mock tool provider for unit testing."""

    def __init__(self):
        super().__init__(name="test", description="Test mock provider")
        self._register_tools()

    def _register_tools(self):
        self._register_tool(ToolDefinition(
            name="echo",
            description="Echo back the message",
            inputSchema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
            },
            category="test",
            cacheable=True,
            timeout_ms=5000,
        ))
        self._register_tool(ToolDefinition(
            name="tool_a",
            description="Tool A",
            inputSchema={"type": "object", "properties": {}},
            category="test",
            cacheable=True,
            timeout_ms=5000,
        ))
        self._register_tool(ToolDefinition(
            name="tool_b",
            description="Tool B",
            inputSchema={"type": "object", "properties": {}},
            category="test",
            cacheable=True,
            timeout_ms=5000,
        ))

    async def call_tool(self, tool_name: str, arguments: dict) -> ToolCallResult:
        if tool_name == "echo":
            msg = arguments.get("message", "hello")
            return ToolCallResult.text_result(tool_name, msg, 1.0)
        return ToolCallResult.text_result(tool_name, f"{tool_name}_output", 1.0)


class MockDependencyProvider(BaseToolProvider):
    """Mock provider with tool dependencies."""

    def __init__(self):
        super().__init__(name="deps", description="Dependency test provider")
        self._register_tools()

    def _register_tools(self):
        self._register_tool(ToolDefinition(
            name="independent",
            description="Independent tool",
            inputSchema={"type": "object", "properties": {}},
            category="test",
            dependencies=[],
            timeout_ms=5000,
        ))
        self._register_tool(ToolDefinition(
            name="dependent",
            description="Dependent tool",
            inputSchema={"type": "object", "properties": {}},
            category="test",
            dependencies=["independent"],
            timeout_ms=5000,
        ))

    async def call_tool(self, tool_name: str, arguments: dict) -> ToolCallResult:
        return ToolCallResult.text_result(tool_name, f"{tool_name}_output", 1.0)


# ============================================================
# ToolRegistry Tests
# ============================================================

class TestToolRegistry:
    """Tool registry tests with IToolProvider pattern."""

    def test_register_provider(self):
        """Test registering a provider adds all its tools."""
        registry = ToolRegistry()
        provider = MockTestProvider()

        registry.register_provider(provider)

        echo_tool = registry.get_tool("echo")
        assert echo_tool is not None
        assert echo_tool.name == "echo"
        assert echo_tool.category == "test"

        tool_a = registry.get_tool("tool_a")
        assert tool_a is not None

    def test_list_tools(self):
        """Test listing all tools and filtering by category."""
        registry = ToolRegistry()
        registry.register_provider(MockTestProvider())

        all_tools = registry.list_tools()
        assert len(all_tools) >= 3

        category_tools = registry.list_tools(category="test")
        assert len(category_tools) >= 3
        names = [t["name"] for t in category_tools]
        assert "echo" in names

    def test_unregister_provider(self):
        """Test removing a provider removes all its tools."""
        registry = ToolRegistry()
        provider = MockTestProvider()
        registry.register_provider(provider)

        assert registry.get_tool("echo") is not None

        registry.unregister_provider("test")
        assert registry.get_tool("echo") is None

    @pytest.mark.asyncio
    async def test_call_tool(self):
        """Test executing a registered tool."""
        registry = ToolRegistry()
        registry.register_provider(MockTestProvider())

        result = await registry.call_tool("echo", {"message": "hello_world"})
        assert not result.is_error
        assert "hello_world" in result.content[0]["text"]

    @pytest.mark.asyncio
    async def test_call_nonexistent_tool(self):
        """Test calling a tool that doesn't exist."""
        registry = ToolRegistry()
        from core.exceptions import ToolNotFoundError
        with pytest.raises(ToolNotFoundError):
            await registry.call_tool("nonexistent", {})

    def test_get_dependency_graph(self):
        """Test dependency graph extraction from tools."""
        registry = ToolRegistry()
        registry.register_provider(MockDependencyProvider())

        independent = registry.get_tool("independent")
        dependent = registry.get_tool("dependent")

        assert independent.dependencies == []
        assert dependent.dependencies == ["independent"]

    def test_get_stats(self):
        """Test registry statistics."""
        registry = ToolRegistry()
        registry.register_provider(MockTestProvider())

        stats = registry.get_stats()
        assert stats["providers"] == 1
        assert stats["tools"] >= 3

    def test_register_tool_with_prefix(self):
        """Test registering provider with prefix."""
        registry = ToolRegistry()
        registry.register_provider(MockTestProvider(), prefix="mcp")

        # Tools should be stored with prefix in registry
        prefixed_tool = registry.get_tool("mcp__echo")
        assert prefixed_tool is not None

        # MCP format retains original name
        all_tools = registry.list_tools()
        names = [t["name"] for t in all_tools]
        assert "echo" in names


# ============================================================
# MCP Protocol Tests
# ============================================================

class TestMCPProtocol:
    """MCP protocol handler tests."""

    def test_request_parsing(self):
        """Test JSONRPCRequest creation."""
        request = JSONRPCRequest(
            jsonrpc="2.0",
            id="req-1",
            method="tools/list",
            params={"category": "test"},
        )
        assert request.jsonrpc == "2.0"
        assert request.method == "tools/list"
        assert request.params["category"] == "test"

    def test_response_format(self):
        """Test JSONRPCResponse format."""
        response = JSONRPCResponse(
            jsonrpc="2.0",
            id="123",
            result={"tools": []},
        )
        assert response.jsonrpc == "2.0"
        assert response.id == "123"
        assert response.result == {"tools": []}
        assert response.error is None

    @pytest.mark.asyncio
    async def test_protocol_handler(self):
        """Test protocol handler with registered method."""
        handler = MCPProtocolHandler(
            server_name="test-server",
            server_version="1.0.0"
        )

        async def handle_test(params):
            return {"echo": params.get("msg", "")}

        handler.register_handler("test", handle_test)

        request = JSONRPCRequest(
            jsonrpc="2.0",
            id="1",
            method="test",
            params={"msg": "hello"},
        )
        response = await handler.handle_request(request)
        assert response is not None
        assert response.result["echo"] == "hello"

    @pytest.mark.asyncio
    async def test_method_not_found(self):
        """Test unknown method returns error."""
        handler = MCPProtocolHandler(
            server_name="test-server",
            server_version="1.0.0"
        )

        request = JSONRPCRequest(
            jsonrpc="2.0",
            id="2",
            method="unknown_method",
            params={},
        )
        response = await handler.handle_request(request)
        assert response is not None
        assert response.error is not None
        assert response.error["code"] == -32601

    @pytest.mark.asyncio
    async def test_notification(self):
        """Test notification handling (no id)."""
        handler = MCPProtocolHandler(
            server_name="test-server",
            server_version="1.0.0"
        )

        # Register a notification handler
        received = []

        async def handle_init(params):
            received.append(params)

        handler.register_notification("notifications/initialized", handle_init)

        request = JSONRPCRequest(
            jsonrpc="2.0",
            id=None,
            method="notifications/initialized",
            params={"client": "test"},
        )
        response = await handler.handle_request(request)
        assert response is None  # Notifications return None
        assert len(received) == 1


# ============================================================
# LLM Tool Provider Tests
# ============================================================

class TestLLMToolProvider:

    def test_llm_provider_registration(self):
        """Test LLMToolProvider registers and lists tools."""
        from mcp_gateway.tools.llm import LLMToolProvider

        provider = LLMToolProvider()
        tools = provider.list_tools()

        assert len(tools) == 2
        tool_names = {t.name for t in tools}
        assert "llm_call" in tool_names
        assert "llm_list_models" in tool_names

    def test_llm_provider_in_registry(self):
        """Test LLMToolProvider works in ToolRegistry."""
        from mcp_gateway.tools.llm import LLMToolProvider

        registry = ToolRegistry()
        provider = LLMToolProvider()
        registry.register_provider(provider)

        stats = registry.get_stats()
        assert stats["tools"] == 2

    def test_llm_call_tool_schema(self):
        """Test llm_call tool has required parameters."""
        from mcp_gateway.tools.llm import LLMToolProvider

        provider = LLMToolProvider()
        tools = provider.list_tools()
        llm_call = next(t for t in tools if t.name == "llm_call")

        assert "model" in llm_call.inputSchema["required"]
        assert "prompt" in llm_call.inputSchema["required"]
        assert llm_call.category == "llm"
        assert llm_call.timeout_ms == 60000

    def test_llm_list_models_tool_schema(self):
        """Test llm_list_models tool is cacheable."""
        from mcp_gateway.tools.llm import LLMToolProvider

        provider = LLMToolProvider()
        tools = provider.list_tools()
        llm_list = next(t for t in tools if t.name == "llm_list_models")

        assert llm_list.cacheable is True
        assert llm_list.category == "llm"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
