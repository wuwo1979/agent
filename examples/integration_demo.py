"""
MCP Gateway 集成示例
====================
展示如何从外部客户端（如 Trae、Cursor、自定义 Agent）通过 MCP 协议调用网关。

运行前提：
  1. 启动 MCP 网关: python main.py --port 9090
  2. 安装依赖: pip install httpx
"""

import json
import httpx
import asyncio

GATEWAY_URL = "http://localhost:9090/mcp"


async def call_mcp(method: str, params: dict = None, request_id: str = "1"):
    """发送 MCP JSON-RPC 请求"""
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GATEWAY_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        return resp.json()


async def demo_integration():
    print("=" * 60)
    print("  MCP Gateway Integration Demo")
    print("  模拟 Trae/Cursor Agent 通过 MCP 协议调用本地工具")
    print("=" * 60)

    # Step 1: Initialize
    print("\n[1/4] 初始化连接 (initialize)...")
    result = await call_mcp("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
    })
    print(f"  服务器: {result['result']['serverInfo']['name']} v{result['result']['serverInfo']['version']}")
    print(f"  协议版本: {result['result']['protocolVersion']}")

    # Step 2: Discover tools
    print("\n[2/4] 发现可用工具 (tools/list)...")
    result = await call_mcp("tools/list")
    tools = result["result"]["tools"]
    print(f"  发现 {len(tools)} 个工具:")
    for t in tools:
        print(f"    - {t['name']}: {t['description'][:60]}...")

    # Step 3: Call tools
    print("\n[3/4] 调用工具 (tools/call)...")

    # 3a: 列出当前目录
    print("\n  >> filesystem/list_dir (列出项目目录)...")
    result = await call_mcp("tools/call", {
        "name": "list_dir",
        "arguments": {"path": "."},
    })
    content = result["result"]["content"][0]["text"]
    files = json.loads(content)
    print(f"  发现 {len(files)} 个文件/目录")

    # 3b: 获取系统信息
    print("\n  >> terminal/sysinfo (获取系统信息)...")
    result = await call_mcp("tools/call", {
        "name": "sysinfo",
        "arguments": {},
    })
    info = json.loads(result["result"]["content"][0]["text"])
    print(f"  平台: {info.get('platform', 'unknown')}")
    print(f"  Python: {info.get('python_version', 'unknown')}")

    # 3c: 数据库查询
    print("\n  >> database/list_tables (列出数据库表)...")
    result = await call_mcp("tools/call", {
        "name": "list_tables",
        "arguments": {},
    })
    print(f"  结果: {result['result']['content'][0]['text'][:100]}")

    # Step 4: Summary
    print("\n[4/4] 集成验证完成")
    print("  所有工具调用均通过标准 MCP JSON-RPC 2.0 协议完成")
    print("  Trae/Cursor 等 AI Agent IDE 可通过相同方式接入")


if __name__ == "__main__":
    asyncio.run(demo_integration())
