param(
    [string]$Url = "http://127.0.0.1:8080/health",
    [int]$Concurrency = 100,
    [string]$Duration = "30s"
)

$hey = Get-Command hey -ErrorAction SilentlyContinue
if (-not $hey) {
    Write-Error "hey is not installed. Install it with: go install github.com/rakyll/hey@latest"
    exit 1
}

Write-Host "Running hey: hey -z $Duration -c $Concurrency $Url"
& $hey.Source -z $Duration -c $Concurrency $Url
