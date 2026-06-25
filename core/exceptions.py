"""
Core exceptions - Typed error hierarchy for the system.

Design principles:
1. Typed errors - Each error type has a specific meaning
2. Recoverable vs Fatal - Clearly distinguish transient vs permanent errors
3. Context-rich - Include enough info for debugging and self-healing
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# ============================================================
# Base Exceptions
# ============================================================

class MCPSystemError(Exception):
    """Base exception for all MCP Gateway system errors."""

    def __init__(self, message: str, code: str = "SYSTEM_ERROR",
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.__class__.__name__,
            "code": self.code,
            "message": str(self),
            "details": self.details,
        }


class AgentError(Exception):
    """Base exception for all Agent scheduling errors."""

    def __init__(self, message: str, code: str = "AGENT_ERROR",
                 recoverable: bool = False,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.__class__.__name__,
            "code": self.code,
            "message": str(self),
            "recoverable": self.recoverable,
            "details": self.details,
        }


# ============================================================
# MCP Protocol Errors
# ============================================================

class ToolNotFoundError(MCPSystemError):
    """Raised when a requested tool is not registered."""
    def __init__(self, tool_name: str):
        super().__init__(
            message=f"Tool not found: {tool_name}",
            code="TOOL_NOT_FOUND",
            details={"tool_name": tool_name},
        )


class ToolExecutionError(MCPSystemError):
    """Raised when a tool execution fails."""
    def __init__(self, tool_name: str, reason: str,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Tool execution failed [{tool_name}]: {reason}",
            code="TOOL_EXECUTION_ERROR",
            details={"tool_name": tool_name, "reason": reason, **(details or {})},
        )


class ToolTimeoutError(MCPSystemError):
    """Raised when a tool execution times out."""
    def __init__(self, tool_name: str, timeout_ms: float):
        super().__init__(
            message=f"Tool execution timed out [{tool_name}]: {timeout_ms}ms",
            code="TOOL_TIMEOUT",
            details={"tool_name": tool_name, "timeout_ms": timeout_ms},
        )


class ProtocolError(MCPSystemError):
    """Raised for JSON-RPC protocol violations."""
    def __init__(self, message: str, code: str = "PROTOCOL_ERROR"):
        super().__init__(message=message, code=code)


class InvalidRequestError(MCPSystemError):
    """Raised for invalid JSON-RPC requests."""
    def __init__(self, message: str = "Invalid request"):
        super().__init__(message=message, code="INVALID_REQUEST")


class MethodNotFoundError(MCPSystemError):
    """Raised when a JSON-RPC method is not found."""
    def __init__(self, method: str):
        super().__init__(
            message=f"Method not found: {method}",
            code="METHOD_NOT_FOUND",
            details={"method": method},
        )


class ResourceNotFoundError(MCPSystemError):
    """Raised when a requested resource is not found."""
    def __init__(self, uri: str):
        super().__init__(
            message=f"Resource not found: {uri}",
            code="RESOURCE_NOT_FOUND",
            details={"uri": uri},
        )


class PromptNotFoundError(MCPSystemError):
    """Raised when a requested prompt is not found."""
    def __init__(self, name: str):
        super().__init__(
            message=f"Prompt not found: {name}",
            code="PROMPT_NOT_FOUND",
            details={"prompt_name": name},
        )


# ============================================================
# Security Errors
# ============================================================

class AuthenticationError(MCPSystemError):
    """Raised when authentication fails."""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message=message, code="AUTH_REQUIRED")


class RateLimitError(MCPSystemError):
    """Raised when rate limit is exceeded."""
    def __init__(self, client_id: str, retry_after: float = 60.0):
        super().__init__(
            message=f"Rate limit exceeded for {client_id}",
            code="RATE_LIMITED",
            details={"client_id": client_id, "retry_after": retry_after},
        )


class PermissionDeniedError(MCPSystemError):
    """Raised when a tool is not allowed by policy."""
    def __init__(self, tool_name: str, reason: str = "Permission denied"):
        super().__init__(
            message=f"Permission denied for tool [{tool_name}]: {reason}",
            code="PERMISSION_DENIED",
            details={"tool_name": tool_name, "reason": reason},
        )


# ============================================================
# Agent Errors
# ============================================================

class PlanningError(AgentError):
    """Raised when task planning fails."""
    def __init__(self, message: str, recoverable: bool = True):
        super().__init__(
            message=message,
            code="PLANNING_ERROR",
            recoverable=recoverable,
        )


class ExecutionError(AgentError):
    """Raised when task execution fails."""
    def __init__(self, message: str, task_id: Optional[str] = None,
                 recoverable: bool = True):
        super().__init__(
            message=message,
            code="EXECUTION_ERROR",
            recoverable=recoverable,
            details={"task_id": task_id} if task_id else {},
        )


class ValidationError(AgentError):
    """Raised when task validation fails."""
    def __init__(self, message: str, recoverable: bool = True):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            recoverable=recoverable,
        )


class MaxRetriesExceededError(AgentError):
    """Raised when max retries are exhausted."""
    def __init__(self, max_retries: int, last_error: Optional[str] = None):
        super().__init__(
            message=f"Max retries ({max_retries}) exceeded",
            code="MAX_RETRIES_EXCEEDED",
            recoverable=False,
            details={"max_retries": max_retries, "last_error": last_error},
        )


# ============================================================
# Configuration & System Errors
# ============================================================

class ConfigurationError(Exception):
    """Raised for configuration-related errors."""
    def __init__(self, message: str, key: Optional[str] = None):
        super().__init__(message)
        self.key = key


class ConnectionError(MCPSystemError):
    """Raised when external service connection fails."""
    def __init__(self, service: str, reason: str):
        super().__init__(
            message=f"Connection to {service} failed: {reason}",
            code="CONNECTION_ERROR",
            details={"service": service, "reason": reason},
        )


class CircuitBreakerOpenError(MCPSystemError):
    """Raised when circuit breaker is open."""
    def __init__(self, service: str, failure_count: int):
        super().__init__(
            message=f"Circuit breaker open for {service} ({failure_count} failures)",
            code="CIRCUIT_BREAKER_OPEN",
            details={"service": service, "failure_count": failure_count},
        )
