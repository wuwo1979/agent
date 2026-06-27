"""
Core types - Shared data structures across the system.

All data classes are designed for:
- Serialization (JSON, pickle)
- Type safety (dataclass with type hints)
- Immutability where appropriate (frozen dataclasses)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ============================================================
# JSON-RPC 2.0 Types
# ============================================================

@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 request."""
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: str = ""
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JSONRPCRequest":
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method", ""),
            params=data.get("params", {}),
        )

    def is_notification(self) -> bool:
        """Check if this is a notification (no id field)."""
        return self.id is None


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 response."""
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    result: Any = None
    error: Optional[Dict[str, Any]] = None

    @classmethod
    def success(cls, req_id: str, result: Any) -> "JSONRPCResponse":
        return cls(jsonrpc="2.0", id=req_id, result=result)

    @classmethod
    def error_response(cls, req_id: Optional[str], code: int, message: str,
              data: Any = None) -> "JSONRPCResponse":
        err = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return cls(jsonrpc="2.0", id=req_id, error=err)

    def to_dict(self) -> Dict[str, Any]:
        d = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            d["id"] = self.id
        if self.error is not None:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d


# ============================================================
# MCP Protocol Types
# ============================================================

@dataclass
class ToolDefinition:
    """
    MCP tool definition (conforms to MCP specification).

    Each tool must have:
    - name: Unique identifier (snake_case recommended)
    - description: Human-readable description for LLM understanding
    - inputSchema: JSON Schema for input parameters
    """
    name: str
    description: str
    inputSchema: Dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
        "required": [],
    })
    category: str = "general"
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    cacheable: bool = True
    timeout_ms: int = 30000
    examples: List[Dict[str, Any]] = field(default_factory=list)

    def to_mcp_format(self) -> Dict[str, Any]:
        """Convert to MCP standard format (for tools/list response)."""
        schema = dict(self.inputSchema)
        # JSON Schema 标准化: 拒绝未定义参数, 确保适当约束
        schema.setdefault("additionalProperties", False)
        # 为 string 类型必填字段添加 minLength 约束
        if "required" in schema and "properties" in schema:
            for prop_name in schema["required"]:
                prop = schema["properties"].get(prop_name, {})
                if prop.get("type") == "string" and "minLength" not in prop:
                    # 仅在 description 为空字符串时也约束，避免 ' 等空值
                    prop["minLength"] = 1
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": schema,
        }

    def to_full_format(self) -> Dict[str, Any]:
        """Convert to full format with all metadata."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema,
            "category": self.category,
            "version": self.version,
            "tags": self.tags,
            "dependencies": self.dependencies,
        }


@dataclass
class ToolCallResult:
    """Result of a tool execution."""
    tool_name: str
    content: List[Dict[str, Any]]
    is_error: bool = False
    execution_time_ms: float = 0.0
    token_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def text_result(cls, tool_name: str, text: str,
                    execution_time_ms: float = 0.0) -> "ToolCallResult":
        """Create a simple text result."""
        return cls(
            tool_name=tool_name,
            content=[{"type": "text", "text": text}],
            execution_time_ms=execution_time_ms,
            token_count=len(text) // 4,
        )

    @classmethod
    def error_result(cls, tool_name: str, error: str,
                     execution_time_ms: float = 0.0) -> "ToolCallResult":
        """Create an error result."""
        return cls(
            tool_name=tool_name,
            content=[{"type": "text", "text": error}],
            is_error=True,
            execution_time_ms=execution_time_ms,
        )

    def to_mcp_format(self) -> Dict[str, Any]:
        """Convert to MCP tools/call response format."""
        return {
            "content": self.content,
            "isError": self.is_error,
        }


@dataclass
class ResourceDefinition:
    """MCP resource definition."""
    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"


@dataclass
class PromptDefinition:
    """MCP prompt template definition."""
    name: str
    description: str = ""
    arguments: List[Dict[str, Any]] = field(default_factory=list)


# ============================================================
# Agent State Types
# ============================================================

class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRole(str, Enum):
    """Agent role in the multi-agent system."""
    SUPERVISOR = "supervisor"    # Central coordinator
    PLANNER = "planner"          # Task decomposition
    EXECUTOR = "executor"        # Tool execution
    VALIDATOR = "validator"      # Result validation
    RESEARCHER = "researcher"    # Information retrieval
    CODER = "coder"              # Code generation


@dataclass
class SubTask:
    """A single sub-task in the execution plan."""
    id: str = field(default_factory=lambda: f"st_{uuid.uuid4().hex[:8]}")
    description: str = ""
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    execution_time_ms: float = 0.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "result": str(self.result)[:1000] if self.result else None,
            "error": self.error,
            "retry_count": self.retry_count,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class AgentState:
    """
    Global agent state - shared across all agents in the workflow.

    Designed for:
    - LangGraph state management
    - Serialization for checkpoint persistence
    - Streaming to clients
    """
    # Task identity
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    user_input: str = ""
    task_status: TaskStatus = TaskStatus.PENDING

    # Plan
    plan: List[SubTask] = field(default_factory=list)
    current_step: int = 0

    # Messages (for LangGraph message accumulation)
    messages: List[Dict[str, Any]] = field(default_factory=list)

    # Execution context
    tool_results: Dict[str, Any] = field(default_factory=dict)
    context_cache: Dict[str, Any] = field(default_factory=dict)

    # Validation
    validation_result: Optional[Dict[str, Any]] = None
    final_output: Optional[str] = None

    # Performance metrics
    start_time: float = 0.0
    end_time: float = 0.0
    total_tokens: int = 0
    successful_tool_calls: int = 0
    failed_tool_calls: int = 0

    # Error handling
    errors: List[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3

    # Snapshot version
    snapshot_version: int = 0

    # Next agent to execute (for Supervisor routing)
    next_agent: Optional[str] = None

    # RAG context
    rag_context: Optional[str] = None

    def add_message(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })

    def add_error(self, error: str):
        self.errors.append(error)
        self.add_message("system", f"[Error] {error}")

    @property
    def elapsed_seconds(self) -> float:
        if self.end_time > 0:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_input": self.user_input,
            "task_status": self.task_status.value,
            "plan": [t.to_dict() for t in self.plan],
            "current_step": self.current_step,
            "messages": self.messages[-20:],
            "tool_results": {k: str(v)[:500] for k, v in self.tool_results.items()},
            "validation_result": self.validation_result,
            "final_output": self.final_output,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_tokens": self.total_tokens,
            "successful_tool_calls": self.successful_tool_calls,
            "failed_tool_calls": self.failed_tool_calls,
            "errors": self.errors[-10:],
            "retry_count": self.retry_count,
            "snapshot_version": self.snapshot_version,
            "rag_context": self.rag_context,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentState":
        state = cls()
        state.task_id = data.get("task_id", "")
        state.user_input = data.get("user_input", "")
        state.task_status = TaskStatus(data.get("task_status", "pending"))
        state.current_step = data.get("current_step", 0)
        state.messages = data.get("messages", [])
        state.validation_result = data.get("validation_result")
        state.final_output = data.get("final_output")
        state.start_time = data.get("start_time", 0.0)
        state.end_time = data.get("end_time", 0.0)
        state.total_tokens = data.get("total_tokens", 0)
        state.successful_tool_calls = data.get("successful_tool_calls", 0)
        state.failed_tool_calls = data.get("failed_tool_calls", 0)
        state.errors = data.get("errors", [])
        state.retry_count = data.get("retry_count", 0)
        state.snapshot_version = data.get("snapshot_version", 0)
        state.rag_context = data.get("rag_context")

        for t_data in data.get("plan", []):
            task = SubTask(
                id=t_data.get("id", ""),
                description=t_data.get("description", ""),
                tool_name=t_data.get("tool_name", ""),
                arguments=t_data.get("arguments", {}),
                dependencies=t_data.get("dependencies", []),
                status=TaskStatus(t_data.get("status", "pending")),
                result=t_data.get("result"),
                error=t_data.get("error"),
                retry_count=t_data.get("retry_count", 0),
                execution_time_ms=t_data.get("execution_time_ms", 0.0),
            )
            state.plan.append(task)

        return state


# ============================================================
# Model & Performance Types
# ============================================================

@dataclass
class ModelConfig:
    """Model configuration."""
    provider: str = "deepseek"
    model_name: str = "deepseek-chat"
    api_base: str = "https://api.deepseek.com/v1"
    api_key_env: str = "DEEPSEEK_API_KEY"
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 0.95
    timeout: float = 60.0
    max_retries: int = 3


@dataclass
class CacheEntry:
    """Context cache entry."""
    key: str
    content: str
    hash: str
    timestamp: float = field(default_factory=time.time)
    hit_count: int = 0
    token_count: int = 0
    original_token_count: int = 0


# ============================================================
# RAG Types
# ============================================================

@dataclass
class Document:
    """Document for RAG knowledge base."""
    id: str = field(default_factory=lambda: f"doc_{uuid.uuid4().hex[:12]}")
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None


@dataclass
class SearchResult:
    """RAG search result."""
    document: Document
    score: float
    rank: int = 0


# ============================================================
# Benchmark Types
# ============================================================

@dataclass
class MetricSnapshot:
    """A single metric measurement."""
    name: str
    value: float
    unit: str = ""
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    """Benchmark execution result."""
    name: str
    description: str = ""
    iterations: int = 1
    metrics: List[MetricSnapshot] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0

    def add_metric(self, name: str, value: float, unit: str = "",
                   tags: Dict[str, str] = None):
        self.metrics.append(MetricSnapshot(
            name=name, value=value, unit=unit, tags=tags or {}
        ))

    @property
    def duration_seconds(self) -> float:
        if self.end_time > 0:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "iterations": self.iterations,
            "duration_seconds": self.duration_seconds,
            "metrics": [
                {"name": m.name, "value": m.value, "unit": m.unit, "tags": m.tags}
                for m in self.metrics
            ],
            "summary": self.summary,
        }
