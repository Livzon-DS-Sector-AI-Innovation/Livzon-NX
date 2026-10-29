param(
  # Retained for compatibility; the root stack always includes Hermes-Lite.
  [switch]$WithHermes,
  [switch]$NoBuild,
  # Review and explicitly authorize a one-shot development migration.
  [switch]$Migrate,
  # For an already authorized non-interactive invocation; never persisted.
  [string]$MigrationApproval
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $Root "compose.dev.yml"
$EnvFile = Join-Path $Root ".env.local"

if (-not (Test-Path -LiteralPath $EnvFile)) {
  throw "Missing $EnvFile. Copy .env.local.example to .env.local first."
}
if ($MigrationApproval -and -not $Migrate) {
  throw "MigrationApproval requires -Migrate."
}

function Invoke-DevCompose {
  param([string[]]$Arguments)
  docker compose --env-file $EnvFile -f $ComposeFile @Arguments
  if ($LASTEXITCODE -ne 0) { throw "Development Compose command failed." }
}

function Remove-StoppedMigrationContainers {
  # Old service containers retain their original unguarded command. A profile
  # change does not update them; remove only this project's stopped jobs.
  $MigrationContainers = @(Invoke-DevCompose -Arguments @("ps", "--all", "--quiet", "migrate"))
  foreach ($Container in $MigrationContainers) {
    if ([string]::IsNullOrWhiteSpace($Container)) { continue }
    $Running = docker inspect --format '{{.State.Running}}' $Container
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect the migration container." }
    if ($Running.Trim() -ne "false") {
      throw "A migration container is running. Review it before starting the stack."
    }
    docker rm $Container
    if ($LASTEXITCODE -ne 0) { throw "Cannot remove the stopped migration container." }
  }
}

$buildArg = @()
if (-not $NoBuild) {
  $buildArg = @("--build")
}

Push-Location $Root
try {
  Remove-StoppedMigrationContainers
  if ($Migrate) {
    if (-not $NoBuild) { Invoke-DevCompose -Arguments @("build", "migrate") }
    Invoke-DevCompose -Arguments @("up", "-d", "--wait", "--wait-timeout", "120", "db")
    $PlanJson = Invoke-DevCompose -Arguments @("run", "--rm", "--no-deps", "-T", "migrate", "plan")
    $Plan = ($PlanJson | Out-String) | ConvertFrom-Json
    Write-Host "Target: $($Plan.database)"
    Write-Host "Revision: $($Plan.current_revision) -> $($Plan.target_revision)"
    if (@($Plan.pending_revisions).Count -eq 0) {
      Write-Host "No pending migrations."
      return
    }
    Write-Warning "This operation changes the displayed development database."
    if (-not $MigrationApproval) {
      Write-Host "Type the complete confirmation: $($Plan.confirmation)"
      $MigrationApproval = Read-Host "Confirmation"
    }
    if ($MigrationApproval -cne $Plan.confirmation) {
      throw "Migration was not confirmed; no upgrade executed."
    }
    # Stdin is an ephemeral pipe. Neither the approval nor an upgrade command
    # becomes the default command of a retained Compose service container.
    $MigrationApproval | docker compose --env-file $EnvFile -f $ComposeFile run --rm --no-deps -T migrate upgrade
    if ($LASTEXITCODE -ne 0) { throw "Development migration failed." }
    Invoke-DevCompose -Arguments @("run", "--rm", "--no-deps", "-T", "migrate", "check")
    Write-Host "Migration verified. Start the stack with .\scripts\dev.ps1 -NoBuild."
    return
  }
  Invoke-DevCompose -Arguments (@("up", "-d") + $buildArg)
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
