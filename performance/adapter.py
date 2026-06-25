"""
性能优化层 - 多模型适配器
统一适配云端 DS-V4 API 和本地 Ollama，无缝切换
"""

import os
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger("performance.adapter")


class ModelProvider(str, Enum):
    """模型提供商"""
    DEEPSEEK = "deepseek"       # DeepSeek-V4 (云端)
    OPENAI = "openai"           # OpenAI 兼容 API
    OLLAMA = "ollama"           # 本地 Ollama
    VLLM = "vllm"               # 本地 vLLM
    CUSTOM = "custom"           # 自定义


@dataclass
class ModelConfig:
    """模型配置"""
    provider: ModelProvider
    model_name: str
    api_base: str = ""
    api_key: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 0.95
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """统一 LLM 响应"""
    content: str
    model: str
    provider: ModelProvider
    tokens_prompt: int = 0
    tokens_completion: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: str = "stop"


class MultiModelAdapter:
    """
    多模型适配器
    统一接口，支持云端/本地模型无缝切换
    """

    def __init__(self):
        self._models: Dict[str, ModelConfig] = {}
        self._providers: Dict[str, Any] = {}  # 缓存的 provider 客户端
        self._call_stats: Dict[str, List[float]] = {}

    def register_model(self, name: str, config: ModelConfig):
        """注册模型"""
        self._models[name] = config
        logger.info(f"Model registered: {name} [{config.provider.value}]")

    def get_model(self, name: str) -> Optional[ModelConfig]:
        """获取模型配置"""
        return self._models.get(name)

    def list_models(self) -> List[Dict[str, Any]]:
        """列出所有模型"""
        return [
            {
                "name": name,
                "provider": cfg.provider.value,
                "model_name": cfg.model_name,
                "api_base": cfg.api_base,
            }
            for name, cfg in self._models.items()
        ]

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "default",
        **kwargs,
    ) -> LLMResponse:
        """
        统一聊天接口
        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称
        Returns:
            LLMResponse
        """
        config = self._models.get(model)
        if not config:
            raise ValueError(f"Unknown model: {model}")

        start = time.perf_counter()

        try:
            if config.provider == ModelProvider.DEEPSEEK:
                response = await self._call_deepseek(config, messages, **kwargs)
            elif config.provider == ModelProvider.OPENAI:
                response = await self._call_openai_compatible(config, messages, **kwargs)
            elif config.provider == ModelProvider.OLLAMA:
                response = await self._call_ollama(config, messages, **kwargs)
            elif config.provider == ModelProvider.VLLM:
                response = await self._call_openai_compatible(config, messages, **kwargs)
            else:
                raise ValueError(f"Unsupported provider: {config.provider}")

            response.latency_ms = (time.perf_counter() - start) * 1000
            response.model = config.model_name
            response.provider = config.provider

            # 记录延迟统计
            self._call_stats.setdefault(model, []).append(response.latency_ms)

            return response

        except Exception as e:
            logger.error(f"Model call failed ({model}): {e}")
            raise

    async def _call_deepseek(self, config: ModelConfig,
                             messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """调用 DeepSeek API"""
        import aiohttp

        api_base = config.api_base or "https://api.deepseek.com/v1"
        api_key = config.api_key or os.getenv("DEEPSEEK_API_KEY", "")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": config.model_name,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            **config.extra_params,
            **kwargs,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                data = await resp.json()

                if "error" in data:
                    raise RuntimeError(f"DeepSeek API error: {data['error']}")

                choice = data["choices"][0]
                usage = data.get("usage", {})
                return LLMResponse(
                    content=choice["message"]["content"],
                    model=config.model_name,
                    provider=ModelProvider.DEEPSEEK,
                    tokens_prompt=usage.get("prompt_tokens", 0),
                    tokens_completion=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    finish_reason=choice.get("finish_reason", "stop"),
                )

    async def _call_openai_compatible(self, config: ModelConfig,
                                      messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """调用 OpenAI 兼容 API（包括 vLLM）"""
        import aiohttp

        api_base = config.api_base or "http://localhost:8000/v1"
        api_key = config.api_key or os.getenv("OPENAI_API_KEY", "not-needed")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": config.model_name,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            **config.extra_params,
            **kwargs,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                data = await resp.json()

                if "error" in data:
                    raise RuntimeError(f"API error: {data['error']}")

                choice = data["choices"][0]
                usage = data.get("usage", {})
                return LLMResponse(
                    content=choice["message"]["content"],
                    model=config.model_name,
                    provider=config.provider,
                    tokens_prompt=usage.get("prompt_tokens", 0),
                    tokens_completion=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    finish_reason=choice.get("finish_reason", "stop"),
                )

    async def _call_ollama(self, config: ModelConfig,
                           messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """调用本地 Ollama"""
        import aiohttp

        api_base = config.api_base or "http://localhost:11434"

        payload = {
            "model": config.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": config.temperature,
                "num_predict": config.max_tokens,
                "top_p": config.top_p,
            },
            **config.extra_params,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{api_base}/api/chat",
                json=payload,
            ) as resp:
                data = await resp.json()

                return LLMResponse(
                    content=data["message"]["content"],
                    model=config.model_name,
                    provider=ModelProvider.OLLAMA,
                    tokens_prompt=data.get("prompt_eval_count", 0),
                    tokens_completion=data.get("eval_count", 0),
                    total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                    finish_reason=data.get("done_reason", "stop"),
                )

    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        stats = {}
        for model_name, latencies in self._call_stats.items():
            if latencies:
                avg = sum(latencies) / len(latencies)
                stats[model_name] = {
                    "calls": len(latencies),
                    "avg_latency_ms": f"{avg:.1f}",
                    "min_latency_ms": f"{min(latencies):.1f}",
                    "max_latency_ms": f"{max(latencies):.1f}",
                    "p95_latency_ms": f"{sorted(latencies)[int(len(latencies)*0.95)]:.1f}",
                }
        return stats


# ============================================================
# 默认模型配置
# ============================================================

def create_default_adapter() -> MultiModelAdapter:
    """创建默认适配器（预配置常用模型）"""
    adapter = MultiModelAdapter()

    # DeepSeek-V4
    adapter.register_model("deepseek-v4", ModelConfig(
        provider=ModelProvider.DEEPSEEK,
        model_name="deepseek-chat",
        api_base="https://api.deepseek.com/v1",
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        temperature=0.7,
        max_tokens=4096,
    ))

    # 本地 Ollama (qwen2.5:7b)
    adapter.register_model("ollama-qwen", ModelConfig(
        provider=ModelProvider.OLLAMA,
        model_name="qwen2.5:7b",
        api_base="http://localhost:11434",
        temperature=0.7,
        max_tokens=2048,
    ))

    # 本地 Ollama (llama3.1:8b)
    adapter.register_model("ollama-llama", ModelConfig(
        provider=ModelProvider.OLLAMA,
        model_name="llama3.1:8b",
        api_base="http://localhost:11434",
        temperature=0.7,
        max_tokens=2048,
    ))

    # 本地 vLLM
    adapter.register_model("vllm-local", ModelConfig(
        provider=ModelProvider.VLLM,
        model_name="qwen2.5-7b-instruct",
        api_base="http://localhost:8000/v1",
        api_key="not-needed",
        temperature=0.7,
        max_tokens=2048,
    ))

    return adapter
