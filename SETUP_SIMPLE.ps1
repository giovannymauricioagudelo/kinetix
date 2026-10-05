# KINETIX STUDIO v5.0.0 - SETUP SIMPLE

Write-Host ""
Write-Host "KINETIX STUDIO v5.0.0 - SETUP" -ForegroundColor Cyan
Write-Host ""

# Check Python
python --version

# Create venv
if (-not (Test-Path "venv")) {
    Write-Host "Creating venv..." -ForegroundColor Yellow
    python -m venv venv
}

# Activate venv
Write-Host "Activating venv..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"

# Install deps
if (Test-Path "requirements-scalability.txt") {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    pip install -r requirements-scalability.txt
}

# Create .env
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "SETUP COMPLETE!" -ForegroundColor Green
Write-Host ""
Write-Host "Run this to start API:" -ForegroundColor Cyan
Write-Host "uvicorn src.api.main_scalable:app --reload" -ForegroundColor White
Write-Host ""
Write-Host "Then open in browser:" -ForegroundColor Cyan
Write-Host "http://localhost:8000/api/docs" -ForegroundColor White
Write-Host ""
