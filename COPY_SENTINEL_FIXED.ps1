# Script para copiar SENTINEL_V1_PHASE2_MFA.py CORREGIDO
# ============================================================================

$ORIGEN = "D:\Desarrollo\kinetix-studio\SENTINEL_V1_PHASE2_MFA.py"
$DESTINO = "D:\Desarrollo\kinetix-studio\SENTINEL_V1_PHASE2_MFA.py"

# Crear backup de versión anterior
if (Test-Path $ORIGEN) {
    $BACKUP = "$ORIGEN.backup"
    Copy-Item $ORIGEN -Destination $BACKUP -Force
    Write-Host "✅ Backup creado: $BACKUP" -ForegroundColor Green
}

# Instrucciones para el usuario
Write-Host ""
Write-Host "════════════════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "SENTINEL V1.0 PHASE 2 - VERSIÓN CORREGIDA" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ El archivo ha sido corregido (funciones reorganizadas)" -ForegroundColor Green
Write-Host ""
Write-Host "🚀 EJECUTA AHORA:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  cd D:\Desarrollo\kinetix-studio" -ForegroundColor White
Write-Host "  python SENTINEL_V1_PHASE2_MFA.py" -ForegroundColor White
Write-Host ""
Write-Host "📍 Esperado:" -ForegroundColor Cyan
Write-Host "  INFO:     Uvicorn running on http://127.0.0.1:8001" -ForegroundColor White
Write-Host ""
Write-Host "════════════════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
