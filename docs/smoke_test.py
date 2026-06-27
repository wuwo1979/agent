"""
全场景冒烟测试 + 面试素材采集
验证三个核心场景，保存所有输出用于截图/文档
"""
import http.client
import json
import sys
import urllib.request

BASE = "http://localhost:9090"
ADMIN_KEY = "admin-key-001"
results = []

def log(label, data):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    results.append({"label": label, "data": data})

def api_get(path):
    r = urllib.request.urlopen(f"{BASE}{path}")
    return json.loads(r.read())

def api_post(path, body, headers=None):
    conn = http.client.HTTPConnection("localhost", 9090, timeout=30)
    default_headers = {"Content-Type": "application/json", "X-API-Key": ADMIN_KEY}
    if headers:
        default_headers.update(headers)
    conn.request("POST", path, json.dumps(body), default_headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    print(f"  [DEBUG] HTTP {resp.status} {resp.reason}, body length={len(raw)}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw[:500]}

# ========== 场景1: 健康检查 + 仪表盘 ==========
print("\n" + "█"*60)
print("  场景 1: 系统状态验证")
print("█"*60)

h = api_get("/api/v1/health")
log("GET /api/v1/health — 网关健康检查", h)

s = api_get("/api/v1/stats")
log("GET /api/v1/stats — 运行统计", s)

# ========== 场景2: Dify HTTP 调用工具 ==========
print("\n" + "█"*60)
print("  场景 2: Dify HTTP REST API 模式 — 工具发现与调用")
print("█"*60)

# 2a: 工具列表
tl = api_post("/api/v1/tools/list", {
    "jsonrpc": "2.0", "id": "t1", "method": "tools/list", "params": {}
})
tools = tl.get("tools", [])
log(f"POST /api/v1/tools/list — 工具列表 ({len(tools)} 个工具)",
    [{"name": t["name"], "desc": t["description"][:50]} for t in tools])

# 2b: 调用 read_file 读取本文件
tc = api_post("/api/v1/tools/call", {
    "name": "read_file",
    "arguments": {"path": __file__}
})
if tc.get("success"):
    log("POST /api/v1/tools/call read_file — 成功",
        {"status": "success", "content_preview": tc.get("result", "")[:200]})
elif "error" in tc:
    log("POST /api/v1/tools/call read_file — 结果", tc)

# 2c: OpenAPI Schema
o = api_get("/api/v1/openapi.json")
log("GET /api/v1/openapi.json — Dify 兼容 Schema",
    {"openapi": o.get("openapi"),
     "title": o.get("info", {}).get("title"),
     "paths_count": len(o.get("paths", {})),
     "schemas_count": len(o.get("components", {}).get("schemas", {})),
     "x-dify": o.get("x-dify", {})})

# ========== 场景3: Ollama 代理异常场景 ==========
print("\n" + "█"*60)
print("  场景 3: Ollama 代理 — 故障隔离验证")
print("█"*60)

oh = api_get("/api/v1/ollama/health")
log("GET /api/v1/ollama/health — Ollama 健康状态", oh)

# 模拟调用 Ollama 时的标准化错误（Ollama 未运行时的表现）
tc_ollama = api_post("/api/v1/tools/call", {
    "name": "llm_ping",
    "arguments": {}
})
log("POST /api/v1/tools/call llm_ping — 标准化错误码返回", tc_ollama)

# ========== 场景4: MCP JSON-RPC 协议直接调用 ==========
print("\n" + "█"*60)
print("  场景 4: MCP JSON-RPC 协议 — Trae IDE 兼容模式")
print("█"*60)

mcp_init = api_post("/mcp", {
    "jsonrpc": "2.0", "id": "init1", "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "smoke-test-client", "version": "1.0.0"}
    }
}, headers={"Content-Type": "application/json"})
log("POST /mcp initialize — MCP 握手", mcp_init.get("result", mcp_init.get("error", mcp_init)))

mcp_list = api_post("/mcp", {
    "jsonrpc": "2.0", "id": "ls1", "method": "tools/list", "params": {}
}, headers={"Content-Type": "application/json"})
tools2 = mcp_list.get("result", {}).get("tools", [])
log(f"POST /mcp tools/list — MCP 工具发现 ({len(tools2)} 个)",
    [t["name"] for t in tools2])

mcp_call = api_post("/mcp", {
    "jsonrpc": "2.0", "id": "call1", "method": "tools/call",
    "params": {"name": "web_fetch", "arguments": {"url": "https://httpbin.org/get"}}
}, headers={"Content-Type": "application/json"})
log("POST /mcp tools/call web_fetch — MCP 工具调用", mcp_call.get("result", mcp_call.get("error", mcp_call)))

# ========== 验证结果 ==========
print("\n" + "█"*60)
print("  验证总结")
print("█"*60)
all_ok = True
checks = [
    ("Health 端点", h.get("status") == "healthy"),
    ("工具列表 >= 15", len(tools) >= 15),
    ("REST read_file调用", tc.get("success")),
    ("OpenAPI Schema", o.get("openapi") == "3.0.3"),
    ("MCP 初始化", mcp_init.get("result", {}).get("serverInfo", {}).get("name") == "mcp-tool-gateway"),
    ("MCP 工具列表", len(tools2) >= 15),
    ("MCP web_fetch调用", not mcp_call.get("result", {}).get("isError", True)),
]
for name, ok in checks:
    status = "✅ PASS" if ok else "❌ FAIL"
    print(f"  {status} | {name}")
    if not ok:
        all_ok = False

if all_ok:
    print(f"\n  ✅ 全部 {len(checks)} 项验证通过! 网关 v2.0 运行正常")
else:
    print("\n  ❌ 存在未通过的验证项")
    sys.exit(1)
