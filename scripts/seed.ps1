$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
if (-not $env:SEED_PASSWORD) {
    $credentialFile = Join-Path $projectRoot '.local/credentials.json'
    if (-not (Test-Path $credentialFile)) { throw '请设置 SEED_PASSWORD（至少 12 位）后重试。' }
    $env:SEED_PASSWORD = (Get-Content -LiteralPath $credentialFile -Raw | ConvertFrom-Json).seed
}
Push-Location (Join-Path $projectRoot 'backend')
try { & ../.venv/Scripts/python.exe -m app.seed; if ($LASTEXITCODE) { throw '种子数据初始化失败' } }
finally { Pop-Location; Remove-Item Env:SEED_PASSWORD -ErrorAction SilentlyContinue }
