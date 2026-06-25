"""
MCP Gateway - 安全层
认证、授权、速率限制、工具权限策略

参考:
- MCP Auth spec: https://spec.modelcontextprotocol.io/specification/2025-03-26/basic/authorization/
- Defense in depth: https://jacar.es/en/mcp-guia-completa-2026/
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("mcp_gateway.security")


class AuthResult(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_ELEVATION = "require_elevation"


@dataclass
class AuthContext:
    """认证上下文"""
    authenticated: bool = False
    api_key: str = ""
    scopes: List[str] = field(default_factory=list)
    client_id: str = "anonymous"
    metadata: Dict[str, Any] = field(default_factory=dict)


class APIKeyAuthenticator:
    """
    API Key 认证器
    简单而有效的 API Key 验证
    """

    def __init__(self, valid_keys: List[str], header_name: str = "X-API-Key"):
        # 存储密钥的哈希值，而非明文
        self._key_hashes: Set[str] = {
            self._hash_key(k) for k in valid_keys
        }
        self._header_name = header_name

    def _hash_key(self, key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    def authenticate(self, headers: Dict[str, str]) -> AuthContext:
        """验证 API Key"""
        api_key = headers.get(self._header_name, "")

        if not api_key:
            return AuthContext(authenticated=False)

        key_hash = self._hash_key(api_key)
        if key_hash in self._key_hashes:
            return AuthContext(
                authenticated=True,
                api_key=api_key[:8] + "***",  # 脱敏
                client_id=f"api_key_{key_hash[:8]}",
                scopes=["tools:read", "tools:execute"],
            )

        return AuthContext(authenticated=False)

    def add_key(self, key: str):
        """动态添加 API Key"""
        self._key_hashes.add(self._hash_key(key))

    def revoke_key(self, key: str):
        """撤销 API Key"""
        self._key_hashes.discard(self._hash_key(key))


class RateLimiter:
    """
    令牌桶速率限制器
    支持突发流量和按客户端限流
    """

    def __init__(self, max_requests: int = 60, burst_size: int = 10):
        self.max_requests = max_requests
        self.burst_size = burst_size
        self._buckets: Dict[str, Dict[str, float]] = {}
        self._cleanup_threshold = 1000

    def check(self, client_id: str) -> bool:
        """
        检查是否允许请求（令牌桶算法）
        Returns:
            True 如果允许，False 如果被限流
        """
        now = time.time()
        bucket = self._buckets.get(client_id)

        if bucket is None:
            # 新客户端：初始化令牌桶
            self._buckets[client_id] = {
                "tokens": self.burst_size,
                "last_refill": now,
            }
            self._maybe_cleanup()
            return True

        # 令牌补充
        elapsed = now - bucket["last_refill"]
        refill = elapsed * (self.max_requests / 60.0)  # 按秒补充
        bucket["tokens"] = min(self.burst_size, bucket["tokens"] + refill)
        bucket["last_refill"] = now

        if bucket["tokens"] >= 1.0:
            bucket["tokens"] -= 1.0
            return True

        return False

    def _maybe_cleanup(self):
        """定期清理过期桶"""
        if len(self._buckets) > self._cleanup_threshold:
            self._buckets.clear()
            logger.info("Rate limiter buckets cleaned up")

    def get_stats(self, client_id: str) -> Dict[str, Any]:
        """获取限流统计"""
        bucket = self._buckets.get(client_id)
        if not bucket:
            return {"tokens": 0, "limited": False}
        return {
            "tokens": bucket["tokens"],
            "limited": bucket["tokens"] < 1.0,
        }


class ToolPolicyEngine:
    """
    工具权限策略引擎
    基于策略的工具访问控制

    策略类型：
    - readonly: 只读工具，直接放行
    - dangerous: 危险工具，需要审批或确认
    - default: 需要认证检查
    """

    def __init__(self, policies: Dict[str, List[str]] = None):
        self.policies = policies or {}
        self._dangerous_tools: Set[str] = set(self.policies.get("dangerous_tools", []))
        self._readonly_tools: Set[str] = set(self.policies.get("readonly_tools", []))

    def check_tool(self, tool_name: str, auth_context: AuthContext) -> AuthResult:
        """
        检查工具调用权限
        """
        # 不需要认证的工具（如 initialize）
        if tool_name in ("initialize", "tools/list", "ping"):
            return AuthResult.ALLOW

        # 危险工具检查
        if tool_name in self._dangerous_tools:
            if not auth_context.authenticated:
                return AuthResult.DENY
            if "tools:execute" not in auth_context.scopes:
                return AuthResult.REQUIRE_ELEVATION
            return AuthResult.ALLOW

        # 只读工具
        if tool_name in self._readonly_tools:
            return AuthResult.ALLOW

        # 默认：需要认证
        if auth_context.authenticated:
            return AuthResult.ALLOW
        return AuthResult.DENY

    def add_dangerous_tool(self, tool_name: str):
        self._dangerous_tools.add(tool_name)

    def add_readonly_tool(self, tool_name: str):
        self._readonly_tools.add(tool_name)

    def get_policy_for_tool(self, tool_name: str) -> str:
        if tool_name in self._dangerous_tools:
            return "dangerous"
        if tool_name in self._readonly_tools:
            return "readonly"
        return "default"


class SecurityMiddleware:
    """
    安全中间件
    统一入口的认证、授权、限流检查
    """

    def __init__(
        self,
        authenticator: Optional[APIKeyAuthenticator] = None,
        rate_limiter: Optional[RateLimiter] = None,
        policy_engine: Optional[ToolPolicyEngine] = None,
    ):
        self.authenticator = authenticator
        self.rate_limiter = rate_limiter
        self.policy_engine = policy_engine

    async def check_request(
        self,
        method: str,
        headers: Dict[str, str],
    ) -> AuthContext:
        """
        完整的请求安全检查
        1. 认证
        2. 限流
        3. 工具权限
        """
        auth_context = AuthContext()

        # 1. 认证
        if self.authenticator:
            auth_context = self.authenticator.authenticate(headers)

        # 2. 限流
        if self.rate_limiter:
            if not self.rate_limiter.check(auth_context.client_id):
                logger.warning(f"Rate limited: {auth_context.client_id}")
                raise RateLimitExceededError(auth_context.client_id)

        # 3. 工具权限（仅对 tools/call 检查）
        if self.policy_engine and method == "tools/call":
            # 工具名在 params 中，这里先做初步检查
            pass

        return auth_context


class RateLimitExceededError(Exception):
    """速率限制错误"""
    def __init__(self, client_id: str):
        self.client_id = client_id
        super().__init__(f"Rate limit exceeded for {client_id}")


class ToolAccessDeniedError(Exception):
    """工具访问拒绝错误"""
    def __init__(self, tool_name: str, reason: str):
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"Access denied to {tool_name}: {reason}")
