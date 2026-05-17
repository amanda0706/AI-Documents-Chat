$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

Write-Host "Preparing ClausePilot..."

if (-not (Test-Path (Join-Path $backend ".venv"))) {
    Write-Host "Creating backend virtual environment..."
    python -m venv (Join-Path $backend ".venv")
}

$python = Join-Path $backend ".venv\Scripts\python.exe"
Write-Host "Installing backend dependencies..."
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $backend "requirements.txt")

if (-not (Test-Path (Join-Path $root ".env"))) {
    Copy-Item (Join-Path $root ".env.example") (Join-Path $root ".env")
    Write-Host "Created root .env from example."
}

if (-not (Test-Path (Join-Path $frontend ".env.local"))) {
    Copy-Item (Join-Path $frontend ".env.example") (Join-Path $frontend ".env.local")
    Write-Host "Created frontend .env.local from example."
}

Write-Host "Installing frontend dependencies..."
Push-Location $frontend
try {
    npm install
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Next step: run .\scripts\run-local.ps1"
