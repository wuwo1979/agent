<#
.SYNOPSIS
    MCP Gateway + Ollama (CPU mode) + 验证 — 一键启动脚本

.DESCRIPTION
    此脚本自动完成以下操作：
    1. 停止正在运行的 Ollama 进程
    2. 设置环境变量隐藏 GPU，强制 Ollama 使用 CPU 模式
    3. 启动 Ollama 服务
    4. 启动 MCP Gateway HTTP 模式（含 Ollama 代理）
    5. 运行连通性验证

    注意：需要以管理员身份运行（PowerShell）。

.PARAMETER GatewayPort
    MCP Gateway 端口（默认 9090）

.PARAMETER SkipOllama
    跳过 Ollama 启动（如果已手动启动）

.PARAMETER TestOnly
    仅运行测试，不启动任何服务

.EXAMPLE
    .\scripts\start_all.ps1                    # 一键启动全部
    .\scripts\start_all.ps1 -TestOnly          # 仅测试连通性
    .\scripts\start_all.ps1 -SkipOllama        # 跳过 Ollama 启动
#>

param(
    [int]$GatewayPort = 9090,
    [switch]$SkipOllama,
    [switch]$TestOnly,
    [switch]$Help
)

function Write-OK   { Write-Host "  [OK] $args" -ForegroundColor Green }
function Write-Warn { Write-Host "  [!] $args" -ForegroundColor Yellow }
function Write-Info { Write-Host "  [*] $args" -ForegroundColor Cyan }
function Write-Fail { Write-Host "  [X] $args" -ForegroundColor Red }
function Write-Section { param($Title) Write-Host "`n$('='*60)" -ForegroundColor DarkCyan; Write-Host "  $Title" -ForegroundColor Cyan; Write-Host "$('='*60)" -ForegroundColor DarkCyan }

if ($Help) {
    Get-Help $MyInvocation.MyCommand.Path -Detailed
    exit 0
}

# ═══════════════════════════════════════════════════════════════════
# 检查运行环境
# ═══════════════════════════════════════════════════════════════════
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

Write-Section "MCP Gateway + Ollama — 一键启动"
Write-Info "项目目录: $ProjectRoot"
Write-Info "Gateway 端口: $GatewayPort"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Fail "未找到 Python，请先安装 Python 3.10+"
    exit 1
}

# ═══════════════════════════════════════════════════════════════════
# Step 0: 仅测试模式
# ═══════════════════════════════════════════════════════════════════
if ($TestOnly) {
    Write-Section "Step 0: 运行连通性测试"

    # 测试 Ollama 直连
    Write-Info "测试 Ollama 直连..."
    $result = python -c "import urllib.request,json; r=urllib.request.urlopen('http://localhost:11434/api/tags',timeout=5); d=json.loads(r.read()); print(len(d.get('models',[])))" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Ollama 连接正常，发现 $result 个模型"
    } else {
        Write-Fail "Ollama 未运行，请先启动 Ollama"
    }

    # 测试生成
    Write-Info "测试 qwen2.5:7b 生成..."
    $test_gen = python -c "
import urllib.request, json
try:
    data = json.dumps({'model':'qwen2.5:7b','prompt':'Hi','stream':False,'options':{'num_predict':10}}).encode()
    req = urllib.request.Request('http://localhost:11434/api/generate', data=data, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    print('OK:' + d.get('response',''))
except Exception as e:
    print('FAIL:' + str(e))
" 2>&1
    if ($test_gen -match '^OK:') {
        Write-OK "生成成功: $($test_gen -replace '^OK:','')"
    } else {
        Write-Fail "生成失败: $($test_gen -replace '^FAIL:','')"
        Write-Warn "提示: 如果失败是 CUDA 兼容问题，请用 --SkipOllama 跳过并在新终端手工启动 Ollama CPU 模式:"
        Write-Info "    `$env:CUDA_VISIBLE_DEVICES=''; ollama serve"
    }

    # 测试 MCP Gateway 代理
    Write-Info "测试 MCP Gateway 代理..."
    try {
        $health = python -c "import urllib.request,json; r=urllib.request.urlopen('http://localhost:$GatewayPort/api/v1/health',timeout=5); print(json.loads(r.read())['status'])" 2>&1
        if ($health -eq 'healthy') {
            Write-OK "Gateway 运行正常"
            $proxy_test = python -c "
import urllib.request,json
r=urllib.request.urlopen('http://localhost:$GatewayPort/api/v1/ollama/proxy/api/tags',timeout=5)
d=json.loads(r.read())
print(len(d.get('models',[])))
" 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-OK "Ollama 代理正常，$proxy_test 个模型"
            } else {
                Write-Fail "Ollama 代理异常: $proxy_test"
            }
        }
    } catch {
        Write-Fail "Gateway 未运行，请先启动: python main.py --port $GatewayPort"
    }

    Write-Info "测试完成"
    exit 0
}

# ═══════════════════════════════════════════════════════════════════
# Step 1: 停止 Ollama 并重启为 CPU 模式
# ═══════════════════════════════════════════════════════════════════
if (-not $SkipOllama) {
    Write-Section "Step 1: Ollama CPU 模式重启"

    # 检查是否已有 Ollama 进程
    $existing = Get-Process ollama -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Info "发现 Ollama 进程 (PID: $($existing.Id))"
        Write-Info "正在停止旧 Ollama 进程..."
        $existing | Stop-Process -Force
        Start-Sleep -Seconds 2
        Write-OK "Ollama 已停止"
    }

    # 设置环境变量隐藏 GPU
    Write-Info "设置环境变量强制 CPU 模式..."
    $env:CUDA_VISIBLE_DEVICES = ""
    $env:OLLAMA_INTEL_GPU = "false"
    $env:OLLAMA_KEEP_ALIVE = "24h"
    $env:OLLAMA_HOST = "0.0.0.0"

    # 启动 Ollama（CPU 模式）
    Write-Info "启动 Ollama (CPU only)..."
    $ollamaProcess = Start-Process -FilePath "ollama" -ArgumentList "serve" `
        -WindowStyle Normal -PassThru -NoNewWindow

    # 等待 Ollama 就绪
    Write-Info "等待 Ollama 启动..."
    $ready = $false
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        try {
            $null = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop
            $ready = $true
            break
        } catch { }
    }

    if ($ready) {
        Write-OK "Ollama 已启动（CPU 模式，PID: $($ollamaProcess.Id)）"
    } else {
        Write-Warn "Ollama 启动超时，请检查: $env:CUDA_VISIBLE_DEVICES=''; ollama serve"
    }

    # 验证 CPU 模式生效
    $test_gen = python -c "
import urllib.request, json
try:
    data = json.dumps({'model':'qwen2.5:7b','prompt':'Hi','stream':False,'options':{'num_predict':10}}).encode()
    req = urllib.request.Request('http://localhost:11434/api/generate', data=data, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    print('OK:' + d.get('response',''))
except Exception as e:
    print('FAIL:' + str(e))
" 2>&1
    if ($test_gen -match '^OK:') {
        Write-OK "Ollama CPU 模式生成验证通过: $($test_gen -replace '^OK:','')"
    } else {
        Write-Fail "Ollama CPU 模式生成失败: $($test_gen -replace '^FAIL:','')"
        Write-Warn "提示：请在新终端手工尝试: `$env:CUDA_VISIBLE_DEVICES=''; ollama serve"
    }
} else {
    Write-Section "Step 1: 跳过 Ollama 启动（--SkipOllama）"
}

# ═══════════════════════════════════════════════════════════════════
# Step 2: 启动 MCP Gateway
# ═══════════════════════════════════════════════════════════════════
Write-Section "Step 2: 启动 MCP Gateway"

# 检查是否已有 Gateway 进程
$existingGateway = $null
try {
    $existingGateway = Invoke-WebRequest -Uri "http://localhost:$GatewayPort/api/v1/health" -TimeoutSec 2 -ErrorAction Stop
} catch { }

if ($existingGateway -and ($existingGateway.Content -match 'healthy')) {
    Write-OK "MCP Gateway 已在运行 (端口 $GatewayPort)"
} else {
    Write-Info "启动 MCP Gateway (STDIO 模式下通过 python 直接运行)..."
    Write-Info "启动命令: python main.py --host 0.0.0.0 --port $GatewayPort"

    # 启动 Gateway 在新窗口中，避免阻塞
    $gwProcess = Start-Process -FilePath "python" -ArgumentList "main.py --host 0.0.0.0 --port $GatewayPort" `
        -WindowStyle Normal -PassThru -NoNewWindow

    Start-Sleep -Seconds 3

    # 检查是否启动成功
    try {
        $health = Invoke-WebRequest -Uri "http://localhost:$GatewayPort/api/v1/health" -TimeoutSec 5 -ErrorAction Stop
        Write-OK "MCP Gateway 已启动 (PID: $($gwProcess.Id), 端口 $GatewayPort)"
    } catch {
        Write-Warn "Gateway 启动检测超时，可能正在初始化..."
        Write-Warn "可用的 API 端点:"
        Write-Info "  http://localhost:$GatewayPort/mcp                        — MCP JSON-RPC"
        Write-Info "  http://localhost:$GatewayPort/api/v1/health              — 健康检查"
        Write-Info "  http://localhost:$GatewayPort/api/v1/ollama/proxy/*      — Ollama 代理"
        Write-Info "  http://localhost:$GatewayPort/api/v1/tools/list          — 工具列表"
    }
}

# ═══════════════════════════════════════════════════════════════════
# Step 3: 运行连通性验证
# ═══════════════════════════════════════════════════════════════════
Write-Section "Step 3: 连通性验证"

# Ollama 验证
try {
    $ollamaTags = python -c "import urllib.request,json; r=urllib.request.urlopen('http://localhost:11434/api/tags',timeout=5); d=json.loads(r.read()); print(len(d.get('models',[])))" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Ollama API 正常，$ollamaTags 个模型可用"
    }
} catch { Write-Fail "Ollama API 不可用" }

# Gateway 健康检查
try {
    $gwHealth = python -c "import urllib.request,json; r=urllib.request.urlopen('http://localhost:$GatewayPort/api/v1/health',timeout=5); print(json.loads(r.read())['status'])" 2>&1
    Write-OK "Gateway 健康检查: $gwHealth"
} catch { Write-Fail "Gateway 不可用" }

# Ollama 代理验证
try {
    $proxyModels = python -c "import urllib.request,json; r=urllib.request.urlopen('http://localhost:$GatewayPort/api/v1/ollama/proxy/api/tags',timeout=5); d=json.loads(r.read()); print(len(d.get('models',[])))" 2>&1
    Write-OK "Ollama 代理: $proxyModels 个模型可通过代理访问"
} catch { Write-Fail "Ollama 代理不可用" }

# ═══════════════════════════════════════════════════════════════════
# 最终摘要
# ═══════════════════════════════════════════════════════════════════
Write-Section "启动完成 — 配置摘要"

$difyOllamaUrl = "http://host.docker.internal:$GatewayPort/api/v1/ollama/proxy"
$traeStdioCmd = "python main.py --mode stdio"

Write-Host ""
Write-Host "  ┌─────────────────────────────────────────────────────┐" -ForegroundColor DarkCyan
Write-Host "  │  MCP Gateway + Ollama 已就绪                         │" -ForegroundColor DarkCyan
Write-Host "  ├─────────────────────────────────────────────────────┤" -ForegroundColor DarkCyan
Write-Host "  │                                                     │" -ForegroundColor DarkCyan
Write-Host "  │  Dify 集成:                                         │" -ForegroundColor White
Write-Host "  │  模型供应商 → Ollama → 添加模型                      │" -ForegroundColor White
Write-Host "  │  Base URL: $($difyOllamaUrl)" -ForegroundColor Green
Write-Host "  │  模型: qwen2.5:7b                                    │" -ForegroundColor Green
Write-Host "  │                                                     │" -ForegroundColor DarkCyan
Write-Host "  │  Trae 集成:                                         │" -ForegroundColor White
Write-Host "  │  MCP 配置 → 添加工具 → STDIO                        │" -ForegroundColor White
Write-Host "  │  命令: $($traeStdioCmd)" -ForegroundColor Green
Write-Host "  │  工作目录: $($ProjectRoot)" -ForegroundColor Green
Write-Host "  │                                                     │" -ForegroundColor DarkCyan
Write-Host "  │  MCP Gateway:                                       │" -ForegroundColor White
Write-Host "  │  MCP JSON-RPC:  http://localhost:$GatewayPort/mcp         │" -ForegroundColor Yellow
Write-Host "  │  Health:         http://localhost:$GatewayPort/api/v1/health│" -ForegroundColor Yellow
Write-Host "  │  Ollama 代理:    $($difyOllamaUrl)        │" -ForegroundColor Yellow
Write-Host "  │  Tools API:     http://localhost:$GatewayPort/api/v1/tools │" -ForegroundColor Yellow
Write-Host "  └─────────────────────────────────────────────────────┘" -ForegroundColor DarkCyan
Write-Host ""

Write-Host "  $('>'*50)" -ForegroundColor DarkGray
Write-Host "  快速验证命令:" -ForegroundColor Gray
Write-Host "  python scripts/test_ollama_proxy.py --all           # 全面诊断" -ForegroundColor Gray
Write-Host "  python scripts\test_ollama_proxy.py --all --port $GatewayPort  # 包含 Gateway 代理测试" -ForegroundColor Gray
Write-Host "  $('<'*50)" -ForegroundColor DarkGray
Write-Host ""

# 如果以管理员身份运行，提示下一步
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Warn "注意: 未以管理员身份运行。如果遇到权限问题，请以管理员身份重新运行。"
}

Write-Info "下一步: 在 Dify 中添加 Ollama 模型供应商"
Write-Info "  1. 打开 http://localhost/integrations/model-provider"
Write-Info "  2. 添加 Ollama 模型供应商"
Write-Info "  3. Base URL: $difyOllamaUrl"
Write-Info "  4. 模型: qwen2.5:7b"
Write-Info "  5. 保存并验证"
Write-Info ""
Write-Info "或者运行: python scripts\test_ollama_proxy.py --all --port $GatewayPort"