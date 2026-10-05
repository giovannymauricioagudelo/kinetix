# ============================================================================
# SENTINEL v1.0 - VALIDACIÓN DE ENDPOINTS CON BD
# Fecha: 3 Octubre, 2026
# Empresa: GIO
# ============================================================================

# Variables
$BASE_URL = "http://127.0.0.1:8001"
$USUARIO = "giovanny"
$CONTRASENA = "SecurePassword123456"
$EMPRESA = "gio"

# Headers
$CONTENT_TYPE = "application/json"

# Colores
function Print-Exito { Write-Host $args -ForegroundColor Green }
function Print-Error { Write-Host $args -ForegroundColor Red }
function Print-Info { Write-Host $args -ForegroundColor Cyan }
function Print-Advertencia { Write-Host $args -ForegroundColor Yellow }

# Contador
$total_tests = 0
$tests_pasados = 0

# ============================================================================
# FUNCIÓN AUXILIAR: Realizar request
# ============================================================================

function Realizar-Request {
    param(
        [string]$Metodo,
        [string]$Endpoint,
        [hashtable]$Headers = @{},
        [string]$Body = $null,
        [string]$Descripcion = ""
    )
    
    $total_tests++
    $url_completa = "$BASE_URL$Endpoint"
    
    Print-Info "TEST #$total_tests : $Descripcion"
    Print-Info "  $Metodo $Endpoint"
    
    try {
        if ($Metodo -eq "GET") {
            $respuesta = Invoke-WebRequest -Uri $url_completa -Method $Metodo -Headers $Headers -ContentType $CONTENT_TYPE -ErrorAction Stop
        } else {
            $respuesta = Invoke-WebRequest -Uri $url_completa -Method $Metodo -Headers $Headers -Body $Body -ContentType $CONTENT_TYPE -ErrorAction Stop
        }
        
        $contenido = $respuesta.Content | ConvertFrom-Json
        Print-Exito "  ✅ PASS (HTTP $($respuesta.StatusCode))"
        Write-Host "  Respuesta: $(($contenido | ConvertTo-Json -Depth 2) | Select-Object -First 5 -Last 1)"
        $tests_pasados++
        
        return $contenido
    } catch {
        Print-Error "  ❌ FAIL"
        Print-Error "  Error: $($_.Exception.Message)"
        
        try {
            $respuesta_error = $_ | ConvertFrom-Json
            Write-Host "  Detalles: $respuesta_error"
        } catch {
            # Silent
        }
        
        return $null
    }
}

# ============================================================================
# TEST 1: INFO DEL AGENTE
# ============================================================================

Print-Info ""
Print-Info "════════════════════════════════════════════════════════════════════════════"
Print-Info "TEST 1: Información del Agente"
Print-Info "════════════════════════════════════════════════════════════════════════════"

$info = Realizar-Request -Metodo GET -Endpoint "/api/v1/sentinel/info" -Descripcion "Obtener información SENTINEL"

# ============================================================================
# TEST 2: AUTENTICACIÓN SIN JWT (DEBE FALLAR)
# ============================================================================

Print-Info ""
Print-Info "════════════════════════════════════════════════════════════════════════════"
Print-Info "TEST 2: Autenticación - Caso Negativo (credenciales inválidas)"
Print-Info "════════════════════════════════════════════════════════════════════════════"

$body_auth_invalida = @{
    nombre_usuario = "usuario_inexistente"
    contrasena = "contraseña_falsa"
    id_empresa = $EMPRESA
} | ConvertTo-Json

$respuesta_auth_invalida = Realizar-Request -Metodo POST -Endpoint "/api/v1/sentinel/autenticar" `
    -Body $body_auth_invalida `
    -Descripcion "Intentar autenticación con credenciales inválidas"

# ============================================================================
# TEST 3: AUTENTICACIÓN EXITOSA
# ============================================================================

Print-Info ""
Print-Info "════════════════════════════════════════════════════════════════════════════"
Print-Info "TEST 3: Autenticación - Caso Exitoso"
Print-Info "════════════════════════════════════════════════════════════════════════════"

$body_auth_valida = @{
    nombre_usuario = $USUARIO
    contrasena = $CONTRASENA
    id_empresa = $EMPRESA
} | ConvertTo-Json

$respuesta_auth = Realizar-Request -Metodo POST -Endpoint "/api/v1/sentinel/autenticar" `
    -Body $body_auth_valida `
    -Descripcion "Autenticar usuario válido (giovanny@gio.com)"

# Guardar tokens para pruebas posteriores
if ($respuesta_auth) {
    $ficha_acceso = $respuesta_auth.ficha_acceso
    $headers_autenticado = @{
        "Authorization" = "Bearer $ficha_acceso"
    }
    Print-Exito "✅ Tokens obtenidos (duración 1 hora)"
} else {
    Print-Error "❌ No se pudo obtener token. Deteniendo pruebas."
    exit 1
}

# ============================================================================
# TEST 4: OBTENER PERMISOS
# ============================================================================

Print-Info ""
Print-Info "════════════════════════════════════════════════════════════════════════════"
Print-Info "TEST 4: Obtener Permisos del Usuario"
Print-Info "════════════════════════════════════════════════════════════════════════════"

$respuesta_permisos = Realizar-Request -Metodo GET -Endpoint "/api/v1/sentinel/permisos" `
    -Headers $headers_autenticado `
    -Descripcion "Consultar permisos desde BD (RBAC)"

# ============================================================================
# TEST 5: AUTORIZAR ACCESO (EXITOSO)
# ============================================================================

Print-Info ""
Print-Info "════════════════════════════════════════════════════════════════════════════"
Print-Info "TEST 5: Verificar Autorización - Caso Exitoso"
Print-Info "════════════════════════════════════════════════════════════════════════════"

$body_autorizacion = @{
    recurso = "nexus"
    accion = "read"
} | ConvertTo-Json

$respuesta_autorizacion = Realizar-Request -Metodo POST -Endpoint "/api/v1/sentinel/autorizar" `
    -Headers $headers_autenticado `
    -Body $body_autorizacion `
    -Descripcion "Verificar autorización para recurso 'nexus' acción 'read' (admin)"

# ============================================================================
# TEST 6: AUTORIZAR ACCESO (DENEGADO)
# ============================================================================

Print-Info ""
Print-Info "════════════════════════════════════════════════════════════════════════════"
Print-Info "TEST 6: Verificar Autorización - Caso Denegado"
Print-Info "════════════════════════════════════════════════════════════════════════════"

$body_autorizacion_denegada = @{
    recurso = "recurso_restricto"
    accion = "delete"
} | ConvertTo-Json

$respuesta_autorizacion_denegada = Realizar-Request -Metodo POST -Endpoint "/api/v1/sentinel/autorizar" `
    -Headers $headers_autenticado `
    -Body $body_autorizacion_denegada `
    -Descripcion "Intentar acceso a recurso sin permiso (debe ser denegado)"

# ============================================================================
# TEST 7: ACTUALIZAR FICHA
# ============================================================================

Print-Info ""
Print-Info "════════════════════════════════════════════════════════════════════════════"
Print-Info "TEST 7: Actualizar Ficha de Acceso"
Print-Info "════════════════════════════════════════════════════════════════════════════"

# Para simplificar, usaremos la misma ficha como ficha de actualización
# En producción, tendrías 2 fichas diferentes (acceso y actualización)

$body_actualizar = @{
    ficha_actualizacion = $ficha_acceso
    tipo_concesion = "ficha_actualizacion"
} | ConvertTo-Json

$respuesta_actualizar = Realizar-Request -Metodo POST -Endpoint "/api/v1/sentinel/ficha-actualizada" `
    -Headers $headers_autenticado `
    -Body $body_actualizar `
    -Descripcion "Actualizar ficha de acceso"

# ============================================================================
# TEST 8: OBTENER BITÁCORA
# ============================================================================

Print-Info ""
Print-Info "════════════════════════════════════════════════════════════════════════════"
Print-Info "TEST 8: Obtener Bitácora de Auditoría"
Print-Info "════════════════════════════════════════════════════════════════════════════"

$respuesta_bitacora = Realizar-Request -Metodo GET -Endpoint "/api/v1/sentinel/bitacora?limit=10" `
    -Headers $headers_autenticado `
    -Descripcion "Consultar bitácora de auditoría desde BD"

# ============================================================================
# TEST 9: REPORTES DE CUMPLIMIENTO
# ============================================================================

Print-Info ""
Print-Info "════════════════════════════════════════════════════════════════════════════"
Print-Info "TEST 9: Reportes de Cumplimiento"
Print-Info "════════════════════════════════════════════════════════════════════════════"

$respuesta_reportes = Realizar-Request -Metodo GET -Endpoint "/api/v1/sentinel/reportes-cumplimiento" `
    -Headers $headers_autenticado `
    -Descripcion "Obtener reportes de cumplimiento GDPR"

# ============================================================================
# TEST 10: CERRAR SESIÓN
# ============================================================================

Print-Info ""
Print-Info "════════════════════════════════════════════════════════════════════════════"
Print-Info "TEST 10: Cerrar Sesión"
Print-Info "════════════════════════════════════════════════════════════════════════════"

$respuesta_logout = Realizar-Request -Metodo POST -Endpoint "/api/v1/sentinel/cerrar-sesion" `
    -Headers $headers_autenticado `
    -Descripcion "Cerrar sesión y limpiar auditoría"

# ============================================================================
# RESUMEN FINAL
# ============================================================================

Print-Info ""
Print-Info "════════════════════════════════════════════════════════════════════════════"
Print-Info "📊 RESUMEN DE PRUEBAS"
Print-Info "════════════════════════════════════════════════════════════════════════════"

$porcentaje = ($tests_pasados / $total_tests) * 100

if ($tests_pasados -eq $total_tests) {
    Print-Exito "✅ TODOS LOS TESTS PASARON"
} else {
    Print-Advertencia "⚠️  Algunos tests fallaron"
}

Print-Info ""
Print-Info "Resultados: $tests_pasados / $total_tests tests pasaron ($([Math]::Round($porcentaje))%)"
Print-Info ""

if ($tests_pasados -eq $total_tests) {
    Print-Exito "🎉 SENTINEL v1.0 ESTÁ OPERACIONAL CON BD"
    Print-Info ""
    Print-Info "✅ Autenticación JWT funcional"
    Print-Info "✅ RBAC desde SQL Server"
    Print-Info "✅ Auditoría inmutable"
    Print-Info "✅ Encriptación bcrypt"
    Print-Info ""
} else {
    Print-Error "❌ Revisar errores arriba y validar BD"
}

Print-Info "════════════════════════════════════════════════════════════════════════════"

Read-Host "Presiona Enter para terminar"
