Write-Host ""
Write-Host "Corrigiendo GZIPMiddleware -> GZipMiddleware..." -ForegroundColor Cyan
Write-Host ""

$filePath = "src\api\main_scalable.py"

if (-not (Test-Path $filePath)) {
    Write-Host "ERROR: No se encontro el archivo: $filePath" -ForegroundColor Red
    Write-Host "Asegurate de estar en D:\Desarrollo\kinetix-studio\" -ForegroundColor Yellow
    exit 1
}

Write-Host "Archivo encontrado: $filePath" -ForegroundColor Green

$contenido = Get-Content $filePath

$nuevoContenido = $contenido -replace "GZIPMiddleware", "GZipMiddleware"

$nuevoContenido | Set-Content $filePath

Write-Host ""
Write-Host "OK - Cambios aplicados:" -ForegroundColor Green
Write-Host "  GZIPMiddleware -> GZipMiddleware (2 ocurrencias)" -ForegroundColor White
Write-Host ""
Write-Host "Ahora ejecuta:" -ForegroundColor Cyan
Write-Host "uvicorn src.api.main_scalable:app --reload" -ForegroundColor Yellow
Write-Host ""
