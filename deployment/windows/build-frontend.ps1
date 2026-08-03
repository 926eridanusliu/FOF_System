param(
    [Parameter(Mandatory = $true)]
    [string]$AppRoot
)

$ErrorActionPreference = "Stop"
$FrontendRoot = Join-Path $AppRoot "frontend"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is not installed or is not in PATH"
}
if (-not (Test-Path (Join-Path $FrontendRoot "package-lock.json"))) {
    throw "Frontend project not found: $FrontendRoot"
}

Set-Location $FrontendRoot
npm ci
if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
npm run test
if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed" }
npm run build
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }

Write-Host "Frontend production files: $(Join-Path $FrontendRoot 'dist')"
