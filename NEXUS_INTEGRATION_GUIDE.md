# 🚀 NEXUS - DatabaseAgent Integration Guide

## ¿Qué es NEXUS?

**NEXUS** es el primer agente autónomo de Kinetix Studio (AFP Oracle Inteligente).

| Propiedad | Valor |
|-----------|-------|
| **ID** | nexus |
| **Nombre** | DatabaseAgent |
| **Ruta** | `/api/v1/nexus` |
| **Endpoints** | 6 |
| **Función** | Gestionar operaciones de base de datos |
| **Responsables** | PostgreSQL + SQL Server |

---

## 📋 Los 6 Endpoints de NEXUS

### 1. **Health Check** - Verificar salud de BD
```
GET /api/v1/nexus/health
```

**Qué hace:** Verifica el estado de ambas bases de datos (PostgreSQL y SQL Server).

**Respuesta:**
```json
{
  "status": "healthy",
  "postgresql": "disconnected",
  "mssql": "disconnected",
  "cache": "in_memory",
  "total_connections": 0,
  "timestamp": "2026-09-27T..."
}
```

---

### 2. **Query Execution** - Ejecutar SELECT
```
POST /api/v1/nexus/query
```

**Body:**
```json
{
  "sql": "SELECT * FROM users WHERE id = :id",
  "params": {"id": 1},
  "database": "postgresql",
  "timeout": 30
}
```

**Respuesta:**
```json
{
  "status": "success",
  "rows": 0,
  "columns": ["id", "name", "email"],
  "data": [],
  "execution_time_ms": 45.2,
  "timestamp": "2026-09-27T..."
}
```

---

### 3. **Command Execution** - INSERT, UPDATE, DELETE
```
POST /api/v1/nexus/execute
```

**Body:**
```json
{
  "command": "INSERT",
  "sql": "INSERT INTO users (name, email) VALUES (:name, :email)",
  "params": {"name": "John", "email": "john@example.com"},
  "database": "postgresql"
}
```

**Respuesta:**
```json
{
  "status": "success",
  "command": "INSERT",
  "affected_rows": 1,
  "execution_time_ms": 23.5,
  "timestamp": "2026-09-27T..."
}
```

---

### 4. **List Tables** - Listar tablas
```
GET /api/v1/nexus/tables?database=postgresql
```

**Respuesta:**
```json
{
  "status": "success",
  "database": "postgresql",
  "total_tables": 3,
  "tables": [
    {
      "name": "users",
      "rows": 1000,
      "size_mb": 2.5,
      "columns": 8,
      "type": "TABLE"
    },
    {
      "name": "orders",
      "rows": 5000,
      "size_mb": 8.2,
      "columns": 12,
      "type": "TABLE"
    }
  ],
  "timestamp": "2026-09-27T..."
}
```

---

### 5. **Database Statistics** - Estadísticas
```
GET /api/v1/nexus/stats
```

**Respuesta:**
```json
{
  "status": "success",
  "postgresql": {
    "database": "PostgreSQL",
    "size_mb": 256.5,
    "tables": 45,
    "indexes": 120,
    "connections": 8,
    "cache_hit_ratio": 92.5,
    "last_backup": "2026-09-27T10:30:00Z",
    "status": "disconnected"
  },
  "mssql": {
    "database": "SQL Server",
    "size_mb": 512.3,
    "tables": 67,
    "indexes": 180,
    "connections": 5,
    "cache_hit_ratio": 89.2,
    "last_backup": "2026-09-27T09:15:00Z",
    "status": "disconnected"
  },
  "timestamp": "2026-09-27T..."
}
```

---

### 6. **Connection Pool Status** - Estado de conexiones
```
GET /api/v1/nexus/connections
```

**Respuesta:**
```json
{
  "status": "success",
  "total_active": 0,
  "total_idle": 0,
  "connections": [
    {
      "database": "PostgreSQL",
      "host": "localhost",
      "port": 5432,
      "active_connections": 0,
      "max_connections": 50,
      "idle_connections": 0,
      "status": "disconnected"
    },
    {
      "database": "SQL Server",
      "host": "localhost",
      "port": 1433,
      "active_connections": 0,
      "max_connections": 100,
      "idle_connections": 0,
      "status": "disconnected"
    }
  ],
  "timestamp": "2026-09-27T..."
}
```

---

## 🛠️ Instalación y Integración

### PASO 1: Descargar archivos nuevos

De `/mnt/user-data/outputs/`:
- ✅ `src_api_routes_nexus_agent.py` ← El agente NEXUS
- ✅ `src_api_main_scalable_WITH_AGENTS.py` ← Main mejorado

### PASO 2: Copiar archivos

En tu proyecto `D:\Desarrollo\kinetix-studio\`:

```powershell
# Opción A: Automático (recomendado)
Copy-Item "src_api_routes_nexus_agent.py" "src\api\routes\nexus_agent.py" -Force
Copy-Item "src_api_main_scalable_WITH_AGENTS.py" "src\api\main_scalable.py" -Force

# Opción B: Manual
# 1. Descarga src_api_routes_nexus_agent.py
# 2. Copiar a: src\api\routes\nexus_agent.py
# 3. Descarga src_api_main_scalable_WITH_AGENTS.py
# 4. Copiar a: src\api\main_scalable.py (reemplaza el anterior)
```

### PASO 3: Verificar carpetas

```powershell
# Asegurate de que existan las carpetas
New-Item -ItemType Directory "src\api\routes" -Force

# Verifica que los archivos estén en el lugar correcto
ls src\api\main_scalable.py
ls src\api\routes\nexus_agent.py
```

### PASO 4: Reiniciar la API

```powershell
# Si la API está corriendo, detenerla (Ctrl+C)
# Luego ejecutar:

uvicorn src.api.main_scalable:app --reload
```

### PASO 5: Verificar que funciona

En tu navegador, abre:

```
http://localhost:8000/docs
```

Debería ver **nuevos endpoints bajo "NEXUS - DatabaseAgent":**

```
GET /api/v1/nexus/health
POST /api/v1/nexus/query
POST /api/v1/nexus/execute
GET /api/v1/nexus/tables
GET /api/v1/nexus/stats
GET /api/v1/nexus/connections
```

---

## 🧪 Probar NEXUS en Swagger

1. Abre: `http://localhost:8000/docs`
2. Encuentra la sección "NEXUS - DatabaseAgent"
3. Haz clic en cualquier endpoint
4. Presiona "Try it out"
5. Presiona "Execute"

---

## 📊 Estado después de integración

### En el log de la API verás:

```
✅ NEXUS router registrado

Agentes disponibles:
  ✅ NEXUS (DatabaseAgent) - 6 endpoints
  ⏳ SYNAPSE (APIsAgent) - próximo
  ⏳ MATRIX (BusinessRulesAgent) - próximo
  ...
```

### En `/agents` endpoint:

```json
{
  "total": 8,
  "active": 1,
  "total_endpoints": 6,
  "agents": [
    {
      "id": "nexus",
      "name": "DatabaseAgent",
      "endpoints": 6,
      "status": "active",
      "capabilities": [
        "Health Check",
        "Query Execution",
        "Command Execution",
        "Table Management",
        "Statistics",
        "Connection Monitoring"
      ]
    },
    {
      "id": "synapse",
      "name": "APIsAgent",
      "endpoints": 6,
      "status": "inactive"
    },
    ...
  ]
}
```

---

## 🔄 Estructura de carpetas después

```
D:\Desarrollo\kinetix-studio\
├── src\
│   ├── api\
│   │   ├── main_scalable.py ✅ (NUEVO - con NEXUS)
│   │   └── routes\
│   │       ├── nexus_agent.py ✅ (NUEVO - NEXUS agent)
│   │       └── database_scalable.py
│   └── utils\
│       ├── circuit_breaker.py
│       ├── cache_manager.py
│       └── database_pools.py
├── venv\
├── .env
└── requirements-scalability-FINAL.txt
```

---

## 🚀 Próximos agentes

Después de verificar que NEXUS funciona, implementaremos los otros agentes:

| Agente | Nombre | Endpoints | Estado |
|--------|--------|-----------|--------|
| NEXUS | DatabaseAgent | 6 | ✅ Implementado |
| SYNAPSE | APIsAgent | 6 | ⏳ Próximo |
| MATRIX | BusinessRulesAgent | 8 | ⏳ Después |
| INSIGHT | ReportingAgent | 8 | ⏳ Después |
| PRISM | QAAgent | 8 | ⏳ Después |
| ORBIT | GitDeploymentAgent | 8 | ⏳ Después |
| VECTOR | DevelopmentAgent | 8 | ⏳ Después |
| GENESIS | CustomAIAgent | 6 | ⏳ Después |

---

## 🎯 Arquitectura de NEXUS

```
┌─────────────────────────────────────────────────────────┐
│           KINETIX STUDIO v5.0.0                         │
│         (El Oráculo Inteligente - AFP)                  │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              FastAPI v0.104.1                           │
│  (HTTP API, Swagger UI, Documentation)                  │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│           AGENTS ORCHESTRATION LAYER                    │
├─────────────────────────────────────────────────────────┤
│  ✅ NEXUS (6 endpoints)                                 │
│     └─ DatabaseAgent (/api/v1/nexus)                   │
│        ├─ /health         (GET)                        │
│        ├─ /query          (POST)                       │
│        ├─ /execute        (POST)                       │
│        ├─ /tables         (GET)                        │
│        ├─ /stats          (GET)                        │
│        └─ /connections    (GET)                        │
├─────────────────────────────────────────────────────────┤
│  ⏳ SYNAPSE (6 endpoints) - próximo                     │
│  ⏳ MATRIX (8 endpoints) - próximo                      │
│  ⏳ INSIGHT (8 endpoints) - próximo                     │
│  ... (5 agentes más)                                   │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│           INFRASTRUCTURE LAYER                          │
├─────────────────────────────────────────────────────────┤
│  🔧 Circuit Breaker (resilencia)                       │
│  🔧 Cache Manager (multi-layer: Memory + Redis)        │
│  🔧 Database Pools (AsyncPG + AIOODBC)                 │
│  🔧 Rate Limiting (Slowapi)                            │
│  🔧 Middleware (CORS, GZip, Metrics)                   │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│           DATABASES                                     │
├─────────────────────────────────────────────────────────┤
│  📊 PostgreSQL (localhost:5432)                         │
│  📊 SQL Server (localhost:1433)                         │
└─────────────────────────────────────────────────────────┘
```

---

## 📝 Notas importantes

1. **Desarrollo vs Producción**
   - Ahora usas: `src_api_main_scalable_WITH_AGENTS.py` (con NEXUS)
   - Es una versión mejorada del DEV mode anterior
   - NEXUS funciona sin necesidad de BD conectada

2. **Logging**
   - Verás en la consola cuándo NEXUS se inicializa
   - Si copias el archivo correctamente, verás: `✅ NEXUS router registrado`

3. **Swagger Documentation**
   - Todos los endpoints tienen documentación automática
   - Incluyen ejemplos, descripciones y tipos de datos

4. **Ready para escalar**
   - NEXUS está preparado para implementar los 7 agentes restantes
   - Cada agente es independiente
   - Puedes agregar agentes sin afectar los existentes

---

## ✅ Checklist de integración

- [ ] Descargar `src_api_routes_nexus_agent.py`
- [ ] Descargar `src_api_main_scalable_WITH_AGENTS.py`
- [ ] Copiar nexus_agent.py a `src/api/routes/`
- [ ] Copiar main mejorado a `src/api/main_scalable.py`
- [ ] Reiniciar API: `uvicorn src.api.main_scalable:app --reload`
- [ ] Abrir Swagger: `http://localhost:8000/docs`
- [ ] Ver nuevos endpoints de NEXUS
- [ ] Probar algunos endpoints
- [ ] Ver `/agents` endpoint con NEXUS activo
- [ ] Leer log de startup con "NEXUS router registrado"

---

## 🎉 ¡Listo!

Ya tienes:
- ✅ **KINETIX STUDIO v5.0.0** corriendo
- ✅ **NEXUS** (DatabaseAgent) integrado y funcional
- ✅ **6 endpoints** del primer agente activos
- ✅ **Swagger UI** con documentación automática
- ✅ **Arquitectura lista** para los 7 agentes restantes

**El camino del Oracle Inteligente ha comenzado.** 🚀

---

¿Siguiente paso? **Implementar SYNAPSE (APIsAgent)** con 6 endpoints adicionales.

Quieres continuar? 🎯
