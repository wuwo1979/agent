"""
vLLM 适配器 - 本地推理服务管理

状态: 🚧 待扩展
当前实现: vLLM 服务进程启停管理（服务端进程管控）
规划目标: 完整模型服务层（自动扩缩容、模型热切换、监控告警）
与 performance/adapter.py 的区别:
  - performance/adapter.py: 客户端 LLM 统一接口（适配 OpenAI/Ollama/vLLM 的 SDK）
  - vllm_adapter/: 服务端 vLLM/Ollama 进程生命周期管理

依赖: pip install vllm（体积大，GPU 环境）
"""
from vllm_adapter.server import OllamaManager, VLLMClient, VLLMServer

__all__ = ["VLLMServer", "VLLMClient", "OllamaManager"]
