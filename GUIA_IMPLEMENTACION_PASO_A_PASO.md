# 🚀 GUÍA DE IMPLEMENTACIÓN - MOTOR DE REGLAS SQL SERVER (ESPAÑOL)

Guía paso a paso para implementar el motor de reglas de negocio en SQL Server.

---

## 📋 Contenido

1. [Prerrequisitos](#prerequisitos)
2. [Paso 1: Preparar el Ambiente](#paso-1-preparar-el-ambiente)
3. [Paso 2: Crear la Base de Datos](#paso-2-crear-la-base-de-datos)
4. [Paso 3: Ejecutar el Schema](#paso-3-ejecutar-el-schema)
5. [Paso 4: Ejecutar los Ejemplos](#paso-4-ejecutar-los-ejemplos)
6. [Paso 5: Validar la Creación](#paso-5-validar-la-creacion)
7. [Paso 6: Integrar con Python/FastAPI](#paso-6-integrar-con-pythonfastapi)
8. [Troubleshooting](#troubleshooting)

---

## ✅ Prerequisitos

### Software Requerido

- ✅ SQL Server 2016 o superior
- ✅ SQL Server Management Studio (SSMS) v17+
- ✅ Python 3.9+ (para integración FastAPI)
- ✅ pyodbc (para conexión SQL Server desde Python)

### Permisos Requeridos

- ✅ Acceso a SQL Server con permisos de crear bases de datos
- ✅ Usuario SA o equivalent
- ✅ Permisos de lectura/escritura en el directorio de archivos

---

## 🔧 PASO 1: Preparar el Ambiente

### 1.1 Verificar Conexión a SQL Server

**En PowerShell:**
```powershell
# Verificar que SQL Server está corriendo
Get-Service MSSQLSERVER

# Resultado esperado:
# Status   Name               DisplayName
# ------   ----               -----------
# Running  MSSQLSERVER        SQL Server (MSSQLSERVER)
```

### 1.2 Verificar SSMS

```powershell
# Abrir SSMS
ssms
```

---

## 🗄️ PASO 2: Crear la Base de Datos

### 2.1 Crear base de datos vacía (Opción A: SSMS)

1. Abrir **SQL Server Management Studio**
2. Conectarse al servidor
3. Clic derecho en **Databases**
4. **New Database**
5. Nombre: `afp_db` (o tu nombre preferido)
6. Click **OK**

### 2.2 Crear base de datos vacía (Opción B: PowerShell)

```powershell
$servidor = "localhost"
$bd = "afp_db"
$usuario = "sa"
$password = "tu_contraseña_sa"

# Crear DB
sqlcmd -S $servidor -U $usuario -P $password -Q "CREATE DATABASE $bd;"

# Verificar creación
sqlcmd -S $servidor -U $usuario -P $password -Q "SELECT name FROM sys.databases WHERE name = '$bd';"
```

---

## 📝 PASO 3: Ejecutar el Schema

### 3.1 Ejecutar Schema (Opción A: SSMS)

1. Abrir **SQL Server Management Studio**
2. Conectarse al servidor y seleccionar DB `afp_db`
3. **File** → **Open** → Seleccionar `reglas_negocio_schema_FINAL.sql`
4. Click en el botón **Execute** (F5 o Ctrl+Shift+E)
5. Esperar a que termine (2-5 segundos)
6. Verificar que NO hay errores en la ventana "Messages"

### 3.2 Ejecutar Schema (Opción B: PowerShell)

```powershell
# Variables
$servidor = "localhost"
$bd = "afp_db"
$usuario = "sa"
$password = "tu_contraseña"
$archivo_schema = "C:\ruta\reglas_negocio_schema_FINAL.sql"

# Ejecutar script
sqlcmd -S $servidor -U $usuario -P $password -d $bd -i $archivo_schema

# Resultado esperado:
# ✅ SCHEMA CREADO EXITOSAMENTE - SIN ERRORES
#
# Objetos creados:
#   - 6 Tablas: reglas_negocio, condiciones_regla, ...
#   - 6 Stored Procedures: sp_crear, sp_evaluar, ...
#   - 3 Vistas: vw_reglas_por_empresa, vw_resumen_auditoria, vw_reglas_activas_por_nivel
#   - 10 Índices optimizados
```

### 3.3 Validar Creación del Schema

```sql
-- Ejecutar en SSMS
SELECT 
    'TABLAS' AS tipo, 
    COUNT(*) AS cantidad
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo' 
  AND TABLE_NAME IN (
    'reglas_negocio', 
    'condiciones_regla', 
    'acciones_regla', 
    'auditoria_evaluacion_reglas', 
    'cache_evaluacion_reglas', 
    'herencia_reglas'
  )

UNION ALL

SELECT 
    'PROCEDURES' AS tipo,
    COUNT(*) AS cantidad
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'dbo'
  AND ROUTINE_TYPE = 'PROCEDURE'
  AND ROUTINE_NAME LIKE 'sp_%'

UNION ALL

SELECT 
    'VISTAS' AS tipo,
    COUNT(*) AS cantidad
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME LIKE 'vw_%';

-- Resultado esperado:
-- tipo         | cantidad
-- TABLAS       | 6
-- PROCEDURES   | 6
-- VISTAS       | 3
```

---

## 📊 PASO 4: Ejecutar los Ejemplos

### 4.1 Cargar Ejemplos (Opción A: SSMS)

1. **File** → **Open** → Seleccionar `reglas_negocio_ejemplos_FINAL.sql`
2. Click **Execute** (F5)
3. Verifica en "Messages" que todas las reglas fueron creadas exitosamente

### 4.2 Cargar Ejemplos (Opción B: PowerShell)

```powershell
$servidor = "localhost"
$bd = "afp_db"
$usuario = "sa"
$password = "tu_contraseña"
$archivo_ejemplos = "C:\ruta\reglas_negocio_ejemplos_FINAL.sql"

# Ejecutar ejemplos
sqlcmd -S $servidor -U $usuario -P $password -d $bd -i $archivo_ejemplos

# Resultado esperado: Mensajes confirmando cada regla creada
# REGLA 1.1 creada: validacion_email_global
# REGLA 1.2 creada: validacion_monto_minimo
# REGLA 1.3 creada: validacion_estado_documento
# REGLA 2.1 creada: limite_descuento_retail
# ... etc ...
# ✅ TODAS LAS REGLAS FUERON CREADAS EXITOSAMENTE
```

---

## ✅ PASO 5: Validar la Creación

### 5.1 Listar todas las reglas

```sql
-- En SSMS
EXEC sp_listar_reglas_por_alcance
    @nivel_alcance_param = NULL,
    @estado_param = 'activa';

-- Resultado esperado: 11 filas (todas las reglas creadas)
```

### 5.2 Ver resumen por nivel

```sql
-- Reglas GLOBALES
EXEC sp_listar_reglas_por_alcance
    @nivel_alcance_param = 'global',
    @estado_param = 'activa';
-- Esperado: 3 reglas

-- Reglas LÍNEA DE NEGOCIO
EXEC sp_listar_reglas_por_alcance
    @nivel_alcance_param = 'linea_negocio',
    @estado_param = 'activa';
-- Esperado: 4 reglas

-- Reglas EMPRESA (Casab)
EXEC sp_listar_reglas_por_alcance
    @nivel_alcance_param = 'empresa',
    @id_empresa_param = 523,
    @estado_param = 'activa';
-- Esperado: 3 reglas
```

### 5.3 Ver vistas de reporting

```sql
-- Resumen de reglas activas por nivel
SELECT * FROM vw_reglas_activas_por_nivel;

-- Reglas por empresa (example: Casab 523)
SELECT * FROM vw_reglas_por_empresa WHERE id_empresa = 523;
```

---

## 🔌 PASO 6: Integrar con Python/FastAPI

### 6.1 Instalación de dependencias

```powershell
# Instalar pyodbc
pip install pyodbc

# Instalar FastAPI y uvicorn
pip install fastapi uvicorn

# Instalar pydantic para validación
pip install pydantic
```

### 6.2 Crear archivo de conexión Python

Crear archivo `conexion_sql.py`:

```python
import pyodbc
import json
from typing import Optional, Dict, Any

class ConexionSQLServer:
    def __init__(self, servidor: str, usuario: str, contraseña: str, base_datos: str):
        self.servidor = servidor
        self.usuario = usuario
        self.contraseña = contraseña
        self.base_datos = base_datos
        self.conexion = None
    
    def conectar(self):
        """Conectar a SQL Server"""
        try:
            connection_string = (
                f'Driver={{ODBC Driver 17 for SQL Server}};'
                f'Server={self.servidor};'
                f'Database={self.base_datos};'
                f'UID={self.usuario};'
                f'PWD={self.contraseña}'
            )
            self.conexion = pyodbc.connect(connection_string)
            self.conexion.autocommit = True
            return True
        except pyodbc.Error as e:
            print(f"Error de conexión: {e}")
            return False
    
    def evaluar_regla(self, id_regla: str, id_empresa: int, 
                     linea_negocio: str, contexto: Dict[str, Any]) -> Dict:
        """Evaluar una regla"""
        try:
            cursor = self.conexion.cursor()
            contexto_json = json.dumps(contexto)
            
            cursor.execute("""
                EXEC sp_evaluar_regla_jerarquica
                    @id_regla_param = ?,
                    @id_empresa_param = ?,
                    @linea_negocio_param = ?,
                    @json_contexto = ?,
                    @evaluada_por = ?
            """, (id_regla, id_empresa, linea_negocio, contexto_json, 'api'))
            
            resultado = cursor.fetchone()
            cursor.close()
            
            return {
                'resultado': resultado[0],
                'id_regla': resultado[1],
                'condiciones_cumplidas': bool(resultado[2]),
                'decision': resultado[3],
                'valores_calculados': json.loads(resultado[4]) if resultado[4] else {},
                'id_auditoria': resultado[5]
            }
        except pyodbc.Error as e:
            return {'error': str(e)}
    
    def listar_reglas(self, nivel: Optional[str] = None, 
                     id_empresa: Optional[int] = None) -> list:
        """Listar reglas"""
        try:
            cursor = self.conexion.cursor()
            cursor.execute("""
                EXEC sp_listar_reglas_por_alcance
                    @nivel_alcance_param = ?,
                    @id_empresa_param = ?,
                    @estado_param = 'activa'
            """, (nivel, id_empresa))
            
            resultados = []
            for row in cursor.fetchall():
                resultados.append({
                    'id_regla': row[0],
                    'nombre': row[1],
                    'nivel_alcance': row[3],
                    'prioridad': row[7],
                    'total_condiciones': row[10],
                    'total_acciones': row[11]
                })
            
            cursor.close()
            return resultados
        except pyodbc.Error as e:
            return [{'error': str(e)}]
    
    def cerrar(self):
        """Cerrar conexión"""
        if self.conexion:
            self.conexion.close()
```

### 6.3 Crear API FastAPI

Crear archivo `app.py`:

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from conexion_sql import ConexionSQLServer

# Inicializar FastAPI
app = FastAPI(
    title="Motor de Reglas de Negocio",
    description="API REST para evaluación de reglas",
    version="1.0.0"
)

# Conexión SQL Server
db = ConexionSQLServer(
    servidor="localhost",
    usuario="sa",
    contraseña="tu_contraseña",
    base_datos="afp_db"
)

# Modelos
class ContextoEvaluacion(BaseModel):
    id_cliente: Optional[int] = None
    monto: Optional[float] = None
    segmento_cliente: Optional[str] = None
    tipo_documento: Optional[str] = None
    porcentaje_descuento: Optional[float] = None

# Conectar a BD al iniciar
@app.on_event("startup")
async def startup():
    db.conectar()

# Endpoints
@app.get("/api/v1/salud")
async def health_check():
    """Verificar que la API está activa"""
    return {"status": "ok", "mensaje": "Motor de Reglas activo"}

@app.post("/api/v1/reglas/evaluar")
async def evaluar_regla(
    id_regla: str,
    id_empresa: int,
    linea_negocio: str,
    contexto: ContextoEvaluacion
):
    """Evaluar una regla contra un contexto"""
    resultado = db.evaluar_regla(
        id_regla=id_regla,
        id_empresa=id_empresa,
        linea_negocio=linea_negocio,
        contexto=contexto.dict(exclude_none=True)
    )
    
    if 'error' in resultado:
        raise HTTPException(status_code=500, detail=resultado['error'])
    
    return resultado

@app.get("/api/v1/reglas/listar")
async def listar_reglas(
    nivel: Optional[str] = None,
    id_empresa: Optional[int] = None
):
    """Listar reglas por criterios"""
    return db.listar_reglas(nivel=nivel, id_empresa=id_empresa)

# Cerrar conexión al terminar
@app.on_event("shutdown")
async def shutdown():
    db.cerrar()

# Para ejecutar:
# uvicorn app:app --reload --port 8000
```

### 6.4 Ejecutar la API

```powershell
# Desde PowerShell (en el directorio del proyecto)
uvicorn app:app --reload --port 8000

# Resultado:
# INFO:     Uvicorn running on http://127.0.0.1:8000
# INFO:     Application startup complete
```

### 6.5 Probar los endpoints

**En PowerShell:**
```powershell
# 1. Health check
curl.exe -X GET http://localhost:8000/api/v1/salud

# 2. Listar reglas globales
curl.exe -X GET "http://localhost:8000/api/v1/reglas/listar?nivel=global"

# 3. Evaluar regla (descuento VIP Casab)
$body = @{
    id_cliente = 1050
    segmento_cliente = "VIP"
    monto = 15000
    tipo_documento = "factura"
} | ConvertTo-Json

curl.exe -X POST "http://localhost:8000/api/v1/reglas/evaluar?id_regla=descuento_vip_casab&id_empresa=523&linea_negocio=RETAIL" `
    -H "Content-Type: application/json" `
    -Body $body
```

**Resultado esperado:**
```json
{
  "resultado": "EXITO",
  "id_regla": "descuento_vip_casab",
  "condiciones_cumplidas": true,
  "decision": "permitida",
  "valores_calculados": {
    "descuento_vip": 3750
  },
  "id_auditoria": 1
}
```

---

## 🆘 Troubleshooting

### Problema: No puedo conectar a SQL Server

```powershell
# Verificar que SQL Server está corriendo
Get-Service MSSQLSERVER | Start-Service

# Verificar que el ODBC driver está instalado
# Descargar de: https://www.microsoft.com/en-us/download/details.aspx?id=50420
```

### Problema: Error "Login failed for user 'sa'"

```powershell
# Verificar usuario y contraseña
sqlcmd -S localhost -U sa -P tu_contraseña -Q "SELECT @@VERSION;"
```

### Problema: Error "Cannot find database afp_db"

```sql
-- Verificar en SSMS
SELECT name FROM sys.databases;

-- Si no existe, crear:
CREATE DATABASE afp_db;
```

### Problema: Error "Cannot open include file"

Asegúrate de que los archivos `.sql` están en la ruta correcta:
```powershell
Test-Path "C:\ruta\reglas_negocio_schema_FINAL.sql"
```

---

## 📊 Verificación Final

Después de todo, ejecutar este script para validar:

```sql
-- Contar objetos
SELECT 
    CONCAT(
        'TABLAS: ', 
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME LIKE 'reglas%' OR TABLE_NAME LIKE 'condiciones%' OR TABLE_NAME LIKE 'acciones%' OR TABLE_NAME LIKE 'auditoria%' OR TABLE_NAME LIKE 'cache%' OR TABLE_NAME LIKE 'herencia%'),
        ' | PROCEDURES: ',
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.ROUTINES WHERE ROUTINE_SCHEMA = 'dbo' AND ROUTINE_TYPE = 'PROCEDURE'),
        ' | VISTAS: ',
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.VIEWS WHERE TABLE_SCHEMA = 'dbo')
    ) AS Status;

-- Resultado esperado:
-- TABLAS: 6 | PROCEDURES: 6 | VISTAS: 3
```

✅ **¡Implementación completada exitosamente!**

---

## 📚 Archivos de Referencia

- `reglas_negocio_schema_FINAL.sql` - Schema principal
- `reglas_negocio_ejemplos_FINAL.sql` - Datos de ejemplo
- `REGLAS_NEGOCIO_SQL_SERVER.md` - Documentación completa
- `CAMBIOS_CORRECCION_SQL_ERRORS.md` - Errores y soluciones
- `ERRORES_FINALES_CORREGIDOS.md` - Errores finales resueltos
- `CONVERSION_NOMBRES_INGLES_ESPANOL.md` - Mapeo de nombres

¡Listo para producción! 🚀
