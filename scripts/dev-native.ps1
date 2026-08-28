[CmdletBinding()]
param(
  # Rebuild the EDBO development image before starting infrastructure.
  [switch]$NoBuild,

  # Synchronize the native Python and Node dependencies before starting.
  [switch]$Sync,

  # Skip the native Alembic migration. Use only when the schema is already up
  # to date; the default is to migrate before starting the backend.
  [switch]$SkipMigrations,

  # Use the existing Webpack development command if Turbopack is unsuitable
  # for a local environment.
  [switch]$FrontendWebpack
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ComposeFile = Join-Path $Root "compose.dev.yml"
$EnvFile = Join-Path $Root ".env.local"
$BackendDir = Join-Path $Root "dazah-backend"
$FrontendDir = Join-Path $Root "dazah-frontend"
$HermesDir = Join-Path $Root "Hermes-Lite"
$HermesHome = Join-Path $Root ".dev-data\hermes"
$HermesTmpfs = Join-Path $HermesHome "feishu-tmp"
$HermesLockDir = Join-Path $HermesHome "gateway-locks"

$NativeProcesses = @()

function Get-ProcessEnvValue {
  param([Parameter(Mandatory)][string]$Name)

  return [Environment]::GetEnvironmentVariable($Name, "Process")
}

function Set-ProcessEnvValue {
  param(
    [Parameter(Mandatory)][string]$Name,
    [AllowNull()][string]$Value
  )

  if ($null -eq $Value) {
    Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
  }
  else {
    Set-Item -LiteralPath "Env:$Name" -Value $Value
  }
}

function Import-DotEnvFile {
  param([Parameter(Mandatory)][string]$Path)

  # Compose supports the same basic KEY=VALUE format. Loading the file into
  # this process lets Docker and all native child processes share one config
  # source without copying secrets into service directories.
  foreach ($RawLine in Get-Content -LiteralPath $Path) {
    $Line = $RawLine.Trim().TrimStart([char]0xFEFF)
    if ([string]::IsNullOrWhiteSpace($Line) -or $Line.StartsWith("#")) {
      continue
    }
    if ($Line.StartsWith("export ")) {
      $Line = $Line.Substring(7).TrimStart()
    }

    $Separator = $Line.IndexOf("=")
    if ($Separator -le 0) {
      continue
    }

    $Name = $Line.Substring(0, $Separator).Trim()
    if ($Name -notmatch "^[A-Za-z_][A-Za-z0-9_]*$") {
      continue
    }

    $Value = $Line.Substring($Separator + 1).Trim()
    $DoubleQuoted = $Value.Length -ge 2 -and $Value.StartsWith('"') -and $Value.EndsWith('"')
    $SingleQuoted = $Value.Length -ge 2 -and $Value.StartsWith("'") -and $Value.EndsWith("'")
    if ($DoubleQuoted -or $SingleQuoted) {
      $Value = $Value.Substring(1, $Value.Length - 2)
      if ($DoubleQuoted) {
        $Value = $Value.Replace('\n', "`n").Replace('\r', "`r").Replace('\"', '"')
      }
    }

    Set-ProcessEnvValue -Name $Name -Value $Value
  }
}

function Get-EnvOrDefault {
  param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][string]$Default
  )

  $Value = Get-ProcessEnvValue -Name $Name
  if ([string]::IsNullOrWhiteSpace($Value)) {
    return $Default
  }
  return $Value.Trim()
}

function Get-PortOrDefault {
  param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][int]$Default
  )

  $RawValue = Get-ProcessEnvValue -Name $Name
  if ([string]::IsNullOrWhiteSpace($RawValue)) {
    return $Default
  }

  [int]$Port = 0
  if (-not [int]::TryParse($RawValue.Trim(), [ref]$Port) -or $Port -lt 1 -or $Port -gt 65535) {
    throw "$Name must be a TCP port between 1 and 65535."
  }
  return $Port
}

function Require-Command {
  param([Parameter(Mandatory)][string]$Name)

  $Command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($null -eq $Command) {
    throw "Required command '$Name' was not found in PATH."
  }
  return $Command.Source
}

function Convert-ContainerUrlToLocal {
  param(
    [AllowEmptyString()][string]$Url,
    [Parameter(Mandatory)][string]$Fallback,
    [Parameter(Mandatory)][string[]]$ContainerHosts,
    [Parameter(Mandatory)][string]$HostName,
    [Parameter(Mandatory)][int]$Port
  )

  if ([string]::IsNullOrWhiteSpace($Url)) {
    return $Fallback
  }

  $Result = $Url.Trim()
  foreach ($ContainerHost in $ContainerHosts) {
    $EscapedHost = [regex]::Escape($ContainerHost)
    $Result = $Result -replace "(?i)@$EscapedHost(?::\d+)?(?=/)", "@${HostName}:$Port"
    $Result = $Result -replace "(?i)//$EscapedHost(?::\d+)?(?=/)", "//${HostName}:$Port"
  }

  # A previous local setup may already use localhost/127.0.0.1 but a custom
  # published port. Normalize that port as well.
  $Result = $Result -replace "(?i)@(?:localhost|127\.0\.0\.1)(?::\d+)?(?=/)", "@${HostName}:$Port"
  $Result = $Result -replace "(?i)//(?:localhost|127\.0\.0\.1)(?::\d+)?(?=/)", "//${HostName}:$Port"
  return $Result
}

function Convert-BindHostToProbeHost {
  param([Parameter(Mandatory)][string]$BindHost)

  if ($BindHost -eq "0.0.0.0" -or $BindHost -eq "::") {
    return "127.0.0.1"
  }
  return $BindHost
}

function Invoke-ExternalCommand {
  param(
    [Parameter(Mandatory)][string]$FilePath,
    [Parameter(Mandatory)][string[]]$Arguments,
    [Parameter(Mandatory)][string]$WorkingDirectory
  )

  Push-Location $WorkingDirectory
  try {
    & $FilePath @Arguments
    $ExitCode = $LASTEXITCODE
  }
  finally {
    Pop-Location
  }

  if ($ExitCode -ne 0) {
    throw "Command '$FilePath' failed with exit code $ExitCode."
  }
}

function Invoke-Compose {
  param([Parameter(Mandatory)][string[]]$Arguments)

  $CommandArguments = @($script:ComposeBaseArguments) + @($Arguments)
  & $script:DockerCommand compose @CommandArguments
  if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose command failed with exit code $LASTEXITCODE."
  }
}

function Test-ComposeExec {
  param([Parameter(Mandatory)][string[]]$Arguments)

  $CommandArguments = @($script:ComposeBaseArguments) + @("exec", "-T") + @($Arguments)
  & $script:DockerCommand compose @CommandArguments *> $null
  return $LASTEXITCODE -eq 0
}

function Test-TcpPort {
  param(
    [Parameter(Mandatory)][string]$HostName,
    [Parameter(Mandatory)][int]$Port
  )

  $Client = [System.Net.Sockets.TcpClient]::new()
  try {
    $ConnectTask = $Client.ConnectAsync($HostName, $Port)
    return $ConnectTask.Wait(1000) -and $Client.Connected
  }
  catch {
    return $false
  }
  finally {
    $Client.Dispose()
  }
}

function Test-HttpEndpoint {
  param([Parameter(Mandatory)][string]$Url)

  try {
    $Response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3 -ErrorAction Stop
    return $Response.StatusCode -ge 200 -and $Response.StatusCode -lt 300
  }
  catch {
    return $false
  }
}

function Test-DatabaseReady {
  return Test-ComposeExec -Arguments @("db", "pg_isready", "-U", $script:PostgresUser, "-d", $script:PostgresDb)
}

function Test-RedisReady {
  $Ready = Test-ComposeExec -Arguments @("redis", "redis-cli", "ping")
  if (-not $Ready) {
    return $false
  }
  return $true
}

function Wait-UntilReady {
  param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][scriptblock]$Probe,
    [Parameter(Mandatory)][int]$TimeoutSeconds
  )

  Write-Host "等待 $Name 就绪..."
  $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $Deadline) {
    Assert-NativeProcessesAlive
    if (& $Probe) {
      Write-Host "$Name 已就绪。"
      return
    }
    Start-Sleep -Seconds 2
  }
  throw "Timed out waiting for $Name."
}

function Assert-NativeProcessesAlive {
  foreach ($Entry in @($script:NativeProcesses)) {
    if ($Entry.Process.HasExited) {
      throw "$($Entry.Name) exited unexpectedly with code $($Entry.Process.ExitCode)."
    }
  }
}

function Start-NativeProcess {
  param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][string]$FilePath,
    [Parameter(Mandatory)][string[]]$Arguments,
    [Parameter(Mandatory)][string]$WorkingDirectory
  )

  Write-Host "启动本机 $Name..."
  $Process = Start-Process `
    -FilePath $FilePath `
    -ArgumentList $Arguments `
    -WorkingDirectory $WorkingDirectory `
    -NoNewWindow `
    -PassThru `
    -ErrorAction Stop

  $script:NativeProcesses += [pscustomobject]@{
    Name = $Name
    Process = $Process
  }
  return $Process
}

function Stop-NativeProcesses {
  foreach ($Entry in @($script:NativeProcesses)) {
    try {
      if (-not $Entry.Process.HasExited) {
        Write-Host "停止本机 $($Entry.Name)..."
        # Kill the complete process tree so uvicorn/Next child processes do
        # not remain attached to a later development run.
        & taskkill.exe /PID $Entry.Process.Id /T /F *> $null
      }
    }
    catch {
      # Cleanup must not hide the original startup or Ctrl+C result.
    }
  }
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
  throw "Missing $EnvFile. Copy .env.local.example to .env.local first."
}

$script:DockerCommand = Require-Command -Name "docker"
$UvCommand = Require-Command -Name "uv"
$PnpmPrefixArguments = @()
$CorepackCommandInfo = Get-Command "corepack" -ErrorAction SilentlyContinue
if ($null -ne $CorepackCommandInfo) {
  # Prefer Corepack so the packageManager field in package.json selects the
  # same pnpm version that created node_modules on every developer machine.
  $PnpmCommand = $CorepackCommandInfo.Source
  $PnpmPrefixArguments = @("pnpm")
}
else {
  $PnpmCommandInfo = Get-Command "pnpm" -ErrorAction SilentlyContinue
  if ($null -eq $PnpmCommandInfo) {
    throw "Required command 'pnpm' was not found in PATH, and Node.js Corepack is unavailable. Install pnpm or Node.js with Corepack enabled."
  }

  $PnpmCommand = $PnpmCommandInfo.Source
  Write-Warning "Node.js Corepack 不可用；将使用 PATH 中的 pnpm。"
}

$PnpmVersionExitCode = 0
Push-Location $FrontendDir
try {
  # Run from the frontend directory so Corepack reads its packageManager field.
  & $PnpmCommand @($PnpmPrefixArguments) "--version" *> $null
  $PnpmVersionExitCode = $LASTEXITCODE
}
finally {
  Pop-Location
}
if ($PnpmVersionExitCode -ne 0) {
  throw "pnpm is unavailable. Install pnpm or run 'corepack prepare pnpm@10.33.0 --activate'."
}

Import-DotEnvFile -Path $EnvFile

$ComposeBaseArguments = @("--env-file", $EnvFile, "-f", $ComposeFile)

$DbPort = Get-PortOrDefault -Name "DB_PORT" -Default 5432
$RedisPort = Get-PortOrDefault -Name "REDIS_PORT" -Default 6379
$MinioPort = Get-PortOrDefault -Name "MINIO_PORT" -Default 9000
$EdboPort = Get-PortOrDefault -Name "EDBO_PORT" -Default 8001
$BackendPort = Get-PortOrDefault -Name "BACKEND_PORT" -Default 8000
$FrontendPort = Get-PortOrDefault -Name "FRONTEND_PORT" -Default 3000
$HermesPort = Get-PortOrDefault -Name "HERMES_PORT" -Default 8100

$MinioBindHost = Get-EnvOrDefault -Name "MINIO_BIND_HOST" -Default "127.0.0.1"
$EdboBindHost = Get-EnvOrDefault -Name "EDBO_BIND_HOST" -Default "127.0.0.1"
$BackendBindHost = Get-EnvOrDefault -Name "BACKEND_BIND_HOST" -Default "127.0.0.1"
$FrontendBindHost = Get-EnvOrDefault -Name "FRONTEND_BIND_HOST" -Default "127.0.0.1"
$HermesBindHost = Get-EnvOrDefault -Name "HERMES_BIND_HOST" -Default "127.0.0.1"

$script:PostgresUser = Get-EnvOrDefault -Name "POSTGRES_USER" -Default "postgres"
$PostgresPassword = Get-EnvOrDefault -Name "POSTGRES_PASSWORD" -Default "postgres"
$script:PostgresDb = Get-EnvOrDefault -Name "POSTGRES_DB" -Default "dazah"

# Native application processes must use published host ports instead of
# Compose DNS names. The Docker infrastructure itself still receives the
# original .env.local through --env-file.
Set-ProcessEnvValue -Name "APP_ENV" -Value "development"
Set-ProcessEnvValue -Name "DATABASE_URL" -Value (Convert-ContainerUrlToLocal `
  -Url (Get-ProcessEnvValue -Name "DATABASE_URL") `
  -Fallback ("postgresql+asyncpg://{0}:{1}@127.0.0.1:{2}/{3}" -f `
    [Uri]::EscapeDataString($script:PostgresUser),
    [Uri]::EscapeDataString($PostgresPassword),
    $DbPort,
    $script:PostgresDb) `
  -ContainerHosts @("db") `
  -HostName "127.0.0.1" `
  -Port $DbPort)

$TestDatabaseUrl = Get-ProcessEnvValue -Name "TEST_DATABASE_URL"
if (-not [string]::IsNullOrWhiteSpace($TestDatabaseUrl)) {
  Set-ProcessEnvValue -Name "TEST_DATABASE_URL" -Value (Convert-ContainerUrlToLocal `
    -Url $TestDatabaseUrl `
    -Fallback $TestDatabaseUrl `
    -ContainerHosts @("db") `
    -HostName "127.0.0.1" `
    -Port $DbPort)
}

$RedisUrl = Convert-ContainerUrlToLocal `
  -Url (Get-ProcessEnvValue -Name "REDIS_URL") `
  -Fallback "redis://127.0.0.1:$RedisPort/0" `
  -ContainerHosts @("redis") `
  -HostName "127.0.0.1" `
  -Port $RedisPort
Set-ProcessEnvValue -Name "REDIS_URL" -Value $RedisUrl

$BackendUrl = "http://127.0.0.1:$BackendPort"
$HermesUrl = "http://127.0.0.1:$HermesPort"
Set-ProcessEnvValue -Name "MINIO_ENABLED" -Value "true"
Set-ProcessEnvValue -Name "MINIO_ENDPOINT" -Value "127.0.0.1:$MinioPort"
Set-ProcessEnvValue -Name "MINIO_SECURE" -Value "false"
Set-ProcessEnvValue -Name "EDBO_SERVICE_URL" -Value "http://127.0.0.1:$EdboPort"
Set-ProcessEnvValue -Name "HERMES_AGENT_V2_URL" -Value "$HermesUrl/v2/agent/runs"
Set-ProcessEnvValue -Name "HERMES_INTERNAL_URL" -Value $HermesUrl
Set-ProcessEnvValue -Name "AGENT_INTERNAL_API_BASE_URL" -Value "$BackendUrl/api/v1"
Set-ProcessEnvValue -Name "INTERNAL_API_BASE_URL" -Value $BackendUrl
Set-ProcessEnvValue -Name "API_BASE_URL" -Value $BackendUrl
Set-ProcessEnvValue -Name "DAZAH_API_BASE_URL" -Value "$BackendUrl/api/v1"
Set-ProcessEnvValue -Name "DAZAH_LLM_BASE_URL" -Value "$BackendUrl/api/v1/agent/llm"
Set-ProcessEnvValue -Name "DAZAH_API_KEY" -Value (Get-ProcessEnvValue -Name "AGENT_LLM_PROXY_TOKEN")
Set-ProcessEnvValue -Name "AGENT_TOOL_TOKEN" -Value (Get-ProcessEnvValue -Name "DAZAH_AGENT_TOOL_TOKEN")
Set-ProcessEnvValue -Name "WATCHFILES_FORCE_POLLING" -Value "false"
Set-ProcessEnvValue -Name "WATCHPACK_POLLING" -Value "false"
Set-ProcessEnvValue -Name "NODE_ENV" -Value "development"
Set-ProcessEnvValue -Name "NEXT_ALLOWED_DEV_ORIGINS" -Value (Get-EnvOrDefault `
  -Name "NEXT_ALLOWED_DEV_ORIGINS" `
  -Default "localhost,127.0.0.1,0.0.0.0")
Set-ProcessEnvValue -Name "FRONTEND_URL" -Value (Convert-ContainerUrlToLocal `
  -Url (Get-ProcessEnvValue -Name "FRONTEND_URL") `
  -Fallback "http://localhost:$FrontendPort" `
  -ContainerHosts @("frontend") `
  -HostName "localhost" `
  -Port $FrontendPort)

Set-ProcessEnvValue -Name "HERMES_HOME" -Value $HermesHome
Set-ProcessEnvValue -Name "HERMES_FEISHU_TMPFS" -Value $HermesTmpfs
Set-ProcessEnvValue -Name "HERMES_GATEWAY_LOCK_DIR" -Value $HermesLockDir

$LarkCli = Get-Command "lark-cli" -ErrorAction SilentlyContinue
if ($null -ne $LarkCli) {
  Set-ProcessEnvValue -Name "LARK_CLI_PATH" -Value $LarkCli.Source
}
else {
  # The native service can start without the optional Feishu CLI. Clearing a
  # container-only path prevents a later tool call from invoking a Unix path
  # on Windows and makes the missing optional capability explicit in Hermes.
  Set-ProcessEnvValue -Name "LARK_CLI_PATH" -Value $null
  Write-Warning "未检测到 lark-cli；Hermes 仍可启动，但飞书资源 CLI 工具不可用。"
}

New-Item -ItemType Directory -Force -Path $HermesHome, $HermesTmpfs, $HermesLockDir | Out-Null
$HermesConfig = Join-Path $HermesHome "config.yaml"
if (-not (Test-Path -LiteralPath $HermesConfig)) {
  Copy-Item -LiteralPath (Join-Path $HermesDir "config.yaml") -Destination $HermesConfig
}

if ($Sync) {
  Write-Host "同步 Backend Python 依赖..."
  Invoke-ExternalCommand -FilePath $UvCommand -Arguments @("sync", "--frozen", "--group", "dev") -WorkingDirectory $BackendDir

  Write-Host "同步 Hermes Python 依赖..."
  Invoke-ExternalCommand -FilePath $UvCommand -Arguments @("sync", "--frozen") -WorkingDirectory $HermesDir

  Write-Host "同步 Frontend Node 依赖..."
  $PnpmInstallArguments = @($PnpmPrefixArguments) + @("install", "--frozen-lockfile")
  Invoke-ExternalCommand -FilePath $PnpmCommand -Arguments $PnpmInstallArguments -WorkingDirectory $FrontendDir
}
else {
  $MissingNativeDependency = @()
  if (-not (Test-Path -LiteralPath (Join-Path $BackendDir ".venv\Scripts\python.exe"))) {
    $MissingNativeDependency += "dazah-backend/.venv"
  }
  if (-not (Test-Path -LiteralPath (Join-Path $HermesDir ".venv\Scripts\python.exe"))) {
    $MissingNativeDependency += "Hermes-Lite/.venv"
  }
  if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir "node_modules"))) {
    $MissingNativeDependency += "dazah-frontend/node_modules"
  }
  if ($MissingNativeDependency.Count -gt 0) {
    throw "Missing native dependencies: $($MissingNativeDependency -join ', '). Run .\scripts\dev-native.ps1 -Sync once."
  }
}

$ExitCode = 0
try {
  Write-Host "停止已有的 Docker 应用容器（保留数据卷）..."
  Invoke-Compose -Arguments @("stop", "app", "frontend", "hermes-lite", "migrate", "frontend-cache-init")

$ComposeUpArguments = @("up", "-d")
if (-not $NoBuild) {
  $ComposeUpArguments += "--build"
}
$ComposeUpArguments += @("db", "redis", "minio", "edbo-service")

  Write-Host "启动 Docker 基础设施：PostgreSQL、Redis、MinIO、EDBO..."
  Invoke-Compose -Arguments $ComposeUpArguments

  Wait-UntilReady -Name "PostgreSQL" -TimeoutSeconds 120 -Probe { Test-DatabaseReady }
  Wait-UntilReady -Name "Redis" -TimeoutSeconds 120 -Probe { Test-RedisReady }
  Wait-UntilReady -Name "MinIO" -TimeoutSeconds 120 -Probe {
    Test-HttpEndpoint -Url "http://$(Convert-BindHostToProbeHost $MinioBindHost):$MinioPort/minio/health/live"
  }
  Wait-UntilReady -Name "EDBO" -TimeoutSeconds 240 -Probe {
    Test-HttpEndpoint -Url "http://$(Convert-BindHostToProbeHost $EdboBindHost):$EdboPort/health"
  }

  if (-not $SkipMigrations) {
    Write-Host "执行本机 Alembic 数据库迁移..."
    Invoke-ExternalCommand -FilePath $UvCommand -Arguments @("run", "--frozen", "alembic", "upgrade", "head") -WorkingDirectory $BackendDir
  }
  else {
    Write-Warning "已跳过 Alembic 迁移；请确认开发数据库结构已是最新版本。"
  }

  $BackendProcess = Start-NativeProcess `
    -Name "Backend" `
    -FilePath $UvCommand `
    -Arguments @(
      "run", "--frozen", "uvicorn", "app.main:app",
      "--reload", "--reload-dir", "app",
      "--host", $BackendBindHost, "--port", "$BackendPort"
    ) `
    -WorkingDirectory $BackendDir

  Wait-UntilReady -Name "Backend" -TimeoutSeconds 180 -Probe {
    Test-HttpEndpoint -Url "http://$(Convert-BindHostToProbeHost $BackendBindHost):$BackendPort/health"
  }

  $HermesProcess = Start-NativeProcess `
    -Name "Hermes" `
    -FilePath $UvCommand `
    -Arguments @(
      "run", "--frozen", "uvicorn", "services.dazah_agent_service:app",
      "--host", $HermesBindHost, "--port", "$HermesPort",
      # Uvicorn's default reload filter watches Python files. Do not pass
      # wildcard include arguments here: Windows expands them before uvicorn
      # receives the command when this process is launched with Start-Process.
      "--reload", "--reload-dir", "."
    ) `
    -WorkingDirectory $HermesDir

  Wait-UntilReady -Name "Hermes" -TimeoutSeconds 180 -Probe {
    Test-HttpEndpoint -Url "http://$(Convert-BindHostToProbeHost $HermesBindHost):$HermesPort/health"
  }

  $FrontendCommandArguments = @($PnpmPrefixArguments) + @("run")
  if ($FrontendWebpack) {
    $FrontendCommandArguments += "dev:webpack"
  }
  else {
    $FrontendCommandArguments += "dev"
  }
  $FrontendCommandArguments += @("--hostname", $FrontendBindHost, "--port", "$FrontendPort")

  $FrontendProcess = Start-NativeProcess `
    -Name "Frontend" `
    -FilePath $PnpmCommand `
    -Arguments $FrontendCommandArguments `
    -WorkingDirectory $FrontendDir

  Wait-UntilReady -Name "Frontend" -TimeoutSeconds 180 -Probe {
    Test-TcpPort -HostName (Convert-BindHostToProbeHost $FrontendBindHost) -Port $FrontendPort
  }

  Write-Host ""
  Write-Host "混合开发环境已启动。"
  Write-Host "Frontend: http://localhost:$FrontendPort"
  Write-Host "Backend:  http://localhost:$BackendPort/docs"
  Write-Host "Hermes:   http://localhost:$HermesPort/health"
  Write-Host "EDBO:     http://localhost:$EdboPort/health"
  Write-Host ""
  Write-Host "当前 PowerShell 窗口会持续显示三个本机服务日志；按 Ctrl+C 停止本机服务。"
  Write-Host "PostgreSQL、Redis、MinIO、EDBO 容器会保留运行，便于下次快速启动。"

  while ($true) {
    Assert-NativeProcessesAlive
    Start-Sleep -Seconds 2
  }
}
catch {
  if ($_.Exception -is [System.Management.Automation.PipelineStoppedException]) {
    Write-Host "收到停止信号。"
  }
  else {
    $ExitCode = 1
    Write-Error $_.Exception.Message
  }
}
finally {
  Stop-NativeProcesses
}

exit $ExitCode
