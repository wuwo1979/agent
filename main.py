"""
MCP Gateway + Multi-Agent Scheduling System
Lightweight local MCP gateway and multi-agent scheduling system.

Usage:
    python main.py                        # Start HTTP gateway
    python main.py --mode stdio          # STDIO mode
    python main.py --benchmark           # Run benchmarks
    python main.py --demo                # Run demo
"""

import asyncio
import argparse
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def run_demo():
    """
    Run full demo showing MCP gateway + Agent scheduling capabilities.
    """
    from mcp_gateway.protocol import ToolRegistry
    from mcp_gateway.tools.filesystem import FilesystemToolProvider
    from mcp_gateway.tools.terminal import TerminalToolProvider
    from mcp_gateway.tools.database import DatabaseToolProvider
    from agent_scheduler.graph import create_agent_graph
    from performance.cache import IncrementalContextCache

    print("=" * 60)
    print("  MCP Gateway + Multi-Agent System - Demo")
    print("=" * 60)

    # 1. Register tool providers
    print("\n[1] Registering MCP tool providers...")
    registry = ToolRegistry()

    providers = [
        FilesystemToolProvider(),
        TerminalToolProvider(),
        DatabaseToolProvider(),
    ]
    for provider in providers:
        registry.register_provider(provider)

    total_tools = sum(len(p.list_tools()) for p in providers)
    print(f"    Registered {len(providers)} providers with {total_tools} tools")

    # 2. List tools
    print("\n[2] Available tools:")
    for tool in registry.list_tools():
        print(f"    - {tool['name']}: {tool['description'][:60]}")

    # 3. Test tool call
    print("\n[3] Testing tool call...")
    try:
        result = await registry.call_tool("sysinfo", {})
        if not result.is_error:
            sysinfo = json.loads(result.content[0]["text"])
            print(f"    Platform: {sysinfo.get('platform')} {sysinfo.get('release')}")
            print(f"    Python: {sysinfo.get('python_version')}")
            print(f"    Time: {result.execution_time_ms:.1f}ms")
    except Exception as e:
        print(f"    Tool call failed: {e}")

    # 4. Agent workflow
    print("\n[4] Running Agent workflow...")
    cache = IncrementalContextCache()
    agent = create_agent_graph(registry, use_simple_agents=True)

    task = "Get system info and list current directory files"
    result = await agent.run(user_input=task, task_id="demo_001")

    print(f"    Task: {task}")
    print(f"    Status: {result.task_status.value}")
    print(f"    Subtasks: {len(result.plan)}")
    for t in result.plan:
        status_icon = "[OK]" if t.status.value == "completed" else "[FAIL]"
        print(f"      {status_icon} [{t.id}] {t.description} ({t.tool_name})")

    print(f"    Successful calls: {result.successful_tool_calls}")
    print(f"    Failed calls: {result.failed_tool_calls}")

    # 5. Cache stats
    print("\n[5] Cache stats:")
    stats = cache.get_stats()
    print(f"    Hit rate: {stats['hit_rate']}")

    print("\n" + "=" * 60)
    print("  Demo complete!")
    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(
        description="MCP Gateway + Multi-Agent Scheduling System"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=9090, help="Bind port")
    parser.add_argument("--mode", choices=["http", "stdio"], default="http",
                        help="Transport mode")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmarks")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--test", action="store_true", help="Run tests")

    args = parser.parse_args()

    if args.benchmark:
        from tests.benchmark import main as bench_main
        await bench_main()
    elif args.demo:
        await run_demo()
    elif args.test:
        import pytest
        test_dir = os.path.join(os.path.dirname(__file__), "tests")
        pytest.main([test_dir, "-v"])
    else:
        from mcp_gateway.server import MCPServer
        server = MCPServer()
        await server.start(host=args.host, port=args.port, mode=args.mode)


if __name__ == "__main__":
    asyncio.run(main())
