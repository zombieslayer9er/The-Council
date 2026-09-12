[CmdletBinding()]
param(
    [string]$Image = "freqtradeorg/freqtrade:2026.8"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeFile = Join-Path $workspaceRoot "integrations\freqtrade\compose.yaml"
$userDataDirectory = Join-Path $workspaceRoot "integrations\freqtrade\user_data"

New-Item -ItemType Directory -Force -Path $userDataDirectory | Out-Null

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$perUserDocker = Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin\docker.exe"
if ($dockerCommand) {
    $dockerExe = $dockerCommand.Source
} elseif (Test-Path -LiteralPath $perUserDocker) {
    $dockerExe = $perUserDocker
} else {
    throw "Docker is not installed or is not on PATH. Install and start Docker Desktop first."
}

$env:BOTNET_COUNCIL_WORKSPACE = $workspaceRoot
$env:FREQTRADE_IMAGE = $Image

& $dockerExe info | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is installed but its engine is not ready."
}

& $dockerExe compose --project-directory (Split-Path $composeFile) --file $composeFile pull freqtrade
if ($LASTEXITCODE -ne 0) {
    throw "Unable to pull the pinned Freqtrade image."
}

& $dockerExe compose --project-directory (Split-Path $composeFile) --file $composeFile run --rm --no-deps -T freqtrade --version
if ($LASTEXITCODE -ne 0) {
    throw "The Freqtrade container did not pass its version probe."
}
