$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Backend environment not found. Run .\scripts\bootstrap.ps1 first."
}

Write-Host "Starting LuminaClause backend and frontend..."

$backendProcess = Start-Process `
    -FilePath $python `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--reload" `
    -WorkingDirectory $backend `
    -WindowStyle Hidden `
    -PassThru

$frontendProcess = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev" `
    -WorkingDirectory $frontend `
    -WindowStyle Hidden `
    -PassThru

Write-Host ""
Write-Host "Frontend: http://localhost:3000"
Write-Host "Backend docs: http://localhost:8000/docs"
Write-Host ""
Write-Host "Press Ctrl+C here when you want to stop both services."

try {
    while ($true) {
        Start-Sleep -Seconds 2
        if ($backendProcess.HasExited -or $frontendProcess.HasExited) {
            throw "One of the local services stopped unexpectedly."
        }
    }
}
finally {
    if (-not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id
    }
    if (-not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id
    }
}
