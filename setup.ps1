# Setup local para Windows (PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python no está en PATH. Instala Python 3.9+ y vuelve a intentar."
}

python -m venv venv
& .\venv\Scripts\python.exe -m pip install --upgrade pip
& .\venv\Scripts\pip.exe install -r requirements-dev.txt

Write-Host ""
Write-Host "Entorno listo. Activa el venv y arranca la API:"
Write-Host "  .\venv\Scripts\Activate.ps1"
Write-Host "  python run.py"
Write-Host ""
