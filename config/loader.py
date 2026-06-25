"""
配置管理模块
基于 YAML + Pydantic 的类型安全配置系统
支持环境变量覆盖、多环境配置、热重载
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger("config")

# ============================================================
# 配置数据类
# ============================================================

class TransportMode(str, Enum):
    STREAMABLE_HTTP = "streamable-http"
    SSE = "sse"
    STDIO = "stdio"


class AgentMode(str, Enum):
    SUPERVISOR = "supervisor"
    PIPELINE = "pipeline"
    SIMPLE = "simple"


class CacheStrategy(str, Enum):
    INCREMENTAL = "incremental"
    SEMANTIC = "semantic"
    NONE = "none"


class AuthType(str, Enum):
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    NONE = "none"


class RAGProvider(str, Enum):
    CHROMADB = "chromadb"
    MILVUS = "milvus"


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 9090
    mode: str = "http"
    log_level: str = "INFO"
    workers: int = 4


@dataclass
class MCPToolDiscoveryConfig:
    auto_scan: bool = True
    scan_paths: List[str] = field(default_factory=lambda: ["mcp_gateway/tools"])
    exclude_patterns: List[str] = field(default_factory=lambda: ["__pycache__", "__init__.py"])


@dataclass
class MCPToolPrefixConfig:
    enabled: bool = True
    mappings: Dict[str, str] = field(default_factory=lambda: {
        "filesystem": "fs", "terminal": "term", "database": "db", "custom": "custom"
    })


@dataclass
class MCPConfig:
    protocol_version: str = "2024-11-05"
    server_name: str = "MCP-Gateway"
    server_version: str = "2.0.0"
    transport: TransportMode = TransportMode.STREAMABLE_HTTP
    stateless: bool = False
    tool_discovery: MCPToolDiscoveryConfig = field(default_factory=MCPToolDiscoveryConfig)
    tool_prefix: MCPToolPrefixConfig = field(default_factory=MCPToolPrefixConfig)


@dataclass
class PlannerConfig:
    model: str = "deepseek-v4"
    temperature: float = 0.1
    max_tokens: int = 2048


@dataclass
class ExecutorConfig:
    timeout_per_tool: int = 30
    batch_size: int = 5


@dataclass
class ValidatorConfig:
    model: str = "deepseek-v4"
    temperature: float = 0.0
    max_tokens: int = 1024


@dataclass
class CheckpointConfig:
    enabled: bool = True
    directory: str = "./snapshots"
    keep_last: int = 5
    auto_save_interval: int = 60


@dataclass
class AgentConfig:
    mode: AgentMode = AgentMode.SUPERVISOR
    max_parallel_tools: int = 5
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0
    planner: PlannerConfig = field(default_factory=PlannerConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    validator: ValidatorConfig = field(default_factory=ValidatorConfig)
    checkpoint: CheckpointConfig = field(default_factory=CheckpointConfig)


@dataclass
class CacheConfig:
    enabled: bool = True
    max_entries: int = 1000
    max_content_length: int = 8000
    compression_threshold: int = 2000
    strategy: CacheStrategy = CacheStrategy.INCREMENTAL


@dataclass
class ParallelConfig:
    enabled: bool = True
    max_concurrency: int = 5
    dependency_aware: bool = True


@dataclass
class ContextCompressionConfig:
    enabled: bool = True
    max_result_length: int = 2000
    list_truncate_threshold: int = 10


@dataclass
class StreamingConfig:
    enabled: bool = True
    chunk_size: int = 512


@dataclass
class PerformanceConfig:
    cache: CacheConfig = field(default_factory=CacheConfig)
    parallel: ParallelConfig = field(default_factory=ParallelConfig)
    context_compression: ContextCompressionConfig = field(default_factory=ContextCompressionConfig)
    streaming: StreamingConfig = field(default_factory=StreamingConfig)


@dataclass
class ModelConfig:
    provider: str = "deepseek"
    model_name: str = "deepseek-chat"
    api_base: str = "https://api.deepseek.com/v1"
    api_key_env: str = "DEEPSEEK_API_KEY"
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 0.95
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def get_api_key(self) -> str:
        return os.getenv(self.api_key_env, "")


@dataclass
class ChromaDBConfig:
    persist_directory: str = "./chroma_db"
    collection_name: str = "agent_knowledge"


@dataclass
class MilvusConfig:
    host: str = "localhost"
    port: int = 19530
    collection_name: str = "agent_knowledge"
    dimension: int = 1536


@dataclass
class RetrievalConfig:
    top_k: int = 5
    score_threshold: float = 0.7
    max_chunk_size: int = 1000
    chunk_overlap: int = 200


@dataclass
class RAGConfig:
    enabled: bool = False
    provider: RAGProvider = RAGProvider.CHROMADB
    embedding_model: str = "text-embedding-3-small"
    chromadb: ChromaDBConfig = field(default_factory=ChromaDBConfig)
    milvus: MilvusConfig = field(default_factory=MilvusConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)


@dataclass
class AuthConfig:
    enabled: bool = False
    type: AuthType = AuthType.API_KEY
    api_key_header: str = "X-API-Key"
    api_keys: List[str] = field(default_factory=lambda: ["mcp-gateway-dev-key-change-in-production"])


@dataclass
class RateLimitConfig:
    enabled: bool = True
    max_requests_per_minute: int = 60
    burst_size: int = 10


@dataclass
class ToolPolicyConfig:
    enabled: bool = True
    policies: Dict[str, List[str]] = field(default_factory=lambda: {
        "dangerous_tools": ["term_run_command", "db_execute"],
        "readonly_tools": [
            "fs_read_file", "fs_list_dir", "fs_search",
            "db_query", "db_list_tables", "db_describe_table", "term_sysinfo"
        ],
    })


@dataclass
class SecurityConfig:
    auth: AuthConfig = field(default_factory=AuthConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    tool_policy: ToolPolicyConfig = field(default_factory=ToolPolicyConfig)


@dataclass
class DockerOllamaConfig:
    enabled: bool = True
    model: str = "qwen2.5:7b"


@dataclass
class DockerChromaDBConfig:
    enabled: bool = True
    port: int = 8001


@dataclass
class DockerMilvusConfig:
    enabled: bool = False
    port: int = 19530


@dataclass
class DockerConfig:
    image: str = "mcp-gateway"
    tag: str = "latest"
    ollama: DockerOllamaConfig = field(default_factory=DockerOllamaConfig)
    chromadb: DockerChromaDBConfig = field(default_factory=DockerChromaDBConfig)
    milvus: DockerMilvusConfig = field(default_factory=DockerMilvusConfig)


@dataclass
class MetricsConfig:
    enabled: bool = True
    port: int = 9091


@dataclass
class TracingConfig:
    enabled: bool = False
    exporter: str = "console"


@dataclass
class HealthCheckConfig:
    enabled: bool = True
    path: str = "/health"
    interval: int = 30


@dataclass
class ObservabilityConfig:
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    tracing: TracingConfig = field(default_factory=TracingConfig)
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)


# ============================================================
# 全局配置
# ============================================================

@dataclass
class AppConfig:
    """应用全局配置"""
    server: ServerConfig = field(default_factory=ServerConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    rag: RAGConfig = field(default_factory=RAGConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    docker: DockerConfig = field(default_factory=DockerConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)


# ============================================================
# 配置加载器
# ============================================================

class ConfigLoader:
    """
    YAML 配置加载器
    支持：
    - 多环境配置（default.yaml → {env}.yaml）
    - 环境变量覆盖（${VAR_NAME} 语法）
    - 嵌套配置合并
    """

    _instance: Optional["ConfigLoader"] = None
    _config: Optional[AppConfig] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def load(
        cls,
        config_path: Optional[str] = None,
        env: Optional[str] = None,
    ) -> AppConfig:
        """
        加载配置
        优先级：环境变量 > {env}.yaml > default.yaml
        """
        if cls._config is not None and config_path is None:
            return cls._config

        # 确定配置文件路径
        if config_path is None:
            config_dir = Path(__file__).parent
            config_path = str(config_dir / "default.yaml")

        # 加载基础配置
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        # 环境特定配置
        env_name = env or os.getenv("APP_ENV", "development")
        env_config_path = Path(config_path).parent / f"{env_name}.yaml"
        if env_config_path.exists():
            with open(env_config_path, "r", encoding="utf-8") as f:
                env_raw = yaml.safe_load(f)
            raw = cls._deep_merge(raw, env_raw)

        # 环境变量替换
        raw = cls._resolve_env_vars(raw)

        # 解析为数据类
        config = cls._parse_config(raw)
        cls._config = config
        return config

    @classmethod
    def reload(cls, config_path: Optional[str] = None) -> AppConfig:
        """重新加载配置"""
        cls._config = None
        return cls.load(config_path)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """深度合并两个字典"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigLoader._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _resolve_env_vars(data: Any) -> Any:
        """递归替换 ${VAR_NAME} 为环境变量值"""
        if isinstance(data, dict):
            return {k: ConfigLoader._resolve_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [ConfigLoader._resolve_env_vars(item) for item in data]
        elif isinstance(data, str) and data.startswith("${") and data.endswith("}"):
            var_name = data[2:-1]
            # 支持默认值: ${VAR:default}
            if ":" in var_name:
                var_name, default = var_name.split(":", 1)
                return os.getenv(var_name, default)
            return os.getenv(var_name, data)
        return data

    @staticmethod
    def _parse_config(raw: dict) -> AppConfig:
        """将原始字典解析为 AppConfig"""
        # 解析 models
        models = {}
        for name, model_data in raw.get("models", {}).items():
            models[name] = ModelConfig(
                provider=model_data.get("provider", "deepseek"),
                model_name=model_data.get("model_name", ""),
                api_base=model_data.get("api_base", ""),
                api_key_env=model_data.get("api_key_env", ""),
                temperature=model_data.get("temperature", 0.7),
                max_tokens=model_data.get("max_tokens", 4096),
                top_p=model_data.get("top_p", 0.95),
                extra_params=model_data.get("extra_params", {}),
            )

        # 解析 agent
        agent_raw = raw.get("agent", {})
        agent = AgentConfig(
            mode=AgentMode(agent_raw.get("mode", "supervisor")),
            max_parallel_tools=agent_raw.get("max_parallel_tools", 5),
            max_retries=agent_raw.get("max_retries", 3),
            retry_delay=agent_raw.get("retry_delay", 1.0),
            retry_backoff=agent_raw.get("retry_backoff", 2.0),
            planner=PlannerConfig(**agent_raw.get("planner", {})),
            executor=ExecutorConfig(**agent_raw.get("executor", {})),
            validator=ValidatorConfig(**agent_raw.get("validator", {})),
            checkpoint=CheckpointConfig(**agent_raw.get("checkpoint", {})),
        )

        # 解析 performance
        perf_raw = raw.get("performance", {})
        cache_raw = perf_raw.get("cache", {})
        parallel_raw = perf_raw.get("parallel", {})
        ctx_raw = perf_raw.get("context_compression", {})
        stream_raw = perf_raw.get("streaming", {})
        performance = PerformanceConfig(
            cache=CacheConfig(
                enabled=cache_raw.get("enabled", True),
                max_entries=cache_raw.get("max_entries", 1000),
                max_content_length=cache_raw.get("max_content_length", 8000),
                compression_threshold=cache_raw.get("compression_threshold", 2000),
                strategy=CacheStrategy(cache_raw.get("strategy", "incremental")),
            ),
            parallel=ParallelConfig(
                enabled=parallel_raw.get("enabled", True),
                max_concurrency=parallel_raw.get("max_concurrency", 5),
                dependency_aware=parallel_raw.get("dependency_aware", True),
            ),
            context_compression=ContextCompressionConfig(
                enabled=ctx_raw.get("enabled", True),
                max_result_length=ctx_raw.get("max_result_length", 2000),
                list_truncate_threshold=ctx_raw.get("list_truncate_threshold", 10),
            ),
            streaming=StreamingConfig(
                enabled=stream_raw.get("enabled", True),
                chunk_size=stream_raw.get("chunk_size", 512),
            ),
        )

        # 解析 security
        sec_raw = raw.get("security", {})
        auth_raw = sec_raw.get("auth", {})
        rl_raw = sec_raw.get("rate_limit", {})
        tp_raw = sec_raw.get("tool_policy", {})
        security = SecurityConfig(
            auth=AuthConfig(
                enabled=auth_raw.get("enabled", False),
                type=AuthType(auth_raw.get("type", "api_key")),
                api_key_header=auth_raw.get("api_key_header", "X-API-Key"),
                api_keys=auth_raw.get("api_keys", []),
            ),
            rate_limit=RateLimitConfig(
                enabled=rl_raw.get("enabled", True),
                max_requests_per_minute=rl_raw.get("max_requests_per_minute", 60),
                burst_size=rl_raw.get("burst_size", 10),
            ),
            tool_policy=ToolPolicyConfig(
                enabled=tp_raw.get("enabled", True),
                policies=tp_raw.get("policies", {}),
            ),
        )

        return AppConfig(
            server=ServerConfig(**raw.get("server", {})),
            mcp=MCPConfig(
                protocol_version=raw.get("mcp", {}).get("protocol_version", "2024-11-05"),
                server_name=raw.get("mcp", {}).get("server_name", "MCP-Gateway"),
                server_version=raw.get("mcp", {}).get("server_version", "2.0.0"),
                transport=TransportMode(raw.get("mcp", {}).get("transport", "streamable-http")),
                stateless=raw.get("mcp", {}).get("stateless", False),
                tool_discovery=MCPToolDiscoveryConfig(**raw.get("mcp", {}).get("tool_discovery", {})),
                tool_prefix=MCPToolPrefixConfig(**raw.get("mcp", {}).get("tool_prefix", {})),
            ),
            agent=agent,
            performance=performance,
            models=models,
            rag=RAGConfig(
                enabled=raw.get("rag", {}).get("enabled", False),
                provider=RAGProvider(raw.get("rag", {}).get("provider", "chromadb")),
                embedding_model=raw.get("rag", {}).get("embedding_model", "text-embedding-3-small"),
                chromadb=ChromaDBConfig(**raw.get("rag", {}).get("chromadb", {})),
                milvus=MilvusConfig(**raw.get("rag", {}).get("milvus", {})),
                retrieval=RetrievalConfig(**raw.get("rag", {}).get("retrieval", {})),
            ),
            security=security,
            docker=DockerConfig(
                image=raw.get("docker", {}).get("image", "mcp-gateway"),
                tag=raw.get("docker", {}).get("tag", "latest"),
                ollama=DockerOllamaConfig(**raw.get("docker", {}).get("ollama", {})),
                chromadb=DockerChromaDBConfig(**raw.get("docker", {}).get("chromadb", {})),
                milvus=DockerMilvusConfig(**raw.get("docker", {}).get("milvus", {})),
            ),
            observability=ObservabilityConfig(
                metrics=MetricsConfig(**raw.get("observability", {}).get("metrics", {})),
                tracing=TracingConfig(**raw.get("observability", {}).get("tracing", {})),
                health_check=HealthCheckConfig(**raw.get("observability", {}).get("health_check", {})),
            ),
        )


# ============================================================
# 全局便捷函数
# ============================================================

def get_config() -> AppConfig:
    """获取全局配置（单例）"""
    return ConfigLoader.load()


def reload_config() -> AppConfig:
    """重新加载配置"""
    return ConfigLoader.reload()
