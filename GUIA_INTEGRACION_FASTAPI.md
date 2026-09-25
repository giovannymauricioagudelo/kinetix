# 📚 Guía de Integración - BusinessRulesAgent FastAPI

**Objetivo:** Integrar los 8 endpoints del BusinessRulesAgent con FastAPI en el proyecto Kinetix Studio

**Tiempo estimado:** 20 minutos

---

## ✅ CHECKLIST PREVIO

- [ ] Python 3.9.7 instalado
- [ ] FastAPI 0.95+ instalado
- [ ] pyodbc instalado (`pip install pyodbc`)
- [ ] SQL Server 2019+ configurado y ejecutando
- [ ] Archivo `reglas_negocio_schema_FINAL.sql` ejecutado en SQL Server
- [ ] Archivo `reglas_negocio_ejemplos_FINAL.sql` ejecutado (11 reglas cargadas)

---

## 📋 PASO 1: Copiar Archivos al Proyecto

### 1.1 Copiar el router FastAPI

```bash
# Desde el terminal, en la raíz del proyecto:

# Windows
copy business_rules.py src\api\routes\

# Linux/Mac
cp business_rules.py src/api/routes/
```

**Resultado esperado:**
```
✅ src/api/routes/business_rules.py (644 líneas)
```

### 1.2 Copiar tests

```bash
# Windows
copy test_business_rules_agent.py tests\unit\

# Linux/Mac
cp test_business_rules_agent.py tests/unit/
```

**Resultado esperado:**
```
✅ tests/unit/test_business_rules_agent.py (17 tests)
```

---

## 🔧 PASO 2: Actualizar main.py

### 2.1 Opción A: Copiar main_UPDATED.py (recomendado)

```bash
# Windows
copy main_UPDATED.py src\api\main.py

# Linux/Mac
cp main_UPDATED.py src/api/main.py
```

**Resultado esperado:**
```
✅ src/api/main.py (350 líneas con BusinessRulesAgent incluido)
```

### 2.2 Opción B: Integración manual

Si prefieres hacerlo manualmente, en `src/api/main.py`:

**PASO 2.2.1: Agregar import**

```python
# Buscar el bloque de importaciones de routers (líneas ~20-30)
# Agregar:

from src.api.routes.business_rules import router as business_rules_router
```

**PASO 2.2.2: Incluir router en FastAPI**

```python
# Buscar donde se hace:
# app.include_router(apis_router, ...)

# Agregar DESPUÉS:

app.include_router(
    business_rules_router,
    prefix="/api/v1/rules",
    tags=["BusinessRulesAgent"]
)
```

**Resultado esperado:**
```python
# El app ahora incluye 3 routers:
app.include_router(database_router, prefix="/api/v1/database", tags=["DatabaseAgent"])
app.include_router(apis_router, prefix="/api/v1/apis", tags=["APIsAgent"])
app.include_router(business_rules_router, prefix="/api/v1/rules", tags=["BusinessRulesAgent"])
```

---

## 🔐 PASO 3: Configurar Conexión SQL Server

En `src/api/routes/business_rules.py`, buscar la función `get_connection()` (línea ~85):

```python
def get_connection():
    """Obtener conexión a SQL Server"""
    try:
        connection_string = (
            'Driver={ODBC Driver 17 for SQL Server};'
            'Server=localhost;'              # ← CAMBIAR AQUÍ
            'Database=afp_db;'               # ← CAMBIAR AQUÍ
            'UID=sa;'                        # ← CAMBIAR AQUÍ
            'PWD=tu_contraseña'              # ← CAMBIAR AQUÍ
        )
```

### Ejemplo 1: Local SQL Server Express
```python
connection_string = (
    'Driver={ODBC Driver 17 for SQL Server};'
    'Server=.\\SQLEXPRESS;'          # Local con SQL Express
    'Database=afp_db;'
    'UID=sa;'
    'PWD=Admin123'
)
```

### Ejemplo 2: SQL Server en Azure
```python
connection_string = (
    'Driver={ODBC Driver 17 for SQL Server};'
    'Server=kinetix-sqlserver.database.windows.net;'
    'Database=afp_db;'
    'UID=admin@kinetix-sqlserver;'
    'PWD=ComplejaP@ssw0rd'
)
```

### Ejemplo 3: SQL Server remoto corporativo
```python
connection_string = (
    'Driver={ODBC Driver 17 for SQL Server};'
    'Server=192.168.1.100,1433;'
    'Database=afp_db;'
    'UID=kinetix_user;'
    'PWD=SecurePass123'
)
```

---

## 📦 PASO 4: Instalar/Verificar Dependencias

### 4.1 Verificar requirements.txt

```bash
pip list | grep -E "(fastapi|pyodbc|pydantic)"
```

### 4.2 Agregar a requirements.txt si falta

```bash
# Abrir requirements.txt y agregar:

pyodbc==4.0.37
```

O instalar directamente:

```bash
pip install pyodbc==4.0.37
```

**Verificación:**
```bash
python -c "import pyodbc; print('✅ pyodbc OK')"
python -c "import fastapi; print('✅ fastapi OK')"
```

---

## 🚀 PASO 5: Iniciar el Servidor

### 5.1 Iniciar con auto-reload (desarrollo)

```bash
python -m uvicorn src.api.main:app --reload --port 8000
```

**Salida esperada:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

### 5.2 Iniciar sin reload (producción)

```bash
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 🌐 PASO 6: Verificar Endpoints

### 6.1 Swagger UI (Documentación interactiva)

```
🌐 http://localhost:8000/api/docs
```

**Verificar que ves:**
- DatabaseAgent (6 endpoints)
- APIsAgent (6 endpoints)
- BusinessRulesAgent (8 endpoints) ← **NUEVO**

### 6.2 Health Check

```bash
curl http://localhost:8000/health
```

**Respuesta esperada:**
```json
{
  "resultado": "OK",
  "aplicacion": "Kinetix Studio",
  "estado": "operacional",
  "agentes_activos": 3,
  "endpoints_totales": 20,
  "timestamp": "2026-09-22T14:30:45.123456"
}
```

### 6.3 Health Check BusinessRulesAgent específico

```bash
curl http://localhost:8000/api/v1/rules/health
```

**Respuesta esperada:**
```json
{
  "resultado": "OK",
  "agente": "BusinessRulesAgent",
  "estado": "HEALTHY",
  "sql_server": "conectado",
  "tablas": "presentes",
  "stored_procedures": "presentes",
  "vistas": "presentes"
}
```

---

## 🧪 PASO 7: Ejecutar Tests

### 7.1 Ejecutar todos los tests

```bash
python -m pytest tests/unit/test_business_rules_agent.py -v
```

**Salida esperada:**
```
tests/unit/test_business_rules_agent.py::test_crear_regla_valida PASSED
tests/unit/test_business_rules_agent.py::test_crear_regla_sin_condiciones PASSED
tests/unit/test_business_rules_agent.py::test_evaluar_regla_nivel_global PASSED
...
=================== 17 passed in 2.32s ===================
```

### 7.2 Ejecutar con coverage

```bash
python -m pytest tests/unit/test_business_rules_agent.py --cov=src.api.routes.business_rules --cov-report=html
```

**Verificar:** `htmlcov/index.html` en el navegador

---

## 🧬 PASO 8: Probar Endpoints (curl)

### 8.1 Crear una regla

```bash
curl -X POST http://localhost:8000/api/v1/rules/create \
  -H "Content-Type: application/json" \
  -d '{
    "id_regla": "test_regla_nuevo",
    "nombre": "Regla de Prueba",
    "descripcion": "Una regla creada vía API",
    "nivel_alcance": "global",
    "prioridad": 50,
    "condiciones": [
      {
        "campo": "monto",
        "operador": "gte",
        "valor": "1000",
        "orden": 1
      }
    ],
    "acciones": [
      {
        "tipo": "permitir",
        "detalles": {"motivo": "monto >= 1000"},
        "orden": 1
      }
    ]
  }' \
  -G --data-urlencode "creada_por=usuario@test.com"
```

**Respuesta esperada:**
```json
{
  "resultado": "EXITO",
  "id_regla": "test_regla_nuevo",
  "mensaje": "Regla 'Regla de Prueba' creada exitosamente",
  "timestamp": "2026-09-22T14:35:12.456789"
}
```

### 8.2 Listar reglas

```bash
curl http://localhost:8000/api/v1/rules/list?nivel_alcance=global
```

**Respuesta esperada:**
```json
{
  "resultado": "EXITO",
  "total": 4,
  "reglas": [
    {
      "id_regla": "validacion_email_global",
      "nombre": "Validación de Email",
      "nivel_alcance": "global",
      "prioridad": 80,
      "estado": "activa",
      "total_condiciones": 1,
      "total_acciones": 1
    }
    ...
  ]
}
```

### 8.3 Evaluar una regla

```bash
curl -X POST http://localhost:8000/api/v1/rules/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "id_cliente": 1050,
    "monto": 15000,
    "segmento_cliente": "VIP",
    "tipo_documento": "factura",
    "estado_documento": "activo"
  }' \
  -G \
  --data-urlencode "id_regla=descuento_vip_casab" \
  --data-urlencode "id_empresa=523" \
  --data-urlencode "linea_negocio=RETAIL"
```

**Respuesta esperada:**
```json
{
  "resultado": "EXITO",
  "id_regla": "descuento_vip_casab",
  "condiciones_cumplidas": true,
  "decision": "permitida",
  "valores_calculados": {
    "descuento_vip": 3750
  },
  "id_auditoria": 142,
  "timestamp": "2026-09-22T14:40:25.789123"
}
```

---

## 🔍 PASO 9: Validación Final

### Checklist de validación

```
✅ main.py contiene import de business_rules_router
✅ FastAPI incluye router con prefix="/api/v1/rules"
✅ Función get_connection() tiene credenciales correctas
✅ pyodbc está instalado
✅ Servidor FastAPI inicia sin errores
✅ http://localhost:8000/api/docs muestra 20 endpoints
✅ /health retorna "operacional"
✅ /api/v1/rules/health retorna "HEALTHY"
✅ Todos los 17 tests pasan
✅ Puedo crear una regla vía POST /create
✅ Puedo listar reglas vía GET /list
✅ Puedo evaluar una regla vía POST /evaluate
```

### Verificación rápida (all-in-one)

```bash
# Script de validación rápida
python << 'EOF'
import requests
import json

print("🔍 Validando endpoints de BusinessRulesAgent...\n")

base_url = "http://localhost:8000/api/v1/rules"

tests = [
    ("Health Check", "GET", f"{base_url}/health", None),
    ("Status", "GET", f"{base_url}/status", None),
    ("List Rules", "GET", f"{base_url}/list", None),
]

for test_name, method, url, data in tests:
    try:
        if method == "GET":
            r = requests.get(url)
        else:
            r = requests.post(url, json=data)
        
        if r.status_code == 200:
            print(f"✅ {test_name}")
        else:
            print(f"❌ {test_name}: HTTP {r.status_code}")
    except Exception as e:
        print(f"❌ {test_name}: {str(e)}")

print("\n✅ Validación completada")
EOF
```

---

## 🐛 SOLUCIÓN DE PROBLEMAS

### Problema: "ModuleNotFoundError: No module named 'pyodbc'"
**Solución:**
```bash
pip install pyodbc==4.0.37
```

### Problema: "Connection string invalid"
**Solución:**
- Verificar que SQL Server está ejecutando
- Verificar credenciales en `get_connection()`
- Verificar firewall: puerto 1433 abierto

### Problema: "Procedure 'sp_crear_regla_negocio' not found"
**Solución:**
- Ejecutar `reglas_negocio_schema_FINAL.sql` en SQL Server
- Verificar que se crearon los 6 SPs: `sp_crear_regla_negocio`, `sp_evaluar_regla_jerarquica`, etc.

### Problema: "Port 8000 already in use"
**Solución:**
```bash
# Cambiar puerto a 8001
python -m uvicorn src.api.main:app --reload --port 8001
```

### Problema: "Test failures en pytest"
**Solución:**
```bash
# Ejecutar tests con output detallado
python -m pytest tests/unit/test_business_rules_agent.py -vv -s

# Ejecutar un test específico
python -m pytest tests/unit/test_business_rules_agent.py::test_crear_regla_valida -vv
```

---

## 📊 VISTA PREVIA DEL SWAGGER UI

Una vez iniciado el servidor, en `http://localhost:8000/api/docs` verás:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Kinetix Studio - AFP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📁 DatabaseAgent (6)
  POST   /api/v1/database/create-table
  POST   /api/v1/database/insert
  POST   /api/v1/database/query
  PUT    /api/v1/database/update/{id}
  DELETE /api/v1/database/delete/{id}
  GET    /api/v1/database/export

📁 APIsAgent (6)
  GET    /api/v1/apis/list
  POST   /api/v1/apis/register
  POST   /api/v1/apis/call/{api_id}
  GET    /api/v1/apis/validate/{api_id}
  GET    /api/v1/apis/logs
  GET    /api/v1/apis/health

📁 BusinessRulesAgent (8) ✨
  POST   /api/v1/rules/create
  POST   /api/v1/rules/evaluate
  GET    /api/v1/rules/list
  PUT    /api/v1/rules/{rule_id}
  DELETE /api/v1/rules/{rule_id}
  GET    /api/v1/rules/audit
  GET    /api/v1/rules/status
  GET    /api/v1/rules/health

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TOTAL: 20 ENDPOINTS OPERACIONALES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 📞 SOPORTE RÁPIDO

| Pregunta | Respuesta |
|----------|-----------|
| ¿Dónde está el archivo `business_rules.py`? | En `/mnt/user-data/outputs/business_rules.py` |
| ¿Dónde está el archivo `main_UPDATED.py`? | En `/mnt/user-data/outputs/main_UPDATED.py` |
| ¿Dónde está la documentación completa? | En `ESTADO_PROYECTO_AFP_SEMANA3.md` |
| ¿Cuántos endpoints hay? | 20 (6+6+8) |
| ¿Cuál es el prefijo del BusinessRulesAgent? | `/api/v1/rules` |
| ¿SQL Server es obligatorio? | Sí, para BusinessRulesAgent |
| ¿PostgreSQL es obligatorio? | Sí, para DatabaseAgent |

---

## ✅ RESUMEN

**Has completado la integración cuando:**

1. ✅ Copiaste `business_rules.py` a `src/api/routes/`
2. ✅ Actualizaste `src/api/main.py` con el router
3. ✅ Configuraste credenciales SQL Server en `get_connection()`
4. ✅ Instalaste `pyodbc`
5. ✅ El servidor FastAPI inicia sin errores
6. ✅ Ves 20 endpoints en `/api/docs`
7. ✅ `/api/v1/rules/health` retorna "HEALTHY"
8. ✅ Todos los 17 tests pasan

**PRÓXIMO PASO:** Implementar el Reporting Agent (Semana 4)

---

**Última actualización:** 2026-09-22 14:30 UTC
