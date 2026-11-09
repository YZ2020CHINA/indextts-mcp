[CmdletBinding()]
param(
    [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }),
    [string]$PythonPath
)
$ErrorActionPreference = 'Stop'
foreach ($name in @('config', 'voices')) {
    $target = Join-Path $PSScriptRoot ($name + '.json')
    if (-not (Test-Path -LiteralPath $target)) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot ($name + '.example.json')) -Destination $target
    }
}
$config = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'config.json') | ConvertFrom-Json
if (-not $PythonPath) { $PythonPath = Join-Path $config.tts_root 'python_embeded/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw "Python not found: $PythonPath" }
$codexExe = (Get-Command codex -ErrorAction Stop).Source
$previousCodexHome = $env:CODEX_HOME
$previousUtf8 = $env:PYTHONUTF8
try {
    New-Item -ItemType Directory -Path $CodexHome -Force | Out-Null
    $env:CODEX_HOME = $CodexHome
    $env:PYTHONUTF8 = '1'
    & $PythonPath (Join-Path $PSScriptRoot 'scripts/build_plugin.py') --python $PythonPath
    if ($LASTEXITCODE -ne 0) { throw 'Plugin build failed' }
    & $codexExe plugin marketplace add $PSScriptRoot --json
    if ($LASTEXITCODE -ne 0) { throw 'Marketplace registration failed' }
    & $codexExe plugin add 'pink-bird-indextts@pink-bird-local' --json
    if ($LASTEXITCODE -ne 0) { throw 'Plugin install failed' }
    $listing = & $codexExe plugin list --marketplace pink-bird-local --json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot verify plugin state' }
    $state = ($listing -join "`n") | ConvertFrom-Json
    $installed = @($state.installed | Where-Object { $_.pluginId -eq 'pink-bird-indextts@pink-bird-local' -and $_.installed -and $_.enabled })
    if ($installed.Count -ne 1) { throw 'Plugin is not installed and enabled' }
    $listing
    Write-Output 'Installed. Start a new Codex chat to load the IndexTTS tools and skill.'
} finally {
    $env:CODEX_HOME = $previousCodexHome
    $env:PYTHONUTF8 = $previousUtf8
}
