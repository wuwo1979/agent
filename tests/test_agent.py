"""
Agent 调度层测试 + 性能优化层测试
"""

import asyncio
import sys
import os
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_gateway.protocol import ToolRegistry, BaseToolProvider
from core.types import ToolDefinition, ToolCallResult
from agent_scheduler.state import AgentState, SubTask, TaskStatus, SnapshotManager
from agent_scheduler.retry import RetryManager, RetryConfig, CircuitBreaker
from agent_scheduler.agents.executor import ExecutorAgent
from agent_scheduler.agents.planner import SimplePlannerAgent
from agent_scheduler.agents.validator import SimpleValidator
from performance.cache import IncrementalContextCache
from performance.parallel import ParallelScheduler, DependencyGraph


# ============================================================
# Mock Provider for Agent Tests
# ============================================================

class MockAgentProvider(BaseToolProvider):
    """Mock tool provider for agent testing."""

    def __init__(self):
        super().__init__(name="agent_test", description="Agent test mock provider")
        self._register_tools()

    def _register_tools(self):
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
        return ToolCallResult.text_result(tool_name, f"{tool_name}_result", 1.0)


# ============================================================
# Agent 状态管理测试
# ============================================================

class TestAgentState:
    """Agent 状态测试"""

    def test_state_creation(self):
        state = AgentState(
            task_id="test_001",
            user_input="读取文件并查询数据库",
        )
        assert state.task_id == "test_001"
        assert state.task_status == TaskStatus.PENDING
        assert len(state.plan) == 0

    def test_add_message(self):
        state = AgentState(task_id="test", user_input="test")
        state.add_message("user", "hello")
        assert len(state.messages) == 1
        assert state.messages[0]["role"] == "user"

    def test_add_error(self):
        state = AgentState(task_id="test", user_input="test")
        state.add_error("something went wrong")
        assert len(state.errors) == 1
        assert "something went wrong" in state.errors[0]

    def test_serialization(self):
        state = AgentState(task_id="test_001", user_input="test task")
        state.plan = [
            SubTask(id="t1", description="task 1", tool_name="tool_a"),
            SubTask(id="t2", description="task 2", tool_name="tool_b"),
        ]
        state.add_message("user", "hi")

        data = state.to_dict()
        restored = AgentState.from_dict(data)

        assert restored.task_id == "test_001"
        assert restored.user_input == "test task"
        assert len(restored.plan) == 2
        assert restored.plan[0].id == "t1"

    def test_snapshot_manager(self):
        sm = SnapshotManager(snapshot_dir="./test_snapshots")
        state = AgentState(task_id="snap_test", user_input="test")

        path = sm.save(state)
        assert os.path.exists(path)

        loaded = sm.load("snap_test")
        assert loaded is not None
        assert loaded.task_id == "snap_test"

        # 清理
        sm.cleanup("snap_test", keep_last=0)
        assert sm.load("snap_test") is None


# ============================================================
# 重试机制测试
# ============================================================

class TestRetry:
    """重试机制测试"""

    @pytest.mark.asyncio
    async def test_retry_success(self):
        """测试重试后成功"""
        retry = RetryManager(RetryConfig(max_retries=3, base_delay=0.01))

        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("temporary error")
            return "success"

        result = await retry.execute_with_retry(flaky_func, tool_name="flaky")
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """测试重试耗尽"""
        retry = RetryManager(RetryConfig(max_retries=2, base_delay=0.01))

        async def always_fails():
            raise ConnectionError("always fail")

        with pytest.raises(ConnectionError):
            await retry.execute_with_retry(always_fails, tool_name="failing")

    @pytest.mark.asyncio
    async def test_fallback(self):
        """测试降级"""
        retry = RetryManager(RetryConfig(max_retries=1, base_delay=0.01))

        async def failing():
            raise ConnectionError("fail")

        async def fallback():
            return "fallback_result"

        result = await retry.execute_with_retry(
            failing, fallback=fallback, tool_name="degraded"
        )
        assert result == "fallback_result"

    def test_circuit_breaker(self):
        """测试熔断器"""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.01)

        assert cb.allow_request()  # closed → allow

        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        assert not cb.allow_request()  # open → block

        # 等待恢复
        time.sleep(0.02)
        assert cb.allow_request()  # half_open → allow


# ============================================================
# 执行器测试
# ============================================================

class TestExecutor:
    """执行器测试"""

    @pytest.mark.asyncio
    async def test_executor(self):
        registry = ToolRegistry()
        registry.register_provider(MockAgentProvider())

        executor = ExecutorAgent(registry)

        state = AgentState(
            task_id="exec_test",
            user_input="test",
            plan=[
                SubTask(id="t1", description="A", tool_name="tool_a", arguments={}),
                SubTask(id="t2", description="B", tool_name="tool_b", arguments={}),
            ],
        )

        result = await executor.execute(state)
        assert result.task_status == TaskStatus.COMPLETED
        assert result.successful_tool_calls == 2


# ============================================================
# 规划器测试
# ============================================================

class TestPlanner:
    """规划器测试"""

    @pytest.mark.asyncio
    async def test_simple_planner(self):
        planner = SimplePlannerAgent()
        state = AgentState(task_id="plan_test", user_input="读取文件并查询系统信息")

        result = await planner.plan(state)
        assert len(result.plan) > 0
        assert result.task_status == TaskStatus.PLANNING


# ============================================================
# 校验器测试
# ============================================================

class TestValidator:
    """校验器测试"""

    @pytest.mark.asyncio
    async def test_simple_validator(self):
        validator = SimpleValidator()
        state = AgentState(
            task_id="valid_test",
            user_input="test",
            plan=[
                SubTask(
                    id="t1", description="success task",
                    tool_name="tool_a", status=TaskStatus.COMPLETED,
                    result="success",
                ),
            ],
        )

        result = await validator.validate(state)
        assert result.validation_result is not None
        assert result.validation_result["valid"] is True


# ============================================================
# 缓存测试
# ============================================================

class TestCache:
    """缓存测试"""

    def test_cache_hit(self):
        cache = IncrementalContextCache()

        # 第一次调用
        result = cache.get("tool_a", {"arg": "1"})
        assert result is None

        cache.set("tool_a", {"arg": "1"}, "result content", 100)

        # 第二次调用 → 命中
        cached = cache.get("tool_a", {"arg": "1"})
        assert cached is not None
        assert cached[0] == "result content"

    def test_cache_different_args(self):
        cache = IncrementalContextCache()

        cache.set("tool_a", {"arg": "1"}, "result_1", 100)
        cache.set("tool_a", {"arg": "2"}, "result_2", 100)

        r1 = cache.get("tool_a", {"arg": "1"})
        r2 = cache.get("tool_a", {"arg": "2"})

        assert r1[0] == "result_1"
        assert r2[0] == "result_2"

    def test_cache_stats(self):
        cache = IncrementalContextCache()

        cache.set("tool_a", {"arg": "1"}, "x" * 100, 100)
        cache.get("tool_a", {"arg": "1"})  # hit
        cache.get("tool_a", {"arg": "2"})  # miss

        stats = cache.get_stats()
        assert stats["total_calls"] == 2
        assert stats["cache_hits"] == 1


# ============================================================
# 并行调度测试
# ============================================================

class TestParallel:
    """并行调度测试"""

    def test_dependency_graph(self):
        deps = {
            "a": [],
            "b": [],
            "c": ["a", "b"],
            "d": ["c"],
        }
        dg = DependencyGraph(deps)
        levels = dg.topological_levels(["a", "b", "c", "d"])

        assert len(levels) == 3
        assert set(levels[0]) == {"a", "b"}
        assert set(levels[1]) == {"c"}
        assert set(levels[2]) == {"d"}

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        scheduler = ParallelScheduler(max_concurrency=5)

        async def slow_task(sleep: float = 0.05, **kwargs):
            await asyncio.sleep(sleep)
            return f"done_{sleep}"

        tool_calls = {
            "t1": (slow_task, {"sleep": 0.05}),
            "t2": (slow_task, {"sleep": 0.05}),
            "t3": (slow_task, {"sleep": 0.05}),
        }

        result = await scheduler.execute_parallel(tool_calls)

        assert len(result.results) == 3
        assert len(result.errors) == 0
        assert result.speedup > 1.0  # 并行应该比串行快


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
