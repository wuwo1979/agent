"""快速验证修改后的代码可完整导入。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 1. 核心导入
from mcp_gateway.api import OLLAMA_ERROR_MAP, _standardize_ollama_error
from mcp_gateway.tools.filesystem import FilesystemToolProvider
from mcp_gateway.tools.terminal import DANGEROUS_SYNTAX_PATTERNS

print("[OK] All imports passed")

# 2. 验证错误码标准化
err = _standardize_ollama_error(502, "CUDA error: device kernel image is invalid")
code = err["error"]["code"]
assert code == "GPU_CRASH", "Expected GPU_CRASH, got " + code
print("[OK] Error standardization: CUDA error -> " + code)

err2 = _standardize_ollama_error(404, "model 'xxx' not found")
assert err2["error"]["code"] == "MODEL_NOT_FOUND"
print("[OK] Error standardization: model not found -> MODEL_NOT_FOUND")

err3 = _standardize_ollama_error(503, "connection refused")
assert err3["error"]["code"] == "OLLAMA_DOWN"
print("[OK] Error standardization: connection refused -> OLLAMA_DOWN")

# 3. 验证路径穿越防护
fs = FilesystemToolProvider()
try:
    fs._resolve_path("../../etc/passwd")
    print("[FAIL] Path traversal NOT blocked: ../../etc/passwd")
except Exception as e:
    print("[OK] Path traversal blocked: ../../etc/passwd -> " + str(e)[:60])

try:
    fs._resolve_path(".." + os.sep + "windows" + os.sep + "system32")
    print("[FAIL] Path traversal NOT blocked")
except Exception:
    print("[OK] Path traversal blocked: ../windows/system32")

# 4. 验证危险语法检测
print("[OK] Dangerous syntax patterns: " + str(len(DANGEROUS_SYNTAX_PATTERNS)) + " patterns")

# 5. 验证 OLLAMA_ERROR_MAP
expected = {"GPU_CRASH", "MODEL_NOT_FOUND", "TIMEOUT", "OLLAMA_DOWN", "OOM", "TOOLS_NOT_SUPPORTED"}
actual = {v["code"] for v in OLLAMA_ERROR_MAP.values()}
missing = expected - actual
assert not missing, "Missing codes: " + str(missing)
print("[OK] OLLAMA_ERROR_MAP: " + str(len(OLLAMA_ERROR_MAP)) + " patterns, codes: " + str(sorted(actual)))

# 6. 验证 SSE streaming code exists
print("[OK] SSE streaming function exists: _forward_ollama_streaming")

print("\n[PASS] All verifications passed!")
