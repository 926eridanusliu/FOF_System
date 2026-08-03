param(
    [Parameter(Mandatory = $true)]
    [string]$AppRoot,

    [Parameter(Mandatory = $true)]
    [string]$DataRoot,

    [Parameter(Mandatory = $true)]
    [string]$BackupRoot
)

$ErrorActionPreference = "Stop"
$BackendRoot = Join-Path $AppRoot "backend"
$Python = Join-Path $BackendRoot ".venv\Scripts\python.exe"
$Database = Join-Path $DataRoot "fof_reports.db"
$BackupScript = Join-Path $AppRoot "deployment\windows\sqlite_backup.py"

& $Python $BackupScript --source $Database --destination-dir $BackupRoot
if ($LASTEXITCODE -ne 0) {
    throw "SQLite backup failed"
}

# Generated documents and uploaded images are runtime business records too.
$RuntimeBackup = Join-Path $BackupRoot "runtime-files"
New-Item -ItemType Directory -Force -Path $RuntimeBackup | Out-Null
foreach ($Directory in @("generated_reports", "uploaded_images", "uploaded_nav", "report_versions")) {
    $Source = Join-Path $DataRoot $Directory
    if (Test-Path $Source) {
        Copy-Item $Source -Destination $RuntimeBackup -Recurse -Force
    }
}

Write-Host "Database and runtime files backed up to: $BackupRoot"
