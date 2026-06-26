"""
测试 Ollama 连通性和 MCP Gateway 代理。
用法:
    python scripts/test_ollama_proxy.py               # 测试 Ollama 直连
    python scripts/test_ollama_proxy.py --proxy       # 测试 MCP Gateway 代理
    python scripts/test_ollama_proxy.py --all         # 全面诊断
"""
import argparse
import json
import urllib.error
import urllib.request


def http_get(url: str, timeout: int = 10) -> dict:
    """HTTP GET 请求，返回 json dict。"""
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post(url: str, data: dict, timeout: int = 30) -> dict:
    """HTTP POST 请求，返回 json dict。"""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_ollama_direct():
    """测试直连 Ollama API。"""
    print("=" * 50)
    print("1. 测试 Ollama 直连 (localhost:11434)")
    print("=" * 50)

    # 1.1 root
    try:
        req = urllib.request.Request("http://localhost:11434/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"  [OK] Ollama root: HTTP {resp.status}")
    except Exception as e:
        print(f"  [FAIL] Ollama root: {e}")

    # 1.2 api/tags
    try:
        data = http_get("http://localhost:11434/api/tags")
        models = data.get("models", [])
        if models:
            print(f"  [OK] 模型列表: {len(models)} 个模型")
            for m in models:
                print(f"       - {m['name']} ({m.get('size', '?')})")
        else:
            print(f"  [WARN] 模型列表为空: {data}")
    except Exception as e:
        print(f"  [FAIL] 获取模型列表: {e}")
        return False

    # 1.3 简单生成测试
    print("\n  生成测试 (qwen2.5:7b)...")
    try:
        resp = http_post("http://localhost:11434/api/generate", {
            "model": "qwen2.5:7b",
            "prompt": "Say 'Hello' in one word.",
            "stream": False,
            "options": {"num_predict": 10}
        })
        if "response" in resp:
            print(f"  [OK] 生成响应: {resp['response'][:60]}")
        else:
            print(f"  [WARN] 响应异常: {json.dumps(resp)[:100]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"  [FAIL] 生成失败: HTTP {e.code}")
        print(f"         响应: {body[:200]}")
        if "llama-server" in body.lower() or "cuda" in body.lower():
            print("  [!!] 可能涉及 CUDA 兼容性问题")
        return False
    except Exception as e:
        print(f"  [FAIL] 生成异常: {e}")
        return False

    return True


def test_mcp_gateway_proxy(gateway_port: int = 9090):
    """测试 MCP Gateway 代理。"""
    print("=" * 50)
    print(f"2. 测试 MCP Gateway 代理 (localhost:{gateway_port})")
    print("=" * 50)

    proxy_url = f"http://localhost:{gateway_port}/api/v1/ollama/proxy"

    # 2.1 health
    try:
        data = http_get(f"http://localhost:{gateway_port}/api/v1/health")
        if data.get("status") == "healthy":
            print("  [OK] Gateway 健康检查通过")
        else:
            print(f"  [WARN] Gateway 响应: {data}")
    except Exception as e:
        print(f"  [FAIL] Gateway 未运行: {e}")
        print(f"  请先启动: python main.py --port {gateway_port}")
        return False

    # 2.2 proxy health
    try:
        req = urllib.request.Request(f"{proxy_url}/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"  [OK] Ollama 代理根路径: HTTP {resp.status}")
    except Exception as e:
        print(f"  [FAIL] Ollama 代理根路径: {e}")

    # 2.3 proxy api/tags
    try:
        data = http_get(f"{proxy_url}/api/tags")
        models = data.get("models", [])
        print(f"  [OK] 代理模型列表: {len(models)} 个模型")
        for m in models:
            print(f"       - {m['name']}")
    except Exception as e:
        print(f"  [FAIL] 代理获取模型列表: {e}")
        return False

    # 2.4 proxy generate test
    print("\n  代理生成测试...")
    try:
        resp = http_post(f"{proxy_url}/api/generate", {
            "model": "qwen2.5:7b",
            "prompt": "Say 'Hi' in one word.",
            "stream": False,
            "options": {"num_predict": 10}
        })
        if "response" in resp:
            print(f"  [OK] 代理生成成功: {resp['response'][:60]}")
        else:
            print(f"  [WARN] 响应: {json.dumps(resp)[:100]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"  [FAIL] 代理生成失败: HTTP {e.code}, {body[:200]}")
    except Exception as e:
        print(f"  [FAIL] 代理生成异常: {e}")
        return False

    return True


def test_dify_compatible(gateway_port: int = 9090):
    """Dify 兼容格式测试（模拟 Dify 的模型供应商验证请求）。"""
    print("=" * 50)
    print("3. Dify 兼容性测试")
    print("=" * 50)

    proxy_url = f"http://localhost:{gateway_port}/api/v1/ollama/proxy"

    # Dify 添加 Ollama 时会调用的端点
    endpoints = [
        ("/api/tags", "GET", None),
        ("/api/ps", "GET", None),
        ("/api/show", "POST", {"model": "qwen2.5:7b"}),
    ]

    for path, method, body in endpoints:
        url = f"{proxy_url}{path}"
        try:
            if method == "GET":
                data = http_get(url, timeout=5)
            else:
                data = http_post(url, body or {}, timeout=10)
            print(f"  [OK] {method} {path}: {json.dumps(data)[:100]}")
        except Exception as e:
            print(f"  [FAIL] {method} {path}: {e}")

    # Dify 验证: 列出模型
    print("\n  Dify 模型供应商 -> Ollama 验证:")
    print(f"  Base URL: {proxy_url}")
    print("  模型: qwen2.5:7b")
    print()
    print("  在 Dify 中添加 Ollama 模型供应商:")
    print("    模型类型: LLM")
    print("    模型: qwen2.5:7b")
    print(f"    Base URL: http://host.docker.internal:{gateway_port}/api/v1/ollama/proxy")


def main():
    parser = argparse.ArgumentParser(description="Ollama 连通性测试")
    parser.add_argument("--proxy", action="store_true", help="测试 MCP Gateway 代理")
    parser.add_argument("--all", action="store_true", help="全面诊断")
    parser.add_argument("--port", type=int, default=9090, help="Gateway 端口")
    args = parser.parse_args()

    if args.all or not (args.proxy or args.all):
        test_ollama_direct()
        print()

    if args.proxy or args.all:
        # 先确保 MCP Gateway 已启动
        test_mcp_gateway_proxy(args.port)
        print()
        test_dify_compatible(args.port)


if __name__ == "__main__":
    main()
