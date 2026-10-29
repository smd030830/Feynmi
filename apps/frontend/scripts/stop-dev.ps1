[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = 'Stop'
$frontendPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dependencyPath = $frontendPath + '\node_modules\'
$devProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" | Where-Object {
    $_.CommandLine -and
    $_.CommandLine.IndexOf($dependencyPath, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
    $_.CommandLine -match '\\next\\dist\\bin\\next"?\s+dev(?:\s|$)'
})

if ($devProcesses.Count -eq 0) {
    Write-Output 'No frontend development server is running for this project.'
    exit 0
}

foreach ($devProcess in $devProcesses) {
    if ($PSCmdlet.ShouldProcess("Frontend dev PID $($devProcess.ProcessId)", 'Stop process tree')) {
        & taskkill.exe /PID $devProcess.ProcessId /T /F
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to stop frontend dev PID $($devProcess.ProcessId)."
        }
    }
}
