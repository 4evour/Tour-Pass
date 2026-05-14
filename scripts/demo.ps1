param(
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Building Tour Pass..." -ForegroundColor Cyan
mingw32-make build

$existing = Get-Process tourpass -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Stopping existing Tour Pass process..." -ForegroundColor Yellow
    $existing | Stop-Process -Force
}

Write-Host "Starting Tour Pass on port $Port..." -ForegroundColor Cyan
$env:PORT = "$Port"
Start-Process -FilePath "$root\bin\tourpass.exe" -WorkingDirectory $root -WindowStyle Hidden
Start-Sleep -Seconds 2

Write-Host "Health:" -ForegroundColor Green
curl.exe -sS "http://127.0.0.1:$Port/health"
Write-Host ""

Write-Host "Candidate plan smoke test:" -ForegroundColor Green
curl.exe -sS -X POST "http://127.0.0.1:$Port/trip/plan" `
    -H "Content-Type: application/json; charset=utf-8" `
    --data-binary "@docs/sample_candidate_request.json" |
    Select-String -Pattern "optimization_summary|variant_name|constraint_explanations"

Write-Host ""
Write-Host "Demo UI: http://127.0.0.1:$Port/" -ForegroundColor Cyan
