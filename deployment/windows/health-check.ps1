param(
    [string]$BaseUrl = "http://127.0.0.1"
)

$ErrorActionPreference = "Stop"
$Response = Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/health" -TimeoutSec 10
if ($Response.status -ne "ok") {
    throw "Unexpected health response: $($Response | ConvertTo-Json -Compress)"
}
Write-Host "FOF system health check passed: $($Response.service)"
