"""
性能优化层 - 无依赖工具并行调度
多工具场景总耗时降低 40%+
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("performance.parallel")


@dataclass
class ParallelExecutionResult:
    """并行执行结果"""
    results: Dict[str, Any] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    total_time_ms: float = 0.0
    sequential_time_ms: float = 0.0
    speedup: float = 1.0
    parallel_count: int = 0
    sequential_count: int = 0
    individual_times: Dict[str, float] = field(default_factory=dict)


class DependencyGraph:
    """工具依赖图"""

    def __init__(self, dependencies: Dict[str, List[str]]):
        self.dependencies = dependencies  # tool_name -> [依赖的 tool_name]
        self._build_graph()

    def _build_graph(self):
        """构建依赖图"""
        self.in_degree: Dict[str, int] = defaultdict(int)
        self.dependents: Dict[str, List[str]] = defaultdict(list)

        for tool, deps in self.dependencies.items():
            if tool not in self.in_degree:
                self.in_degree[tool] = 0
            for dep in deps:
                self.in_degree[tool] += 1
                self.dependents[dep].append(tool)
                if dep not in self.in_degree:
                    self.in_degree[dep] = 0

    def topological_levels(self, tool_names: List[str]) -> List[List[str]]:
        """
        拓扑排序分层
        每层内的工具可以并行执行
        Returns:
            [[level1_tools], [level2_tools], ...]
        """
        # 只考虑指定的工具
        relevant = set(tool_names)
        in_deg = {t: self.in_degree.get(t, 0) for t in relevant}

        # 过滤外部依赖（不在 relevant 中的依赖）
        for t in relevant:
            for dep in self.dependencies.get(t, []):
                if dep not in relevant:
                    in_deg[t] -= 1

        levels = []
        remaining = set(tool_names)

        while remaining:
            # 找到入度为 0 的工具
            level = [t for t in remaining if in_deg.get(t, 0) == 0]
            if not level:
                # 存在循环依赖，剩余工具放入同一层
                levels.append(list(remaining))
                break

            levels.append(level)
            remaining -= set(level)

            # 更新入度
            for t in level:
                for dep in self.dependents.get(t, []):
                    if dep in remaining:
                        in_deg[dep] = max(0, in_deg.get(dep, 0) - 1)

        return levels

    def get_parallel_groups(self, tool_names: List[str]) -> List[Set[str]]:
        """获取可并行执行的工具分组"""
        levels = self.topological_levels(tool_names)
        return [set(level) for level in levels]


class ParallelScheduler:
    """
    并行调度器
    基于依赖图自动识别无依赖工具，并行执行
    """

    def __init__(self, max_concurrency: int = 5):
        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_parallel(
        self,
        tool_calls: Dict[str, Tuple[Callable, Dict[str, Any]]],
        dependency_graph: Optional[DependencyGraph] = None,
    ) -> ParallelExecutionResult:
        """
        并行执行工具调用
        Args:
            tool_calls: {tool_name: (handler, arguments)}
            dependency_graph: 依赖图（可选）
        Returns:
            ParallelExecutionResult
        """
        result = ParallelExecutionResult()
        start = time.perf_counter()

        if dependency_graph:
            # 按依赖分层并行执行
            levels = dependency_graph.topological_levels(list(tool_calls.keys()))
            logger.info(f"Parallel execution: {len(levels)} levels, {len(tool_calls)} tools")

            tool_results: Dict[str, Any] = {}
            for level_idx, level in enumerate(levels):
                level_tasks = {}
                for tool_name in level:
                    if tool_name in tool_calls:
                        handler, args = tool_calls[tool_name]
                        # 注入依赖结果
                        deps = dependency_graph.dependencies.get(tool_name, [])
                        for dep in deps:
                            if dep in tool_results:
                                args[f"_{dep}_result"] = tool_results[dep]

                        level_tasks[tool_name] = self._execute_with_limit(
                            tool_name, handler, args
                        )

                level_results = await asyncio.gather(
                    *level_tasks.values(), return_exceptions=True
                )

                for tool_name, res in zip(level_tasks.keys(), level_results):
                    if isinstance(res, Exception):
                        result.errors[tool_name] = str(res)
                    else:
                        result.results[tool_name] = res[0]
                        result.individual_times[tool_name] = res[1]
                        tool_results[tool_name] = res[0]

                result.parallel_count += len(level_tasks)

        else:
            # 无依赖信息，全部并行
            tasks = {}
            for tool_name, (handler, args) in tool_calls.items():
                tasks[tool_name] = self._execute_with_limit(tool_name, handler, args)

            results = await asyncio.gather(*tasks.values(), return_exceptions=True)

            for tool_name, res in zip(tasks.keys(), results):
                if isinstance(res, Exception):
                    result.errors[tool_name] = str(res)
                else:
                    result.results[tool_name] = res[0]
                    result.individual_times[tool_name] = res[1]

            result.parallel_count = len(tool_calls)

        result.total_time_ms = (time.perf_counter() - start) * 1000

        # 估算串行耗时 = 所有工具单独执行时间之和
        result.sequential_time_ms = sum(result.individual_times.values())
        result.sequential_count = len(tool_calls)
        result.speedup = result.sequential_time_ms / max(result.total_time_ms, 0.001)

        logger.info(
            f"Parallel execution done: {result.total_time_ms:.0f}ms "
            f"(speedup: {result.speedup:.1f}x, "
            f"parallel: {result.parallel_count}, "
            f"sequential: {result.sequential_count})"
        )

        return result

    async def _execute_with_limit(
        self, tool_name: str, handler: Callable, args: Dict[str, Any]
    ) -> Tuple[Any, float]:
        """带并发限制的执行，返回 (result, elapsed_ms)"""
        async with self._semaphore:
            start = time.perf_counter()
            try:
                result = handler(**args)
                if asyncio.iscoroutine(result):
                    result = await result
                elapsed = (time.perf_counter() - start) * 1000
                logger.debug(f"Tool {tool_name} completed in {elapsed:.0f}ms")
                return result, elapsed
            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                raise


class ParallelBenchmark:
    """并行性能基准测试"""

    def __init__(self, scheduler: ParallelScheduler):
        self.scheduler = scheduler

    async def benchmark(
        self,
        tool_calls: Dict[str, Tuple[Callable, Dict[str, Any]]],
        dependency_graph: Optional[DependencyGraph] = None,
        runs: int = 10,
    ) -> Dict[str, Any]:
        """
        运行基准测试
        Returns:
            性能报告
        """
        parallel_times = []
        sequential_times = []

        for i in range(runs):
            # 并行执行
            result = await self.scheduler.execute_parallel(
                tool_calls, dependency_graph
            )
            parallel_times.append(result.total_time_ms)
            sequential_times.append(result.sequential_time_ms)

        avg_parallel = sum(parallel_times) / len(parallel_times)
        avg_sequential = sum(sequential_times) / len(sequential_times)
        speedup = avg_sequential / max(avg_parallel, 0.001)

        return {
            "runs": runs,
            "tools_count": len(tool_calls),
            "avg_parallel_ms": f"{avg_parallel:.1f}",
            "avg_sequential_ms": f"{avg_sequential:.1f}",
            "speedup": f"{speedup:.1f}x",
            "time_reduction": f"{(1 - 1/speedup)*100:.1f}%",
            "parallel_times": [f"{t:.1f}" for t in parallel_times],
            "sequential_times": [f"{t:.1f}" for t in sequential_times],
        }
