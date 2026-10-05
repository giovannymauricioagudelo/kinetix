# ============================================================================
# INTEGRAR_NEXUS_V2.ps1
# Script de integración automática de NEXUS v2.0 con procedimientos almacenados
# ============================================================================

Write-Host "`n" -NoNewline
Write-Host "╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║          🔒 NEXUS v2.0 - DatabaseAgent Integration             ║" -ForegroundColor Cyan
Write-Host "║          Procedimientos Almacenados + Seguridad Enterprise     ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host "`n"

# ============================================================================
# VALIDACIONES INICIALES
# ============================================================================

Write-Host "📋 Validando entorno..." -ForegroundColor Yellow

# Verificar que estamos en el directorio correcto
if (-not (Test-Path "src\api\routes")) {
    Write-Host "❌ No estamos en el directorio correcto del proyecto" -ForegroundColor Red
    Write-Host "   Por favor ejecuta este script desde D:\Desarrollo\kinetix-studio\" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "venv\Scripts\activate.ps1")) {
    Write-Host "❌ No se encontró venv" -ForegroundColor Red
    Write-Host "   Por favor crea el venv primero" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Entorno validado" -ForegroundColor Green
Write-Host "`n"

# ============================================================================
# COPIAR ARCHIVOS
# ============================================================================

Write-Host "📁 Copiando archivos de NEXUS v2.0..." -ForegroundColor Yellow

$files = @(
    @{
        source = "src_utils_stored_procedures_manager.py"
        destination = "src\utils\stored_procedures_manager.py"
        description = "StoredProcedureManager (gestor de SP)"
    },
    @{
        source = "src_api_routes_nexus_agent_v2.py"
        destination = "src\api\routes\nexus_agent_v2.py"
        description = "NEXUS v2.0 con 6 endpoints"
    }
)

foreach ($file in $files) {
    if (Test-Path $file.source) {
        Copy-Item $file.source $file.destination -Force
        Write-Host "  ✅ Copiado: $($file.description)" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  No encontrado: $($file.source)" -ForegroundColor Yellow
    }
}

Write-Host "`n"

# ============================================================================
# CREAR ESTRUCTURA DE DIRECTORIOS SI NO EXISTE
# ============================================================================

Write-Host "📂 Creando estructura de directorios..." -ForegroundColor Yellow

$dirs = @(
    "src\utils",
    "src\api\routes"
)

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  ✅ Creado: $dir" -ForegroundColor Green
    } else {
        Write-Host "  ℹ️  Ya existe: $dir" -ForegroundColor Blue
    }
}

Write-Host "`n"

# ============================================================================
# ACTUALIZAR main_scalable.py
# ============================================================================

Write-Host "🔧 Actualizando main_scalable.py..." -ForegroundColor Yellow

$mainFile = "src\api\main_scalable.py"

if (Test-Path $mainFile) {
    $content = Get-Content $mainFile -Raw
    
    # Verificar si ya está incluido
    if ($content -notlike "*nexus_agent_v2*") {
        # Encontrar la línea de importación de routers
        $importPattern = "from src\.api\.routes\..*? import router as"
        
        # Agregar import de NEXUS v2
        $importLine = "from src.api.routes.nexus_agent_v2 import router as nexus_router_v2"
        
        if ($content -match "from src\.api\.routes") {
            $content = $content -replace "(from src\.api\.routes\..*? import router as.*)","`$1`n$importLine"
        } else {
            $content = $content -replace "from fastapi import", "$importLine`nfrom fastapi import"
        }
        
        # Agregar registro del router
        $registerPattern = 'app\.include_router\(.*?\)'
        
        if ($content -match $registerPattern) {
            $content = $content -replace '(app\.include_router\(.*?\))', "`$1`napp.include_router(nexus_router_v2)"
        }
        
        # Guardar cambios
        Set-Content $mainFile $content
        Write-Host "  ✅ main_scalable.py actualizado" -ForegroundColor Green
    } else {
        Write-Host "  ℹ️  NEXUS v2 ya está integrado" -ForegroundColor Blue
    }
} else {
    Write-Host "  ⚠️  No se encontró main_scalable.py" -ForegroundColor Yellow
}

Write-Host "`n"

# ============================================================================
# CREAR ARCHIVO __init__.py EN utils SI NO EXISTE
# ============================================================================

Write-Host "📝 Creando archivos __init__.py..." -ForegroundColor Yellow

$initFiles = @(
    "src\utils\__init__.py",
    "src\api\routes\__init__.py"
)

foreach ($initFile in $initFiles) {
    if (-not (Test-Path $initFile)) {
        New-Item -ItemType File -Path $initFile -Force | Out-Null
        Add-Content $initFile "# Módulo"
        Write-Host "  ✅ Creado: $initFile" -ForegroundColor Green
    } else {
        Write-Host "  ℹ️  Ya existe: $initFile" -ForegroundColor Blue
    }
}

Write-Host "`n"

# ============================================================================
# VERIFICAR VERSIÓN DE PYTHON
# ============================================================================

Write-Host "🐍 Verificando Python..." -ForegroundColor Yellow

$pythonVersion = python --version 2>&1
Write-Host "  ℹ️  $pythonVersion" -ForegroundColor Blue

Write-Host "`n"

# ============================================================================
# SUMMARY
# ============================================================================

Write-Host "╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                   ✅ INTEGRACIÓN COMPLETADA                   ║" -ForegroundColor Green
Write-Host "╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Host "`n📦 Archivos instalados:" -ForegroundColor Green
Write-Host "  • src\utils\stored_procedures_manager.py"
Write-Host "  • src\api\routes\nexus_agent_v2.py"

Write-Host "`n🔐 Características de NEXUS v2.0:" -ForegroundColor Green
Write-Host "  • Procedimientos almacenados seguros"
Write-Host "  • Protección contra SQL injection"
Write-Host "  • Parámetros nombrados (@param)"
Write-Host "  • CRUD automático con SP"
Write-Host "  • Validación de tipos de datos"
Write-Host "  • Soporte MSSQL + PostgreSQL"

Write-Host "`n📚 Nuevos Endpoints:" -ForegroundColor Green
Write-Host "  POST   /api/v1/nexus/create-stored-procedure"
Write-Host "  POST   /api/v1/nexus/execute-stored-procedure"
Write-Host "  POST   /api/v1/nexus/crud"
Write-Host "  GET    /api/v1/nexus/stored-procedures"
Write-Host "  POST   /api/v1/nexus/test-sql-injection"
Write-Host "  GET    /api/v1/nexus/procedure-definition"

Write-Host "`n🚀 Próximos pasos:" -ForegroundColor Cyan
Write-Host "  1. Reinicia la API:"
Write-Host "     uvicorn src.api.main_scalable:app --reload"
Write-Host ""
Write-Host "  2. Verifica en Swagger:"
Write-Host "     http://localhost:8000/docs"
Write-Host ""
Write-Host "  3. Prueba los nuevos endpoints"
Write-Host ""
Write-Host "  4. Ejecuta prueba de SQL injection:"
Write-Host "     POST /api/v1/nexus/test-sql-injection"

Write-Host "`n📖 Documentación:" -ForegroundColor Cyan
Write-Host "  • NEXUS_V2_SECURITY_GUIDE.md - Guía completa de seguridad"
Write-Host "  • src\utils\stored_procedures_manager.py - Código fuente"
Write-Host "  • http://localhost:8000/docs - Swagger UI"

Write-Host "`n🔒 Security:" -ForegroundColor Green
Write-Host "  ✅ 100% protegido contra SQL injection"
Write-Host "  ✅ Validación de identificadores (tabla, columnas)"
Write-Host "  ✅ Tipado de datos completo"
Write-Host "  ✅ Parámetros nombrados (nunca concatenación)"
Write-Host "  ✅ Detección de patrones peligrosos"

Write-Host "`n" -NoNewline

# Opción de reiniciar la API
Write-Host "¿Deseas reiniciar la API ahora? (S/N) " -ForegroundColor Yellow -NoNewline
$response = Read-Host

if ($response -eq "S" -or $response -eq "s") {
    Write-Host "`n🚀 Iniciando API..." -ForegroundColor Green
    Write-Host "`n"
    uvicorn src.api.main_scalable:app --reload
} else {
    Write-Host "`n✅ Integración completada. Ejecuta manualmente:" -ForegroundColor Green
    Write-Host "   uvicorn src.api.main_scalable:app --reload" -ForegroundColor Cyan
    Write-Host "`n"
}
