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
$env:TOURPASS_JWT_SECRET = "ci-smoke-test-secret-32chars!"
$env:TOURPASS_DB_PATH = Join-Path $root "output\api-smoke-tourpass.sqlite"
$minPoiCount = 100
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
    $healthProblems = @()
    if ($health.status -ne "ok") { $healthProblems += "status=$($health.status)" }
    if ($health.total_poi_count -lt $minPoiCount) { $healthProblems += "total_poi_count=$($health.total_poi_count), min=$minPoiCount" }
    # edge_count is now per-city; skip top-level check
    # travel_provider no longer in health response; skip
    if ($healthProblems.Count -gt 0) {
        $healthJson = $health | ConvertTo-Json -Depth 8 -Compress
        throw "Runtime health check failed: $($healthProblems -join '; '). Health: $healthJson"
    }

    $authBody = '{"username":"ci_smoke_user","password":"ci_smoke_password"}'
    $auth = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/auth/register" -Method Post -ContentType "application/json; charset=utf-8" -Body $authBody
    if ([string]::IsNullOrWhiteSpace($auth.token)) {
        throw "Auth smoke check failed: register did not return a token."
    }
    $authHeaders = @{ Authorization = "Bearer $($auth.token)" }

    $candidateBody = Get-Content -Raw -Encoding UTF8 "docs/sample_candidate_request.json"
    $planResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/trip/plan" -Method Post -ContentType "application/json; charset=utf-8" -Headers $authHeaders -Body $candidateBody -UseBasicParsing
    $plan = $planResponse.Content | ConvertFrom-Json
    if ($null -eq $plan.candidates -or $plan.candidates.Count -lt 2) {
        throw "Candidate plan smoke check failed."
    }
    if ([string]::IsNullOrWhiteSpace($plan.candidates[0].days[0].summary)) {
        throw "Candidate plan summary is empty."
    }

    $sampleEdge = (Get-Content -Raw -Encoding UTF8 "data/edges.json" | ConvertFrom-Json)[0]
    if ([string]::IsNullOrWhiteSpace($sampleEdge.from) -or [string]::IsNullOrWhiteSpace($sampleEdge.to)) {
        throw "Route smoke setup failed: data/edges.json does not contain a usable sample edge."
    }
    $routeFrom = [System.Uri]::EscapeDataString($sampleEdge.from)
    $routeTo = [System.Uri]::EscapeDataString($sampleEdge.to)
    $routeUrl = "http://127.0.0.1:$Port/route/shortest?from=$routeFrom&to=$routeTo&algorithm=astar"
    $routeResponse = Invoke-WebRequest -Uri $routeUrl -Method Get -Headers $authHeaders -UseBasicParsing
    $route = $routeResponse.Content | ConvertFrom-Json
    if ($route.travel_minutes -le 0 -or $route.algorithm -ne "astar") {
        throw "Route smoke check failed."
    }
    $routeCachedResponse = Invoke-WebRequest -Uri $routeUrl -Method Get -Headers $authHeaders -UseBasicParsing
    if ($routeCachedResponse.Headers["X-Cache"] -ne "HIT") {
        throw "Route cache smoke check failed."
    }

    $jobResponse = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/trip/jobs" -Method Post -ContentType "application/json; charset=utf-8" -Headers $authHeaders -Body $candidateBody
    if ([string]::IsNullOrWhiteSpace($jobResponse.job_id) -or $jobResponse.status -ne "QUEUED") {
        throw "Trip job submit smoke check failed."
    }
    $job = $null
    for ($i = 0; $i -lt 40; $i++) {
        $job = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/trip/jobs/$($jobResponse.job_id)" -Method Get -Headers $authHeaders
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

    $history = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/history/jobs?limit=5" -Method Get -Headers $authHeaders
    if ($null -eq $history.data) {
        throw "Job history smoke check failed."
    }

    $benchmarkBody = '{"started_at":"2026-05-22T00:00:00Z","duration_seconds":1,"concurrency_steps_json":"[1]","summary_json":"{}","report_path":"docs/performance_report.md"}'
    $benchmark = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/benchmark/runs" -Method Post -ContentType "application/json; charset=utf-8" -Headers $authHeaders -Body $benchmarkBody
    if ($benchmark.status -ne "recorded") {
        throw "Benchmark run record smoke check failed."
    }

    $alternatives = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/trip/alternatives" -Method Post -ContentType "application/json; charset=utf-8" -Headers $authHeaders -Body '{"scenario":"下雨","limit":3}'
    if ($null -eq $alternatives.data) {
        throw "Alternatives smoke check failed."
    }

    Write-Host "API smoke checks passed on http://127.0.0.1:$Port"
} finally {
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
}
