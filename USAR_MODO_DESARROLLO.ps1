Write-Host ""
Write-Host "KINETIX STUDIO - CAMBIAR A MODO DESARROLLO" -ForegroundColor Cyan
Write-Host ""

$devFile = "src_api_main_scalable_DEV.py"
$mainFile = "src\api\main_scalable.py"

if (-not (Test-Path $devFile)) {
    Write-Host "ERROR: No encontre $devFile" -ForegroundColor Red
    Write-Host "Descargalo de /mnt/user-data/outputs/" -ForegroundColor Yellow
    exit 1
}

Write-Host "Haciendo backup del archivo actual..." -ForegroundColor Yellow
if (Test-Path $mainFile) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    Copy-Item $mainFile "src\api\main_scalable_BACKUP_$timestamp.py" -Force
    Write-Host "Backup: src\api\main_scalable_BACKUP_$timestamp.py" -ForegroundColor Green
}

Write-Host "Copiando archivo DEV..." -ForegroundColor Yellow
Copy-Item $devFile $mainFile -Force

Write-Host ""
Write-Host "OK - Archivo reemplazado!" -ForegroundColor Green
Write-Host ""
Write-Host "Ahora ejecuta:" -ForegroundColor Cyan
Write-Host "uvicorn src.api.main_scalable:app --reload" -ForegroundColor Yellow
Write-Host ""
Write-Host "La API arrancara SIN errores de PostgreSQL" -ForegroundColor Green
Write-Host ""
