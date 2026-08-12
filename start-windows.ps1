$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $AppDir ".runtime"
$VenvDir = Join-Path $RuntimeDir "venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "data") | Out-Null

if (-not (Test-Path $Python)) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "请先安装 Python 3.12 或更高版本，并启用 py 命令。"
    }
    py -3.12 -m venv $VenvDir
}

& $Python -m pip install -q -r (Join-Path $AppDir "backend\requirements.txt")
$env:FOF_DATA_DIR = Join-Path $AppDir "data"
if (-not $env:PUBLIC_FRONTEND_URL) { $env:PUBLIC_FRONTEND_URL = "http://127.0.0.1:8000" }
if (-not $env:CORS_ORIGINS) { $env:CORS_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000" }

Write-Host "FOF 系统即将启动：$env:PUBLIC_FRONTEND_URL"
Write-Host "按 Ctrl+C 停止系统。"
Set-Location (Join-Path $AppDir "backend")
& $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
