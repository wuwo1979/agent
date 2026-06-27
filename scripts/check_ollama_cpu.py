"""检查 Ollama 是否在 CPU 模式下运行"""
import json
import sys
import urllib.request

# 1. Check basic connectivity
try:
    req = urllib.request.Request("http://localhost:11434/api/tags")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
        models = data.get("models", [])
        print(f"Ollama API: OK ({len(models)} models)")
        for m in models:
            print(f"  - {m['name']}")
except Exception as e:
    print(f"Ollama API: FAILED - {e}")
    sys.exit(1)

# 2. Test generation (this will crash if GPU mode is still active)
print("\nTesting generation...")
payload = json.dumps({
    "model": "qwen2.5:7b",
    "prompt": "Say 'OK' in one word",
    "stream": False,
    "options": {"num_predict": 10}
}).encode("utf-8")

try:
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
        if "response" in result:
            print(f"Generation: OK - '{result['response']}'")
            print("Ollama is running in CPU mode (GPU hidden)")
        else:
            print(f"Generation: unexpected response: {json.dumps(result)[:100]}")
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8")
    print(f"Generation: FAILED (HTTP {e.code})")
    print(f"  {body[:200]}")
    if "llama-server" in body or "cuda" in body.lower():
        print("\n=> CUDA issue persists. GPU not hidden.")
        print("=> To fix, run in NEW PowerShell as ADMIN:")
        print("   $env:CUDA_VISIBLE_DEVICES=''")
        print("   ollama serve")
        print("\n   Or kill tray icon first, then:")
        print("   taskkill /f /im ollama.exe")
        print("   $env:CUDA_VISIBLE_DEVICES=''")
        print("   ollama serve")
except Exception as e:
    print(f"Generation: ERROR - {e}")

# 3. Test via MCP Gateway proxy
print("\nTesting MCP Gateway proxy...")
try:
    req = urllib.request.Request("http://localhost:9090/api/v1/health")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
        print(f"Gateway: OK ({data.get('status')})")
except Exception as e:
    print(f"Gateway: FAILED - {e}")

try:
    req = urllib.request.Request("http://localhost:9090/api/v1/ollama/proxy/api/tags")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
        models = data.get("models", [])
        print(f"Proxy API: OK ({len(models)} models via proxy)")
except Exception as e:
    print(f"Proxy API: FAILED - {e}")
