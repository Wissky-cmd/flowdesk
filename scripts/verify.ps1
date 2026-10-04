$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    & .venv/Scripts/python.exe -m pip check
    if ($LASTEXITCODE) { throw 'pip check failed' }
    & .venv/Scripts/python.exe -m alembic -c backend/alembic.ini check
    if ($LASTEXITCODE) { throw 'Migration drift detected' }
    Push-Location backend
    try { & ../.venv/Scripts/python.exe -m pytest --junitxml=../docs/evidence/pytest.xml -q; if ($LASTEXITCODE) { throw 'Backend tests failed' } }
    finally { Pop-Location }
    Push-Location frontend
    try {
        & node node_modules/vue-tsc/bin/vue-tsc.js --noEmit
        if ($LASTEXITCODE) { throw 'Type checking failed' }
        & node node_modules/vite/bin/vite.js build
        if ($LASTEXITCODE) { throw 'Frontend build failed' }
        & node node_modules/@playwright/test/cli.js test
        if ($LASTEXITCODE) { throw 'Browser tests failed' }
    } finally { Pop-Location }
} finally { Pop-Location }
