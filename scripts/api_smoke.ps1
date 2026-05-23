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
$env:TOURPASS_DB_PATH = Join-Path $root "output\api-smoke-tourpass.sqlite"
Remove-Item -LiteralPath $env:TOURPASS_DB_PATH -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$($env:TOURPASS_DB_PATH)-wal" -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$($env:TOURPASS_DB_PATH)-shm" -Force -ErrorAction SilentlyContinue

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
    if ($health.workers -lt 1 -or $health.job_workers -lt 1 -or $health.max_queue -lt 1 -or $health.max_in_flight -lt 1 -or $health.cache_enabled -ne $true -or $health.poi_count -ne 25 -or $health.edge_count -ne 46 -or $health.db_enabled -ne $true) {
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
    if ($null -eq $job -or $job.status -ne "SUCCEEDED" -or $null -eq $job.result -or $job.execution_ms -lt 0 -or $job.queue_wait_ms -lt 0) {
        throw "Trip job completion smoke check failed."
    }

    $metricsResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/metrics" -Method Get -UseBasicParsing
    $metrics = $metricsResponse.Content | ConvertFrom-Json
    if ($metrics.total_requests -lt 1 -or $null -eq $metrics.cache -or $null -eq $metrics.jobs -or $null -eq $metrics.db -or $metrics.max_in_flight -lt 1) {
        throw "Metrics smoke check failed."
    }

    $history = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/history/jobs?limit=5" -Method Get
    if ($null -eq $history.data) {
        throw "Job history smoke check failed."
    }

    $benchmarkBody = '{"started_at":"2026-05-22T00:00:00Z","duration_seconds":1,"concurrency_steps_json":"[1]","summary_json":"{}","report_path":"docs/performance_report.md"}'
    $benchmark = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/benchmark/runs" -Method Post -ContentType "application/json; charset=utf-8" -Body $benchmarkBody
    if ($benchmark.status -ne "recorded") {
        throw "Benchmark run record smoke check failed."
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
