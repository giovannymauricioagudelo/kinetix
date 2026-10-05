# ============================================================================
# KINETIX STUDIO v5.0.0 - SETUP SCRIPT (WINDOWS POWERSHELL - FIXED)
# ============================================================================

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("dev", "prod")]
    [string]$Environment = "dev"
)

Write-Host ""
Write-Host "============================================================================" -ForegroundColor Blue
Write-Host "KINETIX STUDIO v5.0.0 - SETUP IMPLEMENTATION" -ForegroundColor Blue
Write-Host "Environment: $Environment" -ForegroundColor Blue
Write-Host "============================================================================" -ForegroundColor Blue

# ============================================================================
# 1. VALIDAR PYTHON
# ============================================================================

Write-Host ""
Write-Host "[1/5] Validando Python..." -ForegroundColor Yellow

$pythonCheck = python --version 2>&1
if ($pythonCheck -match "3\.1[0-9]") {
    Write-Host "✅ Python encontrado: $pythonCheck" -ForegroundColor Green
} else {
    Write-Host "❌ Se requiere Python 3.10+" -ForegroundColor Red
    exit 1
}

# ============================================================================
# 2. CREAR DIRECTORIOS
# ============================================================================

Write-Host ""
Write-Host "[2/5] Creando estructura de directorios..." -ForegroundColor Yellow

$dirs = @("src\api\routes", "src\utils", "logs", "tests", "docs")
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
    }
}
Write-Host "✅ Directorios creados" -ForegroundColor Green

# ============================================================================
# 3. VIRTUAL ENVIRONMENT
# ============================================================================

Write-Host ""
Write-Host "[3/5] Configurando Virtual Environment..." -ForegroundColor Yellow

if (-not (Test-Path "venv")) {
    python -m venv venv
    Write-Host "✅ Virtual environment creado" -ForegroundColor Green
} else {
    Write-Host "✅ Virtual environment ya existe" -ForegroundColor Green
}

# Activar venv
& ".\venv\Scripts\Activate.ps1"

# Actualizar pip
python -m pip install --upgrade pip 2>&1 | Out-Null
Write-Host "✅ pip actualizado" -ForegroundColor Green

# ============================================================================
# 4. INSTALAR DEPENDENCIAS
# ============================================================================

Write-Host ""
Write-Host "[4/5] Instalando dependencias..." -ForegroundColor Yellow

if (Test-Path "requirements-scalability.txt") {
    pip install -r requirements-scalability.txt 2>&1 | Out-Null
    Write-Host "✅ Dependencias instaladas" -ForegroundColor Green
} else {
    Write-Host "⚠️  requirements-scalability.txt no encontrado" -ForegroundColor Yellow
    Write-Host "   Descárgalo de los outputs" -ForegroundColor Yellow
}

# ============================================================================
# 5. CREAR .ENV
# ============================================================================

Write-Host ""
Write-Host "[5/5] Configurando variables de entorno..." -ForegroundColor Yellow

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "✅ .env creado desde .env.example" -ForegroundColor Green
    } else {
        Write-Host "⚠️  .env.example no encontrado" -ForegroundColor Yellow
    }
} else {
    Write-Host "✅ .env ya existe" -ForegroundColor Green
}

# ============================================================================
# RESUMEN
# ============================================================================

Write-Host ""
Write-Host "============================================================================" -ForegroundColor Green
Write-Host "✅ SETUP COMPLETADO" -ForegroundColor Green
Write-Host "============================================================================" -ForegroundColor Green

Write-Host ""
Write-Host "PRÓXIMO PASO:" -ForegroundColor Blue
Write-Host ""
Write-Host "  uvicorn src.api.main_scalable:app --reload" -ForegroundColor Cyan
Write-Host ""
Write-Host "Acceder a:" -ForegroundColor Blue
Write-Host "  http://localhost:8000/api/docs" -ForegroundColor Cyan
Write-Host ""
