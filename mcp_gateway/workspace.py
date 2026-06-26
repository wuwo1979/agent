"""
Workspace Manager - Directory sandbox and resource discovery.

Provides:
- Workspace directory discovery (from env/config)
- Resource scanning (files inside workspace)
- Path validation (prevent escape from workspace)
- Built-in prompt templates for development scenarios
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from core.exceptions import PermissionDeniedError

logger = logging.getLogger("mcp_gateway.workspace")

# Default workspace = current working directory or MCP_WORKSPACE env
_DEFAULT_WORKSPACE = os.getcwd()
_MCP_WORKSPACE = os.environ.get("MCP_WORKSPACE", "")
WORKSPACE_DIR = os.path.abspath(_MCP_WORKSPACE) if _MCP_WORKSPACE else _DEFAULT_WORKSPACE


# Built-in resource name patterns (relative to workspace root)
RESOURCE_PATTERNS = [
    "README.md",
    "config/*.yaml",
    "config/*.yml",
    "requirements/*.txt",
    "pyproject.toml",
    "main.py",
    "docker/*.yml",
    "docker/*.yaml",
    ".github/workflows/*.yml",
]

# Resource names to always scan for
RESOURCE_NAMES = {
    "README.md": "Project README",
    "pyproject.toml": "Project Metadata",
    "main.py": "Application Entrypoint",
}


class WorkspaceManager:
    """
    Manages the workspace directory for MCP resource exposure and file sandboxing.
    """

    def __init__(self, workspace_dir: Optional[str] = None):
        self._workspace_dir = os.path.abspath(workspace_dir or WORKSPACE_DIR)
        logger.info(f"Workspace initialized: {self._workspace_dir}")

    @property
    def workspace_dir(self) -> str:
        return self._workspace_dir

    def resolve_path(self, path: str) -> str:
        """Resolve a path relative to workspace and validate it's within bounds."""
        resolved = os.path.abspath(os.path.join(self._workspace_dir, path))
        if not resolved.startswith(self._workspace_dir):
            raise PermissionDeniedError(
                "workspace",
                f"Path '{resolved}' is outside workspace directory '{self._workspace_dir}'"
            )
        return resolved

    def is_path_safe(self, path: str) -> bool:
        """Check if a path is within the workspace."""
        try:
            self.resolve_path(path)
            return True
        except PermissionDeniedError:
            return False

    def scan_resources(self) -> List[Dict[str, Any]]:
        """
        Scan workspace for discoverable resources.
        Returns MCP-compatible resource list.
        """
        resources = []

        # 1. Well-known files
        for fname, desc in RESOURCE_NAMES.items():
            full_path = os.path.join(self._workspace_dir, fname)
            if os.path.isfile(full_path):
                resources.append({
                    "uri": f"file://{full_path}",
                    "name": desc,
                    "description": f"Project {desc.lower()}",
                    "mimeType": _guess_mime(fname),
                })

        # 2. Config files
        config_dir = os.path.join(self._workspace_dir, "config")
        if os.path.isdir(config_dir):
            for f in os.listdir(config_dir):
                if f.endswith((".yaml", ".yml")):
                    full = os.path.join(config_dir, f)
                    resources.append({
                        "uri": f"file://{full}",
                        "name": f"Config: {f}",
                        "description": f"Configuration file: {f}",
                        "mimeType": "text/yaml",
                    })

        # 3. Requirements files
        req_dir = os.path.join(self._workspace_dir, "requirements")
        if os.path.isdir(req_dir):
            for f in os.listdir(req_dir):
                if f.endswith(".txt"):
                    full = os.path.join(req_dir, f)
                    resources.append({
                        "uri": f"file://{full}",
                        "name": f"Dependencies: {f}",
                        "description": f"Python dependency file: {f}",
                        "mimeType": "text/plain",
                    })

        # 4. Docker files
        docker_dir = os.path.join(self._workspace_dir, "docker")
        if os.path.isdir(docker_dir):
            for f in os.listdir(docker_dir):
                if f.endswith((".yml", ".yaml", ".Dockerfile", "Dockerfile")):
                    full = os.path.join(docker_dir, f)
                    resources.append({
                        "uri": f"file://{full}",
                        "name": f"Docker: {f}",
                        "description": f"Docker configuration: {f}",
                        "mimeType": "text/yaml" if f.endswith((".yml", ".yaml")) else "text/plain",
                    })

        return resources

    def read_resource(self, uri: str) -> Dict[str, Any]:
        """
        Read a resource by URI.
        Returns MCP-compatible content dict.
        """
        # Parse file:// URI
        if not uri.startswith("file://"):
            raise ValueError(f"Unsupported URI scheme: {uri}")

        file_path = uri[len("file://"):]

        # Validate path is within workspace
        if not self.is_path_safe(file_path):
            raise PermissionDeniedError(
                "workspace",
                "Cannot read resource: path outside workspace"
            )

        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Resource not found: {file_path}")

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        return {
            "uri": uri,
            "mimeType": _guess_mime(file_path),
            "text": content,
        }


# ============================================================
# Built-in prompt templates (MCP prompts)
# ============================================================

BUILTIN_PROMPTS: List[Dict[str, Any]] = [
    {
        "name": "code_review",
        "description": "审查代码文件，检查潜在问题、代码质量和最佳实践",
        "arguments": [
            {"name": "file_path", "description": "要审查的文件路径", "required": True},
            {"name": "focus", "description": "审查重点 (security|performance|style|all)", "required": False},
        ],
    },
    {
        "name": "debug_issue",
        "description": "分析 Bug 或错误输出，定位根因并给出修复建议",
        "arguments": [
            {"name": "error_message", "description": "错误信息或堆栈跟踪", "required": True},
            {"name": "context", "description": "相关代码或上下文", "required": False},
        ],
    },
    {
        "name": "refactor_suggestion",
        "description": "分析代码结构，提出重构建议（提取函数、优化复杂度等）",
        "arguments": [
            {"name": "file_path", "description": "要重构的文件路径", "required": True},
            {"name": "goal", "description": "重构目标 (readability|performance|maintainability)", "required": False},
        ],
    },
    {
        "name": "summarize_file",
        "description": "总结文件内容，提取关键信息和结构",
        "arguments": [
            {"name": "path", "description": "要总结的文件路径", "required": True},
            {"name": "detail_level", "description": "详细程度 (brief|normal|detailed)", "required": False},
        ],
    },
    {
        "name": "generate_test",
        "description": "为指定函数或模块生成单元测试",
        "arguments": [
            {"name": "target", "description": "要测试的函数/模块名称", "required": True},
            {"name": "framework", "description": "测试框架 (pytest|unittest)", "required": False},
        ],
    },
    {
        "name": "explain_code",
        "description": "解释代码的功能和工作原理",
        "arguments": [
            {"name": "file_path", "description": "要解释的文件路径", "required": True},
            {"name": "lines", "description": "要解释的行范围 (如: 10-30)", "required": False},
        ],
    },
]


def get_prompt_content(name: str, arguments: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Get a prompt template with arguments substituted.
    Returns MCP-compatible prompt format.
    """
    args = arguments or {}

    templates = {
        "code_review": (
            "请审查以下代码文件，检查：\n"
            "1. 潜在的 Bug 和逻辑错误\n"
            "2. 安全漏洞\n"
            "3. 性能问题\n"
            "4. 代码风格和可读性\n"
            "5. 最佳实践遵循情况\n\n"
            f"文件：{args.get('file_path', '(未指定)')}\n"
            f"审查重点：{args.get('focus', 'all')}\n\n"
            "请逐项列出发现的问题，并给出修复建议。"
        ),
        "debug_issue": (
            "请分析以下错误信息，定位根因并给出修复方案：\n\n"
            f"错误信息：\n{args.get('error_message', '(未提供)')}\n\n"
            f"上下文：\n{args.get('context', '(未提供)')}\n\n"
            "请按以下格式回复：\n"
            "1. 错误类型和根因\n"
            "2. 影响范围\n"
            "3. 修复方案（含代码示例）\n"
            "4. 预防措施"
        ),
        "refactor_suggestion": (
            "请审查以下代码，提出重构建议：\n\n"
            f"文件：{args.get('file_path', '(未指定)')}\n"
            f"重构目标：{args.get('goal', 'maintainability')}\n\n"
            "请关注：\n"
            "- 函数过长/职责不单一\n"
            "- 重复代码\n"
            "- 复杂的条件嵌套\n"
            "- 可读性差的命名和结构\n"
            "- 可优化的性能瓶颈"
        ),
        "summarize_file": (
            f"请总结文件 {args.get('path', '(未指定)')} 的内容：\n"
            f"详细程度：{args.get('detail_level', 'normal')}\n\n"
            "提取以下信息：\n"
            "1. 文件用途和功能\n"
            "2. 主要类和函数\n"
            "3. 关键配置和常量\n"
            "4. 依赖关系\n"
            "5. 注意事项"
        ),
        "generate_test": (
            f"请为目标 {args.get('target', '(未指定)')} 生成单元测试：\n"
            f"测试框架：{args.get('framework', 'pytest')}\n\n"
            "覆盖以下场景：\n"
            "1. 正常路径\n"
            "2. 边界条件\n"
            "3. 错误处理\n"
            "4. 异常输入\n\n"
            "请直接输出可运行的测试代码。"
        ),
        "explain_code": (
            f"请解释文件 {args.get('file_path', '(未指定)')} 的代码：\n"
            f"关注行范围：{args.get('lines', '全部')}\n\n"
            "请说明：\n"
            "1. 这段代码的功能是什么\n"
            "2. 核心逻辑和工作流程\n"
            "3. 关键数据结构和算法\n"
            "4. 输入输出说明\n"
            "5. 使用示例"
        ),
    }

    prompt_text = templates.get(name, f"Prompt template '{name}' not found.")

    # Find matching prompt definition for the return structure
    prompt_def = next((p for p in BUILTIN_PROMPTS if p["name"] == name), None)
    desc = prompt_def["description"] if prompt_def else ""

    return {
        "description": desc,
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": prompt_text,
                },
            }
        ],
    }


def _guess_mime(file_path: str) -> str:
    """Guess MIME type from file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {
        ".py": "text/x-python",
        ".md": "text/markdown",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
        ".json": "application/json",
        ".env": "text/plain",
        ".cfg": "text/plain",
        ".ini": "text/plain",
        ".csv": "text/csv",
        ".html": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
        ".ts": "application/typescript",
        ".sh": "text/x-shellscript",
        ".bat": "text/x-bat",
        ".ps1": "text/x-powershell",
        ".dockerfile": "text/plain",
    }
    return mime_map.get(ext, "text/plain")


# ============================================================
# Convenience functions
# ============================================================

_workspace_instance: Optional[WorkspaceManager] = None


def get_workspace() -> WorkspaceManager:
    """Get the global workspace manager singleton."""
    global _workspace_instance
    if _workspace_instance is None:
        _workspace_instance = WorkspaceManager()
    return _workspace_instance


def get_workspace_dir() -> str:
    """Get the current workspace directory."""
    return get_workspace().workspace_dir
