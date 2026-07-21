$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Push-Location "$Root\dazah-backend"
try {
  uv run python scripts/export_openapi.py
}
finally {
  Pop-Location
}

Push-Location "$Root\dazah-frontend"
try {
  pnpm generate:api
}
finally {
  Pop-Location
}

Write-Host ""
Write-Host "OpenAPI spec and frontend generated types are up to date."
