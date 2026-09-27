param([string]$Environment = "dev")

Clear-Host

Write-Host ""
Write-Host "KINETIX STUDIO v5.0.0 - SETUP" -ForegroundColor Cyan
Write-Host "Environment: $Environment" -ForegroundColor Yellow
Write-Host ""

# 1. Validar Python
Write-Host "[1/6] Validando Python..." -ForegroundColor Cyan
python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Python no instalado" -ForegroundColor Red
    exit 1
}
Write-Host "OK" -ForegroundColor Green
Write-Host ""

# 2. Crear carpetas
Write-Host "[2/6] Creando carpetas..." -ForegroundColor Cyan
$carpetas = @("src/utils", "src/api/routes", "src/models", "logs", "data")
foreach ($c in $carpetas) {
    if (-not (Test-Path $c)) {
        New-Item -ItemType Directory -Path $c -Force | Out-Null
    }
}
Write-Host "OK" -ForegroundColor Green
Write-Host ""

# 3. Virtual Environment
Write-Host "[3/6] Configurando venv..." -ForegroundColor Cyan
if (-not (Test-Path "venv")) {
    python -m venv venv
}
& ".\venv\Scripts\Activate.ps1"
Write-Host "OK" -ForegroundColor Green
Write-Host ""

# 4. Instalar dependencias
Write-Host "[4/6] Instalando dependencias..." -ForegroundColor Cyan
pip install --upgrade pip setuptools wheel -q
if (Test-Path "requirements-scalability-FINAL.txt") {
    pip install -r requirements-scalability-FINAL.txt
} else {
    Write-Host "Instalando paquetes basicos..." -ForegroundColor Yellow
    pip install fastapi uvicorn asyncpg aioodbc redis aioredis aio-pika==10.0.4 pydantic slowapi pybreaker tenacity prometheus-client
}
Write-Host "OK" -ForegroundColor Green
Write-Host ""

# 5. Copiar archivos
Write-Host "[5/6] Copiando archivos de codigo..." -ForegroundColor Cyan
if (Test-Path "src_api_main_scalable.py") {
    Copy-Item "src_api_main_scalable.py" "src/api/main_scalable.py" -Force
}
if (Test-Path "src_utils_circuit_breaker.py") {
    Copy-Item "src_utils_circuit_breaker.py" "src/utils/circuit_breaker.py" -Force
}
if (Test-Path "src_utils_cache_manager.py") {
    Copy-Item "src_utils_cache_manager.py" "src/utils/cache_manager.py" -Force
}
if (Test-Path "src_utils_database_pools.py") {
    Copy-Item "src_utils_database_pools.py" "src/utils/database_pools.py" -Force
}
if (Test-Path "src_api_routes_database_scalable.py") {
    Copy-Item "src_api_routes_database_scalable.py" "src/api/routes/database_scalable.py" -Force
}
Write-Host "OK" -ForegroundColor Green
Write-Host ""

# 6. Crear .env
Write-Host "[6/6] Configurando .env..." -ForegroundColor Cyan
if (-not (Test-Path ".env")) {
    @"
ENVIRONMENT=$Environment
DEBUG=true
API_HOST=0.0.0.0
API_PORT=8000
POSTGRES_HOST=localhost
POSTGRES_DB=kinetix
MSSQL_SERVER=localhost
MSSQL_DATABASE=kinetix
REDIS_HOST=localhost
"@ | Out-File -FilePath ".env" -Encoding UTF8
}
Write-Host "OK" -ForegroundColor Green
Write-Host ""

Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "SETUP COMPLETO!" -ForegroundColor Green
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Ejecuta ahora:" -ForegroundColor Yellow
Write-Host "uvicorn src.api.main_scalable:app --reload" -ForegroundColor White
Write-Host ""
Write-Host "Luego abre en navegador:" -ForegroundColor Yellow
Write-Host "http://localhost:8000/api/docs" -ForegroundColor White
Write-Host ""
