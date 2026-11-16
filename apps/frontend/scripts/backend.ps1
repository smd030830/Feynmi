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
    # --build: pull 뒤 백엔드 의존성(파서·OCR 라이브러리, Tesseract)이 바뀌었으면 이미지를 다시 만든다 (바뀐 게 없으면 캐시로 바로 끝남).
    # gcs: 학습자료 원본을 보관하는 로컬 GCS 에뮬레이터 (.env의 GCS_BUCKET이 있으면 백엔드는 그 버킷을 쓴다).
    $composeArgs += @('up', '-d', '--build', '--wait', 'db', 'gcs', 'backend')
} else {
    $composeArgs += @('stop', 'backend', 'gcs', 'db')
}

if ($PSCmdlet.ShouldProcess('Feynmi backend and database', $Action)) {
    & $dockerCommand.Source @composeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Backend $Action failed. Check that Docker Desktop is running and review the Docker output above."
    }
}
