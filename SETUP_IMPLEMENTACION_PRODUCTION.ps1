param(
    [string]$Environment = "dev"
)

# ============================================================================
# KINETIX STUDIO v5.0.0 - SETUP IMPLEMENTATION (WINDOWS)
# ============================================================================

Clear-Host

Write-Host ""
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "KINETIX STUDIO v5.0.0 - SETUP IMPLEMENTATION (WINDOWS)" -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Environment: $Environment" -ForegroundColor Yellow
Write-Host ""

# ============================================================================
# 1. VALIDACIONES INICIALES
# ============================================================================

Write-Host "[STEP 1] Validando ambiente..." -ForegroundColor Cyan

# Validar que estamos en la carpeta correcta
if (-not (Test-Path "src")) {
    Write-Host "ERROR: No se encuentra carpeta 'src'" -ForegroundColor Red
    Write-Host "Asegurate de estar en D:\Desarrollo\kinetix-studio\" -ForegroundColor Yellow
    exit 1
}

# Validar Python
Write-Host "  - Validando Python..." -ForegroundColor Gray
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "    ERROR: Python no instalado" -ForegroundColor Red
    exit 1
}
Write-Host "    OK: $pythonVersion" -ForegroundColor Green

# Validar pip
Write-Host "  - Validando pip..." -ForegroundColor Gray
$pipVersion = pip --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "    ERROR: pip no instalado" -ForegroundColor Red
    exit 1
}
Write-Host "    OK: $pipVersion" -ForegroundColor Green

Write-Host ""

# ============================================================================
# 2. CREAR ESTRUCTURA DE CARPETAS
# ============================================================================

Write-Host "[STEP 2] Creando estructura de carpetas..." -ForegroundColor Cyan

$carpetas = @(
    "src\utils",
    "src\api\routes",
    "src\models",
    "src\schemas",
    "logs",
    "data"
)

foreach ($carpeta in $carpetas) {
    if (-not (Test-Path $carpeta)) {
        New-Item -ItemType Directory -Path $carpeta -Force | Out-Null
        Write-Host "  ✓ Creada: $carpeta" -ForegroundColor Green
    } else {
        Write-Host "  - Existe: $carpeta" -ForegroundColor Gray
    }
}

Write-Host ""

# ============================================================================
# 3. CREAR VENV
# ============================================================================

Write-Host "[STEP 3] Configurando Virtual Environment..." -ForegroundColor Cyan

if (-not (Test-Path "venv")) {
    Write-Host "  - Creando venv..." -ForegroundColor Yellow
    python -m venv venv
    Write-Host "  ✓ venv creado" -ForegroundColor Green
} else {
    Write-Host "  - venv ya existe" -ForegroundColor Gray
}

Write-Host "  - Activando venv..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: No se pudo activar venv" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ venv activado" -ForegroundColor Green

Write-Host ""

# ============================================================================
# 4. INSTALAR DEPENDENCIAS
# ============================================================================

Write-Host "[STEP 4] Instalando dependencias..." -ForegroundColor Cyan

Write-Host "  - Actualizando pip, setuptools, wheel..." -ForegroundColor Yellow
pip install --upgrade pip setuptools wheel --quiet

$requirementsFile = "requirements-scalability-FINAL.txt"

if (Test-Path $requirementsFile) {
    Write-Host "  - Instalando desde $requirementsFile..." -ForegroundColor Yellow
    pip install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Fallo en instalacion" -ForegroundColor Red
        Write-Host ""
        Write-Host "  ALTERNATIVA RAPIDA (sin archivo):" -ForegroundColor Yellow
        Write-Host "  pip install fastapi uvicorn asyncpg aioodbc redis aioredis aio-pika==10.0.4 pydantic slowapi pybreaker tenacity prometheus-client" -ForegroundColor White
        exit 1
    }
    Write-Host "  ✓ Dependencias instaladas" -ForegroundColor Green
} else {
    Write-Host "  WARNING: $requirementsFile no encontrado" -ForegroundColor Yellow
    Write-Host "  - Instalando paquetes basicos manualmente..." -ForegroundColor Yellow
    pip install fastapi uvicorn asyncpg aioodbc redis aioredis aio-pika==10.0.4 pydantic slowapi pybreaker tenacity prometheus-client
    Write-Host "  ✓ Paquetes basicos instalados" -ForegroundColor Green
}

Write-Host ""

# ============================================================================
# 5. COPIAR ARCHIVOS DE CODIGO
# ============================================================================

Write-Host "[STEP 5] Copiando archivos de codigo..." -ForegroundColor Cyan

$archivos = @(
    @{ origen = "src_utils_circuit_breaker.py"; destino = "src\utils\circuit_breaker.py" },
    @{ origen = "src_utils_cache_manager.py"; destino = "src\utils\cache_manager.py" },
    @{ origen = "src_utils_database_pools.py"; destino = "src\utils\database_pools.py" },
    @{ origen = "src_api_main_scalable.py"; destino = "src\api\main_scalable.py" },
    @{ origen = "src_api_routes_database_scalable.py"; destino = "src\api\routes\database_scalable.py" }
)

foreach ($archivo in $archivos) {
    $origenPath = ".\$($archivo.origen)"
    if (Test-Path $origenPath) {
        Copy-Item $origenPath $archivo.destino -Force
        Write-Host "  ✓ $($archivo.destino)" -ForegroundColor Green
    } else {
        Write-Host "  - OMITIDO: $($archivo.origen) (no encontrado)" -ForegroundColor Gray
    }
}

Write-Host ""

# ============================================================================
# 6. CREAR/CONFIGURAR .ENV
# ============================================================================

Write-Host "[STEP 6] Configurando variables de entorno..." -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Write-Host "  - Creando .env para environment: $Environment..." -ForegroundColor Yellow
    
    $envContent = @"
# KINETIX STUDIO v5.0.0 Environment Configuration
ENVIRONMENT=$Environment
DEBUG=true

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# Database - PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=kinetix
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Database - SQL Server
MSSQL_SERVER=localhost
MSSQL_DATABASE=kinetix
MSSQL_USER=sa
MSSQL_PASSWORD=Geomou0812

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# RabbitMQ
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Monitoring
PROMETHEUS_ENABLED=true
JAEGER_ENABLED=true

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/kinetix.log
"@
    
    $envContent | Out-File -FilePath ".env" -Encoding UTF8 -Force
    Write-Host "  ✓ .env creado" -ForegroundColor Green
} else {
    Write-Host "  - .env ya existe" -ForegroundColor Gray
}

Write-Host ""

# ============================================================================
# 7. VERIFICACIONES FINALES
# ============================================================================

Write-Host "[STEP 7] Verificaciones finales..." -ForegroundColor Cyan

Write-Host "  - Verificando modulos instalados..." -ForegroundColor Yellow
python -c "import fastapi, uvicorn, asyncpg, redis, pydantic; print('  OK: FastAPI, Uvicorn, Asyncpg, Redis, Pydantic')" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Modulos core verificados" -ForegroundColor Green
}

Write-Host ""

# ============================================================================
# 8. RESUMEN FINAL
# ============================================================================

Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "SETUP COMPLETO!" -ForegroundColor Green
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Proximos pasos:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Iniciar la API:" -ForegroundColor White
Write-Host "   uvicorn src.api.main_scalable:app --reload" -ForegroundColor Yellow
Write-Host ""
Write-Host "2. Abrir en navegador:" -ForegroundColor White
Write-Host "   http://localhost:8000/api/docs" -ForegroundColor Yellow
Write-Host ""
Write-Host "3. Verificar health check:" -ForegroundColor White
Write-Host "   http://localhost:8000/health" -ForegroundColor Yellow
Write-Host ""
Write-Host "4. Ver metricas:" -ForegroundColor White
Write-Host "   http://localhost:8000/metrics/all" -ForegroundColor Yellow
Write-Host ""

Write-Host "Informacion del setup:" -ForegroundColor Cyan
Write-Host "  - Python: $pythonVersion" -ForegroundColor Gray
Write-Host "  - Environment: $Environment" -ForegroundColor Gray
Write-Host "  - Carpeta: $(Get-Location)" -ForegroundColor Gray
Write-Host "  - Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
Write-Host ""

Write-Host "Troubleshooting:" -ForegroundColor Cyan
Write-Host "  Si hay error con aio-pika:" -ForegroundColor Gray
Write-Host "    pip install aio-pika==10.0.4 --force-reinstall" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Si hay error con uvloop (Windows):" -ForegroundColor Gray
Write-Host "    Es normal - uvloop solo funciona en Linux/macOS" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Para instalar paquetes adicionales:" -ForegroundColor Gray
Write-Host "    pip install nombre-paquete" -ForegroundColor Yellow
Write-Host ""

Write-Host "============================================================================" -ForegroundColor Cyan
