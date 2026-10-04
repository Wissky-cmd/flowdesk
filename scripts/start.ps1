$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    & .venv/Scripts/python.exe scripts/local_db.py
    if ($LASTEXITCODE) { throw 'PostgreSQL 启动失败' }
    & .venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
    if ($LASTEXITCODE) { throw '数据库迁移失败' }
    & ./scripts/seed.ps1
    $processes = @{}
    if (Test-Path .local/processes.json) {
        $saved = Get-Content .local/processes.json -Raw | ConvertFrom-Json
        foreach ($property in $saved.PSObject.Properties) { $processes[$property.Name] = $property.Value }
    }
    if (-not (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) {
        $api = Start-Process -FilePath (Join-Path $projectRoot '.venv/Scripts/python.exe') -ArgumentList 'backend/run.py' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput '.local/api.log' -RedirectStandardError '.local/api-error.log' -PassThru
        $processes.api = $api.Id
    }
    if (-not (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)) {
        $web = Start-Process -FilePath (Get-Command node).Source -ArgumentList 'node_modules/vite/bin/vite.js --host 127.0.0.1' -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput '.local/web.log' -RedirectStandardError '.local/web-error.log' -PassThru
        $processes.web = $web.Id
    }
    $processes | ConvertTo-Json | Set-Content .local/processes.json
    Write-Host 'FlowDesk: http://127.0.0.1:5173'
    Write-Host '演示账户：admin@flowdesk.example；密码见 .local/credentials.json 的 seed 字段。'
} finally { Pop-Location }
