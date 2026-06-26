"""
MCP Gateway 集成示例
====================
展示如何从外部客户端通过 MCP 协议或 REST API 调用网关。

支持三类集成场景:
  1. MCP JSON-RPC 协议 (Trae/Cursor/VS Code Agent)
  2. REST API (Dify HTTP 工具 / 自定义脚本)
  3. Ollama 本地模型

运行前提:
  1. 启动 MCP 网关: python main.py --host 0.0.0.0 --port 9090
  2. 安装依赖: pip install httpx
"""

import json

import httpx

GATEWAY_URL = "http://localhost:9090"
MCP_ENDPOINT = f"{GATEWAY_URL}/mcp"
API_ENDPOINT = f"{GATEWAY_URL}/api/v1"
API_KEY = "mcp-gateway-dev-key-change-in-production"


# ================================================================
# 场景 1: MCP JSON-RPC 协议 (Trae / Cursor Agent)
# ================================================================

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
            MCP_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        return resp.json()


# ================================================================
# 场景 2: REST API (Dify HTTP 工具)
# ================================================================

async def call_api(path: str, method: str = "GET", body: dict = None):
    """调用 REST API (Dify 兼容格式)"""
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }
    url = f"{API_ENDPOINT}{path}"
    async with httpx.AsyncClient() as client:
        if method == "GET":
            resp = await client.get(url, headers=headers, timeout=30)
        else:
            resp = await client.post(url, json=body, headers=headers, timeout=30)
        return resp.json()


# ================================================================
# Demo Runner
# ================================================================

async def demo_mcp_protocol():
    """场景 1: 通过 MCP 协议调用 (Trae/Cursor)"""
    print("\n" + "=" * 60)
    print("  [场景 1] MCP JSON-RPC 协议 — Trae / Cursor Agent")
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

    print("\n  >> filesystem/list_dir (列出项目目录)...")
    result = await call_mcp("tools/call", {
        "name": "list_dir",
        "arguments": {"path": "."},
    })
    content = result["result"]["content"][0]["text"]
    files = json.loads(content)
    print(f"  发现 {len(files)} 个文件/目录")

    print("\n  >> terminal/sysinfo (获取系统信息)...")
    result = await call_mcp("tools/call", {
        "name": "sysinfo",
        "arguments": {},
    })
    info = json.loads(result["result"]["content"][0]["text"])
    print(f"  平台: {info.get('platform', 'unknown')}")
    print(f"  Python: {info.get('python_version', 'unknown')}")

    # Step 4: Summary
    print("\n[4/4] MCP 协议集成验证完成 ✓")


async def demo_dify_rest_api():
    """场景 2: 通过 REST API 调用 (Dify HTTP 工具)"""
    print("\n" + "=" * 60)
    print("  [场景 2] REST API — Dify HTTP 工具")
    print("=" * 60)

    # Dify 配置示例:
    # 在 Dify 工作流中创建「HTTP 请求」节点:
    #   URL: http://<gateway-host>:9090/api/v1/tools/list
    #   方法: POST
    #   请求头:
    #     X-API-Key: mcp-gateway-dev-key-change-in-production
    #   Body: {"platform": "dify"}
    #
    #   工具调用:
    #   URL: http://<gateway-host>:9090/api/v1/tools/call
    #   方法: POST
    #   请求头:
    #     X-API-Key: mcp-gateway-dev-key-change-in-production
    #   Body: {"name": "sysinfo", "arguments": {}}

    print("\n[Dify HTTP 节点配置参考]")
    print('  ┌─────────────────────────────────────────────────────────────┐')
    print('  │ 工具列表:                                                    │')
    print('  │   URL:   POST /api/v1/tools/list                            │')
    print('  │   Body:  {"platform": "dify"}                               │')
    print('  │                                                             │')
    print('  │ 调用工具:                                                    │')
    print('  │   URL:   POST /api/v1/tools/call                            │')
    print('  │   Body:  {"name": "sysinfo", "arguments": {}}               │')
    print('  │                                                             │')
    print('  │ 健康检查:                                                    │')
    print('  │   URL:   GET  /api/v1/health                                │')
    print('  │                                                             │')
    print('  │ 通用请求头: X-API-Key: <your-api-key>                       │')
    print('  └─────────────────────────────────────────────────────────────┘')

    # 实际调用验证
    print("\n[1/3] 健康检查...")
    result = await call_api("/health")
    data = result if isinstance(result, dict) else json.loads(result)
    print(f"  状态: {data.get('status', 'unknown')}")
    print(f"  工具数: {data.get('tools', 0)}")

    print("\n[2/3] 工具列表...")
    result = await call_api("/tools/list", method="POST", body={"platform": "dify"})
    data = result if isinstance(result, dict) else json.loads(result)
    tools = data.get("tools", data.get("result", {}).get("tools", []))
    print(f"  可用工具: {len(tools)}")
    for t in tools[:5]:
        print(f"    - {t.get('name')}: {t.get('description', '')[:50]}...")
    if len(tools) > 5:
        print(f"    ... 还有 {len(tools) - 5} 个")

    print("\n[3/3] 调用系统信息工具...")
    result = await call_api("/tools/call", method="POST", body={
        "name": "sysinfo",
        "arguments": {},
    })
    data = result if isinstance(result, dict) else json.loads(result)
    print(f"  成功: {data.get('success', False)}")
    result_text = data.get("result", "")
    if result_text:
        try:
            info = json.loads(result_text)
            print(f"  平台: {info.get('platform', info.get('system', 'unknown'))}")
        except json.JSONDecodeError:
            print(f"  结果: {result_text[:100]}...")

    print("\n  REST API 集成验证完成 ✓")


async def demo_ollama_integration():
    """场景 3: Ollama 本地模型调用"""
    print("\n" + "=" * 60)
    print("  [场景 3] Ollama 本地大模型集成")
    print("=" * 60)

    # 先检查 Ollama 连通性
    print("\n[1/2] 检查 Ollama 服务...")
    result = await call_api("/tools/call", method="POST", body={
        "name": "llm_ping",
        "arguments": {},
    })
    data = result if isinstance(result, dict) else json.loads(result)
    if data.get("success", False):
        ping = json.loads(data.get("result", "{}"))
        print(f"  状态: {ping.get('status', 'unknown')}")
        print(f"  模型数: {ping.get('models_count', 0)}")
        print(f"  模型列表: {ping.get('models', [])}")
    else:
        print(f"  Ollama 未连接: {data.get('message', data.get('result', 'unknown error'))}")
        print("  请先启动: docker compose -f docker/docker-compose.yml up -d ollama")

    # 列出模型
    print("\n[2/2] 列出可用模型...")
    result = await call_api("/tools/call", method="POST", body={
        "name": "llm_list_models",
        "arguments": {},
    })
    data = result if isinstance(result, dict) else json.loads(result)
    if data.get("success", False):
        models_text = data.get("result", "[]")
        try:
            models = json.loads(models_text)
            for m in models:
                print(f"  - {m.get('name')} ({m.get('parameter_size', '?')}, {m.get('size_gb', 0):.1f}GB)")
        except json.JSONDecodeError:
            print(f"  {models_text[:100]}")
    else:
        print(f"  获取失败: {data.get('message', '')}")

    print("\n  Ollama 集成验证完成 ✓")


async def main():
    """运行所有集成场景"""
    print("=" * 60)
    print("  MCP Gateway 集成验证套件")
    print("  支持: Trae/Cursor (MCP) | Dify (REST) | Ollama (本地推理)")
    print("=" * 60)

    await demo_mcp_protocol()
    await demo_dify_rest_api()
    await demo_ollama_integration()

    print("\n" + "=" * 60)
    print("  全部集成验证完成!")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
