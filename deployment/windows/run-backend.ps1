param(
    [Parameter(Mandatory = $true)]
    [string]$AppRoot,

    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$BackendRoot = Join-Path $AppRoot "backend"
$Python = Join-Path $BackendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Python virtual environment not found: $Python"
}
if (-not (Test-Path (Join-Path $BackendRoot ".env"))) {
    throw "Production configuration not found: $(Join-Path $BackendRoot '.env')"
}

Set-Location $BackendRoot

# Keep one application process while generation and notification tasks use the
# built-in durable queues. Scale only after replacing them with an external queue.
& $Python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1
if ($LASTEXITCODE -ne 0) {
    throw "FastAPI exited with code $LASTEXITCODE"
}
