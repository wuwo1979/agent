"""
Filesystem Tool Provider - MCP tools for file system operations.

Provides read, write, list, search, and stat operations with safety checks.
References: MCP Specification tools/list, tools/call primitives.
"""

from __future__ import annotations
import os
import glob
import json
from typing import Any, Dict, List
from datetime import datetime

from core.types import ToolDefinition, ToolCallResult
from core.exceptions import ToolExecutionError, PermissionDeniedError
from mcp_gateway.protocol import BaseToolProvider

# Safe directories (prevent path traversal attacks)
SAFE_ROOTS = [
    os.getcwd(),
    os.path.expanduser("~"),
]


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

    def _resolve_path(self, path: str) -> str:
        """Resolve and validate a file path."""
        resolved = os.path.abspath(os.path.expanduser(path))
        is_safe = any(resolved.startswith(os.path.abspath(r)) for r in SAFE_ROOTS)
        if not is_safe:
            raise PermissionDeniedError(
                "read_file",
                f"Path '{resolved}' is outside safe directories"
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

    async def _read_file(self, path: str, encoding: str = "utf-8",
                         max_lines: int = 0) -> ToolCallResult:
        """Read a file."""
        full_path = self._resolve_path(path)

        if not os.path.exists(full_path):
            raise ToolExecutionError("read_file", f"File not found: {path}")

        if not os.path.isfile(full_path):
            raise ToolExecutionError("read_file", f"Not a file: {path}")

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
