# PostgreSQL Connection Error - Soluciones

## 🔴 El error que ves:

```
OSError: Multiple exceptions: [Errno 10061] Connect call failed ('::1', 5432, 0, 0), 
[Errno 10061] Connect call failed ('127.0.0.1', 5432)
```

**Significa:** PostgreSQL no está corriendo en el puerto 5432.

---

## 🛠️ OPCIÓN 1: Usar versión DEVELOPMENT (Recomendada para empezar)

Esta versión **NO falla** si PostgreSQL/Redis no están disponibles.

### Paso 1: Descargar archivo nuevo

Descarga de `/mnt/user-data/outputs/`:
- **src_api_main_scalable_DEV.py**

### Paso 2: Reemplazar archivo actual

En `D:\Desarrollo\kinetix-studio\src\api\`:
- Renombra: `main_scalable.py` → `main_scalable_OLD.py` (backup)
- Copia: `src_api_main_scalable_DEV.py` → `main_scalable.py`

O simplemente ejecuta esto en PowerShell (en tu carpeta del proyecto):

```powershell
Copy-Item "src_api_main_scalable_DEV.py" "src\api\main_scalable.py" -Force
```

### Paso 3: Ejecutar

```powershell
uvicorn src.api.main_scalable:app --reload
```

Debería ver:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete

⚠️  No se pudo conectar a bases de datos: ...
   Continuando en modo sin BD

✅ Circuit breaker pool inicializado
==================================================
API disponible en: http://localhost:8000
Swagger UI: http://localhost:8000/api/docs
==================================================
```

**✅ Esto es CORRECTO para desarrollo!**

---

## 🚀 OPCIÓN 2: Instalar PostgreSQL y Redis (Para producción)

Si quieres que funcione completamente, necesitas:

### A. PostgreSQL

**Windows - Descarga e instala:**
- [PostgreSQL 15.x para Windows](https://www.postgresql.org/download/windows/)
- Durante instalación:
  - Puerto: **5432** (default)
  - Password: algo seguro (que recuerdes)
  - Usuario: `postgres` (default)

**Después de instalar, crear BD:**

```sql
-- Abre pgAdmin (que viene con PostgreSQL)
-- O usa psql en PowerShell:

psql -U postgres

-- Crear usuario
CREATE USER kinetix_user WITH PASSWORD 'kinetix_pass';

-- Crear BD
CREATE DATABASE kinetix OWNER kinetix_user;

-- Permisos
GRANT ALL PRIVILEGES ON DATABASE kinetix TO kinetix_user;

-- Conectar
psql -U kinetix_user -d kinetix
```

### B. Redis

**Windows - Opción A: Windows Subsystem for Linux (WSL)**

```powershell
# En WSL (bash)
sudo apt-get update
sudo apt-get install redis-server

# Iniciar Redis
redis-server
```

**Windows - Opción B: Docker (si tienes Docker Desktop)**

```powershell
# En PowerShell
docker run -d -p 6379:6379 redis:latest
```

**Windows - Opción C: Redis Windows (memurai)**

- Descarga: https://github.com/microsoftarchive/redis/releases
- O: [Memurai for Redis](https://www.memurai.com/)

### Verificar que funciona

```powershell
# Terminal 1: PostgreSQL
# Deberia estar corriendo automaticamente en Windows

# Terminal 2: Redis
redis-cli
# Deberia responder "PONG"

# Terminal 3: Tu API
uvicorn src.api.main_scalable:app --reload
```

---

## 📋 Comparación

| Aspecto | Opción 1 (DEV) | Opción 2 (Full) |
|---------|-----------------|-----------------|
| **Facilidad** | ⭐⭐⭐⭐⭐ Muy fácil | ⭐⭐ Requiere setup |
| **Rapidez** | Inmediato | 20-30 min |
| **BD disponible** | ❌ No | ✅ Sí |
| **Cache disponible** | ❌ (solo en memoria) | ✅ Redis |
| **Para desarrollo** | ✅ Perfecto | ✅ Sí |
| **Para producción** | ❌ No | ✅ Sí |
| **API funciona** | ✅ Sí | ✅ Sí |
| **Health checks** | ✅ Sí | ✅ Sí |
| **Endpoints DB** | ⚠️ Retornan error | ✅ Funcionan |

---

## ✅ Recomendación

**Para AHORA:** Usa **Opción 1 (DEV)**
- Levanta en 10 segundos
- API funciona perfectamente
- Explora los endpoints
- Verifica salud del sistema

**Para DESPUÉS:** Instala **Opción 2 (Full)**
- Cuando necesites probar con datos reales
- Antes de llevar a producción
- Para testing completo

---

## 🎯 Próximos pasos con Opción 1 (DEV)

```powershell
# 1. Reemplazar archivo
Copy-Item "src_api_main_scalable_DEV.py" "src\api\main_scalable.py" -Force

# 2. Ejecutar API
uvicorn src.api.main_scalable:app --reload

# 3. Verificar salud
curl http://localhost:8000/health

# 4. Abrir en navegador
http://localhost:8000/api/docs

# 5. Ver metricas
curl http://localhost:8000/metrics/all
```

---

## ❓ FAQs

**P: ¿Perderé data si uso Opción 1?**
A: No hay data que perder - no hay BD conectada. Es solo desarrollo.

**P: ¿Los endpoints de BD funcionan con Opción 1?**
A: No. Retornarán "not_initialized". Usa Opción 2 si los necesitas.

**P: ¿Puedo cambiar de Opción 1 a Opción 2 después?**
A: Sí, sin problemas. Solo reemplaza el archivo y reinicia.

**P: ¿Qué pasa si PostgreSQL cae con Opción 2?**
A: La API falla en startup. Usa Opción 1 para modo desarrollo más robusto.

---

## 🚀 ¡EJECUTA AHORA!

Opción 1 (recomendada):
```powershell
Copy-Item "src_api_main_scalable_DEV.py" "src\api\main_scalable.py" -Force
uvicorn src.api.main_scalable:app --reload
```

Abre en navegador:
```
http://localhost:8000/api/docs
```

¡Listo! 🎉
