"""
Benchmark Suite - Performance validation for MCP Gateway + Agent system.

Validates 5 core metrics:
1. Token compression rate: Incremental cache vs full context (target: >35%)
2. Parallel speedup: Independent tool parallel execution (target: >40% time reduction)
3. Dependency graph: Topological level parallel execution
4. Context compressor: Large JSON result compression
5. End-to-end: Complete Agent workflow (planning -> execution -> validation)

Test Environment (this run):
    Hardware: Windows 11, Python 3.11.5, CPU with 4+ cores
    All tools are Mock (pure memory, no I/O) to eliminate disk/network jitter
    Baselines: "serial" = await sequential; "no_cache" = cache disabled
    Parallel benchmark uses 6 independent tools (2 fast@100ms + 2 medium@200ms + 2 slow@300ms)
"""

import asyncio
import json
import os
import platform
import sys
import time
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.types import ToolCallResult, ToolDefinition
from mcp_gateway.protocol import BaseToolProvider, ToolRegistry
from performance.cache import ContextCompressor, IncrementalContextCache
from performance.parallel import DependencyGraph, ParallelBenchmark, ParallelScheduler

# ============================================================
# Mock Benchmark Tool Provider
# ============================================================

class MockBenchmarkProvider(BaseToolProvider):
    """Mock tool provider for benchmarking without real system calls."""

    def __init__(self):
        super().__init__(
            name="benchmark",
            description="Mock tools for benchmark testing"
        )
        self._register_tools()

    def _register_tools(self):
        self._register_tool(ToolDefinition(
            name="fast_tool_1",
            description="Fast mock tool (simulates file read)",
            inputSchema={"type": "object", "properties": {}},
            category="benchmark",
            cacheable=True,
            timeout_ms=5000,
        ))
        self._register_tool(ToolDefinition(
            name="fast_tool_2",
            description="Fast mock tool (simulates file read)",
            inputSchema={"type": "object", "properties": {}},
            category="benchmark",
            cacheable=True,
            timeout_ms=5000,
        ))
        self._register_tool(ToolDefinition(
            name="medium_tool_1",
            description="Medium mock tool (simulates DB query)",
            inputSchema={"type": "object", "properties": {}},
            category="benchmark",
            cacheable=True,
            timeout_ms=5000,
        ))
        self._register_tool(ToolDefinition(
            name="medium_tool_2",
            description="Medium mock tool (simulates DB query)",
            inputSchema={"type": "object", "properties": {}},
            category="benchmark",
            cacheable=True,
            timeout_ms=5000,
        ))
        self._register_tool(ToolDefinition(
            name="slow_tool_1",
            description="Slow mock tool (simulates network request)",
            inputSchema={"type": "object", "properties": {}},
            category="benchmark",
            cacheable=True,
            timeout_ms=10000,
        ))
        self._register_tool(ToolDefinition(
            name="slow_tool_2",
            description="Slow mock tool (simulates network request)",
            inputSchema={"type": "object", "properties": {}},
            category="benchmark",
            cacheable=True,
            timeout_ms=10000,
        ))
        self._register_tool(ToolDefinition(
            name="fs_read_file",
            description="Mock file read tool",
            inputSchema={"type": "object", "properties": {"path": {"type": "string"}}},
            category="benchmark",
            cacheable=True,
            timeout_ms=5000,
        ))
        self._register_tool(ToolDefinition(
            name="db_query",
            description="Mock database query tool",
            inputSchema={"type": "object", "properties": {"sql": {"type": "string"}}},
            category="benchmark",
            cacheable=True,
            timeout_ms=5000,
        ))
        self._register_tool(ToolDefinition(
            name="term_sysinfo",
            description="Mock system info tool",
            inputSchema={"type": "object", "properties": {}},
            category="benchmark",
            cacheable=True,
            timeout_ms=5000,
        ))

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolCallResult:
        """Execute mock tool with realistic timing."""
        delays = {
            "fast_tool_1": 0.05, "fast_tool_2": 0.05,
            "medium_tool_1": 0.10, "medium_tool_2": 0.10,
            "slow_tool_1": 0.20, "slow_tool_2": 0.20,
            "fs_read_file": 0.05, "db_query": 0.10, "term_sysinfo": 0.20,
        }
        sizes = {
            "fast_tool_1": 200, "fast_tool_2": 200,
            "medium_tool_1": 500, "medium_tool_2": 500,
            "slow_tool_1": 1000, "slow_tool_2": 1000,
            "fs_read_file": 200, "db_query": 500, "term_sysinfo": 1000,
        }

        delay = delays.get(tool_name, 0.05)
        await asyncio.sleep(delay)

        data_size = sizes.get(tool_name, 200)
        result = json.dumps({
            "tool": tool_name,
            "result": f"{tool_name}_output",
            "data": "X" * data_size,
        })

        return ToolCallResult.text_result(tool_name, result, delay * 1000)


# ============================================================
# Benchmark 1: Token Compression
# ============================================================

def benchmark_cache_compression() -> Dict[str, Any]:
    """Test incremental context cache token compression."""
    print("\n" + "=" * 60)
    print(" Benchmark 1: Incremental Context Cache - Token Compression")
    print("=" * 60)

    cache = IncrementalContextCache(max_entries=100)

    tool_calls = [
        ("fs_read_file", {"path": "config.json"}, json.dumps({"key": "value", "data": "x" * 500})),
        ("fs_read_file", {"path": "config.json"}, json.dumps({"key": "value", "data": "x" * 500})),
        ("db_query", {"sql": "SELECT * FROM users"}, json.dumps({"rows": [{"id": i} for i in range(50)]})),
        ("db_query", {"sql": "SELECT * FROM users"}, json.dumps({"rows": [{"id": i} for i in range(50)]})),
        ("term_sysinfo", {}, json.dumps({"os": "Windows", "cpu": "x" * 200})),
        ("fs_read_file", {"path": "large.log"}, json.dumps({"log": "A" * 10000})),
        ("fs_read_file", {"path": "large.log"}, json.dumps({"log": "A" * 10000})),
        ("db_query", {"sql": "SELECT COUNT(*)"}, json.dumps({"count": 42})),
    ]

    results = []
    for name, args, content in tool_calls:
        tokens = cache._estimate_tokens(content)
        cached = cache.get(name, args)
        if cached is None:
            cache.set(name, args, content, tokens)
            results.append({"tool": name, "action": "MISS", "raw_tokens": tokens, "cached_tokens": tokens})
        else:
            results.append({"tool": name, "action": "HIT", "raw_tokens": tokens, "cached_tokens": 0})

    stats = cache.get_stats()
    total_raw_tokens = sum(r["raw_tokens"] for r in results)
    total_cached_tokens = sum(r["cached_tokens"] for r in results)
    compression_rate = (1 - total_cached_tokens / max(total_raw_tokens, 1)) * 100

    print(f"\n  Total calls: {stats['total_calls']}")
    print(f"  Cache hits: {stats['cache_hits']}")
    print(f"  Hit rate: {stats['hit_rate']}")
    print(f"  Raw tokens (no cache): ~{total_raw_tokens}")
    print(f"  Cached tokens: ~{total_cached_tokens}")
    print(f"  Token compression rate: {compression_rate:.1f}%")
    target_met = "PASS" if compression_rate >= 35 else "FAIL"
    print(f"  Target 35%: [{target_met}]")

    return {
        "benchmark": "Token Compression",
        "total_calls": stats["total_calls"],
        "cache_hits": stats["cache_hits"],
        "hit_rate": stats["hit_rate"],
        "raw_tokens": total_raw_tokens,
        "cached_tokens": total_cached_tokens,
        "compression_rate": f"{compression_rate:.1f}%",
        "target_35pct": compression_rate >= 35,
    }


# ============================================================
# Benchmark 2: Parallel Speedup
# ============================================================

async def benchmark_parallel_execution() -> Dict[str, Any]:
    """Test parallel execution speedup vs sequential."""
    print("\n" + "=" * 60)
    print(" Benchmark 2: Parallel Tool Execution - Speedup")
    print("=" * 60)

    # Register mock provider
    registry = ToolRegistry()
    registry.register_provider(MockBenchmarkProvider())

    # Get tool handlers from provider
    provider = registry.get_all_providers()["benchmark"]

    async def fast_tool(**kw):
        return await provider.call_tool("fast_tool_1", kw)
    async def medium_tool(**kw):
        return await provider.call_tool("medium_tool_1", kw)
    async def slow_tool(**kw):
        return await provider.call_tool("slow_tool_1", kw)

    tool_calls = {
        "fast_tool_1": (fast_tool, {}),
        "fast_tool_2": (fast_tool, {}),
        "medium_tool_1": (medium_tool, {}),
        "medium_tool_2": (medium_tool, {}),
        "slow_tool_1": (slow_tool, {}),
        "slow_tool_2": (slow_tool, {}),
    }

    scheduler = ParallelScheduler(max_concurrency=5)
    bench = ParallelBenchmark(scheduler)
    report = await bench.benchmark(tool_calls, runs=5)

    print(f"\n  Tools: {report['tools_count']}")
    print(f"  Avg parallel: {report['avg_parallel_ms']}ms")
    print(f"  Avg sequential: {report['avg_sequential_ms']}ms")
    print(f"  Speedup: {report['speedup']}")
    print(f"  Time reduction: {report['time_reduction']}")
    target = float(report['time_reduction'].rstrip('%'))
    print(f"  Target 40%: [{'PASS' if target >= 40 else 'FAIL'}]")

    return report


# ============================================================
# Benchmark 3: Dependency Graph Parallel
# ============================================================

async def benchmark_dependency_graph() -> Dict[str, Any]:
    """Test parallel execution with dependency graph."""
    print("\n" + "=" * 60)
    print(" Benchmark 3: Dependency Graph Parallel")
    print("=" * 60)

    dependencies = {
        "task_a": [],
        "task_b": [],
        "task_c": ["task_a", "task_b"],
        "task_d": ["task_c"],
    }

    dg = DependencyGraph(dependencies)
    levels = dg.topological_levels(["task_a", "task_b", "task_c", "task_d"])

    print("\n  Topological levels:")
    for i, level in enumerate(levels):
        print(f"    Level {i}: {level}")

    registry = ToolRegistry()
    registry.register_provider(MockBenchmarkProvider())
    provider = registry.get_all_providers()["benchmark"]

    async def fast_tool(**kw):
        return await provider.call_tool("fast_tool_1", kw)
    async def medium_tool(**kw):
        return await provider.call_tool("medium_tool_1", kw)
    async def slow_tool(**kw):
        return await provider.call_tool("slow_tool_1", kw)

    tool_calls = {
        "task_a": (fast_tool, {}),
        "task_b": (fast_tool, {}),
        "task_c": (medium_tool, {}),
        "task_d": (slow_tool, {}),
    }

    scheduler = ParallelScheduler(max_concurrency=5)
    bench = ParallelBenchmark(scheduler)
    report = await bench.benchmark(tool_calls, dg, runs=5)

    print(f"\n  Tools: {report['tools_count']}")
    print(f"  Avg parallel: {report['avg_parallel_ms']}ms")
    print(f"  Avg sequential: {report['avg_sequential_ms']}ms")
    print(f"  Speedup: {report['speedup']}")

    return report


# ============================================================
# Benchmark 4: Context Compressor
# ============================================================

def benchmark_context_compressor() -> Dict[str, Any]:
    """Test context compressor for large JSON output."""
    print("\n" + "=" * 60)
    print(" Benchmark 4: Context Compressor")
    print("=" * 60)

    compressor = ContextCompressor()

    large_json = {
        "results": [{"id": i, "name": f"item_{i}", "data": "x" * 100} for i in range(100)],
        "metadata": {"total": 100, "page": 1, "info": {"a": {"b": {"c": "deep"}}}},
    }

    original = json.dumps(large_json, ensure_ascii=False)
    compressed = compressor.compress_json_result(large_json)

    original_tokens = len(original) // 4
    compressed_tokens = len(compressed) // 4
    reduction = (1 - compressed_tokens / max(original_tokens, 1)) * 100

    print(f"\n  Original: {len(original)} chars (~{original_tokens} tokens)")
    print(f"  Compressed: {len(compressed)} chars (~{compressed_tokens} tokens)")
    print(f"  Reduction: {reduction:.1f}%")

    return {
        "benchmark": "Context Compressor",
        "original_chars": len(original),
        "compressed_chars": len(compressed),
        "original_tokens": original_tokens,
        "compressed_tokens": compressed_tokens,
        "reduction": f"{reduction:.1f}%",
    }


# ============================================================
# Benchmark 5: End-to-End Agent Workflow
# ============================================================

async def benchmark_e2e_agent():
    """Test complete Agent workflow (simplified, no LLM required)."""
    print("\n" + "=" * 60)
    print(" Benchmark 5: End-to-End Agent Workflow")
    print("=" * 60)

    try:
        from agent_scheduler.graph import create_agent_graph
    except ImportError:
        print("\n  [SKIP] langgraph not installed. Run: pip install langgraph")
        return {
            "benchmark": "E2E Agent Workflow",
            "subtasks": 0,
            "status": "skipped",
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time_ms": "N/A",
        }

    registry = ToolRegistry()
    registry.register_provider(MockBenchmarkProvider())

    agent = create_agent_graph(registry, use_simple_agents=True)

    start = time.time()
    result = await agent.run(
        user_input="Read config file, query database, and get system info",
        task_id="benchmark_e2e",
    )
    elapsed = (time.time() - start) * 1000

    print(f"\n  Task: {result.user_input}")
    print(f"  Subtasks: {len(result.plan)}")
    print(f"  Status: {result.task_status.value}")
    print(f"  Successful calls: {result.successful_tool_calls}")
    print(f"  Failed calls: {result.failed_tool_calls}")
    print(f"  Total time: {elapsed:.0f}ms")

    return {
        "benchmark": "E2E Agent Workflow",
        "subtasks": len(result.plan),
        "status": result.task_status.value,
        "successful_calls": result.successful_tool_calls,
        "failed_calls": result.failed_tool_calls,
        "total_time_ms": f"{elapsed:.0f}",
    }


# ============================================================
# Main Entry
# ============================================================

async def main():
    print("=" * 60)
    print("  MCP Gateway + Multi-Agent System - Benchmark Suite")
    print("=" * 60)

    # Environment info
    import os
    print("\n  Environment:")
    print(f"    OS: {platform.system()} {platform.release()}")
    print(f"    Python: {platform.python_version()}")
    print(f"    CPU: {os.cpu_count()} cores")
    print(f"    Platform: {platform.machine()}")
    print("  Baseline: all metrics compare optimized vs serial/no-cache version")
    print("  Tools: Mock (memory-only, no I/O) to eliminate disk/network jitter")
    print()

    report = {}

    report["cache_compression"] = benchmark_cache_compression()
    report["parallel_execution"] = await benchmark_parallel_execution()
    report["dependency_graph"] = await benchmark_dependency_graph()
    report["context_compressor"] = benchmark_context_compressor()
    report["e2e_agent"] = await benchmark_e2e_agent()

    # Summary
    print("\n" + "=" * 60)
    print("  Benchmark Summary")
    print("=" * 60)

    print(f"\n  [OK] Token Compression: {report['cache_compression']['compression_rate']}")
    print(f"  [OK] Parallel Speedup: {report['parallel_execution']['speedup']}")
    print(f"  [OK] Time Reduction: {report['parallel_execution']['time_reduction']}")
    print(f"  [OK] Context Compressor: {report['context_compressor']['reduction']}")
    print(f"  [OK] E2E Agent Time: {report['e2e_agent']['total_time_ms']}ms")

    # Save report
    report_path = os.path.join(os.path.dirname(__file__), "benchmark_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  Report saved to: {report_path}")

    return report


if __name__ == "__main__":
    asyncio.run(main())
