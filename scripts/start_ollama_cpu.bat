@echo off
chcp 65001 >nul
title Ollama CPU Mode + MCP Gateway

echo ============================================
echo  Ollama CPU Mode + MCP Gateway 启动
echo ============================================
echo.

:: ── 1. 停止所有 Ollama 进程 ──
echo [1/4] 停止现有 Ollama 进程...
taskkill /f /im "ollama.exe" 2>nul
taskkill /f /im "ollama app.exe" 2>nul
timeout /t 3 /nobreak >nul

:: ── 2. 设置环境变量（隐藏 GPU，强制 CPU 模式） ──
echo [2/4] 设置环境变量（CUDA_VISIBLE_DEVICES=空，强制 CPU）...
set CUDA_VISIBLE_DEVICES=
set OLLAMA_HOST=0.0.0.0
set OLLAMA_KEEP_ALIVE=24h

:: ── 3. 启动 Ollama（CPU 模式） ──
echo [3/4] 启动 Ollama（CPU 模式）...
start "Ollama CPU" /B /MIN ollama serve

:: 等待 Ollama 就绪
echo  等待 Ollama 就绪...
:wait_ollama
timeout /t 2 /nobreak >nul
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 goto wait_ollama
echo  [OK] Ollama 已就绪（CPU 模式）
echo.

:: ── 4. 启动 MCP Gateway ──
echo [4/4] 启动 MCP Gateway...
start "MCP Gateway" /B /MIN python main.py --host 0.0.0.0 --port 9090

:: 等待 Gateway 就绪
:wait_gateway
timeout /t 2 /nobreak >nul
curl -s http://localhost:9090/api/v1/health >nul 2>&1
if errorlevel 1 goto wait_gateway
echo  [OK] MCP Gateway 已就绪（端口 9090）
echo.

:: ── 验证 ──
echo ============================================
echo  验证连通性
echo ============================================
python scripts\test_ollama_proxy.py --proxy --port 9090
echo.

:: ── 使用说明 ──
echo ============================================
echo  所有服务已启动！
echo ============================================
echo.
echo  Dify 集成:
echo   模型供应商 → Ollama
echo   Base URL: http://host.docker.internal:9090/api/v1/ollama/proxy
echo   模型: qwen2.5:7b
echo.
echo  Trae 集成:
echo   MCP 配置 → 添加工具 → STDIO
echo   命令: python main.py --mode stdio
echo.
echo  验证命令:
echo   python scripts\test_ollama_proxy.py --all
echo.
echo  按任意键关闭此窗口...
pause >nul