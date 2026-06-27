# ============================================================
# 下载 llama-server (CUDA 12.4) 替代 Ollama CUDA 崩溃问题
# ============================================================
# 
# RTX 3060 Laptop GPU 上 Ollama 0.3.x 存在 CUDA 兼容缺陷
# (exit code 0xc0000409, stack-based buffer overrun)。
# 使用 llama.cpp 的 llama-server 替代。
#
# 用法:
#   powershell -ExecutionPolicy Bypass -File scripts/download_llama_server.ps1
#
# 下载后运行:
#   .\llama.cpp\build\bin\Release\llama-server.exe -m <MODEL_PATH> --port 11434 --host 0.0.0.0
# ============================================================

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$OutDir = Join-Path $PSScriptRoot ".." "llama.cpp"
$OutDir = (Resolve-Path $OutDir -ErrorAction SilentlyContinue) ?? (New-Item -ItemType Directory -Path $OutDir -Force).FullName
$ZipPath = Join-Path $OutDir "llama-b3997-cu12.4.0-win64.zip"

$Url = "https://github.com/ggml-org/llama.cpp/releases/download/b3997/llama-b3997-cu12.4.0-win64.zip"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  下载 llama-server CUDA 12.4" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "文件大小: 391 MB"
Write-Host "保存到: $ZipPath"
Write-Host "解压到: $OutDir"
Write-Host ""

# --- 检查是否已有 ---
$ExistingExe = Get-ChildItem $OutDir -Recurse -Filter "llama-server.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ExistingExe) {
    Write-Host "[OK] 已存在 llama-server.exe ($($ExistingExe.Length) bytes)" -ForegroundColor Green
    Write-Host "    路径: $($ExistingExe.FullName)"
    exit 0
}

# --- 下载 ---
Write-Host "下载 llama-server CUDA 12.4 (391 MB)..." -ForegroundColor Yellow
try {
    # 方法1: Start-BitsTransfer (推荐，支持断点续传)
    $bitsJob = Start-BitsTransfer -Source $Url -Destination $ZipPath -Asynchronous -Priority High
    do {
        Start-Sleep -Seconds 2
        $bitsJob = Get-BitsTransfer -JobId $bitsJob.Id
        $pct = [math]::Round($bitsJob.BytesTransferred / $bitsJob.BytesTotal * 100, 1)
        Write-Host "  进度: $pct% ($([math]::Round($bitsJob.BytesTransferred / 1MB, 1)) MB / $([math]::Round($bitsJob.BytesTotal / 1MB, 1)) MB)" -NoNewline
        # 清除行以便刷新
        Write-Host "`r" -NoNewline
    } while ($bitsJob.JobState -eq "Transferring")
    Complete-BitsTransfer -BitsJob $bitsJob
}
catch {
    Write-Host "  BITS 失败，改用 Invoke-WebRequest..." -ForegroundColor DarkYellow
    # 方法2: Invoke-WebRequest 回退
    Invoke-WebRequest -Uri $Url -OutFile $ZipPath -UseBasicParsing -TimeoutSec 3600
}

# --- 解压 ---
Write-Host "`n下载完成！" -ForegroundColor Green
Write-Host "解压到: $OutDir"
try {
    Expand-Archive -Path $ZipPath -DestinationPath $OutDir -Force
    Write-Host "解压完成！" -ForegroundColor Green
}
catch {
    Write-Host "解压失败: $_" -ForegroundColor Red
    Write-Host "请手动解压: $ZipPath → $OutDir"
    exit 1
}

# --- 验证 ---
$ExeFiles = Get-ChildItem $OutDir -Recurse -Filter "llama-server.exe" -ErrorAction SilentlyContinue
if ($ExeFiles) {
    Write-Host "" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  llama-server 就绪！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    foreach ($exe in $ExeFiles) {
        Write-Host "  路径: $($exe.FullName)"
        Write-Host "  大小: $([math]::Round($exe.Length / 1MB, 1)) MB"
    }
    Write-Host ""
    Write-Host "启动示例:" -ForegroundColor Cyan
    Write-Host "  .\llama.cpp\build\bin\Release\llama-server.exe -m D:\models\qwen2.5-7b-q4.gguf --port 11434 --host 0.0.0.0"
    Write-Host ""
} else {
    Write-Host "[WARN] 未找到 llama-server.exe，请检查解压目录" -ForegroundColor Yellow
}