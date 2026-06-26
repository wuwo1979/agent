"""Agent 调度层主模块

合并自原 agent_scheduler/ 模块。
包含 Planner-Executor-Validator 三阶段 Agent 工作流
和 Supervisor-Worker 多 Agent 协作模式。

依赖: pip install langgraph（可选，graph 相关功能）
"""

from mcp_gateway.agents.executor import ExecutorAgent, SequentialExecutor
from mcp_gateway.agents.retry import CircuitBreaker, RetryConfig, RetryManager
from mcp_gateway.agents.state import AgentRole, AgentState, SnapshotManager, SubTask, TaskStatus
from mcp_gateway.agents.supervisor import SupervisorAgent, WorkerRole, create_supervisor_agent

# Optional langchain-dependent agents
try:
    from mcp_gateway.agents.planner import PlannerAgent, SimplePlannerAgent
except ImportError:
    PlannerAgent = None
    SimplePlannerAgent = None

try:
    from mcp_gateway.agents.validator import SimpleValidator, ValidatorAgent
except ImportError:
    ValidatorAgent = None
    SimpleValidator = None

# Optional langgraph-dependent graph
try:
    from mcp_gateway.agents.graph import AgentGraph, create_agent_graph
except ImportError:
    AgentGraph = None
    create_agent_graph = None

__all__ = [
    "AgentState",
    "SubTask",
    "TaskStatus",
    "AgentRole",
    "SnapshotManager",
    "RetryManager",
    "RetryConfig",
    "CircuitBreaker",
    "SupervisorAgent",
    "WorkerRole",
    "create_supervisor_agent",
    "PlannerAgent",
    "SimplePlannerAgent",
    "ExecutorAgent",
    "SequentialExecutor",
    "ValidatorAgent",
    "SimpleValidator",
    "AgentGraph",
    "create_agent_graph",
]
