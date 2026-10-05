# Crear directorios
New-Item -ItemType Directory -Path "src\utils" -Force | Out-Null
New-Item -ItemType Directory -Path "src\api\routes" -Force | Out-Null

# Copiar archivos
Copy-Item "src_utils_stored_procedures_manager.py" "src\utils\stored_procedures_manager.py" -Force
Copy-Item "src_api_routes_nexus_agent_v2.py" "src\api\routes\nexus_agent_v2.py" -Force

# Crear __init__.py
"" | Out-File "src\utils\__init__.py" -Force
"" | Out-File "src\api\routes\__init__.py" -Force

Write-Host "OK - Archivos copiados"
Write-Host ""
Write-Host "PROXIMO PASO: Edita src/api/main_scalable.py"
Write-Host "Agrega estas dos lineas al principio:"
Write-Host ""
Write-Host "from src.api.routes.nexus_agent_v2 import router as nexus_router_v2"
Write-Host ""
Write-Host "Y al final agrega:"
Write-Host ""
Write-Host "app.include_router(nexus_router_v2)"
Write-Host ""
