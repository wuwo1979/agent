"""
启动 Ollama 为 CPU 模式。

用法:
    python scripts/ensure_ollama_cpu.py              # 静默启动
    python scripts/ensure_ollama_cpu.py --verbose    # 显示详细信息
    python scripts/ensure_ollama_cpu.py --test       # 仅测试

此脚本继承当前环境变量，因此可以确实地传递 CUDA_VISIBLE_DEVICES="" 给 ollama 进程。
"""
import argparse
import os
import signal
import subprocess
import sys
import time

OLLAMA_PID_FILE = os.path.join(os.path.dirname(__file__), "..", ".ollama_cpu_pid")


def find_ollama_processes() -> list:
    """Find all ollama processes."""
    procs = []
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq ollama.exe", "/FO", "CSV"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.strip().split("\n")[1:]:
                if line.strip():
                    parts = line.strip('"').split('","')
                    if len(parts) >= 2:
                        try:
                            procs.append(int(parts[1]))
                        except ValueError:
                            pass
        else:
            result = subprocess.run(
                ["pgrep", "-x", "ollama"], capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    try:
                        procs.append(int(line.strip()))
                    except ValueError:
                        pass
    except Exception:
        pass
    return procs


def kill_ollama(verbose: bool = False):
    """Kill all ollama processes."""
    procs = find_ollama_processes()
    if not procs:
        if verbose:
            print("  No ollama processes found")
        return

    for pid in procs:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=5)
            else:
                os.kill(pid, signal.SIGTERM)
            if verbose:
                print(f"  Killed ollama PID {pid}")
        except Exception as e:
            if verbose:
                print(f"  Failed to kill PID {pid}: {e}")

    time.sleep(2)
    remaining = find_ollama_processes()
    if remaining and verbose:
        print(f"  Warning: {len(remaining)} ollama processes still running")


def start_ollama_cpu(verbose: bool = False) -> bool:
    """Start ollama in CPU mode."""
    # Set environment variables to disable GPU
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = ""
    env["OLLAMA_HOST"] = "0.0.0.0"
    env["OLLAMA_KEEP_ALIVE"] = "24h"

    if verbose:
        print("  CUDA_VISIBLE_DEVICES=''")
        print("  OLLAMA_HOST=0.0.0.0")
        print("  OLLAMA_KEEP_ALIVE=24h")

    try:
        process = subprocess.Popen(
            ["ollama", "serve"],
            env=env,
            stdout=subprocess.DEVNULL if not verbose else None,
            stderr=subprocess.DEVNULL if not verbose else None,
        )

        # Save PID
        pid_file = os.path.abspath(OLLAMA_PID_FILE)
        with open(pid_file, "w") as f:
            f.write(str(process.pid))

        if verbose:
            print(f"  Started ollama with PID {process.pid}")

        # Wait for ready
        for i in range(30):
            time.sleep(1)
            try:
                import urllib.request
                req = urllib.request.Request("http://localhost:11434/api/tags")
                with urllib.request.urlopen(req, timeout=3):
                    if verbose:
                        print(f"  Ollama ready after {i+1}s")
                    return True
            except Exception:
                continue

        if verbose:
            print("  Ollama startup timeout (30s)")
        return False

    except FileNotFoundError:
        print("  ERROR: ollama command not found. Is Ollama installed?")
        return False
    except Exception as e:
        print(f"  ERROR starting ollama: {e}")
        return False


def test_generation(verbose: bool = False) -> bool:
    """Test if generation works (CPU mode verification)."""
    try:
        import json
        import urllib.request

        payload = json.dumps({
            "model": "qwen2.5:7b",
            "prompt": "Say 'OK' in one word",
            "stream": False,
            "options": {"num_predict": 10}
        }).encode("utf-8")

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            if "response" in result:
                if verbose:
                    print(f"  Generation: OK - '{result['response']}'")
                return True
            else:
                if verbose:
                    print(f"  Unexpected response: {result}")
                return False
    except Exception as e:
        if verbose:
            print(f"  Generation failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Start Ollama in CPU mode")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--test", "-t", action="store_true", help="Test only")
    args = parser.parse_args()

    if args.verbose:
        print("=" * 50)
        print("  Ollama CPU Mode Launcher")
        print("=" * 50)

    if args.test:
        if args.verbose:
            print("\nTesting existing Ollama state:")
        ok = test_generation(args.verbose)
        if ok:
            print("CPU mode: ACTIVE (generation works)")
        else:
            print("CPU mode: INACTIVE (generation fails - GPU mode)")
        return

    # Kill existing ollama
    if args.verbose:
        print("\n[1] Stopping existing ollama...")
    kill_ollama(args.verbose)

    # Start with CPU env
    if args.verbose:
        print("\n[2] Starting ollama (CPU mode)...")
    success = start_ollama_cpu(args.verbose)

    if success:
        print("Ollama CPU mode: STARTED")
    else:
        print("Ollama CPU mode: FAILED - check if ollama is installed")
        sys.exit(1)

    # Verify generation
    if args.verbose:
        print("\n[3] Verifying generation (CPU mode)...")
    ok = test_generation(args.verbose)
    if ok:
        print("Generation: OK (CPU mode verified)")
    else:
        print("Generation: FAILED - GPU still active")
        print("Try: $env:CUDA_VISIBLE_DEVICES=''; ollama serve")
        sys.exit(1)


if __name__ == "__main__":
    main()
