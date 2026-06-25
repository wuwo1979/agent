"""
Core interfaces - Abstract base classes defining the system contract.

Design principles:
1. Interface Segregation - Small, focused interfaces
2. Dependency Inversion - High-level modules depend on abstractions
3. Plugin Architecture - Components implement interfaces for extensibility
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional
from core.types import (
    ToolDefinition, ToolCallResult, AgentState, SearchResult,
    Document, CacheEntry,
)


# ============================================================
# Lifecycle Interface
# ============================================================

class ILifecycle(ABC):
    """Component lifecycle management."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the component. Called once at startup."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully shutdown the component. Called once at shutdown."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the component is healthy."""
        ...


# ============================================================
# Tool Provider Interface
# ============================================================

class IToolProvider(ABC):
    """
    Tool provider interface - plugin architecture for MCP tools.

    Each provider manages a group of related tools (e.g., filesystem, terminal, database).
    Implement this interface to add new tool categories.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this provider offers."""
        ...

    @abstractmethod
    def list_tools(self) -> List[ToolDefinition]:
        """Return all tools provided by this provider."""
        ...

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolCallResult:
        """
        Execute a tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments as key-value pairs

        Returns:
            ToolCallResult with execution output and metadata

        Raises:
            ToolNotFoundError: If tool_name is not found
            ToolExecutionError: If tool execution fails
        """
        ...

    def get_server_instructions(self) -> str:
        """Return instructions for LLM on how to use tools from this provider."""
        tools_desc = "\n".join(
            f"  - {t.name}: {t.description}" for t in self.list_tools()
        )
        return f"## {self.name}\n{self.description}\n\nTools:\n{tools_desc}"


# ============================================================
# Tool Registry Interface
# ============================================================

class IToolRegistry(ABC):
    """
    Central tool registry - manages all tool providers.

    Responsible for:
    - Tool registration and discovery
    - Tool name resolution (with prefix support)
    - Tool invocation routing
    - Tool metadata management
    """

    @abstractmethod
    def register_provider(self, provider: IToolProvider, prefix: str = "") -> None:
        """Register a tool provider with optional name prefix."""
        ...

    @abstractmethod
    def unregister_provider(self, provider_name: str) -> None:
        """Remove a tool provider."""
        ...

    @abstractmethod
    def list_tools(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all registered tools in MCP-compatible format.

        Args:
            category: Optional filter by tool category

        Returns:
            List of tool definitions in MCP format
        """
        ...

    @abstractmethod
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get a specific tool definition by name."""
        ...

    @abstractmethod
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolCallResult:
        """
        Execute a registered tool.

        Args:
            name: Full tool name (including prefix if applicable)
            arguments: Tool arguments

        Returns:
            ToolCallResult with execution output
        """
        ...

    @abstractmethod
    def get_all_providers(self) -> Dict[str, IToolProvider]:
        """Get all registered providers."""
        ...


# ============================================================
# Model Adapter Interface
# ============================================================

class IModelAdapter(ABC):
    """
    Unified model adapter interface.

    Supports multiple backends:
    - Cloud: DeepSeek, OpenAI, Anthropic
    - Local: Ollama, vLLM
    """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Unique model identifier."""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional tool definitions for function calling
            stream: Whether to stream the response
            **kwargs: Model-specific parameters

        Returns:
            Response dict with 'content', 'tool_calls', 'usage', etc.
        """
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream chat completion response.

        Yields:
            Response chunks with 'delta', 'tool_call_delta', etc.
        """
        ...

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Returns:
            List of embedding vectors
        """
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for a given text.

        Returns:
            Estimated token count
        """
        ...


# ============================================================
# Vector Store Interface
# ============================================================

class IVectorStore(ABC):
    """
    Vector store interface for RAG knowledge base.

    Supports ChromaDB and Milvus backends.
    """

    @abstractmethod
    async def add_documents(self, documents: List[Document]) -> int:
        """
        Add documents to the vector store.

        Returns:
            Number of documents added
        """
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> List[SearchResult]:
        """
        Semantic search for relevant documents.

        Args:
            query: Search query text
            top_k: Number of results to return
            score_threshold: Minimum relevance score

        Returns:
            List of search results ranked by relevance
        """
        ...

    @abstractmethod
    async def delete(self, ids: List[str]) -> int:
        """
        Delete documents by ID.

        Returns:
            Number of documents deleted
        """
        ...

    @abstractmethod
    async def count(self) -> int:
        """Return total number of documents."""
        ...


# ============================================================
# Checkpoint Store Interface
# ============================================================

class ICheckpointStore(ABC):
    """
    Checkpoint store for agent state persistence.

    Supports:
    - SQLite (local development)
    - PostgreSQL (production)
    """

    @abstractmethod
    async def save(self, thread_id: str, state: AgentState) -> None:
        """Save agent state checkpoint."""
        ...

    @abstractmethod
    async def load(self, thread_id: str) -> Optional[AgentState]:
        """
        Load agent state checkpoint.

        Returns:
            AgentState or None if not found
        """
        ...

    @abstractmethod
    async def list_threads(self) -> List[str]:
        """List all saved thread IDs."""
        ...

    @abstractmethod
    async def delete(self, thread_id: str) -> bool:
        """
        Delete a checkpoint.

        Returns:
            True if deleted, False if not found
        """
        ...

    @abstractmethod
    async def cleanup(self, max_age_seconds: float = 86400) -> int:
        """
        Clean up old checkpoints.

        Returns:
            Number of checkpoints removed
        """
        ...


# ============================================================
# Context Cache Interface
# ============================================================

class IContextCache(ABC):
    """
    Context cache for reducing token consumption.

    Strategies:
    - Content hash deduplication
    - Incremental compression
    - LRU eviction
    """

    @abstractmethod
    async def get(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[CacheEntry]:
        """
        Get cached result for a tool call.

        Returns:
            CacheEntry or None if cache miss
        """
        ...

    @abstractmethod
    async def set(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        content: str,
        token_count: int = 0,
    ) -> CacheEntry:
        """
        Cache a tool call result.

        Returns:
            CacheEntry with compression info
        """
        ...

    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        ...

    @abstractmethod
    async def clear(self) -> None:
        """Clear all cached entries."""
        ...
