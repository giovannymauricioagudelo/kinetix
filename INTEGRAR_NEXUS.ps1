Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "KINETIX STUDIO - INTEGRAR NEXUS (DatabaseAgent)" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host ""

# Validaciones
Write-Host "[1/5] Validando archivos..." -ForegroundColor Yellow

$nexusAgent = "src_api_routes_nexus_agent.py"
$mainWithAgents = "src_api_main_scalable_WITH_AGENTS.py"

if (-not (Test-Path $nexusAgent)) {
    Write-Host "ERROR: No encontré $nexusAgent" -ForegroundColor Red
    Write-Host "Descargate de /mnt/user-data/outputs/" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $mainWithAgents)) {
    Write-Host "ERROR: No encontré $mainWithAgents" -ForegroundColor Red
    Write-Host "Descargate de /mnt/user-data/outputs/" -ForegroundColor Yellow
    exit 1
}

Write-Host "OK - Archivos encontrados" -ForegroundColor Green
Write-Host ""

# Crear carpeta
Write-Host "[2/5] Creando estructura..." -ForegroundColor Yellow

if (-not (Test-Path "src\api\routes")) {
    New-Item -ItemType Directory "src\api\routes" -Force | Out-Null
}

Write-Host "OK - Carpeta src\api\routes creada" -ForegroundColor Green
Write-Host ""

# Copiar NEXUS agent
Write-Host "[3/5] Instalando NEXUS agent..." -ForegroundColor Yellow

Copy-Item $nexusAgent "src\api\routes\nexus_agent.py" -Force

Write-Host "OK - nexus_agent.py copiado a src\api\routes\" -ForegroundColor Green
Write-Host ""

# Copiar main mejorado
Write-Host "[4/5] Actualizando main.py..." -ForegroundColor Yellow

if (Test-Path "src\api\main_scalable.py") {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    Copy-Item "src\api\main_scalable.py" "src\api\main_scalable_BACKUP_$timestamp.py" -Force
    Write-Host "Backup: src\api\main_scalable_BACKUP_$timestamp.py" -ForegroundColor Gray
}

Copy-Item $mainWithAgents "src\api\main_scalable.py" -Force

Write-Host "OK - main_scalable.py actualizado" -ForegroundColor Green
Write-Host ""

# Verificar
Write-Host "[5/5] Verificando integración..." -ForegroundColor Yellow

$filePath = "src\api\main_scalable.py"
$content = Get-Content $filePath -Raw

if ($content -like "*nexus_router*") {
    Write-Host "OK - NEXUS router import detectado" -ForegroundColor Green
}

if (Test-Path "src\api\routes\nexus_agent.py") {
    Write-Host "OK - Archivo de NEXUS agent existe" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "INTEGRACIÓN COMPLETA!" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Ahora ejecuta:" -ForegroundColor Yellow
Write-Host "uvicorn src.api.main_scalable:app --reload" -ForegroundColor White
Write-Host ""

Write-Host "Luego abre en navegador:" -ForegroundColor Yellow
Write-Host "http://localhost:8000/docs" -ForegroundColor White
Write-Host ""

Write-Host "Busca la sección 'NEXUS - DatabaseAgent' con 6 endpoints:" -ForegroundColor Cyan
Write-Host "  GET /api/v1/nexus/health" -ForegroundColor Gray
Write-Host "  POST /api/v1/nexus/query" -ForegroundColor Gray
Write-Host "  POST /api/v1/nexus/execute" -ForegroundColor Gray
Write-Host "  GET /api/v1/nexus/tables" -ForegroundColor Gray
Write-Host "  GET /api/v1/nexus/stats" -ForegroundColor Gray
Write-Host "  GET /api/v1/nexus/connections" -ForegroundColor Gray
Write-Host ""

Write-Host "Lee más: NEXUS_INTEGRATION_GUIDE.md" -ForegroundColor Cyan
Write-Host ""
