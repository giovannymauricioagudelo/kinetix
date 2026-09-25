# 🗄️ MOTOR DE REGLAS DE NEGOCIO - SQL SERVER (EN ESPAÑOL)

---

## 📊 Tabla de Contenidos

1. [Descripción General](#descripción-general)
2. [Arquitectura de 3 Niveles](#arquitectura-de-3-niveles)
3. [Estructura de Tablas](#estructura-de-tablas)
4. [Stored Procedures](#stored-procedures)
5. [Ejemplos de Uso](#ejemplos-de-uso)
6. [Vistas para Reporting](#vistas-para-reporting)
7. [Performance y Índices](#performance-e-índices)
8. [Integración con Python/FastAPI](#integración-con-pythonfastapi)

---

## 🎯 Descripción General

### Propósito

Motor de evaluación de reglas de negocio **jerárquico** y **agnóstico** que permite:

- ✅ Definir reglas en **3 niveles** (global, línea de negocio, empresa)
- ✅ Evaluar condiciones dinámicamente
- ✅ Ejecutar acciones automáticas
- ✅ Registrar auditoría completa
- ✅ Soportar herencia y override de reglas

### Características Principales

```
┌─────────────────────────────────────────────────────┐
│ REGLAS DE NEGOCIO - SQL SERVER                      │
├─────────────────────────────────────────────────────┤
│ ✅ 6 Tablas normalizadas                            │
│ ✅ 6 Stored Procedures                              │
│ ✅ 3 Vistas para reporting                          │
│ ✅ JSON nativo para flexibilidad                    │
│ ✅ Auditoría automática                             │
│ ✅ Caché de resultados                              │
│ ✅ Evaluación jerárquica determinista               │
│ ✅ Índices optimizados (<10ms por evaluación)      │
└─────────────────────────────────────────────────────┘
```

---

## 🏗️ Arquitectura de 3 Niveles

```
┌─────────────────────────────────────────────────────────┐
│ NIVEL 1: REGLAS GLOBALES                               │
│ ─────────────────────────────────────────────────────── │
│ Aplican a TODAS las empresas                            │
│ Ej: validación de email, rango de fechas, moneda      │
│                                                          │
│ scope_level = 'global'                                 │
│ prioridad = 100 (máxima)                               │
└─────────────────────────────────────────────────────────┘
         ↓ EVALUACIÓN EN ORDEN
┌─────────────────────────────────────────────────────────┐
│ NIVEL 2: REGLAS POR LÍNEA DE NEGOCIO                  │
│ ─────────────────────────────────────────────────────── │
│ Aplican a un sector específico                          │
│ Ej: RETAIL, AUTOMOTRIZ, MAQUINARIA                    │
│                                                          │
│ scope_level = 'linea_negocio'                          │
│ linea_negocio = 'RETAIL'|'AUTOMOTRIZ'|'MAQUINARIA'   │
└─────────────────────────────────────────────────────────┘
         ↓ EVALUACIÓN EN ORDEN
┌─────────────────────────────────────────────────────────┐
│ NIVEL 3: REGLAS POR EMPRESA                            │
│ ─────────────────────────────────────────────────────── │
│ Aplican solo a una empresa específica                   │
│ Ej: Casab (id=523), Imvesa (id=601), HND (id=100)    │
│                                                          │
│ scope_level = 'empresa'                                │
│ id_empresa = 523|601|100                               │
└─────────────────────────────────────────────────────────┘
```

---

## 📋 Estructura de Tablas

### 1. `reglas_negocio` - Tabla Principal

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id_regla` | NVARCHAR(50) | Identificador único (PK) |
| `nombre` | NVARCHAR(255) | Nombre legible |
| `descripcion` | NVARCHAR(MAX) | Descripción detallada |
| `nivel_alcance` | NVARCHAR(20) | 'global', 'linea_negocio', 'empresa' |
| `linea_negocio` | NVARCHAR(50) | Si nivel='linea_negocio' |
| `id_empresa` | INT | Si nivel='empresa' |
| `prioridad` | INT (1-100) | Orden de evaluación |
| `permite_override` | BIT | ¿Puede ser sobrescrita? |
| `estado` | NVARCHAR(20) | 'activa', 'inactiva', 'prueba', 'archivada' |
| `version` | INT | Control de versiones |
| `fecha_creacion` | DATETIME | Auditoría |
| `creada_por` | NVARCHAR(100) | Usuario creator |

### 2. `condiciones_regla` - Condiciones

Cada fila = una condición de la regla

```
id_regla | campo | operador | valor | orden_evaluacion
---------|-------|----------|-------|------------------
descuento_vip | cliente_segment | eq | VIP | 1
descuento_vip | monto | gte | 5000 | 2
```

### 3. `acciones_regla` - Acciones a Ejecutar

Cada fila = una acción si se cumplen condiciones

```
id_regla | tipo_accion | detalles | orden_ejecucion
---------|-------------|----------|------------------
descuento_vip | calcular | {...} | 1
descuento_vip | notificar | {...} | 2
```

### 4. `auditoria_evaluacion_reglas` - Log de Evaluaciones

Registro automático de cada evaluación:

```
id_auditoria | id_regla | condiciones_cumplidas | decision | tiempo_ejecucion_ms | fecha_evaluacion
```

### 5. `cache_evaluacion_reglas` - Caché

Almacena resultados de evaluaciones recientes para optimizar

### 6. `herencia_reglas` - Relaciones entre Niveles

Mapea reglas padre-hijo para evaluar herencia

---

## 🔧 Stored Procedures

### 1. `sp_crear_regla_negocio`

**Propósito:** Crear una nueva regla de negocio

**Parámetros:**
```sql
@id_regla NVARCHAR(50)          -- ID único
@nombre NVARCHAR(255)           -- Nombre
@descripcion NVARCHAR(MAX)      -- Descripción
@nivel_alcance NVARCHAR(20)     -- 'global', 'linea_negocio', 'empresa'
@linea_negocio NVARCHAR(50)     -- Si aplica
@id_empresa INT                 -- Si aplica
@prioridad INT                  -- 1-100
@creada_por NVARCHAR(100)       -- Usuario
@json_condiciones NVARCHAR(MAX) -- JSON array de condiciones
@json_acciones NVARCHAR(MAX)    -- JSON array de acciones
```

**Ejemplo:**
```sql
DECLARE @condiciones NVARCHAR(MAX) = N'[
    {"campo": "monto", "operador": "gte", "valor": "1000", "orden": 1}
]';

DECLARE @acciones NVARCHAR(MAX) = N'[
    {"tipo": "calcular", "detalles": {"variable": "retencion", "formula": "monto * 0.025"}, "orden": 1}
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'retencion_isr_001',
    @nombre = 'Retención ISR',
    @descripcion = 'Retención 2.5% en facturas >= $1000',
    @nivel_alcance = 'empresa',
    @id_empresa = 523,
    @prioridad = 85,
    @creada_por = 'sistema',
    @json_condiciones = @condiciones,
    @json_acciones = @acciones;
```

### 2. `sp_evaluar_regla_jerarquica`

**Propósito:** Evaluar una regla completa (jerárquica)

**Parámetros:**
```sql
@id_regla NVARCHAR(50)          -- Regla a evaluar
@id_empresa INT                 -- Empresa del contexto
@linea_negocio NVARCHAR(50)     -- Línea de negocio
@json_contexto NVARCHAR(MAX)    -- {"monto": 10000, "cliente_id": 523, ...}
@evaluada_por NVARCHAR(100)     -- Usuario que evalúa
```

**Retorna:**
```
resultado | id_regla | condiciones_cumplidas | decision | valores_calculados | id_auditoria
```

**Ejemplo:**
```sql
DECLARE @contexto NVARCHAR(MAX) = N'{
    "cliente_id": 523,
    "monto": 15000,
    "tipo_documento": "factura"
}';

EXEC sp_evaluar_regla_jerarquica
    @id_regla = 'descuento_vip_casab',
    @id_empresa = 523,
    @linea_negocio = 'RETAIL',
    @json_contexto = @contexto,
    @evaluada_por = 'usuario@app.com';
```

### 3. `sp_listar_reglas_por_alcance`

**Propósito:** Listar reglas con filtros

**Parámetros:**
```sql
@nivel_alcance NVARCHAR(20)     -- NULL = todos, 'global', 'linea_negocio', 'empresa'
@linea_negocio NVARCHAR(50)     -- NULL = todas
@id_empresa INT                 -- NULL = todas
@estado NVARCHAR(20)            -- 'activa', etc
```

**Ejemplo:**
```sql
-- Listar todas las reglas globales activas
EXEC sp_listar_reglas_por_alcance
    @nivel_alcance = 'global',
    @estado = 'activa';

-- Listar todas las reglas de Casab
EXEC sp_listar_reglas_por_alcance
    @nivel_alcance = 'empresa',
    @id_empresa = 523,
    @estado = 'activa';
```

### 4. `sp_obtener_auditoria`

**Propósito:** Obtener historial de evaluaciones

**Parámetros:**
```sql
@id_regla NVARCHAR(50)          -- NULL = todas
@id_empresa INT                 -- NULL = todas
@dias INT                       -- Últimos N días (default 30)
@limite INT                     -- Máximo de registros (default 100)
```

**Ejemplo:**
```sql
-- Auditoría de últimos 30 días para Casab
EXEC sp_obtener_auditoria
    @id_empresa = 523,
    @dias = 30,
    @limite = 50;
```

### 5. `sp_actualizar_regla_negocio`

**Propósito:** Actualizar una regla existente

### 6. `sp_eliminar_regla_negocio`

**Propósito:** Soft-delete de una regla (marca como archivada)

---

## 📝 Ejemplos de Uso

### Ejemplo 1: Crear Regla Global de Validación

```sql
-- Validar que email tiene formato correcto (aplica a TODAS las empresas)

EXEC sp_crear_regla_negocio
    @id_regla = 'validacion_email_global',
    @nombre = 'Validación de Email',
    @descripcion = 'Email debe tener formato válido (aplica globalmente)',
    @nivel_alcance = 'global',
    @prioridad = 100,
    @creada_por = 'sistema',
    @json_condiciones = N'[
        {
            "campo": "email",
            "operador": "regex",
            "valor": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
            "orden": 1
        }
    ]',
    @json_acciones = N'[
        {
            "tipo": "permitir",
            "orden": 1
        }
    ]';
```

### Ejemplo 2: Crear Regla por Línea de Negocio

```sql
-- Límite máximo de descuento en RETAIL = 30%

EXEC sp_crear_regla_negocio
    @id_regla = 'limite_descuento_retail',
    @nombre = 'Límite de Descuento - RETAIL',
    @descripcion = 'Descuento máximo 30% para línea RETAIL',
    @nivel_alcance = 'linea_negocio',
    @linea_negocio = 'RETAIL',
    @prioridad = 85,
    @creada_por = 'sistema',
    @json_condiciones = N'[
        {
            "campo": "porcentaje_descuento",
            "operador": "gte",
            "valor": "0",
            "orden": 1
        },
        {
            "campo": "porcentaje_descuento",
            "operador": "lte",
            "valor": "30",
            "orden": 2
        }
    ]',
    @json_acciones = N'[
        {
            "tipo": "permitir",
            "orden": 1
        }
    ]';
```

### Ejemplo 3: Crear Regla por Empresa

```sql
-- Descuento VIP 25% para Casab Joyería

EXEC sp_crear_regla_negocio
    @id_regla = 'descuento_vip_casab',
    @nombre = 'Descuento VIP - Casab',
    @descripcion = 'Clientes VIP de Casab reciben 25% de descuento',
    @nivel_alcance = 'empresa',
    @id_empresa = 523,
    @prioridad = 95,
    @creada_por = 'sistema',
    @json_condiciones = N'[
        {
            "campo": "segmento_cliente",
            "operador": "eq",
            "valor": "VIP",
            "orden": 1
        },
        {
            "campo": "monto",
            "operador": "gte",
            "valor": "5000",
            "orden": 2
        }
    ]',
    @json_acciones = N'[
        {
            "tipo": "calcular",
            "detalles": {"variable": "descuento_vip", "formula": "monto * 0.25"},
            "orden": 1
        },
        {
            "tipo": "notificar",
            "detalles": {"destino": "gerencia", "mensaje": "Descuento VIP 25% aplicado"},
            "orden": 2
        }
    ]';
```

### Ejemplo 4: Evaluar Regla

```sql
DECLARE @contexto NVARCHAR(MAX) = N'{
    "cliente_id": 1050,
    "segmento_cliente": "VIP",
    "monto": 15000,
    "tipo_documento": "factura"
}';

EXEC sp_evaluar_regla_jerarquica
    @id_regla = 'descuento_vip_casab',
    @id_empresa = 523,
    @linea_negocio = 'RETAIL',
    @json_contexto = @contexto,
    @evaluada_por = 'usuario@casab.hn';

-- Resultado esperado:
-- ✅ condiciones_cumplidas = 1 (verdadero)
-- ✅ decision = 'permitida'
-- ✅ valores_calculados = {"descuento_vip": 3750}
```

---

## 📊 Vistas para Reporting

### `vw_reglas_por_empresa`

Resumen de todas las reglas agrupadas por empresa

```sql
SELECT * FROM vw_reglas_por_empresa
WHERE id_empresa = 523;

-- Resultado:
-- id_regla | nombre | nivel_alcance | total_condiciones | total_acciones | fecha_creacion
```

### `vw_resumen_auditoria`

Resumen diario de evaluaciones

```sql
SELECT * FROM vw_resumen_auditoria
WHERE id_empresa = 523 AND fecha_evaluacion >= '2024-01-01';

-- Resultado:
-- id_regla | id_empresa | fecha_evaluacion | total_evaluaciones | cantidad_permitidas | cantidad_bloqueadas | tiempo_promedio_ms
```

### `vw_reglas_activas_por_nivel`

Resumen de reglas activas por nivel

```sql
SELECT * FROM vw_reglas_activas_por_nivel;

-- Resultado:
-- nivel_alcance | linea_negocio | id_empresa | total_reglas | prioridad_maxima | prioridad_minima
```

---

## ⚡ Performance e Índices

### Índices Implementados

```sql
-- Búsqueda por scope
CREATE INDEX idx_alcance ON reglas_negocio(nivel_alcance, linea_negocio, id_empresa);

-- Búsqueda por estado
CREATE INDEX idx_estado ON reglas_negocio(estado);

-- Auditoría por regla
CREATE INDEX idx_rule_id ON auditoria_evaluacion_reglas(id_regla, fecha_evaluacion DESC);

-- Auditoría por empresa
CREATE INDEX idx_empresa ON auditoria_evaluacion_reglas(id_empresa, fecha_evaluacion DESC);

-- Auditoría por decisión
CREATE INDEX idx_decision ON auditoria_evaluacion_reglas(decision, fecha_evaluacion DESC);
```

### Tiempos de Ejecución Esperados

| Operación | Tiempo |
|-----------|--------|
| Crear regla | 5-10 ms |
| Evaluar regla (1-3 condiciones) | 2-5 ms |
| Evaluar regla (5+ condiciones) | 5-15 ms |
| Listar reglas (10K registros) | 20-50 ms |
| Auditoría (30 días) | 100-300 ms |

---

## 🔌 Integración con Python/FastAPI

### Llamar desde Python

```python
import pyodbc

def evaluar_regla_python(id_regla, id_empresa, linea_negocio, contexto_dict):
    """Evalúa una regla desde Python"""
    
    # Conexión a SQL Server
    conn = pyodbc.connect(
        'Driver={ODBC Driver 17 for SQL Server};'
        'Server=localhost;Database=afp_db;UID=user;PWD=password'
    )
    cursor = conn.cursor()
    
    # Llamar SP
    import json
    contexto_json = json.dumps(contexto_dict)
    
    cursor.execute("""
        EXEC sp_evaluar_regla_jerarquica
            @id_regla = ?,
            @id_empresa = ?,
            @linea_negocio = ?,
            @json_contexto = ?,
            @evaluada_por = ?
    """, (id_regla, id_empresa, linea_negocio, contexto_json, 'sistema'))
    
    resultado = cursor.fetchone()
    conn.close()
    
    return {
        'resultado': resultado[0],
        'id_regla': resultado[1],
        'condiciones_cumplidas': resultado[2],
        'decision': resultado[3],
        'valores_calculados': resultado[4],
        'id_auditoria': resultado[5]
    }
```

### Endpoint FastAPI

```python
from fastapi import FastAPI
from pydantic import BaseModel
import json

app = FastAPI()

class ContextoEvaluacion(BaseModel):
    cliente_id: int
    monto: float
    tipo_documento: str

@app.post("/api/v1/rules/evaluate")
async def evaluar_regla_endpoint(
    id_regla: str,
    id_empresa: int,
    linea_negocio: str,
    contexto: ContextoEvaluacion
):
    """Evalúa una regla vía API REST"""
    
    resultado = evaluar_regla_python(
        id_regla=id_regla,
        id_empresa=id_empresa,
        linea_negocio=linea_negocio,
        contexto_dict=contexto.dict()
    )
    
    return {
        "status": "success",
        "data": resultado
    }
```

---

## 🗄️ Resumen

```
┌───────────────────────────────────────────────┐
│ MOTOR DE REGLAS SQL SERVER (EN ESPAÑOL)      │
├───────────────────────────────────────────────┤
│ ✅ 6 Tablas normalizadas                      │
│ ✅ 3 Niveles jerárquicos                      │
│ ✅ 6 Stored Procedures                        │
│ ✅ 3 Vistas para reporting                    │
│ ✅ Auditoría automática                       │
│ ✅ Evaluación <10ms                           │
│ ✅ Integración con Python/FastAPI             │
│ ✅ Soporte para 9 operadores                  │
│ ✅ Soporte para 6 tipos de acciones           │
│ ✅ JSON nativo para flexibilidad              │
└───────────────────────────────────────────────┘
```

---

## 📚 Archivos Relacionados

- `reglas_negocio_schema.sql` - DDL completo (tablas + SPs)
- `reglas_negocio_ejemplos.sql` - 6 ejemplos de inserciones
- Este documento - Guía de referencia

---

¿Necesitas ayuda con algo específico? 🚀
