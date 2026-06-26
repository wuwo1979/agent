"""
Build standalone executable with PyInstaller.

Usage:
    python scripts/build_exe.py

Requires: pip install pyinstaller
Output: dist/mcp-gateway.exe  (single file, ~15MB with compression)

The executable bundles all core modules (mcp_gateway, performance,
config, core) into a single .exe file with no Python dependency required.
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build():
    # Clean previous builds
    for d in ["build", "dist"]:
        shutil.rmtree(ROOT / d, ignore_errors=True)

    # Hidden imports: modules PyInstaller can't detect automatically
    hidden = [
        "--hidden-import", "mcp_gateway",
        "--hidden-import", "mcp_gateway.protocol",
        "--hidden-import", "mcp_gateway.security",
        "--hidden-import", "mcp_gateway.server",
        "--hidden-import", "mcp_gateway.transport",
        "--hidden-import", "mcp_gateway.tools",
        "--hidden-import", "mcp_gateway.tools.filesystem",
        "--hidden-import", "mcp_gateway.tools.terminal",
        "--hidden-import", "mcp_gateway.tools.database",
        "--hidden-import", "performance",
        "--hidden-import", "performance.cache",
        "--hidden-import", "performance.parallel",
        "--hidden-import", "performance.adapter",
        "--hidden-import", "mcp_gateway.agents",
        "--hidden-import", "mcp_gateway.agents.graph",
        "--hidden-import", "mcp_gateway.agents.retry",
        "--hidden-import", "mcp_gateway.agents.supervisor",
        "--hidden-import", "mcp_gateway.agents.state",
        "--hidden-import", "mcp_gateway.agents.executor",
        "--hidden-import", "mcp_gateway.agents.planner",
        "--hidden-import", "mcp_gateway.agents.validator",
        "--hidden-import", "config",
        "--hidden-import", "config.loader",
        "--hidden-import", "core",
        "--hidden-import", "core.exceptions",
        "--hidden-import", "core.interfaces",
        "--hidden-import", "core.observability",
        "--hidden-import", "core.types",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                         # Single .exe
        "--console",                          # Console mode (CLI)
        "--name", "mcp-gateway",
        "--clean",
        "--noconfirm",
        "--strip",                           # Strip debug symbols
        *hidden,
        str(ROOT / "main.py"),
    ]

    os.chdir(ROOT)
    os.system(" ".join(cmd))

    exe_path = ROOT / "dist" / "mcp-gateway.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\nBuild OK: {exe_path} ({size_mb:.1f} MB)")
        print(f"Usage: {exe_path} --help")
        print(f"       {exe_path}                        # Start HTTP server (port 9090)")
        print(f"       {exe_path} --benchmark             # Run benchmarks")
    else:
        print("\nBuild failed: dist/mcp-gateway.exe not found")


if __name__ == "__main__":
    build()
