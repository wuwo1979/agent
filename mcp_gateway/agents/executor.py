"""
Agent 调度层 - 执行 Agent
负责任务执行、工具调用、并行调度
"""

import asyncio
import logging
import time
from typing import Any, List, Optional

from mcp_gateway.agents.retry import RetryManager
from mcp_gateway.agents.state import AgentState, SubTask, TaskStatus
from mcp_gateway.protocol import ToolCallResult, ToolRegistry

logger = logging.getLogger("agent_scheduler.executor")


class ExecutorAgent:
    """
    执行 Agent
    负责按计划执行子任务，支持串行/并行、重试、降级
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        retry_manager: Optional[RetryManager] = None,
        max_parallel: int = 5,
    ):
        self.registry = tool_registry
        self.retry_manager = retry_manager or RetryManager()
        self.max_parallel = max_parallel

    async def execute(self, state: AgentState) -> AgentState:
        """
        执行任务计划
        自动识别依赖关系，无依赖任务并行执行
        """
        if not state.plan:
            state.add_error("没有可执行的计划")
            state.task_status = TaskStatus.FAILED
            return state

        logger.info(f"ExecutorAgent: executing {len(state.plan)} subtasks")
        state.task_status = TaskStatus.EXECUTING
        state.add_message("executor", f"开始执行 {len(state.plan)} 个子任务")

        # 构建依赖图
        completed: set = set()
        failed: set = set()

        while len(completed) + len(failed) < len(state.plan):
            # 找出所有就绪的任务（依赖已满足、未执行）
            ready_tasks = []
            for task in state.plan:
                if task.id in completed or task.id in failed:
                    continue
                if all(dep in completed for dep in task.dependencies):
                    ready_tasks.append(task)

            if not ready_tasks:
                # 死锁检测：如果有未完成任务但没有就绪任务
                remaining = [t for t in state.plan if t.id not in completed and t.id not in failed]
                logger.error(f"Deadlock detected! Remaining: {[t.id for t in remaining]}")
                for task in remaining:
                    task.status = TaskStatus.FAILED
                    task.error = "Deadlock: unresolved dependencies"
                    failed.add(task.id)
                break

            # 并行执行就绪任务（限制最大并发数）
            batches = self._split_into_batches(ready_tasks, self.max_parallel)

            for batch in batches:
                tasks_coroutines = [
                    self._execute_single_task(task, state) for task in batch
                ]
                results = await asyncio.gather(*tasks_coroutines, return_exceptions=True)

                for task, result in zip(batch, results):
                    if isinstance(result, Exception):
                        logger.error(f"Task {task.id} failed: {result}")
                        task.status = TaskStatus.FAILED
                        task.error = str(result)
                        failed.add(task.id)
                        state.failed_tool_calls += 1
                    else:
                        task.status = TaskStatus.COMPLETED
                        completed.add(task.id)
                        state.successful_tool_calls += 1

        # 更新状态
        all_completed = len(failed) == 0
        state.task_status = TaskStatus.COMPLETED if all_completed else TaskStatus.FAILED
        state.add_message(
            "executor",
            f"执行完成: {len(completed)} 成功, {len(failed)} 失败"
        )

        return state

    async def _execute_single_task(self, task: SubTask, state: AgentState) -> Any:
        """执行单个子任务（带重试）"""
        start = time.perf_counter()
        task.status = TaskStatus.EXECUTING

        try:
            result = await self.retry_manager.execute_with_retry(
                self.registry.call_tool,
                task.tool_name,
                task.arguments,
                tool_name=task.tool_name,
            )
            task.execution_time_ms = (time.perf_counter() - start) * 1000

            if isinstance(result, ToolCallResult):
                task.result = result.content
                state.tool_results[task.id] = result.content
                if result.is_error:
                    raise RuntimeError(str(result.content))
            else:
                task.result = result
                state.tool_results[task.id] = result

            return result

        except Exception as e:
            task.execution_time_ms = (time.perf_counter() - start) * 1000
            task.error = str(e)
            raise

    def _split_into_batches(self, tasks: List[SubTask], batch_size: int) -> List[List[SubTask]]:
        """将任务分批"""
        return [tasks[i:i + batch_size] for i in range(0, len(tasks), batch_size)]


class SequentialExecutor:
    """串行执行器（用于对比测试）"""

    def __init__(self, tool_registry: ToolRegistry):
        self.registry = tool_registry

    async def execute(self, state: AgentState) -> AgentState:
        """串行执行所有任务"""
        state.task_status = TaskStatus.EXECUTING

        for task in state.plan:
            task.status = TaskStatus.EXECUTING
            try:
                result = await self.registry.call_tool(task.tool_name, task.arguments)
                task.result = result.content if isinstance(result, ToolCallResult) else result
                task.status = TaskStatus.COMPLETED
                state.successful_tool_calls += 1
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                state.failed_tool_calls += 1

        state.task_status = TaskStatus.COMPLETED
        return state
