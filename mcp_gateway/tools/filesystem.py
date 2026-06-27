"""
Filesystem Tool Provider - MCP tools for file system operations.

Provides read, write, list, search, and stat operations with safety checks.
References: MCP Specification tools/list, tools/call primitives.
"""

from __future__ import annotations

import glob
import json
import os
from datetime import datetime
from typing import Any, Dict, List

from core.exceptions import PermissionDeniedError, ToolExecutionError
from core.types import ToolCallResult, ToolDefinition
from mcp_gateway.protocol import BaseToolProvider
from mcp_gateway.workspace import WORKSPACE_DIR

# Safe directories (prevent path traversal attacks)
# Priority: MCP_FS_SAFE_ROOTS env > MCP_WORKSPACE env > current directory + home
# MCP_WORKSPACE is also used by terminal tool for command sandboxing
_DEFAULT_ROOTS = [WORKSPACE_DIR, os.path.expanduser("~")]
_env_roots = os.environ.get("MCP_FS_SAFE_ROOTS") or os.environ.get("SAFE_ROOTS")
if _env_roots:
    SAFE_ROOTS = [os.path.abspath(p.strip()) for p in _env_roots.split(";") if p.strip()]
else:
    SAFE_ROOTS = _DEFAULT_ROOTS[:]


class FilesystemToolProvider(BaseToolProvider):
    """Filesystem tool provider for MCP gateway."""

    def __init__(self):
        super().__init__(
            name="filesystem",
            description="File system operations: read, write, list, search, and stat files"
        )
        self._register_tools()

    def _register_tools(self):
        """Register all filesystem tools."""
        self._register_tool(ToolDefinition(
            name="read_file",
            description="Read the contents of a file. Returns the file content as text.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read (absolute or relative)"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default: utf-8)",
                        "default": "utf-8"
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Maximum number of lines to read (default: all)",
                        "default": 0
                    },
                },
                "required": ["path"],
            },
            category="filesystem",
            tags=["read", "file"],
            cacheable=True,
            timeout_ms=10000,
        ))

        self._register_tool(ToolDefinition(
            name="write_file",
            description="Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default: utf-8)",
                        "default": "utf-8"
                    },
                },
                "required": ["path", "content"],
            },
            category="filesystem",
            tags=["write", "file"],
            cacheable=False,
            timeout_ms=10000,
        ))

        self._register_tool(ToolDefinition(
            name="list_dir",
            description="List files and directories in a given path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to filter files (e.g., '*.py')",
                        "default": "*"
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Whether to list recursively",
                        "default": False
                    },
                },
                "required": ["path"],
            },
            category="filesystem",
            tags=["list", "directory"],
            cacheable=True,
            timeout_ms=5000,
        ))

        self._register_tool(ToolDefinition(
            name="search_files",
            description="Search for files matching a pattern. Supports glob patterns and recursive search.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory to search in"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match (e.g., '**/*.py')"
                    },
                    "exclude": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Patterns to exclude",
                        "default": []
                    },
                },
                "required": ["directory", "pattern"],
            },
            category="filesystem",
            tags=["search", "file"],
            cacheable=True,
            timeout_ms=10000,
        ))

        self._register_tool(ToolDefinition(
            name="file_stat",
            description="Get file metadata: size, modification time, type, permissions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file"
                    },
                },
                "required": ["path"],
            },
            category="filesystem",
            tags=["stat", "metadata"],
            cacheable=True,
            timeout_ms=5000,
        ))

    @staticmethod
    def _resolve_short_path_windows(path: str) -> str:
        """Windows 短文件名（8.3 格式）解析为真实长路径。"""
        if os.name != "nt":
            return path
        try:
            import ctypes
            from ctypes import wintypes
            GetLongPathNameW = ctypes.windll.kernel32.GetLongPathNameW
            GetLongPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
            GetLongPathNameW.restype = wintypes.DWORD
            buf = ctypes.create_unicode_buffer(32768)
            n = GetLongPathNameW(path, buf, len(buf))
            if n and n <= len(buf):
                return buf.value
        except Exception:
            pass
        return path

    def _resolve_path(self, path: str) -> str:
        """
        Resolve and validate a file path with strict traversal protection.

        安全层级：
        1. 拒绝 Windows 设备路径（CON, NUL, COM1 等保留名）
        2. 拒绝 UNC 路径（\\\\ 开头共享路径）
        3. 展开用户目录 ~
        4. 规范化路径分隔符，解析 ..
        5. 转为绝对路径
        6. 解析 8.3 短文件名 → 长文件名（仅 Windows）
        7. 解析符号链接 / 挂载点 → 真实路径
        8. 大小写不敏感前缀匹配白名单（Windows，带分隔符后缀防护）
        """
        # 0. 拒绝空路径 / 非字符串路径
        if not isinstance(path, str):
            raise PermissionDeniedError("path", f"Path must be a string, got {type(path).__name__}")
        if not path.strip():
            raise PermissionDeniedError("path", "Empty path is not allowed")

        # 1. 拒绝 Windows 设备路径（保留名，如 CON, NUL, COM1, LPT1）
        basename = os.path.basename(path.rstrip("/\\")).upper()
        device_names = {"CON", "PRN", "AUX", "NUL",
                        "COM1", "COM2", "COM3", "COM4", "COM5",
                        "COM6", "COM7", "COM8", "COM9",
                        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5",
                        "LPT6", "LPT7", "LPT8", "LPT9"}
        name_stripped = basename.split(".")[0]  # CON.txt → CON
        if name_stripped in device_names:
            raise PermissionDeniedError(
                "path", f"Windows reserved device path blocked: '{basename}'"
            )

        # 2. 拒绝 UNC 路径
        p_stripped = path.strip()
        if p_stripped.startswith("\\\\") or p_stripped.startswith("//"):
            raise PermissionDeniedError(
                "path", "UNC paths are not allowed (block path traversal via network share)"
            )

        # 3. 展开用户目录
        expanded = os.path.expanduser(path)
        # 4. 规范化路径分隔符，解析 ..
        normalized = os.path.normpath(expanded)
        # 5. 转为绝对路径
        if not os.path.isabs(normalized):
            normalized = os.path.abspath(normalized)
        # 6. 解析 8.3 短文件名（仅 Windows）
        resolved = self._resolve_short_path_windows(normalized)
        # 7. 解析符号链接 / 挂载点（若有）
        try:
            resolved = os.path.realpath(resolved)
        except OSError:
            pass

        # 8. 严格前缀检查：确保路径在白名单目录内
        resolved_norm = os.path.normpath(resolved)
        is_safe = False
        for root in SAFE_ROOTS:
            root_norm = os.path.normpath(os.path.abspath(root))
            # Windows 下大小写不敏感匹配
            if os.name == "nt":
                resolved_check = resolved_norm.lower()
                root_check = root_norm.lower()
            else:
                resolved_check = resolved_norm
                root_check = root_norm
            # 追加分隔符，防止 C:\Users\admin 匹配 C:\Users\admin_hacker
            root_prefix = root_check + os.sep
            if resolved_check == root_check or resolved_check.startswith(root_prefix):
                is_safe = True
                break

        if not is_safe:
            raise PermissionDeniedError(
                "read_file",
                f"Path traversal blocked: '{resolved}' is outside safe directories "
                f"(allowed: {SAFE_ROOTS})"
            )
        return resolved

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Route tool calls to the appropriate handler."""
        handlers = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_dir": self._list_dir,
            "search_files": self._search_files,
            "file_stat": self._file_stat,
        }

        handler = handlers.get(tool_name)
        if not handler:
            raise ToolExecutionError(tool_name, f"Unknown tool: {tool_name}")

        return await handler(**arguments)

    # 文件读取层缓存：key=(full_path, mtime) → content
    _file_cache: Dict[tuple, str] = {}
    _cache_max_entries: int = 128

    async def _read_file(self, path: str, encoding: str = "utf-8",
                         max_lines: int = 0) -> ToolCallResult:
        """Read a file with mtime-aware caching (auto-invalidate on change)."""
        full_path = self._resolve_path(path)

        if not os.path.exists(full_path):
            raise ToolExecutionError("read_file", f"File not found: {path}")

        if not os.path.isfile(full_path):
            raise ToolExecutionError("read_file", f"Not a file: {path}")

        # mtime + 文件大小 = 缓存失效信号
        try:
            stat = os.stat(full_path)
            cache_key = (full_path, stat.st_mtime, stat.st_size)
        except OSError:
            cache_key = None

        if cache_key and cache_key in self._file_cache:
            content = self._file_cache[cache_key]
            return ToolCallResult.text_result("read_file", content)

        try:
            with open(full_path, "r", encoding=encoding) as f:
                if max_lines > 0:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= max_lines:
                            break
                        lines.append(line)
                    content = "".join(lines)
                else:
                    content = f.read()

            # 更新缓存
            if cache_key:
                if len(self._file_cache) >= self._cache_max_entries:
                    # LRU 简单淘汰：清空一半
                    keys = list(self._file_cache.keys())
                    for k in keys[:len(keys)//2]:
                        del self._file_cache[k]
                self._file_cache[cache_key] = content

            return ToolCallResult.text_result(
                "read_file",
                content,
            )

        except UnicodeDecodeError:
            raise ToolExecutionError(
                "read_file",
                f"Cannot decode file with encoding '{encoding}'. File may be binary."
            )

    async def _write_file(self, path: str, content: str,
                          encoding: str = "utf-8") -> ToolCallResult:
        """Write to a file."""
        full_path = self._resolve_path(path)

        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w", encoding=encoding) as f:
            f.write(content)

        return ToolCallResult.text_result(
            "write_file",
            f"Successfully wrote {len(content)} characters to {path}"
        )

    async def _list_dir(self, path: str, pattern: str = "*",
                        recursive: bool = False) -> ToolCallResult:
        """List directory contents."""
        full_path = self._resolve_path(path)

        if not os.path.exists(full_path):
            raise ToolExecutionError("list_dir", f"Directory not found: {path}")

        if not os.path.isdir(full_path):
            raise ToolExecutionError("list_dir", f"Not a directory: {path}")

        items = []
        if recursive:
            for root, dirs, files in os.walk(full_path):
                for name in files:
                    if glob.fnmatch.fnmatch(name, pattern):
                        rel_path = os.path.relpath(os.path.join(root, name), full_path)
                        full = os.path.join(root, name)
                        items.append({
                            "name": rel_path,
                            "type": "file",
                            "size": os.path.getsize(full),
                            "modified": datetime.fromtimestamp(
                                os.path.getmtime(full)
                            ).isoformat(),
                        })
        else:
            for name in os.listdir(full_path):
                if glob.fnmatch.fnmatch(name, pattern):
                    full = os.path.join(full_path, name)
                    is_dir = os.path.isdir(full)
                    items.append({
                        "name": name,
                        "type": "directory" if is_dir else "file",
                        "size": 0 if is_dir else os.path.getsize(full),
                        "modified": datetime.fromtimestamp(
                            os.path.getmtime(full)
                        ).isoformat(),
                    })

        return ToolCallResult(
            tool_name="list_dir",
            content=[{
                "type": "text",
                "text": json.dumps({
                    "path": path,
                    "count": len(items),
                    "items": sorted(items, key=lambda x: x["name"]),
                }, ensure_ascii=False, indent=2),
            }],
        )

    async def _search_files(self, directory: str, pattern: str,
                            exclude: List[str] = None) -> ToolCallResult:
        """Search for files matching a pattern."""
        full_dir = self._resolve_path(directory)
        exclude = exclude or []

        matches = []
        for root, dirs, files in os.walk(full_dir):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, full_dir)

                # Check exclude patterns
                if any(glob.fnmatch.fnmatch(rel, ex) for ex in exclude):
                    continue

                if glob.fnmatch.fnmatch(rel, pattern):
                    matches.append({
                        "path": rel,
                        "size": os.path.getsize(full),
                        "modified": datetime.fromtimestamp(
                            os.path.getmtime(full)
                        ).isoformat(),
                    })

        return ToolCallResult(
            tool_name="search_files",
            content=[{
                "type": "text",
                "text": json.dumps({
                    "pattern": pattern,
                    "count": len(matches),
                    "matches": matches[:50],  # Limit to 50 results
                    "truncated": len(matches) > 50,
                }, ensure_ascii=False, indent=2),
            }],
        )

    async def _file_stat(self, path: str) -> ToolCallResult:
        """Get file metadata."""
        full_path = self._resolve_path(path)

        if not os.path.exists(full_path):
            raise ToolExecutionError("file_stat", f"File not found: {path}")

        stat = os.stat(full_path)
        is_file = os.path.isfile(full_path)

        import stat as stat_module
        perms = stat_module.filemode(stat.st_mode)

        info = {
            "path": path,
            "type": "file" if is_file else "directory",
            "size": stat.st_size,
            "size_human": _format_size(stat.st_size),
            "permissions": perms,
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
        }

        return ToolCallResult(
            tool_name="file_stat",
            content=[{
                "type": "text",
                "text": json.dumps(info, ensure_ascii=False, indent=2),
            }],
        )


def _format_size(size: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"
