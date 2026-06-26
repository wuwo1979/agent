"""
多租户权限隔离 — API Key 分组 + 独立文件白名单 + 工具策略

每个租户 (Tenant) 拥有：
- 一组 API Key（可动态增删）
- 独立的文件系统访问白名单（路径隔离）
- 独立的工具调用策略（允许/禁止特定工具）

使用方式：
    tenancy = TenancyManager()
    tenancy.add_tenant(
        tenant_id="dify_app_001",
        api_keys=["dify-key-001"],
        file_whitelist=["/project/dify_01/"],
        allowed_tools=["sysinfo", "read_file", "list_dir", "web_fetch"],
    )
    tenancy.add_tenant(
        tenant_id="ollama_local",
        api_keys=["ollama-key-001"],
        file_whitelist=["/project/ollama/"],
        allowed_tools=["llm_call", "llm_list_models", "sysinfo"],
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from mcp_gateway.security import APIKeyAuthenticator, AuthContext, AuthResult

logger = logging.getLogger("mcp_gateway.tenancy")


@dataclass
class Tenant:
    """单个租户的权限配置"""

    tenant_id: str
    label: str = ""  # 可读标签
    api_keys: List[str] = field(default_factory=list)
    file_whitelist: List[str] = field(default_factory=list)  # 允许访问的文件路径
    allowed_tools: Set[str] = field(default_factory=set)  # 允许的工具（空=全部）
    denied_tools: Set[str] = field(default_factory=set)  # 禁止的工具
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据

    def is_path_allowed(self, path: str) -> bool:
        """检查文件路径是否在白名单内。白名单为空表示允许所有路径。"""
        if not self.file_whitelist:
            return True
        normalized = str(Path(path).resolve())
        for allowed in self.file_whitelist:
            allowed_normalized = str(Path(allowed).resolve())
            if normalized.startswith(allowed_normalized):
                return True
        return False

    def is_tool_allowed(self, tool_name: str) -> AuthResult:
        """检查工具是否允许调用"""
        if self.denied_tools and tool_name in self.denied_tools:
            return AuthResult.DENY
        if not self.allowed_tools:
            return AuthResult.ALLOW
        if tool_name in self.allowed_tools:
            return AuthResult.ALLOW
        return AuthResult.DENY

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "label": self.label,
            "file_whitelist": self.file_whitelist,
            "allowed_tools": sorted(self.allowed_tools),
            "denied_tools": sorted(self.denied_tools),
            "metadata": self.metadata,
        }


class TenancyManager:
    """
    多租户管理器。

    根据 API Key 识别租户，返回该租户的权限配置。
    对外暴露统一的 check_access() 接口。
    """

    def __init__(self):
        self._tenants: Dict[str, Tenant] = {}
        # key_hash -> tenant_id 映射（O(1) 查找）
        self._key_to_tenant: Dict[str, str] = {}
        self._authenticator = APIKeyAuthenticator(valid_keys=[])

    # ── 租户管理 ──

    def add_tenant(
        self,
        tenant_id: str,
        api_keys: Optional[List[str]] = None,
        file_whitelist: Optional[List[str]] = None,
        allowed_tools: Optional[Set[str]] = None,
        denied_tools: Optional[Set[str]] = None,
        label: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tenant:
        """添加一个租户"""
        tenant = Tenant(
            tenant_id=tenant_id,
            label=label or tenant_id,
            api_keys=api_keys or [],
            file_whitelist=file_whitelist or [],
            allowed_tools=allowed_tools or set(),
            denied_tools=denied_tools or set(),
            metadata=metadata or {},
        )
        self._tenants[tenant_id] = tenant

        # 注册 API Key
        for key in api_keys or []:
            self._authenticator.add_key(key)
            key_hash = self._authenticator._hash_key(key)
            self._key_to_tenant[key_hash] = tenant_id

        logger.info(
            f"Tenant added: {tenant_id} "
            f"(keys={len(api_keys or [])}, "
            f"tools={len(allowed_tools or set())}, "
            f"paths={len(file_whitelist or [])})"
        )
        return tenant

    def remove_tenant(self, tenant_id: str):
        """移除租户"""
        tenant = self._tenants.pop(tenant_id, None)
        if tenant:
            for key in tenant.api_keys:
                key_hash = self._authenticator._hash_key(key)
                self._key_to_tenant.pop(key_hash, None)
                self._authenticator.revoke_key(key)
            logger.info(f"Tenant removed: {tenant_id}")

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> List[dict]:
        return [t.to_dict() for t in self._tenants.values()]

    # ── 权限检查（核心入口） ──

    def authenticate(self, headers: Dict[str, str]) -> AuthContext:
        """认证请求，返回带 tenant_id 的 AuthContext"""
        auth_context = self._authenticator.authenticate(headers)

        if auth_context.authenticated:
            # 通过 API Key Hash 反查租户
            # 注意：APIKeyAuthenticator 存储的是 hash，我们需要重新计算
            api_key = headers.get(self._authenticator._header_name, "")
            if api_key:
                key_hash = self._authenticator._hash_key(api_key)
                tenant_id = self._key_to_tenant.get(key_hash, "")
                if tenant_id:
                    auth_context.metadata["tenant_id"] = tenant_id

        return auth_context

    def check_path_access(self, tenant_id: str, path: str) -> bool:
        """检查租户是否有权访问指定路径"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False
        return tenant.is_path_allowed(path)

    def check_tool_access(self, tenant_id: str, tool_name: str) -> AuthResult:
        """检查租户是否有权调用指定工具"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return AuthResult.DENY
        return tenant.is_tool_allowed(tool_name)

    def check_access(
        self,
        auth_context: AuthContext,
        tool_name: str = "",
        path: str = "",
    ) -> AuthResult:
        """
        统一的访问检查入口。

        返回 ALLOW / DENY / REQUIRE_ELEVATION。
        """
        tenant_id = auth_context.metadata.get("tenant_id", "")

        if not tenant_id:
            # 无租户 = 匿名访问，允许只读工具
            if tool_name in ("sysinfo", "list_dir", "tools/list", "ping", "initialize"):
                return AuthResult.ALLOW
            return AuthResult.DENY

        # 检查工具权限
        if tool_name:
            result = self.check_tool_access(tenant_id, tool_name)
            if result != AuthResult.ALLOW:
                logger.warning(
                    f"Tool access denied: tenant={tenant_id}, tool={tool_name}"
                )
                return result

        # 检查路径权限
        if path:
            if not self.check_path_access(tenant_id, path):
                logger.warning(
                    f"Path access denied: tenant={tenant_id}, path={path}"
                )
                return AuthResult.DENY

        return AuthResult.ALLOW

    # ── 内置默认租户（开箱即用） ──

    def setup_default_tenants(self):
        """创建默认租户配置，开箱即用"""
        self.add_tenant(
            tenant_id="admin",
            label="管理员（全部权限）",
            api_keys=["admin-key-001"],
            file_whitelist=["/", "C:\\", "f:\\"],
            allowed_tools=set(),  # 空 = 全部允许
        )
        self.add_tenant(
            tenant_id="dify_default",
            label="Dify 默认租户",
            api_keys=["dify-key-001"],
            file_whitelist=["f:\\python_projects\\"],
            allowed_tools={
                "sysinfo", "read_file", "list_dir", "file_stat",
                "search_files", "web_fetch", "web_api", "json_query",
                "llm_call", "llm_list_models",
            },
        )
        self.add_tenant(
            tenant_id="ollama_local",
            label="Ollama 本地工具",
            api_keys=["ollama-key-001"],
            file_whitelist=["f:\\python_projects\\"],
            allowed_tools={
                "llm_call", "llm_list_models", "sysinfo",
                "read_file", "list_dir", "web_fetch",
            },
        )
        logger.info(
            f"Default tenants set up: "
            f"{len(self._tenants)} tenants, "
            f"{len(self._key_to_tenant)} API keys"
        )


# ── 全局单例 ──

_tenancy: Optional[TenancyManager] = None


def get_tenancy() -> TenancyManager:
    global _tenancy
    if _tenancy is None:
        _tenancy = TenancyManager()
        _tenancy.setup_default_tenants()
    return _tenancy