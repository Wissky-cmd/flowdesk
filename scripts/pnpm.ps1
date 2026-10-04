$ErrorActionPreference = 'Stop'
$pnpmCommand = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
if ($pnpmCommand) {
    & $pnpmCommand.Source @args
} else {
    $bundledPnpm = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/pnpm/bin/pnpm.cjs'
    if (-not (Test-Path -LiteralPath $bundledPnpm)) { throw '请先安装 pnpm 11.25.0，或使用已安装的 Codex Node 运行时。' }
    & node $bundledPnpm @args
}
exit $LASTEXITCODE
