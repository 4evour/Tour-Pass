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
$AppPath = (Resolve-Path $AppPath).Path

if (-not (Test-Path $AppPath)) {
    throw "Tour Pass executable not found: $AppPath"
}

$env:PORT = "$Port"
$env:LLM_DISABLED = "1"

$process = $null
try {
    $process = Start-Process -FilePath $AppPath -WorkingDirectory $root -WindowStyle Hidden -PassThru

    $health = $null
    $healthResponse = $null
    for ($i = 0; $i -lt 20; $i++) {
        try {
            if ($process.HasExited) {
                throw "process exited with code $($process.ExitCode)"
            }
            $healthResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -Method Get -UseBasicParsing
            $health = $healthResponse.Content | ConvertFrom-Json
            if ($health.status -eq "ok") {
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if ($null -eq $health -or $health.status -ne "ok") {
        $state = if ($process.HasExited) { "process exited with code $($process.ExitCode)" } else { "process still running" }
        throw "Health check failed: $state"
    }
    if ([string]::IsNullOrWhiteSpace($healthResponse.Headers["X-Request-Id"])) {
        throw "Missing X-Request-Id response header."
    }
    if ([string]::IsNullOrWhiteSpace($healthResponse.Headers["X-Response-Time-Ms"])) {
        throw "Missing X-Response-Time-Ms response header."
    }
    if ($health.workers -lt 1 -or $health.max_queue -lt 1 -or $health.cache_enabled -ne $true) {
        throw "Runtime health fields are missing."
    }

    $candidateBody = Get-Content -Raw -Encoding UTF8 "docs/sample_candidate_request.json"
    $planResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/trip/plan" -Method Post -ContentType "application/json; charset=utf-8" -Body $candidateBody -UseBasicParsing
    $plan = $planResponse.Content | ConvertFrom-Json
    if ($null -eq $plan.candidates -or $plan.candidates.Count -lt 2) {
        throw "Candidate plan smoke check failed."
    }
    if ([string]::IsNullOrWhiteSpace($plan.candidates[0].days[0].summary)) {
        throw "Candidate plan summary is empty."
    }

    $routeUrl = "http://127.0.0.1:$Port/route/shortest?from=hotel_wuyi&to=yuelu_academy&algorithm=astar"
    $routeResponse = Invoke-WebRequest -Uri $routeUrl -Method Get -UseBasicParsing
    $route = $routeResponse.Content | ConvertFrom-Json
    if ($route.travel_minutes -le 0 -or $route.algorithm -ne "astar") {
        throw "Route smoke check failed."
    }
    $routeCachedResponse = Invoke-WebRequest -Uri $routeUrl -Method Get -UseBasicParsing
    if ($routeCachedResponse.Headers["X-Cache"] -ne "HIT") {
        throw "Route cache smoke check failed."
    }

    $jobResponse = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/trip/jobs" -Method Post -ContentType "application/json; charset=utf-8" -Body $candidateBody
    if ([string]::IsNullOrWhiteSpace($jobResponse.job_id) -or $jobResponse.status -ne "QUEUED") {
        throw "Trip job submit smoke check failed."
    }
    $job = $null
    for ($i = 0; $i -lt 40; $i++) {
        $job = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/trip/jobs/$($jobResponse.job_id)" -Method Get
        if ($job.status -eq "SUCCEEDED") {
            break
        }
        Start-Sleep -Milliseconds 250
    }
    if ($null -eq $job -or $job.status -ne "SUCCEEDED" -or $null -eq $job.result) {
        throw "Trip job completion smoke check failed."
    }

    $metricsResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/metrics" -Method Get -UseBasicParsing
    $metrics = $metricsResponse.Content | ConvertFrom-Json
    if ($metrics.total_requests -lt 1 -or $null -eq $metrics.cache -or $null -eq $metrics.jobs) {
        throw "Metrics smoke check failed."
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
