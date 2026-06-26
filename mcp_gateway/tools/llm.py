"""
LLM 工具 Provider — 对接 Ollama 本地大模型。

让 AI Agent 能够：
- 调用本地 Ollama 模型进行文本生成
- 列出已安装的 Ollama 模型
- 查询模型信息

依赖：Ollama 服务需在本地运行（默认 http://localhost:11434）
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict

from core.exceptions import ToolExecutionError
from core.types import ToolCallResult, ToolDefinition
from mcp_gateway.protocol import BaseToolProvider


class LLMToolProvider(BaseToolProvider):
    """Ollama 本地大模型工具集。"""

    def __init__(self, base_url: str = "http://localhost:11434"):
        super().__init__(
            name="llm",
            description="Local LLM operations via Ollama: text generation, model listing"
        )
        self._base_url = base_url.rstrip("/")
        self._register_tools()

    def _register_tools(self):
        self._register_tool(ToolDefinition(
            name="llm_call",
            description="调用本地 Ollama 大模型生成文本。"
                        "支持所有已安装的模型（如 qwen2.5, llama3, deepseek-r1 等）。"
                        "注意：首次调用冷启动模型需加载时间，后续调用会更快。",
            inputSchema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "description": "模型名称（如 qwen2.5:7b, llama3:8b, deepseek-r1:8b）。"
                                        "留空则自动选择第一个已安装的模型。",
                        "default": "",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "提示词 / 问题",
                    },
                    "system": {
                        "type": "string",
                        "description": "系统提示词（可选，设定模型角色和行为）",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "温度参数（0-2，越高越随机，默认 0.7）",
                        "default": 0.7,
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "最大生成 token 数（默认 1024）",
                        "default": 1024,
                    },
                },
                "required": ["prompt"],
            },
            category="llm",
            tags=["ollama", "llm", "generate", "ai"],
            cacheable=False,
            timeout_ms=60000,
        ))

        self._register_tool(ToolDefinition(
            name="llm_list_models",
            description="列出本地 Ollama 已安装的所有模型及其详细信息。",
            inputSchema={
                "type": "object",
                "properties": {},
            },
            category="llm",
            tags=["ollama", "models", "list"],
            cacheable=True,
            timeout_ms=10000,
        ))

        self._register_tool(ToolDefinition(
            name="llm_ping",
            description="检查 Ollama 服务的连通性，返回服务状态和已安装的模型列表。",
            inputSchema={
                "type": "object",
                "properties": {},
            },
            category="llm",
            tags=["ollama", "health", "ping"],
            cacheable=False,
            timeout_ms=5000,
        ))

    # ── call_tool 分发 ──

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "llm_call":
            return await self._llm_call(**arguments)
        elif tool_name == "llm_list_models":
            return await self._llm_list_models()
        elif tool_name == "llm_ping":
            return await self._llm_ping()
        else:
            raise ToolExecutionError(tool_name, f"Unknown tool: {tool_name}")

    # ── llm_call ──

    async def _llm_call(
        self,
        model: str = "",
        prompt: str = "",
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> ToolCallResult:
        # Auto-detect first available model if none specified
        if not model:
            model = await self._get_first_model()
            if not model:
                return ToolCallResult(
                    tool_name="llm_call",
                    content=[{
                        "type": "text",
                        "text": "未找到已安装的 Ollama 模型。请先执行: ollama pull qwen2.5:7b",
                    }],
                    is_error=True,
                )

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self._base_url}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                response_text = result.get("response", "")

                return ToolCallResult(
                    tool_name="llm_call",
                    content=[{
                        "type": "text",
                        "text": response_text,
                    }],
                    metadata={
                        "model": model,
                        "eval_count": result.get("eval_count", 0),
                        "eval_duration_ms": result.get("eval_duration", 0) / 1_000_000,
                        "total_duration_ms": result.get("total_duration", 0) / 1_000_000,
                    },
                )

        except urllib.error.URLError as e:
            return ToolCallResult(
                tool_name="llm_call",
                content=[{
                    "type": "text",
                    "text": f"无法连接 Ollama 服务 ({self._base_url})。请确认 Ollama 已启动。\n错误: {e.reason}",
                }],
                is_error=True,
            )
        except Exception as e:
            return ToolCallResult(
                tool_name="llm_call",
                content=[{"type": "text", "text": f"LLM 调用失败: {e}"}],
                is_error=True,
            )

    # ── llm_list_models ──

    async def _llm_list_models(self) -> ToolCallResult:
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                models = result.get("models", [])

                if not models:
                    return ToolCallResult(
                        tool_name="llm_list_models",
                        content=[{
                            "type": "text",
                            "text": "未找到已安装的模型。请使用 'ollama pull <model>' 下载模型。",
                        }],
                    )

                model_list = []
                for m in models:
                    size_gb = m.get("size", 0) / (1024 ** 3)
                    model_list.append({
                        "name": m.get("name", "unknown"),
                        "size_gb": round(size_gb, 2),
                        "modified": m.get("modified_at", ""),
                        "family": m.get("details", {}).get("family", ""),
                        "parameter_size": m.get("details", {}).get("parameter_size", ""),
                    })

                return ToolCallResult(
                    tool_name="llm_list_models",
                    content=[{
                        "type": "text",
                        "text": json.dumps(model_list, indent=2, ensure_ascii=False),
                    }],
                    metadata={"count": len(models)},
                )

        except urllib.error.URLError as e:
            return ToolCallResult(
                tool_name="llm_list_models",
                content=[{
                    "type": "text",
                    "text": f"无法连接 Ollama 服务。请确认 Ollama 已启动。\n错误: {e.reason}",
                }],
                is_error=True,
            )
        except Exception as e:
            return ToolCallResult(
                tool_name="llm_list_models",
                content=[{"type": "text", "text": f"查询失败: {e}"}],
                is_error=True,
            )

    # ── ollama_ping ──

    async def _llm_ping(self) -> ToolCallResult:
        """检查 Ollama 服务连通性"""
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                models = result.get("models", [])
                return ToolCallResult(
                    tool_name="llm_ping",
                    content=[{
                        "type": "text",
                        "text": json.dumps({
                            "status": "ok",
                            "ollama_url": self._base_url,
                            "models_count": len(models),
                            "models": [m.get("name") for m in models],
                        }, ensure_ascii=False),
                    }],
                )
        except urllib.error.URLError as e:
            return ToolCallResult(
                tool_name="llm_ping",
                content=[{
                    "type": "text",
                    "text": json.dumps({
                        "status": "error",
                        "ollama_url": self._base_url,
                        "error": str(e.reason),
                    }),
                }],
                is_error=True,
            )

    # ── helpers ──

    async def _get_first_model(self) -> str:
        """获取第一个可用的 Ollama 模型名称"""
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                models = result.get("models", [])
                if models:
                    return models[0].get("name", "")
        except Exception:
            pass
        return ""
