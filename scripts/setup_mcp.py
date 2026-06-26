#!/usr/bin/env python
"""
MCP 一键接入工具 — 自动为 Trae / Cursor / VS Code / Claude / Windsurf 配置 MCP Gateway。

用法:
    python scripts/setup_mcp.py                    # 交互式向导
    python scripts/setup_mcp.py --ide trae         # 仅生成 Trae 配置
    python scripts/setup_mcp.py --ide cursor --url http://localhost:9090/mcp
    python scripts/setup_mcp.py --list             # 列出已检测到的 IDE
    python scripts/setup_mcp.py --test             # 测试 MCP 连通性

支持 IDE:
    trae      - Trae IDE (字节跳动 AI 原生 IDE)
    cursor    - Cursor IDE
    vscode    - VS Code + Claude Code 扩展
    claude    - Claude Desktop
    windsurf  - Windsurf (Codeium)
"""

import argparse
import json
import platform
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Optional

# ── 各 IDE 的 MCP 配置文件路径 ──────────────────────────────────────────

SYSTEM = platform.system()  # Windows / Darwin / Linux
HOME = Path.home()

IDE_CONFIG_PATHS = {
    "trae": {
        "Windows": HOME / "AppData" / "Roaming" / "Trae CN" / "User" / "globalStorage" / "trae" / "mcp.json",
        "Darwin": HOME / "Library" / "Application Support" / "Trae CN" / "User" / "globalStorage" / "trae" / "mcp.json",
        "Linux": HOME / ".config" / "Trae CN" / "User" / "globalStorage" / "trae" / "mcp.json",
    },
    "cursor": {
        "Windows": HOME / ".cursor" / "mcp.json",
        "Darwin": HOME / ".cursor" / "mcp.json",
        "Linux": HOME / ".cursor" / "mcp.json",
    },
    "vscode": {
        "Windows": HOME / "AppData" / "Roaming" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json",
        "Darwin": HOME / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json",
        "Linux": HOME / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json",
    },
    "claude": {
        "Windows": HOME / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
        "Darwin": HOME / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        "Linux": HOME / ".config" / "claude" / "claude_desktop_config.json",
    },
    "windsurf": {
        "Windows": HOME / ".codeium" / "windsurf" / "mcp.json",
        "Darwin": HOME / ".codeium" / "windsurf" / "mcp.json",
        "Linux": HOME / ".codeium" / "windsurf" / "mcp.json",
    },
}

# IDE 中文名称
IDE_LABELS = {
    "trae": "Trae IDE (字节跳动)",
    "cursor": "Cursor IDE",
    "vscode": "VS Code + Claude Code",
    "claude": "Claude Desktop",
    "windsurf": "Windsurf (Codeium)",
}

# ── 颜色输出 ────────────────────────────────────────────────────────────

BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
RESET = "\033[0m"


def _ensure_encoding():
    """确保 Windows 下输出不因 GBK 报错。"""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def color(text: str, code: str) -> str:
    """仅在终端支持时输出颜色。"""
    if sys.stdout.isatty() and sys.platform != "win32":
        return f"{code}{text}{RESET}"
    return text


def ok(msg: str) -> str:
    return color(f"[OK] {msg}", GREEN)


def warn(msg: str) -> str:
    return color(f"[!] {msg}", YELLOW)


def info(msg: str) -> str:
    return color(f"[*] {msg}", CYAN)


def fail(msg: str) -> str:
    return color(f"[X] {msg}", RED)


# ── 核心功能 ────────────────────────────────────────────────────────────

def detect_ides() -> list[str]:
    """检测当前系统中已安装的 IDE。"""
    detected = []
    for ide_id, paths in IDE_CONFIG_PATHS.items():
        config_path = paths.get(SYSTEM)
        if config_path is None:
            continue
        # 检查配置目录是否存在（IDE 至少安装过）
        parent = config_path.parent
        if parent.exists():
            detected.append(ide_id)
            continue
        # 备用：检查 IDE 可执行文件
        if ide_id == "trae":
            trae_path = HOME / "AppData" / "Local" / "Programs" / "Trae CN"
            if trae_path.exists():
                detected.append(ide_id)
        elif ide_id == "cursor":
            if shutil.which("cursor") or (HOME / "AppData" / "Local" / "Programs" / "Cursor").exists():
                detected.append(ide_id)
        elif ide_id == "vscode":
            if shutil.which("code") or shutil.which("code-oss"):
                detected.append(ide_id)
        elif ide_id == "windsurf":
            if shutil.which("windsurf"):
                detected.append(ide_id)
    return detected


def get_config_path(ide_id: str) -> Optional[Path]:
    """获取指定 IDE 的 MCP 配置文件路径。"""
    paths = IDE_CONFIG_PATHS.get(ide_id, {})
    return paths.get(SYSTEM)


def make_mcp_entry(server_name: str, url: str, api_key: Optional[str] = None) -> dict:
    """生成 MCP 配置条目（HTTP 模式）。"""
    entry = {
        "type": "http",
        "url": url,
    }
    if api_key:
        entry["headers"] = {"X-API-Key": api_key}
    return entry


def make_mcp_entry_stdio(server_name: str, python_path: str, project_root: str) -> dict:
    """生成 MCP 配置条目（STDIO 模式）。"""
    return {
        "type": "stdio",
        "command": python_path or sys.executable,
        "args": ["-m", "mcp_gateway.server", "--mode", "stdio"],
        "cwd": project_root,
    }


def read_mcp_config(config_path: Path) -> dict:
    """读取现有 MCP 配置文件。"""
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def write_mcp_config(config_path: Path, config: dict):
    """写入 MCP 配置文件。"""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def add_server_to_config(
    ide_id: str,
    server_name: str,
    url: str,
    api_key: Optional[str] = None,
    use_stdio: bool = False,
) -> bool:
    """
    将 MCP 服务器配置写入指定 IDE 的配置文件。

    返回 True 表示写入成功，False 表示仅输出 JSON 到终端。
    """
    config_path = get_config_path(ide_id)

    if config_path is None:
        print(fail(f"  不支持的操作系统: {SYSTEM}"))
        return False

    config = read_mcp_config(config_path)

    # 确保 mcpServers 键存在
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    if use_stdio:
        entry = make_mcp_entry_stdio(server_name, sys.executable, str(Path.cwd()))
    else:
        entry = make_mcp_entry(server_name, url, api_key)

    config["mcpServers"][server_name] = entry

    try:
        write_mcp_config(config_path, config)
        print(ok(f"  配置已写入: {config_path}"))
        print(info(f"  服务器名: {server_name}"))
        if use_stdio:
            print(info("  模式: STDIO"))
        else:
            print(info(f"  地址: {url}"))
        return True
    except PermissionError:
        print(fail(f"  权限不足，无法写入 {config_path}"))
        print(info("  请以管理员身份运行，或手动粘贴以下配置:"))
        print()
        print_json_snippet(ide_id, server_name, url, api_key, use_stdio)
        return False


def print_json_snippet(
    ide_id: str,
    server_name: str,
    url: str,
    api_key: Optional[str] = None,
    use_stdio: bool = False,
):
    """打印 JSON 配置片段，供用户手动粘贴。"""
    if use_stdio:
        entry = make_mcp_entry_stdio(server_name, sys.executable, str(Path.cwd()))
    else:
        entry = make_mcp_entry(server_name, url, api_key)

    snippet = {
        "mcpServers": {
            server_name: entry
        }
    }
    print(json.dumps(snippet, indent=2, ensure_ascii=False))


def test_connection(url: str, api_key: Optional[str] = None) -> bool:
    """测试 MCP 服务器连通性。"""
    print(f"\n{info('测试 MCP 服务器连通性...')}")

    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": "setup_test",
        "method": "tools/list",
        "params": {}
    }).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "result" in data and "tools" in data["result"]:
                tools = data["result"]["tools"]
                print(ok(f"  连接成功！发现 {len(tools)} 个可用工具:"))
                for tool in tools[:10]:  # 最多显示 10 个
                    print(f"    - {tool['name']}: {tool.get('description', '')[:60]}")
                if len(tools) > 10:
                    print(f"    ... 还有 {len(tools) - 10} 个工具")
                return True
            else:
                print(fail(f"  响应格式异常: {json.dumps(data, indent=2)[:200]}"))
                return False
    except urllib.error.URLError as e:
        print(fail(f"  无法连接: {e.reason}"))
        print(info(f"  请确认 MCP 服务器已启动: python main.py --port {_extract_port(url)}"))
        return False
    except Exception as e:
        print(fail(f"  测试失败: {e}"))
        return False


def _extract_port(url: str) -> str:
    """从 URL 中提取端口号。"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return str(parsed.port) if parsed.port else "9090"
    except Exception:
        return "9090"


# ── 交互式向导 ──────────────────────────────────────────────────────────

def interactive_wizard():
    """交互式配置向导。"""
    _ensure_encoding()
    print()
    print(color("╔══════════════════════════════════════════════╗", BOLD))
    print(color("║   MCP 本地工具网关 — 一键接入向导          ║", BOLD))
    print(color("║   为 Trae / Cursor / VS Code / Claude 配置    ║", BOLD))
    print(color("╚══════════════════════════════════════════════╝", BOLD))
    print()

    # 1. 检测已安装的 IDE
    detected = detect_ides()
    if detected:
        print(ok(f"检测到 {len(detected)} 个 IDE:"))
        for ide_id in detected:
            print(f"    [{ide_id}] {IDE_LABELS.get(ide_id, ide_id)}")
    else:
        print(warn("未检测到已安装的 IDE，仍可手动生成配置片段。"))

    print()

    # 2. 选择 IDE
    print("支持的 IDE:")
    for i, (ide_id, label) in enumerate(IDE_LABELS.items(), 1):
        marker = " [已检测到]" if ide_id in detected else ""
        print(f"  {i}. {label}{marker}")

    print()
    print("  0. 仅生成 JSON 片段（不写入文件）")
    print("  a. 生成全部 IDE 配置")

    choice = input(f"\n请选择 [1-{len(IDE_LABELS)} / 0 / a]: ").strip()

    if choice == "a":
        targets = list(IDE_LABELS.keys())
    elif choice == "0":
        targets = []
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(IDE_LABELS):
                targets = [list(IDE_LABELS.keys())[idx]]
            else:
                print(fail("无效选择"))
                return
        except ValueError:
            print(fail("无效输入"))
            return

    if not targets:
        # 仅输出 JSON
        server_name = input("服务器名称 (默认: mcp-gateway): ").strip() or "mcp-gateway"
        url = input("MCP 服务器地址 (默认: http://localhost:9090/mcp): ").strip()
        url = url or "http://localhost:9090/mcp"
        api_key = input("API Key (可选，直接回车跳过): ").strip() or None
        print()
        print(color("── JSON 配置片段（粘贴到 IDE 的 MCP 设置中）──", CYAN))
        print_json_snippet("cursor", server_name, url, api_key, use_stdio=False)
        return

    # 3. 服务器配置
    print()
    server_name = input("服务器名称 (默认: mcp-gateway): ").strip() or "mcp-gateway"

    print("\n连接模式:")
    print("  1. HTTP 模式 — 服务器已独立运行，通过 URL 连接")
    print("  2. STDIO 模式 — IDE 自动启动/管理服务器进程")

    mode_choice = input("请选择 [1/2] (默认: 1): ").strip() or "1"
    use_stdio = mode_choice == "2"

    url = ""
    api_key = None

    if not use_stdio:
        url = input("MCP 服务器地址 (默认: http://localhost:9090/mcp): ").strip()
        url = url or "http://localhost:9090/mcp"
        api_key = input("API Key (可选，直接回车跳过): ").strip() or None

    # 4. 写入配置
    print()
    for ide_id in targets:
        label = IDE_LABELS.get(ide_id, ide_id)
        print(f"\n{'─' * 50}")
        print(f"  [{ide_id}] {label}")
        print(f"{'─' * 50}")

        success = add_server_to_config(ide_id, server_name, url, api_key, use_stdio)

        if not success:
            print(warn("  请手动将上述 JSON 粘贴到对应 IDE 的 MCP 设置中"))

    # 5. 测试连接（仅 HTTP 模式）
    if not use_stdio and url:
        test_connection(url, api_key)

    # 6. 完成
    print()
    print(color("╔══════════════════════════════════════════════╗", BOLD))
    print(color("║  配置完成！                                   ║", BOLD))
    print(color("╚══════════════════════════════════════════════╝", BOLD))
    print()
    print("下一步:")
    print("  1. 重启 IDE 使配置生效")
    print("  2. 在 IDE 对话框中测试: \"列出所有可用工具\"")
    print("  3. 验证: python scripts/setup_mcp.py --test")
    print()


# ── CLI 入口 ─────────────────────────────────────────────────────────────

def main():
    _ensure_encoding()
    parser = argparse.ArgumentParser(
        description="MCP 本地工具网关 — 一键接入工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/setup_mcp.py                         # 交互式向导
  python scripts/setup_mcp.py --ide trae              # 仅生成 Trae 配置
  python scripts/setup_mcp.py --ide cursor --url http://localhost:9090/mcp
  python scripts/setup_mcp.py --list                  # 列出已检测到的 IDE
  python scripts/setup_mcp.py --test                  # 测试连通性
        """,
    )

    parser.add_argument(
        "--ide", "-i",
        choices=list(IDE_LABELS.keys()) + ["all"],
        help="目标 IDE (trae/cursor/vscode/claude/windsurf/all)"
    )
    parser.add_argument(
        "--url", "-u",
        default="http://localhost:9090/mcp",
        help="MCP 服务器 URL (默认: http://localhost:9090/mcp)"
    )
    parser.add_argument(
        "--name", "-n",
        default="mcp-gateway",
        help="MCP 服务器名称 (默认: mcp-gateway)"
    )
    parser.add_argument(
        "--api-key", "-k",
        default=None,
        help="API Key (可选)"
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="使用 STDIO 模式（IDE 自动管理进程）"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出已检测到的 IDE"
    )
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="测试 MCP 服务器连通性"
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="仅输出 JSON 配置片段，不写入文件"
    )

    args = parser.parse_args()

    # --list
    if args.list:
        detected = detect_ides()
        if detected:
            print(ok(f"检测到 {len(detected)} 个 IDE:"))
            for ide_id in detected:
                config_path = get_config_path(ide_id)
                path_info = f" → {config_path}" if config_path else ""
                print(f"  [{ide_id}] {IDE_LABELS.get(ide_id, ide_id)}{path_info}")
        else:
            print(warn("未检测到已安装的 IDE"))
        print()
        print("支持的 IDE:")
        for ide_id, label in IDE_LABELS.items():
            print(f"  [{ide_id}] {label}")
        return

    # --test
    if args.test:
        test_connection(args.url, args.api_key)
        return

    # --ide 模式
    if args.ide:
        ide_ids = list(IDE_LABELS.keys()) if args.ide == "all" else [args.ide]

        for ide_id in ide_ids:
            label = IDE_LABELS.get(ide_id, ide_id)
            print(f"\n[{ide_id}] {label}")

            if args.json_only:
                print_json_snippet(ide_id, args.name, args.url, args.api_key, args.stdio)
            else:
                success = add_server_to_config(
                    ide_id, args.name, args.url, args.api_key, args.stdio
                )
                if not success:
                    print_json_snippet(ide_id, args.name, args.url, args.api_key, args.stdio)

        if not args.stdio:
            test_connection(args.url, args.api_key)
        return

    # 默认：交互式向导
    interactive_wizard()


if __name__ == "__main__":
    main()
