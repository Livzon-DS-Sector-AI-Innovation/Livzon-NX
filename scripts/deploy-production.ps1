[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [ValidateSet('Build', 'Deploy', 'Rollback', 'Status', 'Verify', 'Help')]
  [string]$Action = 'Help',

  [Parameter(Position = 1)]
  [string]$Version,

  [string]$PreviousVersion,
  [string]$Server = '150.158.111.91',
  [string]$PublicHost = '150.158.111.91',
  [string]$SshUser = 'ubuntu',
  [string]$SshKey = "$env:USERPROFILE\.ssh\id_ed25519",
  [string]$Builder = 'dazah-builder',
  [string]$BuildContext,
  [string]$ReuseUnchangedFrom,
  [string]$ReleaseRoot,
  [switch]$SkipUpload,
  [switch]$SkipDeploy,
  [switch]$NoSudo
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $Root 'compose.yml'
$Dockerfile = Join-Path $Root 'Dockerfile'
$BuildRoot = if ($BuildContext) {
  (Resolve-Path -LiteralPath $BuildContext).Path
}
else {
  $Root
}
$ReleaseBase = if ($ReleaseRoot) { $ReleaseRoot } else { Join-Path $Root 'release' }
$RemoteRoot = '/opt/dazah'
$RemoteRelease = "$RemoteRoot/releases"
$RemoteCurrent = "$RemoteRoot/current"
$RemoteScript = "$RemoteCurrent/deploy-production.sh"

function Write-Step([string]$Message) {
  Write-Host "[dazah-deploy] $Message" -ForegroundColor Cyan
}

function Fail([string]$Message) {
  throw "[dazah-deploy] $Message"
}

function Require-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Fail "找不到命令: $Name"
  }
}

function Assert-Version([string]$Value) {
  if ([string]::IsNullOrWhiteSpace($Value) -or $Value -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$') {
    Fail "版本号不合法: $Value"
  }
}

function Assert-PublicHost([string]$Value) {
  if ([string]::IsNullOrWhiteSpace($Value) -or $Value -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$') {
    Fail "公网主机名/IP 不合法: $Value"
  }
}

function Invoke-Ssh([string]$Command) {
  & ssh -i $SshKey -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SshUser@$Server" $Command
  if ($LASTEXITCODE -ne 0) {
    Fail "远程命令失败，退出码: $LASTEXITCODE"
  }
}

function Invoke-Scp([string]$Source, [string]$Destination) {
  & scp -i $SshKey -o BatchMode=yes -o StrictHostKeyChecking=accept-new $Source "$SshUser@$Server`:$Destination"
  if ($LASTEXITCODE -ne 0) {
    Fail "文件上传失败，退出码: $LASTEXITCODE"
  }
}

function Ensure-Builder {
  $existing = docker buildx ls --format '{{.Name}}' 2>$null | Where-Object { $_ -eq $Builder }
  if (-not $existing) {
    Write-Step "创建 Buildx 缓存 Builder: $Builder"
    docker buildx create --name $Builder --driver docker-container --use
  }
  else {
    docker buildx use $Builder
  }
  docker buildx inspect $Builder --bootstrap | Out-Host
}

function Build-Image([string]$Target, [string]$Image) {
  Write-Step "构建 $Image`:$Version（使用本地缓存）"
  docker buildx build `
    --builder $Builder `
    --platform linux/amd64 `
    --target $Target `
    --tag "$Image`:$Version" `
    --file $Dockerfile `
    --load `
    $BuildRoot
  if ($LASTEXITCODE -ne 0) {
    Fail "构建失败: $Image"
  }
}

function Prepare-Release {
  Assert-PublicHost $PublicHost
  $releaseDir = Join-Path $ReleaseBase $Version
  if (Test-Path -LiteralPath $releaseDir) {
    $resolvedRelease = (Resolve-Path -LiteralPath $releaseDir).Path
    Fail "本地发布目录已存在，版本发布包必须保持不可变: $resolvedRelease"
  }
  New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

  $TarPath = Join-Path $releaseDir "dazah-$Version.tar"
  Write-Step "导出应用镜像包"
  $images = @(
    "dazah/backend:$Version"
    "dazah/frontend:$Version"
  )
  if (-not $ReuseUnchangedFrom) {
    $images += "dazah/hermes-lite:$Version"
  }
  docker save @images -o $TarPath
  if ($LASTEXITCODE -ne 0) {
    Fail 'docker save 失败'
  }

  $hash = (Get-FileHash -LiteralPath $TarPath -Algorithm SHA256).Hash.ToLowerInvariant()
  "$hash  dazah-$Version.tar" |
    Set-Content -LiteralPath "$TarPath.sha256" -Encoding ascii -NoNewline
  Copy-Item -LiteralPath $ComposeFile -Destination (Join-Path $releaseDir 'compose.yml')
  Copy-Item -LiteralPath (Join-Path $Root 'deploy/compose.edge.yml') -Destination (Join-Path $releaseDir 'compose.edge.yml')
  $nginxTemplate = Get-Content -Raw -LiteralPath (Join-Path $Root 'deploy/nginx.default.conf.template')
  $nginxConfig = $nginxTemplate.Replace('__PUBLIC_HOST__', $PublicHost)
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText((Join-Path $releaseDir 'nginx.default.conf'), $nginxConfig, $utf8NoBom)
  Copy-Item -LiteralPath (Join-Path $Root 'scripts/deploy-production-remote.sh') -Destination (Join-Path $releaseDir 'deploy-production.sh')

  Write-Step "发布包已生成: $releaseDir"
  Get-Item -LiteralPath $TarPath, "$TarPath.sha256", (Join-Path $releaseDir 'compose.yml') |
    Select-Object FullName, Length | Format-Table -AutoSize | Out-Host
  return $releaseDir
}

function Upload-Release([string]$ReleaseDir) {
  Write-Step "上传发布包到服务器"
  $staging = "/tmp/dazah-release-$Version"
  $sudo = if ($NoSudo) { '' } else { 'sudo ' }
  Invoke-Ssh "${sudo}rm -rf $staging; ${sudo}mkdir -p $staging; ${sudo}chown $SshUser`:$SshUser $staging"
  foreach ($name in @(
      "dazah-$Version.tar",
      "dazah-$Version.tar.sha256",
      'compose.yml',
      'compose.edge.yml',
      'nginx.default.conf',
      'deploy-production.sh'
    )) {
    Invoke-Scp (Join-Path $ReleaseDir $name) "$staging/"
  }
  Invoke-Ssh "if ${sudo}test -e $RemoteRelease/$Version; then echo '远端版本目录已存在，拒绝覆盖' >&2; exit 1; fi; ${sudo}mkdir -p $RemoteRelease/$Version; ${sudo}mv $staging/* $RemoteRelease/$Version/; ${sudo}rmdir $staging; ${sudo}install -m 0755 $RemoteRelease/$Version/deploy-production.sh $RemoteCurrent/deploy-production.sh"
}

function Deploy-Remote {
  Write-Step "执行服务器部署"
  if ($NoSudo) {
    Invoke-Ssh "DAZAH_ALLOW_UNPRIVILEGED=1 DAZAH_DEPLOY_LOCK=$RemoteCurrent/dazah-deploy.lock bash $RemoteScript deploy $Version $RemoteRelease/$Version"
  }
  else {
    Invoke-Ssh "sudo $RemoteScript deploy $Version $RemoteRelease/$Version"
  }
}

function Tag-Remote-UnchangedImages {
  if (-not $ReuseUnchangedFrom) {
    return
  }
  Assert-Version $ReuseUnchangedFrom
  Write-Step "复用未变化的 Hermes 镜像: $ReuseUnchangedFrom"
  $docker = if ($NoSudo) { 'docker' } else { 'sudo docker' }
  Invoke-Ssh "$docker image inspect dazah/hermes-lite:$ReuseUnchangedFrom >/dev/null; $docker tag dazah/hermes-lite:$ReuseUnchangedFrom dazah/hermes-lite:$Version"
}

function Build-Action {
  Assert-Version $Version
  Require-Command docker
  if (-not $SkipUpload) {
    Require-Command ssh
    Require-Command scp
  }
  Ensure-Builder
  Build-Image 'backend' 'dazah/backend'
  Build-Image 'frontend' 'dazah/frontend'
  if (-not $ReuseUnchangedFrom) {
    Build-Image 'hermes' 'dazah/hermes-lite'
  }
  $releaseDir = Prepare-Release
  if (-not $SkipUpload) {
    Upload-Release $releaseDir
  }
  if (-not $SkipDeploy) {
    Tag-Remote-UnchangedImages
    Deploy-Remote
  }
}

function Deploy-Action {
  Assert-Version $Version
  Require-Command ssh
  if (-not $SkipUpload) {
    Require-Command scp
  }
  $releaseDir = Join-Path $ReleaseBase $Version
  if (-not (Test-Path -LiteralPath $releaseDir)) {
    Fail "找不到本地发布目录: $releaseDir"
  }
  if (-not $SkipUpload) {
    Upload-Release $releaseDir
  }
  if (-not $SkipDeploy) {
    Tag-Remote-UnchangedImages
    Deploy-Remote
  }
}

function Remote-Action([string]$RemoteAction, [string]$TargetVersion) {
  Require-Command ssh
  $arguments = if ($TargetVersion) {
    "$RemoteAction $TargetVersion $RemoteRelease/$TargetVersion"
  }
  else {
    $RemoteAction
  }
  $command = if ($NoSudo) {
    "DAZAH_ALLOW_UNPRIVILEGED=1 DAZAH_DEPLOY_LOCK=$RemoteCurrent/dazah-deploy.lock bash $RemoteScript $arguments"
  }
  else {
    "sudo $RemoteScript $arguments"
  }
  Invoke-Ssh $command
}

function Show-Help {
  @'
Dazah 生产离线部署脚本

首次或完整更新（构建、导出、上传、部署）：
  .\scripts\deploy-production.ps1 Build -Version 20260813-a1b2c3d

使用已有发布包上传并部署：
  .\scripts\deploy-production.ps1 Deploy -Version 20260813-a1b2c3d

回滚到已上传的历史版本：
  .\scripts\deploy-production.ps1 Rollback -Version 20260813-67bf77b

查询线上状态：
  .\scripts\deploy-production.ps1 Status

验证线上当前版本：
  .\scripts\deploy-production.ps1 Verify

仅本地构建并保留发布包：
  .\scripts\deploy-production.ps1 Build -Version 20260813-a1b2c3d -SkipUpload -SkipDeploy

注意：
  - 生产 .env 始终只保留在服务器，不会被脚本下载或覆盖。
  - 构建使用持久 Buildx 缓存；不要随意执行 docker builder prune。
  - 回滚只切换镜像和 Compose 配置，不自动回滚已经执行的数据库迁移。
'@ | Write-Host
}

try {
  switch ($Action) {
    'Build' { Build-Action }
    'Deploy' { Deploy-Action }
    'Rollback' {
      $target = if ($PreviousVersion) { $PreviousVersion } else { $Version }
      Assert-Version $target
      Remote-Action 'rollback' $target
    }
    'Status' { Remote-Action 'status' '' }
    'Verify' { Remote-Action 'verify' '' }
    default { Show-Help }
  }
}
catch {
  Write-Error $_
  exit 1
}
