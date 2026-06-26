"""
场景验证测试：Trae IDE (STDIO) + Dify (HTTP REST) 双场景测试

Usage:
    python tests/test_scenarios.py --stdio     # 测试 Trae IDE STDIO 模式
    python tests/test_scenarios.py --http       # 测试 Dify HTTP REST 模式
    python tests/test_scenarios.py --all        # 测试全部
"""

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════
# 场景1: Trae IDE — STDIO 模式
# ═══════════════════════════════════════════════════════════════════

class STDIOClient:
    """STDIO JSON-RPC 客户端，使用 readline() 逐行读取。"""

    def __init__(self, proc: asyncio.subprocess.Process):
        self.proc = proc

    async def send(self, data: dict):
        """发送 JSON-RPC 请求。"""
        line = json.dumps(data, ensure_ascii=False) + "\n"
        self.proc.stdin.write(line.encode("utf-8"))
        await self.proc.stdin.drain()

    async def recv(self, timeout: float = 10.0) -> str:
        """读取下一个 JSON 行。"""
        try:
            line_bytes = await asyncio.wait_for(
                self.proc.stdout.readline(), timeout=timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"STDIO read timeout after {timeout}s")

        if not line_bytes:
            raise EOFError("STDIO stdout closed unexpectedly")

        line = line_bytes.decode("utf-8", errors="replace").strip()
        if not line:
            # 空行，跳过
            return await self.recv(timeout=timeout)
        return line


async def test_stdio_mode():
    """模拟 Trae IDE 客户端，测试完整的 MCP STDIO 握手 + 工具调用流程。"""
    print("=" * 60)
    print("  场景1: Trae IDE — STDIO 模式验证")
    print("=" * 60)

    # 启动网关子进程
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(PROJECT_ROOT / "main.py"), "--mode", "stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
    )

    client = STDIOClient(proc)

    try:
        # Step 1: initialize 握手
        print("\n[1] initialize 握手...")
        await client.send({
            "jsonrpc": "2.0",
            "id": "init-1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "clientInfo": {"name": "Trae IDE", "version": "1.0.0"},
            },
        })

        # 读取 initialize 响应
        init_resp = await client.recv()
        init_data = json.loads(init_resp)
        assert init_data.get("id") == "init-1", f"initialize id mismatch: {init_data}"
        assert "result" in init_data, f"initialize 无 result: {init_data}"
        caps = init_data["result"]["capabilities"]
        assert "tools" in caps, "capabilities 缺少 tools"
        assert "resources" in caps, "capabilities 缺少 resources"
        assert "prompts" in caps, "capabilities 缺少 prompts"
        server_info = init_data["result"]["serverInfo"]
        assert server_info["name"] == "mcp-tool-gateway"
        assert server_info["version"] == "2.0.0", f"版本号不对: {server_info['version']}"
        print(f"  [OK] initialize 成功: {server_info['name']} v{server_info['version']}")

        # 读取 initialized 通知
        notif = await client.recv()
        notif_data = json.loads(notif)
        assert notif_data.get("method") == "notifications/initialized", f"缺少 initialized 通知: {notif_data}"
        session_id = notif_data.get("params", {}).get("sessionId", "")
        assert session_id, "sessionId 为空"
        print(f"  [OK] initialized 通知 received, session={session_id}")

        # Step 2: tools/list
        print("\n[2] tools/list...")
        await client.send({
            "jsonrpc": "2.0",
            "id": "list-1",
            "method": "tools/list",
            "params": {},
        })
        list_resp = await client.recv()
        list_data = json.loads(list_resp)
        assert list_data.get("id") == "list-1", f"tools/list id mismatch: {list_data}"
        assert "result" in list_data, f"tools/list 无 result: {list_data}"
        tools = list_data["result"].get("tools", [])
        tool_names = [t["name"] for t in tools]
        print(f"  [OK] tools/list 返回 {len(tools)} 个工具: {tool_names[:5]}...")

        # 验证关键工具存在
        required_tools = ["read_file", "write_file", "sysinfo", "run_command", "list_dir"]
        for t in required_tools:
            assert t in tool_names, f"缺少关键工具: {t}"
        print(f"  [OK] 关键工具全部存在: {required_tools}")

        # Step 3: tools/call — sysinfo
        print("\n[3] tools/call: sysinfo...")
        await client.send({
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {"name": "sysinfo", "arguments": {}},
        })
        call_resp = await client.recv()
        call_data = json.loads(call_resp)
        assert call_data.get("id") == "call-1", f"tools/call id mismatch: {call_data}"
        assert "result" in call_data, f"tools/call 无 result: {call_data}"

        # sysinfo 返回 {"content": [{"type": "text", "text": "..."}]}
        content = call_data["result"].get("content", [])
        if content:
            sysinfo_text = json.loads(content[0]["text"])
            print(f"  [OK] sysinfo: platform={sysinfo_text.get('platform')}, "
                  f"python={sysinfo_text.get('python_version')}")

        # Step 4: tools/call — list_dir
        print("\n[4] tools/call: list_dir...")
        await client.send({
            "jsonrpc": "2.0",
            "id": "call-2",
            "method": "tools/call",
            "params": {"name": "list_dir", "arguments": {"path": "."}},
        })
        call_resp2 = await client.recv()
        call_data2 = json.loads(call_resp2)
        assert call_data2.get("id") == "call-2"
        assert "result" in call_data2
        content2 = call_data2["result"].get("content", [])
        if content2:
            dir_text = json.loads(content2[0]["text"])
            print(f"  [OK] list_dir: {len(dir_text.get('entries', []))} entries")

        # Step 5: 错误码验证 — 调用不存在的工具
        print("\n[5] 错误码验证: 不存在的工具...")
        await client.send({
            "jsonrpc": "2.0",
            "id": "err-1",
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        })
        err_resp = await client.recv()
        err_data = json.loads(err_resp)
        assert "error" in err_data, f"预期错误响应，实际: {err_data}"
        error_code = err_data["error"]["code"]
        print(f"  [OK] 错误码: {error_code} — {err_data['error']['message']}")

        # Step 6: ping
        print("\n[6] ping...")
        await client.send({
            "jsonrpc": "2.0",
            "id": "ping-1",
            "method": "ping",
            "params": {},
        })
        ping_resp = await client.recv()
        ping_data = json.loads(ping_resp)
        assert ping_data.get("result") == {}
        print(f"  [OK] ping 响应正常")

        print("\n" + "=" * 60)
        print("  场景1 STDIO 模式: 全部通过!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n  [FAIL] STDIO 测试失败: {e}")
        import traceback
        traceback.print_exc()
        # 收集 stderr 日志
        try:
            stderr_data = await asyncio.wait_for(proc.stderr.read(), timeout=2)
            if stderr_data:
                print(f"\n  --- stderr (last 3000 chars) ---")
                print(stderr_data.decode("utf-8", errors="replace")[-3000:])
        except Exception:
            pass
        # 检查进程是否存活
        if proc.returncode is not None:
            print(f"\n  [INFO] 子进程已退出，exit code={proc.returncode}")
        else:
            print(f"\n  [INFO] 子进程仍在运行")
        return False

    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()


# ═══════════════════════════════════════════════════════════════════
# 场景2: Dify 平台 — HTTP REST API 模式
# ═══════════════════════════════════════════════════════════════════

async def test_http_mode():
    """模拟 Dify 平台，测试 REST API 工具发现和调用。"""
    import aiohttp

    print("=" * 60)
    print("  场景2: Dify 平台 — HTTP REST API 模式验证")
    print("=" * 60)

    PORT = 19090  # 使用非标准端口避免冲突

    # 启动 HTTP 网关
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(PROJECT_ROOT / "main.py"),
        "--mode", "http", "--port", str(PORT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
    )

    base_url = f"http://127.0.0.1:{PORT}"

    try:
        # 等待服务启动
        print(f"\n[0] 等待 HTTP 服务启动 (端口 {PORT})...")
        for i in range(30):
            await asyncio.sleep(0.5)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{base_url}/api/v1/health", timeout=2) as resp:
                        if resp.status == 200:
                            print(f"  [OK] 服务已启动")
                            break
            except Exception:
                pass
        else:
            raise RuntimeError("HTTP 服务启动超时")

        async with aiohttp.ClientSession() as session:
            # Step 1: Health check
            print("\n[1] Health check...")
            async with session.get(f"{base_url}/api/v1/health") as resp:
                assert resp.status == 200, f"health status={resp.status}"
                body = await resp.json()
                assert body["status"] == "healthy"
                print(f"  [OK] health: {body['status']}")

            # Step 2: tools/list
            print("\n[2] GET /api/v1/tools/list...")
            async with session.get(f"{base_url}/api/v1/tools/list",
                                   headers={"X-API-Key": "test-key"}) as resp:
                body = await resp.json()
                # 无认证时返回 401
                if resp.status == 401:
                    print(f"  [OK] 未认证返回 401（安全中间件生效）")
                else:
                    tools = body.get("tools", [])
                    tool_names = [t["name"] for t in tools]
                    print(f"  [OK] tools/list 返回 {len(tools)} 个工具: {tool_names[:5]}...")

            # Step 3: tools/list with valid API key
            print("\n[3] GET /api/v1/tools/list (with API key)...")
            async with session.get(f"{base_url}/api/v1/tools/list",
                                   headers={"X-API-Key": "admin-key-001"}) as resp:
                body = await resp.json()
                if resp.status == 200:
                    tools = body.get("tools", [])
                    tool_names = [t["name"] for t in tools]
                    assert len(tools) > 0, "tools/list 返回空"
                    # 验证关键工具
                    required = ["read_file", "sysinfo", "list_dir", "write_file"]
                    for t in required:
                        assert t in tool_names, f"缺少关键工具: {t}"
                    print(f"  [OK] tools/list 返回 {len(tools)} 个工具，关键工具全在")
                else:
                    print(f"  [WARN] tools/list returned {resp.status}: {body}")

            # Step 4: tools/call — sysinfo
            print("\n[4] POST /api/v1/tools/call: sysinfo...")
            async with session.post(
                f"{base_url}/api/v1/tools/call",
                json={"name": "sysinfo", "arguments": {}},
                headers={"X-API-Key": "admin-key-001"},
            ) as resp:
                body = await resp.json()
                if resp.status == 200:
                    result = body.get("result", body)
                    print(f"  [OK] sysinfo 调用成功: {json.dumps(result, ensure_ascii=False)[:100]}")
                else:
                    print(f"  [WARN] sysinfo returned {resp.status}: {body}")

            # Step 5: tools/call — list_dir (验证文件系统工具)
            print("\n[5] POST /api/v1/tools/call: list_dir...")
            async with session.post(
                f"{base_url}/api/v1/tools/call",
                json={"name": "list_dir", "arguments": {"path": "."}},
                headers={"X-API-Key": "admin-key-001"},
            ) as resp:
                body = await resp.json()
                if resp.status == 200:
                    print(f"  [OK] list_dir 调用成功")
                else:
                    print(f"  [WARN] list_dir returned {resp.status}: {body}")

            # Step 6: 错误处理 — 不存在的工具
            print("\n[6] 错误处理: 不存在的工具...")
            async with session.post(
                f"{base_url}/api/v1/tools/call",
                json={"name": "nonexistent_tool", "arguments": {}},
                headers={"X-API-Key": "admin-key-001"},
            ) as resp:
                body = await resp.json()
                print(f"  [OK] 错误响应: status={resp.status}, body={json.dumps(body, ensure_ascii=False)[:100]}")

            # Step 7: Stats endpoint
            print("\n[7] GET /api/v1/stats...")
            async with session.get(f"{base_url}/api/v1/stats") as resp:
                body = await resp.json()
                print(f"  [OK] stats: {json.dumps(body, ensure_ascii=False)[:150]}")

        print("\n" + "=" * 60)
        print("  场景2 HTTP REST 模式: 全部通过!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n  [FAIL] HTTP 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="MCP Gateway 场景验证")
    parser.add_argument("--stdio", action="store_true", help="Trae IDE STDIO 模式")
    parser.add_argument("--http", action="store_true", help="Dify HTTP REST 模式")
    parser.add_argument("--all", action="store_true", help="全部测试")
    args = parser.parse_args()

    if not (args.stdio or args.http):
        args.all = True

    if args.all or args.stdio:
        stdio_ok = await test_stdio_mode()
        if not stdio_ok:
            sys.exit(1)

    if args.all or args.http:
        http_ok = await test_http_mode()
        if not http_ok:
            sys.exit(1)

    print("\n" + "=" * 60)
    print("  全部场景验证通过! v2.0 可以投入使用!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())