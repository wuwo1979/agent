"""
Terminal Tool Provider - MCP tools for terminal command execution.

Provides safe command execution with timeout, output capture, and security controls.
"""

from __future__ import annotations
import asyncio
import json
import subprocess
from typing import Any, Dict, List

from core.types import ToolDefinition, ToolCallResult
from core.exceptions import ToolExecutionError, ToolTimeoutError
from mcp_gateway.protocol import BaseToolProvider

# Blocked commands for safety
BLOCKED_COMMANDS = [
    "rm -rf /", "mkfs.", "dd if=", ":(){ :|:& };:",  # Fork bomb
    "shutdown", "reboot", "halt", "poweroff",
    "chmod 777 /", "chown -R",
]


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
            description="Execute a shell command and return the output. Commands have a 30-second timeout.",
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
        # Safety check: block dangerous commands
        for blocked in BLOCKED_COMMANDS:
            if blocked in command:
                raise ToolExecutionError(
                    "run_command",
                    f"Command blocked for safety: '{blocked}' pattern detected"
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