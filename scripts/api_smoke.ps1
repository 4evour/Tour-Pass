param(
    [int]$Port = 8080,
    [string]$AppPath = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ([string]::IsNullOrWhiteSpace($AppPath)) {
    $AppPath = Join-Path $root "bin/tourpass.exe"
}

if (-not (Test-Path $AppPath)) {
    throw "Tour Pass executable not found: $AppPath"
}

$env:PORT = "$Port"
$env:LLM_DISABLED = "1"

$process = $null
try {
    $process = Start-Process -FilePath $AppPath -WorkingDirectory $root -WindowStyle Hidden -PassThru

    $health = $null
    for ($i = 0; $i -lt 20; $i++) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -Method Get
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if ($null -eq $health -or $health.status -ne "ok") {
        throw "Health check failed."
    }

    $candidateBody = Get-Content -Raw -Encoding UTF8 "docs/sample_candidate_request.json"
    $plan = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/trip/plan" -Method Post -ContentType "application/json; charset=utf-8" -Body $candidateBody
    if ($null -eq $plan.candidates -or $plan.candidates.Count -lt 2) {
        throw "Candidate plan smoke check failed."
    }
    if ([string]::IsNullOrWhiteSpace($plan.candidates[0].days[0].summary)) {
        throw "Candidate plan summary is empty."
    }

    $route = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/route/shortest?from=hotel_wuyi&to=yuelu_academy&algorithm=astar" -Method Get
    if ($route.travel_minutes -le 0 -or $route.algorithm -ne "astar") {
        throw "Route smoke check failed."
    }

    $alternatives = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/trip/alternatives" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"scenario":"下雨","limit":3}'
    if ($null -eq $alternatives.data) {
        throw "Alternatives smoke check failed."
    }

    Write-Host "API smoke checks passed on http://127.0.0.1:$Port"
} finally {
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
}
