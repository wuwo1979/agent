"""
Core module - Foundation interfaces and base classes for the MCP Gateway + Multi-Agent system.

Layered Architecture:
    core/           - Interfaces, base classes, exceptions (zero dependencies)
    mcp_gateway/    - MCP protocol implementation (depends on core)
    mcp_gateway/agents/ - Agent orchestration (depends on core, mcp_gateway)
    performance/    - Performance optimization (depends on core)
    rag/            - RAG knowledge base (depends on core)
    tools/          - Concrete tool implementations (depends on core)
"""

from core.exceptions import (
    AgentError,
    AuthenticationError,
    ConfigurationError,
    MCPSystemError,
    RateLimitError,
    ToolExecutionError,
    ToolNotFoundError,
)
from core.interfaces import (
    ICheckpointStore,
    IContextCache,
    ILifecycle,
    IModelAdapter,
    IToolProvider,
    IToolRegistry,
    IVectorStore,
)
from core.types import (
    AgentRole,
    AgentState,
    BenchmarkResult,
    CacheEntry,
    Document,
    JSONRPCRequest,
    JSONRPCResponse,
    MetricSnapshot,
    ModelConfig,
    SearchResult,
    SubTask,
    TaskStatus,
    ToolCallResult,
    ToolDefinition,
)

__all__ = [
    # Interfaces
    "IToolProvider",
    "IToolRegistry",
    "IModelAdapter",
    "IVectorStore",
    "ICheckpointStore",
    "IContextCache",
    "ILifecycle",
    # Exceptions
    "MCPSystemError",
    "ToolNotFoundError",
    "ToolExecutionError",
    "AgentError",
    "ConfigurationError",
    "RateLimitError",
    "AuthenticationError",
    # Types
    "ToolDefinition",
    "ToolCallResult",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "AgentState",
    "SubTask",
    "TaskStatus",
    "AgentRole",
    "ModelConfig",
    "CacheEntry",
    "SearchResult",
    "Document",
    "BenchmarkResult",
    "MetricSnapshot",
]
