param(
  [switch]$WithHermes,
  [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Invoke-InProject {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][scriptblock]$Command
  )

  Push-Location $Path
  try {
    & $Command
  }
  finally {
    Pop-Location
  }
}

$buildArg = @()
if (-not $NoBuild) {
  $buildArg = @("--build")
}

Invoke-InProject "$Root\dazah-backend" {
  docker compose --profile app up -d @buildArg
}

Invoke-InProject "$Root\dazah-frontend" {
  docker compose -f docker-compose.dev.yml up -d @buildArg
}

if ($WithHermes) {
  Invoke-InProject "$Root\Hermes-Lite" {
    docker compose -f docker-compose.dev.yml up -d @buildArg
  }
}

Write-Host ""
Write-Host "Dazah development services requested."
Write-Host "Frontend: http://localhost:3000"
Write-Host "Backend:  http://localhost:8000/docs"
if ($WithHermes) {
  Write-Host "Hermes:   http://localhost:8100/health"
}
