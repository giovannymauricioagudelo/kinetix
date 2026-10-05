# Script simple de integración NEXUS v2.0

Write-Host "🔒 NEXUS v2.0 Integration" -ForegroundColor Cyan
Write-Host ""

# Crear directorios
New-Item -ItemType Directory -Path "src\utils" -Force | Out-Null
New-Item -ItemType Directory -Path "src\api\routes" -Force | Out-Null

# Copiar archivos
Write-Host "Copiando archivos..." -ForegroundColor Yellow

if (Test-Path "src_utils_stored_procedures_manager.py") {
    Copy-Item "src_utils_stored_procedures_manager.py" "src\utils\stored_procedures_manager.py" -Force
    Write-Host "✅ StoredProcedureManager copiado" -ForegroundColor Green
}

if (Test-Path "src_api_routes_nexus_agent_v2.py") {
    Copy-Item "src_api_routes_nexus_agent_v2.py" "src\api\routes\nexus_agent_v2.py" -Force
    Write-Host "✅ NEXUS Agent copiado" -ForegroundColor Green
}

# Crear __init__.py
"# Módulo" | Out-File "src\utils\__init__.py" -Force
"# Módulo" | Out-File "src\api\routes\__init__.py" -Force

Write-Host ""
Write-Host "✅ Integración completada" -ForegroundColor Green
Write-Host ""
Write-Host "Próximos pasos:" -ForegroundColor Cyan
Write-Host "1. Edita src/api/main_scalable.py y agrega:" -ForegroundColor White
Write-Host "   from src.api.routes.nexus_agent_v2 import router as nexus_router_v2" -ForegroundColor Gray
Write-Host "   app.include_router(nexus_router_v2)" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Reinicia API:" -ForegroundColor White
Write-Host "   uvicorn src.api.main_scalable:app --reload" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Verifica en:" -ForegroundColor White
Write-Host "   http://localhost:8000/docs" -ForegroundColor Gray
