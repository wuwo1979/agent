"""
MCP Gateway - Protocol Handler (v3.0)
Complete MCP protocol implementation with JSON-RPC 2.0, Streamable HTTP, and plugin architecture.

References:
- MCP Specification 2024-11-05: https://spec.modelcontextprotocol.io/
- JSON-RPC 2.0: https://www.jsonrpc.org/specification
- Envoy AI Gateway MCP: https://aigateway.envoyproxy.io/docs/capabilities/mcp/
- Docker MCP Gateway Paper: https://raw.githubusercontent.com/wiki/TerrenceMcGuinness-NOAA/global-workflow/Docker_MCP_Gateway_Paper.pdf
"""

from __future__ import annotations
import asyncio
import json
import logging
import time
import traceback
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass, field

from core.interfaces import IToolProvider, IToolRegistry
from core.types import (
    ToolDefinition, ToolCallResult, ResourceDefinition, PromptDefinition,
    JSONRPCRequest, JSONRPCResponse,
)
from core.exceptions import (
    ToolNotFoundError, ToolExecutionError, ToolTimeoutError,
    InvalidRequestError, MethodNotFoundError, ProtocolError,
    PermissionDeniedError,
)

logger = logging.getLogger("mcp_gateway.protocol")


# ============================================================
# JSON-RPC 2.0 Error Codes
# ============================================================

class JSONRPCErrorCode:
    """JSON-RPC 2.0 standard error codes + MCP extensions."""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # MCP server errors (-32000 to -32099)
    SERVER_NOT_INITIALIZED = -32002
    UNKNOWN_ERROR = -32001

    # Custom MCP errors
    TOOL_NOT_FOUND = -32001
    TOOL_EXECUTION_ERROR = -32002
    TOOL_TIMEOUT = -32003
    RESOURCE_NOT_FOUND = -32004
    PERMISSION_DENIED = -32005
    RATE_LIMITED = -32006
    AUTH_REQUIRED = -32007


# ============================================================
# MCP Protocol Handler
# ============================================================

class MCPProtocolHandler:
    """
    Complete MCP protocol handler.

    Handles all MCP method requests:
    - Lifecycle: initialize, initialized, ping
    - Tools: tools/list, tools/call
    - Resources: resources/list, resources/read, resources/templates/list
    - Prompts: prompts/list, prompts/get
    - Notifications: notifications/initialized, notifications/cancelled
    """

    def __init__(self, server_name: str = "MCP-Gateway", server_version: str = "3.0.0"):
        self.server_name = server_name
        self.server_version = server_version
        self._handlers: Dict[str, Callable] = {}
        self._notification_handlers: Dict[str, Callable] = {}
        self._initialized = False
        self._client_capabilities: Dict[str, Any] = {}

        # Register core handlers
        self._register_core_handlers()

    def _register_core_handlers(self):
        """Register core MCP protocol handlers."""
        self.register_handler("initialize", self._handle_initialize)
        self.register_handler("ping", self._handle_ping)
        self.register_notification("notifications/initialized", self._handle_initialized)

    def register_handler(self, method: str, handler: Callable):
        """Register a method handler."""
        self._handlers[method] = handler

    def register_notification(self, method: str, handler: Callable):
        """Register a notification handler."""
        self._notification_handlers[method] = handler

    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request."""
        self._client_capabilities = params.get("capabilities", {})
        protocol_version = params.get("protocolVersion", "2024-11-05")

        return {
            "protocolVersion": protocol_version,
            "serverInfo": {
                "name": self.server_name,
                "version": self.server_version,
            },
            "capabilities": {
                "tools": {
                    "listChanged": True,
                },
                "resources": {
                    "subscribe": False,
                    "listChanged": True,
                },
                "prompts": {
                    "listChanged": True,
                },
                "logging": {},
            },
            "instructions": (
                f"Welcome to {self.server_name} v{self.server_version}. "
                f"Use tools/list to discover available tools, "
                f"tools/call to execute them."
            ),
        }

    async def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ping request."""
        return {}

    async def _handle_initialized(self, params: Dict[str, Any]):
        """Handle initialized notification."""
        self._initialized = True
        logger.info("Client initialized successfully")

    async def handle_request(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """
        Handle a JSON-RPC request.

        Returns:
            JSONRPCResponse for regular requests, None for notifications
        """
        try:
            if request.method in self._notification_handlers:
                # Handle notification (no response)
                await self._notification_handlers[request.method](request.params)
                return None

            if request.method in self._handlers:
                result = await self._handlers[request.method](request.params)
                return JSONRPCResponse.success(request.id, result)

            raise MethodNotFoundError(request.method)

        except MethodNotFoundError as e:
            return JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.METHOD_NOT_FOUND, str(e)
            )
        except InvalidRequestError as e:
            return JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.INVALID_REQUEST, str(e)
            )
        except ToolNotFoundError as e:
            return JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.TOOL_NOT_FOUND, str(e), e.to_dict()
            )
        except ToolExecutionError as e:
            return JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.TOOL_EXECUTION_ERROR, str(e), e.to_dict()
            )
        except PermissionDeniedError as e:
            return JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.PERMISSION_DENIED, str(e), e.to_dict()
            )
        except Exception as e:
            logger.error(f"Unhandled error in {request.method}: {traceback.format_exc()}")
            return JSONRPCResponse.error_response(
                request.id, JSONRPCErrorCode.INTERNAL_ERROR,
                f"Internal error: {str(e)}"
            )

    def parse_request(self, raw: Union[str, bytes]) -> JSONRPCRequest:
        """Parse a raw JSON-RPC request string."""
        try:
            data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
            return JSONRPCRequest.from_dict(data)
        except json.JSONDecodeError as e:
            raise InvalidRequestError(f"Invalid JSON: {e}")
        except Exception as e:
            raise InvalidRequestError(f"Invalid request format: {e}")


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


# ============================================================
# Security Middleware
# ============================================================

class SecurityMiddleware:
    """
    Security middleware for MCP requests.

    Provides:
    - API Key authentication
    - Rate limiting (token bucket)
    - Tool-level permission policies
    """

    def __init__(self):
        self._auth_enabled = False
        self._rate_limit_enabled = False
        self._policy_enabled = False
        self._valid_keys: Set[str] = set()
        self._rate_limits: Dict[str, Tuple[float, int]] = {}  # client_id -> (tokens, last_refill)
        self._max_rpm: int = 60
        self._burst_size: int = 10
        self._dangerous_tools: Set[str] = set()
        self._readonly_tools: Set[str] = set()

    def configure(self, config: Dict[str, Any]):
        """Configure security from config dict."""
        auth = config.get("auth", {})
        if auth.get("enabled"):
            self._auth_enabled = True
            self._valid_keys = set(auth.get("api_keys", []))

        rate_limit = config.get("rate_limit", {})
        if rate_limit.get("enabled"):
            self._rate_limit_enabled = True
            self._max_rpm = rate_limit.get("max_requests_per_minute", 60)
            self._burst_size = rate_limit.get("burst_size", 10)

        policy = config.get("tool_policy", {})
        if policy.get("enabled"):
            self._policy_enabled = True
            self._dangerous_tools = set(policy.get("dangerous_tools", []))
            self._readonly_tools = set(policy.get("readonly_tools", []))

    def authenticate(self, headers: Dict[str, str]) -> bool:
        """Verify API key authentication."""
        if not self._auth_enabled:
            return True
        api_key = headers.get("X-API-Key", headers.get("Authorization", ""))
        if api_key.startswith("Bearer "):
            api_key = api_key[7:]
        return api_key in self._valid_keys

    def check_rate_limit(self, client_id: str) -> Tuple[bool, float]:
        """
        Check rate limit using token bucket algorithm.

        Returns:
            (allowed, retry_after_seconds)
        """
        if not self._rate_limit_enabled:
            return True, 0

        now = time.time()
        tokens, last_refill = self._rate_limits.get(client_id, (self._burst_size, now))

        # Refill tokens
        elapsed = now - last_refill
        refill = elapsed * (self._max_rpm / 60.0)
        tokens = min(self._burst_size, tokens + refill)

        if tokens < 1:
            wait_time = (1 - tokens) / (self._max_rpm / 60.0)
            return False, wait_time

        tokens -= 1
        self._rate_limits[client_id] = (tokens, now)
        return True, 0

    def check_tool_permission(self, tool_name: str, is_readonly: bool = False) -> bool:
        """
        Check if tool execution is allowed by policy.

        Returns:
            True if allowed
        Raises:
            PermissionDeniedError if blocked
        """
        if not self._policy_enabled:
            return True

        # Check if tool is in dangerous list
        if tool_name in self._dangerous_tools:
            raise PermissionDeniedError(
                tool_name,
                "This tool is classified as dangerous and requires explicit approval"
            )

        return True