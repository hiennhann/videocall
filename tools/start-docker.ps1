[CmdletBinding()]
param(
    [switch]$Lan,
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $composeFiles = @('-f', 'docker-compose.yml')
    if ($Lan) { $composeFiles += @('-f', '.lan/compose.yml') }
    $buildFlag = if ($NoBuild) { '--no-build' } else { '--build' }

    docker compose @composeFiles up -d $buildFlag --wait
    if ($LASTEXITCODE -ne 0) { throw 'Videocall could not start. Check docker compose logs.' }

    docker compose @composeFiles rm -f migrate
    if ($LASTEXITCODE -ne 0) { throw 'Could not remove the completed migration container.' }
} finally {
    Pop-Location
}
