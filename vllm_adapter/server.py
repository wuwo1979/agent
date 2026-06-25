"""
vLLM 适配层
本地部署开源模型，封装 OpenAI 兼容 API
"""

import os
import subprocess
import asyncio
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger("vllm_adapter")


class VLLMServer:
    """
    vLLM 本地推理服务器管理器
    管理 vLLM 服务的启动、停止、健康检查
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-7B-Instruct",
        host: str = "0.0.0.0",
        port: int = 8000,
        gpu_memory_utilization: float = 0.9,
        max_model_len: int = 4096,
        tensor_parallel_size: int = 1,
        dtype: str = "auto",
    ):
        self.model_name = model_name
        self.host = host
        self.port = port
        self.gpu_memory_utilization = gpu_memory_utilization
        self.max_model_len = max_model_len
        self.tensor_parallel_size = tensor_parallel_size
        self.dtype = dtype
        self._process: Optional[subprocess.Popen] = None

    @property
    def api_base(self) -> str:
        return f"http://{self.host}:{self.port}/v1"

    def start(self) -> bool:
        """启动 vLLM 服务"""
        cmd = [
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--model", self.model_name,
            "--host", self.host,
            "--port", str(self.port),
            "--gpu-memory-utilization", str(self.gpu_memory_utilization),
            "--max-model-len", str(self.max_model_len),
            "--tensor-parallel-size", str(self.tensor_parallel_size),
            "--dtype", self.dtype,
        ]

        logger.info(f"Starting vLLM server: {' '.join(cmd)}")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__)),
            )
            logger.info(f"vLLM server started (PID: {self._process.pid})")
            return True
        except FileNotFoundError:
            logger.error("vLLM not installed. Run: pip install vllm")
            return False
        except Exception as e:
            logger.error(f"Failed to start vLLM: {e}")
            return False

    def stop(self):
        """停止 vLLM 服务"""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
            logger.info("vLLM server stopped")

    async def health_check(self) -> bool:
        """健康检查"""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_base}/models") as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def wait_until_ready(self, timeout: int = 300) -> bool:
        """等待服务就绪"""
        import time
        start = time.time()
        while time.time() - start < timeout:
            if await self.health_check():
                logger.info("vLLM server is ready")
                return True
            await asyncio.sleep(2)
        logger.error("vLLM server startup timed out")
        return False

    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            "model": self.model_name,
            "host": self.host,
            "port": self.port,
            "api_base": self.api_base,
            "running": self._process is not None and self._process.poll() is None,
            "pid": self._process.pid if self._process else None,
        }


class VLLMClient:
    """
    vLLM OpenAI 兼容客户端
    封装标准 OpenAI SDK 调用方式
    """

    def __init__(self, api_base: str = "http://localhost:8000/v1",
                 api_key: str = "not-needed"):
        self.api_base = api_base
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        """延迟初始化 OpenAI 客户端"""
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                base_url=self.api_base,
                api_key=self.api_key,
            )
        return self._client

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        OpenAI 兼容的聊天接口
        """
        client = self._get_client()

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        return {
            "content": response.choices[0].message.content,
            "model": response.model,
            "tokens_prompt": response.usage.prompt_tokens,
            "tokens_completion": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
            "finish_reason": response.choices[0].finish_reason,
        }

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "default",
        **kwargs,
    ):
        """流式聊天"""
        client = self._get_client()

        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def list_models(self) -> List[str]:
        """列出可用模型"""
        client = self._get_client()
        models = await client.models.list()
        return [m.id for m in models.data]


# ============================================================
# Ollama 管理工具
# ============================================================

class OllamaManager:
    """Ollama 本地模型管理"""

    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host

    async def list_models(self) -> List[Dict[str, Any]]:
        """列出已安装的模型"""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.host}/api/tags") as resp:
                data = await resp.json()
                return data.get("models", [])

    async def pull_model(self, model_name: str) -> bool:
        """拉取模型"""
        import aiohttp

        logger.info(f"Pulling model: {model_name}")
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.host}/api/pull", json={
                "name": model_name,
                "stream": False,
            }) as resp:
                return resp.status == 200

    async def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """获取模型详情"""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.host}/api/show", json={
                "name": model_name,
            }) as resp:
                return await resp.json()
