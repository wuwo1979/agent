# 修复 Docker 镜像源配置
# 中科大镜像源 docker.mirrors.ustc.edu.cn 超时，移除它
# 保留 163 和百度镜像源

$daemonPath = "$env:ProgramData\Docker\config\daemon.json"

if (Test-Path $daemonPath) {
    $config = Get-Content $daemonPath -Raw | ConvertFrom-Json
    
    # 移除中科大镜像（超时）
    $config."registry-mirrors" = $config."registry-mirrors" | Where-Object { 
        $_ -notmatch "ustc" 
    }
    
    $config | ConvertTo-Json -Depth 10 | Set-Content $daemonPath -Force
    Write-Host "[OK] daemon.json 已更新，移除了中科大镜像源"
    Write-Host "当前镜像源:"
    $config."registry-mirrors" | ForEach-Object { Write-Host "  - $_" }
} else {
    Write-Host "[WARN] daemon.json 不存在于 $daemonPath"
    Write-Host "请手动检查 Docker 配置位置"
}

Write-Host ""
Write-Host "请重启 Docker Desktop 使配置生效！"