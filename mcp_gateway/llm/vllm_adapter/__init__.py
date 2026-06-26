"""
vLLM 适配器 - 本地推理服务管理

管理 vLLM / Ollama 推理服务的进程生命周期（启动、停止、健康检查）。
与 performance/adapter.py 的区别:
  - performance/adapter.py: 客户端 LLM 统一接口（适配 OpenAI/Ollama/vLLM 的 SDK）
  - vllm_adapter/: 服务端 vLLM/Ollama 进程生命周期管理

依赖: pip install vllm（体积大，GPU 环境）
"""
from mcp_gateway.llm.vllm_adapter.server import OllamaManager, VLLMClient, VLLMServer

__all__ = ["VLLMServer", "VLLMClient", "OllamaManager"]
