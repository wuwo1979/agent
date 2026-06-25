"""
Agent 调度层 - LangGraph 工作流
实现任务自动拆分、串行/并行工具执行、失败自愈重试、状态快照
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agent_scheduler.agents.executor import ExecutorAgent
from agent_scheduler.agents.planner import PlannerAgent, SimplePlannerAgent
from agent_scheduler.agents.validator import SimpleValidator, ValidatorAgent
from agent_scheduler.state import AgentState, SnapshotManager, TaskStatus
from mcp_gateway.protocol import ToolRegistry

logger = logging.getLogger("agent_scheduler.graph")


# ============================================================
# LangGraph 节点定义
# ============================================================

async def planning_node(state: AgentState, planner: Any) -> AgentState:
    """规划节点：拆解任务"""
    logger.info(f"[Graph] Planning node: {state.user_input[:50]}...")
    return await planner.plan(state)


async def execution_node(state: AgentState, executor: Any) -> AgentState:
    """执行节点：调用工具"""
    logger.info(f"[Graph] Execution node: {len(state.plan)} subtasks")
    return await executor.execute(state)


async def validation_node(state: AgentState, validator: Any) -> AgentState:
    """校验节点：验证结果"""
    logger.info("[Graph] Validation node")
    return await validator.validate(state)


def routing_function(state: AgentState) -> str:
    """路由判断：决定下一步"""
    if state.task_status == TaskStatus.FAILED:
        if state.retry_count < state.max_retries:
            logger.info(f"[Graph] Routing: RETRY ({state.retry_count + 1}/{state.max_retries})")
            state.retry_count += 1
            return "planning"
        else:
            logger.info("[Graph] Routing: END (max retries exhausted)")
            return END

    if state.task_status == TaskStatus.RETRYING:
        logger.info("[Graph] Routing: RETRY → planning")
        state.retry_count += 1
        return "planning"

    if state.task_status == TaskStatus.COMPLETED:
        logger.info("[Graph] Routing: END (completed)")
        return END

    # 默认流向：planning → execution → validation
    if state.task_status == TaskStatus.PLANNING:
        return "execution"
    if state.task_status == TaskStatus.EXECUTING:
        return "validation"
    if state.task_status == TaskStatus.VALIDATING:
        return END

    return END


# ============================================================
# Agent Graph 封装
# ============================================================

@dataclass
class AgentGraph:
    """
    Agent 工作流图
    封装 LangGraph 的构建和执行
    """

    planner: Any
    executor: Any
    validator: Any
    snapshot_manager: SnapshotManager = field(default_factory=SnapshotManager)
    graph: Optional[StateGraph] = None
    compiled_graph: Optional[Any] = None

    def __post_init__(self):
        self._build_graph()

    def _build_graph(self):
        """构建 LangGraph 工作流"""
        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node(
            "planning",
            lambda s: planning_node(s, self.planner)
        )
        workflow.add_node(
            "execution",
            lambda s: execution_node(s, self.executor)
        )
        workflow.add_node(
            "validation",
            lambda s: validation_node(s, self.validator)
        )

        # 设置入口
        workflow.set_entry_point("planning")

        # 添加条件边
        workflow.add_conditional_edges(
            "planning",
            routing_function,
            {
                "execution": "execution",
                END: END,
            }
        )

        workflow.add_conditional_edges(
            "execution",
            routing_function,
            {
                "validation": "validation",
                "planning": "planning",  # 重试
                END: END,
            }
        )

        workflow.add_conditional_edges(
            "validation",
            routing_function,
            {
                "planning": "planning",  # 校验不通过 → 重新规划
                END: END,
            }
        )

        # 编译图（带检查点支持断点续跑）
        memory = MemorySaver()
        self.graph = workflow
        self.compiled_graph = workflow.compile(checkpointer=memory)

    async def run(
        self,
        user_input: str,
        task_id: Optional[str] = None,
        resume: bool = False,
        use_supervisor: bool = False,
        stream: bool = False,
    ) -> AgentState:
        """
        Run Agent workflow.

        Args:
            user_input: User input text
            task_id: Task ID (for checkpoint resume)
            resume: Restore from snapshot if True
            use_supervisor: Use Supervisor-Worker mode (recommended for production)
            stream: Enable streaming output (Supervisor mode only)

        Returns:
            Final AgentState
        """
        if use_supervisor:
            return await self._run_supervisor(user_input, task_id, resume, stream)

        if resume and task_id:
            state = self.snapshot_manager.load(task_id)
            if state:
                logger.info(f"Resuming task {task_id} from snapshot")
                return await self._invoke_graph(state)

        # New task
        state = AgentState(
            task_id=task_id or f"task_{uuid.uuid4().hex[:12]}",
            user_input=user_input,
        )

        result = await self._invoke_graph(state)

        # Save snapshot
        self.snapshot_manager.save(result)

        return result

    async def _run_supervisor(
        self,
        user_input: str,
        task_id: Optional[str] = None,
        resume: bool = False,
        stream: bool = False,
    ) -> AgentState:
        """Run using Supervisor-Worker pattern."""
        from agent_scheduler.supervisor import SupervisorAgent

        state = AgentState(
            task_id=task_id or f"task_{uuid.uuid4().hex[:12]}",
            user_input=user_input,
        )

        supervisor = SupervisorAgent(
            planner=self.planner,
            executor=self.executor,
            validator=self.validator,
        )

        if stream:
            logger.info(f"Running Supervisor-Worker with streaming: {user_input[:50]}")
            state = await supervisor.run(state)
            # Note: streaming collected via run_streaming() if needed
        else:
            state = await supervisor.run(state)

        self.snapshot_manager.save(state)
        return state

    async def run_streaming(self, user_input: str, task_id: Optional[str] = None):
        """Run with streaming status updates using Supervisor-Worker."""
        from agent_scheduler.supervisor import SupervisorAgent

        state = AgentState(
            task_id=task_id or f"task_{uuid.uuid4().hex[:12]}",
            user_input=user_input,
        )

        supervisor = SupervisorAgent(
            planner=self.planner,
            executor=self.executor,
            validator=self.validator,
        )

        async for update in supervisor.run_streaming(state):
            yield update

        self.snapshot_manager.save(state)

    async def _invoke_graph(self, state: AgentState) -> AgentState:
        """调用 LangGraph 执行"""
        import time
        state.start_time = time.time()

        config = {"configurable": {"thread_id": state.task_id}}

        final_state = await self.compiled_graph.ainvoke(state, config)

        final_state.end_time = time.time()

        # 修复：LangGraph 返回的是 dict，需要转换
        if isinstance(final_state, dict):
            result = AgentState()
            result.__dict__.update(final_state)
            return result

        return final_state

    def visualize(self) -> str:
        """生成 Mermaid 流程图"""
        return """
```mermaid
graph TD
    START([用户输入]) --> PLANNING[规划 Agent<br/>任务拆解]
    PLANNING -->|成功| EXECUTION[执行 Agent<br/>串行/并行工具调用]
    PLANNING -->|失败| END_FAIL([失败结束])
    EXECUTION -->|成功| VALIDATION[校验 Agent<br/>结果验证]
    EXECUTION -->|失败| RETRY{重试?}
    RETRY -->|是| PLANNING
    RETRY -->|否| END_FAIL
    VALIDATION -->|通过| END_OK([完成])
    VALIDATION -->|不通过| RETRY2{重试?}
    RETRY2 -->|是| PLANNING
    RETRY2 -->|否| END_OK
```
"""


# ============================================================
# 工厂函数
# ============================================================

def create_agent_graph(
    tool_registry: ToolRegistry,
    llm: Optional[Any] = None,
    use_simple_agents: bool = False,
) -> AgentGraph:
    """
    创建 Agent 工作流图
    Args:
        tool_registry: 工具注册中心
        llm: LLM 实例（可选，None 时使用简化版 Agent）
        use_simple_agents: 是否使用简化版 Agent（无需 LLM）
    Returns:
        AgentGraph 实例
    """
    # 构建工具描述
    tools_desc = json.dumps(tool_registry.list_tools(), ensure_ascii=False, indent=2)

    if use_simple_agents or llm is None:
        planner = SimplePlannerAgent(tools_description=tools_desc)
        validator = SimpleValidator()
    else:
        planner = PlannerAgent(llm=llm, tools_description=tools_desc)
        validator = ValidatorAgent(llm=llm)

    executor = ExecutorAgent(tool_registry=tool_registry)

    return AgentGraph(
        planner=planner,
        executor=executor,
        validator=validator,
    )
