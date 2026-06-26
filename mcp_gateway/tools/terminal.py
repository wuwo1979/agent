"""
Terminal Tool Provider - MCP tools for terminal command execution.

Provides safe command execution with timeout, output capture, and security controls.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from typing import Any, Dict

from core.exceptions import ToolExecutionError, ToolTimeoutError
from core.types import ToolCallResult, ToolDefinition
from mcp_gateway.protocol import BaseToolProvider
from mcp_gateway.workspace import WORKSPACE_DIR

# Blocked commands for safety
BLOCKED_COMMANDS = [
    # Destructive file operations
    "rm -rf /", "rm -rf /*", "rm -r /", "rm -fr /", "rm -f /",
    "mkfs.", "dd if=", "format ", "fdisk", "parted",
    "chmod 777 /", "chmod -R 777 /", "chown -R",
    # System control
    "shutdown", "reboot", "halt", "poweroff", "init 0", "init 6",
    "systemctl poweroff", "systemctl reboot", "systemctl halt",
    # Network attacks
    ":(){ :|:& };:",  # Fork bomb
    "wget ", "curl -o ", "curl -O ",  # Download files
    # Overwrite protection
    "> /dev/", "< /dev/",
]

# Interactive commands that should not be run in non-interactive mode
INTERACTIVE_COMMANDS_PATTERNS = [
    "vim", "nano", "less ", "more ", "top", "htop",
    "tail -f", "watch ", "vi ", "ed ",
]

# ════════════════════════════════════════════════════════════
# 危险语法检测 — 防止绕过白名单
# 禁止管道、重定向、后台执行、命令替换等，避免恶意利用
# ════════════════════════════════════════════════════════════
DANGEROUS_SYNTAX_PATTERNS = [
    # ── 管道 ─────────────────────────────────────────────
    ("|", "管道 (|) 已禁用，请使用子命令参数替代"),
    # ── 重定向 ───────────────────────────────────────────
    (">>", "输出追加 (>>) 已禁用"),
    (">", "输出重定向 (>) 已禁用"),
    (" 2>", "错误重定向 (2>) 已禁用"),
    ("<", "输入重定向 (<) 已禁用"),
    # ── 后台执行 ─────────────────────────────────────────
    ("& ", "后台执行 (&) 已禁用"),
    ("&&", "链式执行 (&&) 已禁用"),
    ("||", "条件执行 (||) 已禁用"),
    # ── 命令替换 / 子 shell ──────────────────────────────
    ("$(", "命令替换 ($()) 已禁用"),
    ("`", "反引号命令替换已禁用"),
    (";", "多命令分隔符 (;) 已禁用"),
    # ── 进程替换 ─────────────────────────────────────────
    ("<(", "进程替换 (<()) 已禁用"),
    (">(", "进程替换 (>() ) 已禁用"),
]

# Maximum command length
MAX_COMMAND_LENGTH = 500

# ========== Optional whitelist mode ==========
# Set to True to enable strict command whitelist.
# Can be configured via MCP_TERMINAL_USE_WHITELIST env var ("1" or "true" to enable)
# or by setting USE_COMMAND_WHITELIST = True in this file.
USE_COMMAND_WHITELIST = os.environ.get("MCP_TERMINAL_USE_WHITELIST", "").lower() in ("1", "true", "yes")

# Allowed command prefixes (used only when USE_COMMAND_WHITELIST=True)
# Can be extended via MCP_TERMINAL_ALLOWED_COMMANDS env var (semicolon-separated)
_ALLOWED_DEFAULTS = [
    # File operations (read-only)
    "ls", "cat ", "head ", "tail ", "wc ", "find ", "grep ", "stat ",
    "du ", "df ", "tree ", "which ", "type ",
    # System info
    "uname", "date", "whoami", "id", "pwd", "echo", "hostname",
    "uptime", "ps ", "top -bn", "free ", "vmstat",
    # Git operations (read-only)
    "git status", "git log", "git diff", "git branch", "git show",
    # Directory operations
    "mkdir ", "cd ", "cp ", "mv ", "touch ",
    # Python
    "python --version", "python3 --version", "pip list", "pip freeze",
    "pip install ", "pip3 install ",
]
_env_allowed = os.environ.get("MCP_TERMINAL_ALLOWED_COMMANDS")
if _env_allowed:
    ALLOWED_COMMANDS_PREFIXES = [c.strip() for c in _env_allowed.split(";") if c.strip()]
else:
    ALLOWED_COMMANDS_PREFIXES = _ALLOWED_DEFAULTS


class TerminalToolProvider(BaseToolProvider):
    """Terminal command execution tool provider."""

    def __init__(self):
        super().__init__(
            name="terminal",
            description="Terminal command execution: run shell commands, get system info"
        )
        self._register_tools()

    def _register_tools(self):
        self._register_tool(ToolDefinition(
            name="run_command",
            description="Execute a shell command. Security: blocklist prevents dangerous operations (rm -rf, shutdown etc). "
                        "Whitelist mode can be enabled via USE_COMMAND_WHITELIST config for strict production use.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute"
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory for the command",
                        "default": "."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Command timeout in seconds (max 60)",
                        "default": 30,
                        "maximum": 60,
                    },
                },
                "required": ["command"],
            },
            category="terminal",
            tags=["command", "shell", "execute"],
            cacheable=False,
            timeout_ms=60000,
        ))

        self._register_tool(ToolDefinition(
            name="sysinfo",
            description="Get system information: OS, CPU, memory, disk usage.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
            category="terminal",
            tags=["system", "info", "diagnostic"],
            cacheable=True,
            timeout_ms=10000,
        ))

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "run_command":
            return await self._run_command(**arguments)
        elif tool_name == "sysinfo":
            return await self._sysinfo()
        else:
            raise ToolExecutionError(tool_name, f"Unknown tool: {tool_name}")

    async def _run_command(self, command: str, cwd: str = ".",
                           timeout: int = 30) -> ToolCallResult:
        """Execute a shell command with safety checks."""

        # Safety check 1: command length limit
        if len(command) > MAX_COMMAND_LENGTH:
            raise ToolExecutionError(
                "run_command",
                f"Command too long: {len(command)} chars (max {MAX_COMMAND_LENGTH})"
            )

        # Safety check 2: block dangerous commands
        cmd_lower = command.lower()
        for blocked in BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                raise ToolExecutionError(
                    "run_command",
                    f"Command blocked for safety: '{blocked}' pattern detected"
                )

        # Safety check 3: block interactive commands
        for pattern in INTERACTIVE_COMMANDS_PATTERNS:
            if pattern in cmd_lower:
                raise ToolExecutionError(
                    "run_command",
                    f"Interactive command '{pattern}' not supported in non-interactive mode"
                )

        # Safety check 4: optional whitelist (strict mode)
        if USE_COMMAND_WHITELIST:
            command_stripped = cmd_lower.strip()
            allowed = False
            for prefix in ALLOWED_COMMANDS_PREFIXES:
                if command_stripped.startswith(prefix.lower()):
                    allowed = True
                    break
            if not allowed:
                raise ToolExecutionError(
                    "run_command",
                    f"Command not in whitelist. Allowed prefixes: {', '.join(ALLOWED_COMMANDS_PREFIXES[:10])}... (config USE_COMMAND_WHITELIST=True)"
                )

        # Safety check 5: dangerous syntax check — prevents bypass of command whitelist
        for syntax, msg in DANGEROUS_SYNTAX_PATTERNS:
            if syntax in command:
                raise ToolExecutionError("run_command", f"危险语法: {msg}")

        # Safety check 6: workspace sandbox - working directory must be within workspace
        resolved_cwd = os.path.abspath(os.path.join(os.getcwd(), cwd))
        if not resolved_cwd.startswith(WORKSPACE_DIR):
            raise ToolExecutionError(
                "run_command",
                f"Working directory '{cwd}' is outside workspace '{WORKSPACE_DIR}'"
            )

        timeout = min(timeout, 60)

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            result = {
                "exit_code": process.returncode,
                "stdout": stdout_text[:10000],
                "stderr": stderr_text[:5000],
                "truncated": len(stdout_text) > 10000 or len(stderr_text) > 5000,
            }

            return ToolCallResult(
                tool_name="run_command",
                content=[{
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False, indent=2),
                }],
                is_error=process.returncode != 0,
            )

        except asyncio.TimeoutError:
            raise ToolTimeoutError("run_command", timeout * 1000)

    async def _sysinfo(self) -> ToolCallResult:
        """Get system information."""
        info = {"platform": "windows"}

        try:
            # Try to get CPU info
            result = subprocess.run(
                ["wmic", "cpu", "get", "name,NumberOfCores,MaxClockSpeed"],
                capture_output=True, text=True, timeout=5,
            )
            info["cpu"] = result.stdout.strip()
        except Exception:
            info["cpu"] = "unavailable"

        try:
            # Try to get memory info
            result = subprocess.run(
                ["wmic", "OS", "get", "TotalVisibleMemorySize,FreePhysicalMemory"],
                capture_output=True, text=True, timeout=5,
            )
            info["memory"] = result.stdout.strip()
        except Exception:
            info["memory"] = "unavailable"

        try:
            info["python_version"] = __import__("sys").version
            info["cwd"] = __import__("os").getcwd()
        except Exception:
            pass

        return ToolCallResult(
            tool_name="sysinfo",
            content=[{
                "type": "text",
                "text": json.dumps(info, ensure_ascii=False, indent=2),
            }],
        )
