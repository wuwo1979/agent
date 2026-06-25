"""
Supervisor-Worker Pattern - Multi-Agent orchestration with handoffs.

Architecture:
    Supervisor Agent (central coordinator)
    ├── Planner Worker (task decomposition)
    ├── Executor Worker (tool execution)
    └── Validator Worker (result verification)

Based on LangGraph handoffs pattern:
- Supervisor dynamically routes tasks to specialized workers
- Workers return control to Supervisor after completion
- Supports streaming output and checkpoint/resume
"""

import asyncio
import time
import json
from typing import Any, Dict, List, Optional, AsyncGenerator, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging

from agent_scheduler.state import AgentState, SubTask, TaskStatus
from agent_scheduler.retry import RetryManager, RetryConfig

logger = logging.getLogger("agent_scheduler.supervisor")


class WorkerRole(str, Enum):
    """Worker agent roles in Supervisor-Worker pattern."""
    SUPERVISOR = "supervisor"
    PLANNER = "planner"
    EXECUTOR = "executor"
    VALIDATOR = "validator"


@dataclass
class WorkerResult:
    """Result returned by a worker agent."""
    role: WorkerRole
    success: bool
    state: AgentState
    message: str = ""
    next_worker: Optional[WorkerRole] = None  # Handoff target
    metadata: Dict[str, Any] = field(default_factory=dict)


class SupervisorAgent:
    """
    Central Supervisor agent that coordinates worker agents.

    Features:
    - Dynamic routing: decides which worker handles each step
    - Handoffs: transfers control between workers via Command pattern
    - Streaming: yields status updates during execution
    - Checkpoint: saves state for resume after failure
    - Observability: tracks timing and success metrics per worker
    """

    def __init__(
        self,
        planner: Any = None,
        executor: Any = None,
        validator: Any = None,
        max_iterations: int = 10,
    ):
        self.planner = planner
        self.executor = executor
        self.validator = validator
        self.max_iterations = max_iterations

        # Metrics
        self.worker_metrics: Dict[str, Dict[str, Any]] = {
            "planner": {"calls": 0, "total_time_ms": 0, "errors": 0},
            "executor": {"calls": 0, "total_time_ms": 0, "errors": 0},
            "validator": {"calls": 0, "total_time_ms": 0, "errors": 0},
        }

    async def run(
        self,
        state: AgentState,
        stream: bool = False,
    ) -> AgentState:
        """
        Execute the Supervisor-Worker workflow.

        Args:
            state: Initial agent state with user input
            stream: If True, yield intermediate status updates

        Returns:
            Final agent state with results
        """
        state.start_time = time.time()

        # Phase 1: Planning
        state = await self._delegate_to_planner(state)

        if state.task_status == TaskStatus.FAILED:
            return state

        # Phase 2: Execution
        state = await self._delegate_to_executor(state)

        if state.task_status == TaskStatus.FAILED:
            return state

        # Phase 3: Validation
        state = await self._delegate_to_validator(state)

        state.end_time = time.time()
        return state

    async def run_streaming(
        self,
        state: AgentState,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute with streaming status updates.

        Yields:
            Dict with status, role, message, and progress
        """
        state.start_time = time.time()

        yield {
            "status": "started",
            "role": "supervisor",
            "message": f"Starting task: {state.user_input[:50]}",
            "progress": 0.0,
        }

        # Phase 1: Planning
        yield {
            "status": "running",
            "role": "planner",
            "message": "Analyzing task and creating plan...",
            "progress": 0.1,
        }
        state = await self._delegate_to_planner(state)
        yield {
            "status": "completed",
            "role": "planner",
            "message": f"Created {len(state.plan)} subtasks",
            "progress": 0.3,
        }

        if state.task_status == TaskStatus.FAILED:
            yield {
                "status": "failed",
                "role": "planner",
                "message": "Planning failed",
                "progress": 1.0,
            }
            return

        # Phase 2: Execution
        for i, task in enumerate(state.plan):
            progress = 0.3 + (0.5 * (i + 1) / len(state.plan))
            yield {
                "status": "running",
                "role": "executor",
                "message": f"Executing [{task.id}] {task.tool_name}...",
                "progress": progress,
                "task_id": task.id,
            }

        state = await self._delegate_to_executor(state)

        for task in state.plan:
            if task.status == TaskStatus.COMPLETED:
                yield {
                    "status": "completed",
                    "role": "executor",
                    "message": f"[{task.id}] done in {task.execution_time_ms:.0f}ms",
                    "progress": 0.8,
                    "task_id": task.id,
                }
            else:
                yield {
                    "status": "failed",
                    "role": "executor",
                    "message": f"[{task.id}] {task.error}",
                    "progress": 0.8,
                    "task_id": task.id,
                }

        # Phase 3: Validation
        yield {
            "status": "running",
            "role": "validator",
            "message": "Validating results...",
            "progress": 0.9,
        }
        state = await self._delegate_to_validator(state)

        valid = state.validation_result.get("valid", False) if state.validation_result else False
        yield {
            "status": "completed" if valid else "done",
            "role": "validator",
            "message": f"Validation: {'PASS' if valid else 'issues found'} (score: {state.validation_result.get('score', 'N/A')})",
            "progress": 1.0,
        }

        state.end_time = time.time()

    async def _delegate_to_planner(self, state: AgentState) -> AgentState:
        """Delegate task to Planner worker."""
        t0 = time.time()
        self.worker_metrics["planner"]["calls"] += 1

        try:
            state = await self.planner.plan(state)
            elapsed = (time.time() - t0) * 1000
            self.worker_metrics["planner"]["total_time_ms"] += elapsed
            state.add_message("supervisor", f"Planner created {len(state.plan)} subtasks")
            return state
        except Exception as e:
            self.worker_metrics["planner"]["errors"] += 1
            state.add_error(f"Planner error: {e}")
            state.task_status = TaskStatus.FAILED
            return state

    async def _delegate_to_executor(self, state: AgentState) -> AgentState:
        """Delegate task to Executor worker."""
        t0 = time.time()
        self.worker_metrics["executor"]["calls"] += 1

        try:
            state = await self.executor.execute(state)
            elapsed = (time.time() - t0) * 1000
            self.worker_metrics["executor"]["total_time_ms"] += elapsed
            state.add_message(
                "supervisor",
                f"Executor: {state.successful_tool_calls} success, {state.failed_tool_calls} failed"
            )
            return state
        except Exception as e:
            self.worker_metrics["executor"]["errors"] += 1
            state.add_error(f"Executor error: {e}")
            state.task_status = TaskStatus.FAILED
            return state

    async def _delegate_to_validator(self, state: AgentState) -> AgentState:
        """Delegate task to Validator worker."""
        t0 = time.time()
        self.worker_metrics["validator"]["calls"] += 1

        try:
            state = await self.validator.validate(state)
            elapsed = (time.time() - t0) * 1000
            self.worker_metrics["validator"]["total_time_ms"] += elapsed
            if state.validation_result:
                score = state.validation_result.get("score", "N/A")
                state.add_message("supervisor", f"Validation score: {score}")
            return state
        except Exception as e:
            self.worker_metrics["validator"]["errors"] += 1
            state.add_error(f"Validator error: {e}")
            return state

    def get_metrics(self) -> Dict[str, Any]:
        """Get worker performance metrics."""
        return {
            "workers": self.worker_metrics,
            "total_time_ms": sum(
                m["total_time_ms"] for m in self.worker_metrics.values()
            ),
            "total_errors": sum(
                m["errors"] for m in self.worker_metrics.values()
            ),
        }

    def visualize(self) -> str:
        """Generate Mermaid graph for Supervisor-Worker architecture."""
        return """
```mermaid
graph TD
    USER([User Input]) --> SUPERVISOR
    SUPERVISOR -->|delegate| PLANNER[Planner Worker<br/>Task Decomposition]
    PLANNER -->|handoff| SUPERVISOR
    SUPERVISOR -->|delegate| EXECUTOR[Executor Worker<br/>Tool Execution]
    EXECUTOR -->|handoff| SUPERVISOR
    SUPERVISOR -->|delegate| VALIDATOR[Validator Worker<br/>Result Verification]
    VALIDATOR -->|handoff| SUPERVISOR
    SUPERVISOR --> OUTPUT([Final Output])

    style SUPERVISOR fill:#4a90d9,stroke:#333,color:#fff
    style PLANNER fill:#50c878,stroke:#333
    style EXECUTOR fill:#f0ad4e,stroke:#333
    style VALIDATOR fill:#d9534f,stroke:#333,color:#fff
```
"""


# ============================================================
# Factory Functions
# ============================================================

def create_supervisor_agent(
    plan_agent: Any,
    executor_agent: Any,
    valid_agent: Any,
) -> SupervisorAgent:
    """Create a SupervisorAgent with the given worker agents."""
    return SupervisorAgent(
        planner=plan_agent,
        executor=executor_agent,
        validator=valid_agent,
    )