[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateSet('start', 'stop')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
# Resolve docker.exe explicitly: an extensionless docker shim can shadow it on Windows.
$dockerCommand = Get-Command docker.exe -CommandType Application -ErrorAction SilentlyContinue
if (-not $dockerCommand) {
    throw 'Docker Desktop is not installed or docker.exe is not on PATH.'
}

$composeArgs = @('compose', '--project-directory', $projectPath, '-f', (Join-Path $projectPath 'compose.yaml'))
if ($Action -eq 'start') {
    $composeArgs += @('up', '-d', '--wait', 'db', 'backend')
} else {
    $composeArgs += @('stop', 'backend', 'db')
}

if ($PSCmdlet.ShouldProcess('Feynmi backend and database', $Action)) {
    & $dockerCommand.Source @composeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Backend $Action failed. Check that Docker Desktop is running and review the Docker output above."
    }
}
