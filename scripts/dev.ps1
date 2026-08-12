param(
  # Retained for compatibility; the root stack always includes Hermes-Lite.
  [switch]$WithHermes,
  [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $Root "compose.dev.yml"
$EnvFile = Join-Path $Root ".env.local"

if (-not (Test-Path -LiteralPath $EnvFile)) {
  throw "Missing $EnvFile. Copy .env.local.example to .env.local first."
}

$buildArg = @()
if (-not $NoBuild) {
  $buildArg = @("--build")
}

Push-Location $Root
try {
  docker compose --env-file $EnvFile -f $ComposeFile up -d @buildArg
}
finally {
  Pop-Location
}

Write-Host ""
Write-Host "Dazah root development stack requested."
Write-Host "Frontend: http://localhost:3000"
Write-Host "Backend:  http://localhost:8000/docs"
Write-Host "Hermes:   http://localhost:8100/health"
Write-Host "MinIO:    http://localhost:9001"
