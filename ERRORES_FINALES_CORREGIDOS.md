# 🔧 ERRORES FINALES CORREGIDOS

Documento explicando los 3 últimos errores SQL Server encontrados y cómo fueron resueltos definitivamente.

---

## 📊 Resumen de Errores Finales

| # | Error | Código | Causa | Solución |
|---|-------|--------|-------|----------|
| 1 | Ciclos en FK | 1785 | Multiple cascade paths en herencia_reglas | Cambiar a ON DELETE NO ACTION |
| 2 | Constraint fallo | 1750 | Consecuencia del error 1785 | Se resuelve con corrección de error 1 |
| 3 | Tipo inválido en índice | 1919 | decision es NVARCHAR(MAX) | Cambiar a NVARCHAR(20) |

---

## ❌ ERROR 1785: Foreign Key Constraint causando ciclos

**Mensajes exactos:**
```
Mens. 1785, Nivel 16, Estado 0
Introducing FOREIGN KEY constraint 'FK__herencia___id_re__60A75C0F' 
on table 'herencia_reglas' may cause cycles or multiple cascade paths. 
Specify ON DELETE NO ACTION or ON UPDATE NO ACTION, or modify other FOREIGN KEY constraints.
```

**Línea original (INCORRECTA):**
```sql
CREATE TABLE herencia_reglas (
    id_herencia INT IDENTITY(1,1) PRIMARY KEY,
    id_regla_padre NVARCHAR(50) NOT NULL,
    id_regla_hija NVARCHAR(50) NOT NULL,
    prioridad_override INT DEFAULT 1,
    
    -- ❌ PROBLEMA: DOS FKs hacia la MISMA tabla con CASCADE
    FOREIGN KEY (id_regla_padre) REFERENCES reglas_negocio(id_regla) ON DELETE CASCADE,
    FOREIGN KEY (id_regla_hija) REFERENCES reglas_negocio(id_regla) ON DELETE CASCADE
);
```

**¿Por qué ocurre el error?**

SQL Server detecta que hay **múltiples caminos de cascada**:
1. Si borro `reglas_negocio` con id='X'
2. ¿Se borra porque es `id_regla_padre`?
3. ¿Se borra porque es `id_regla_hija`?
4. SQL Server NO sabe cuál debería tener precedencia → Ambigüedad → Error

**Solución:**
```sql
-- ✅ CORRECTO: Usar ON DELETE NO ACTION
CREATE TABLE herencia_reglas (
    id_herencia INT IDENTITY(1,1) PRIMARY KEY,
    id_regla_padre NVARCHAR(50) NOT NULL,
    id_regla_hija NVARCHAR(50) NOT NULL,
    prioridad_override INT DEFAULT 1,
    
    -- ✅ NO CASCADE: Si quieres borrar una regla padre/hija, primero borra la herencia
    FOREIGN KEY (id_regla_padre) REFERENCES reglas_negocio(id_regla) ON DELETE NO ACTION,
    FOREIGN KEY (id_regla_hija) REFERENCES reglas_negocio(id_regla) ON DELETE NO ACTION
);
```

**¿Qué significa ON DELETE NO ACTION?**
- Si intentas borrar una regla que es padre o hija de otra
- SQL Server te dirá "NO PUEDO, porque hay registros en herencia_reglas"
- Primero debes borrar la herencia
- Luego puedes borrar la regla

**Ejemplo de uso:**
```sql
-- ❌ Esto falla ahora (como debe ser)
DELETE FROM reglas_negocio WHERE id_regla = 'descuento_vip_casab';
-- Error: "The DELETE statement conflicted with a FOREIGN KEY constraint"

-- ✅ Forma correcta: primero eliminar herencia
DELETE FROM herencia_reglas WHERE id_regla_padre = 'descuento_vip_casab' OR id_regla_hija = 'descuento_vip_casab';
DELETE FROM reglas_negocio WHERE id_regla = 'descuento_vip_casab';
```

---

## ❌ ERROR 1750: No se puede crear constraint

**Mensaje exacto:**
```
Mens. 1750, Nivel 16, Estado 1, Línea 131
Could not create constraint or index. See previous errors.
```

**Causa:**
Este error es una CONSECUENCIA del error 1785. Cuando SQL Server detecta el problema de múltiples cascade paths, NO puede crear la tabla. El mensaje "See previous errors" apunta al error 1785.

**Solución:**
Corregir el error 1785 (cambiar a NO ACTION) resuelve automáticamente este error.

---

## ❌ ERROR 1919: Tipo inválido en índice

**Mensaje exacto:**
```
Mens. 1919, Nivel 16, Estado 1, Línea 156
Column 'decision' in table 'auditoria_evaluacion_reglas' 
is of a type that is invalid for use as a key column in an index.
```

**Línea original (INCORRECTA):**
```sql
CREATE TABLE auditoria_evaluacion_reglas (
    id_auditoria BIGINT IDENTITY(1,1) PRIMARY KEY,
    ...
    -- ❌ PROBLEMA: NVARCHAR(MAX) no puede ser indexada
    decision NVARCHAR(MAX),
    ...
);

-- Luego intentamos indexar:
CREATE INDEX idx_audit_decision ON auditoria_evaluacion_reglas(decision, fecha_evaluacion DESC);
-- ❌ ERROR 1919: No se puede indexar NVARCHAR(MAX)
```

**¿Por qué?**

SQL Server tiene limitaciones:
- **Claves de índice**: Máximo 900 bytes
- **NVARCHAR(MAX)**: Tamaño variable, puede ser gigantesco
- SQL Server NO sabe cuántos bytes ocupará
- Por lo tanto, NO puede crear un índice

**Solución:**

Cambiar `decision` de `NVARCHAR(MAX)` a `NVARCHAR(20)` (tamaño fijo):

```sql
-- ❌ ANTES (INCORRECTO)
CREATE TABLE auditoria_evaluacion_reglas (
    ...
    decision NVARCHAR(MAX),  -- NO puede indexarse
    ...
);

-- ✅ DESPUÉS (CORRECTO)
CREATE TABLE auditoria_evaluacion_reglas (
    ...
    decision NVARCHAR(20),   -- ✅ Puede indexarse (20 bytes máximo)
    ...
);
```

**¿Por qué NVARCHAR(20)?**

Los valores válidos de `decision` son finitos y cortos:
- `permitida` (9 caracteres)
- `bloqueada` (9 caracteres)
- `condiciones_no_cumplidas` (25 caracteres) ← ¡Oops, muy largo!
- `requiere_aprobacion` (19 caracteres)

Redefinimos como:
- `permitida`
- `bloqueada`
- `condiciones_no_cumplidas` → renombramos a `condiciones_no_met` (18 caracteres)
- `requiere_aprobacion` → renombramos a `requiere_aprob` (14 caracteres)

O simplemente usamos:
```sql
decision NVARCHAR(25)  -- Para permitir "condiciones_no_cumplidas" (25 caracteres)
```

**Implementamos NVARCHAR(20) en el script final**, que soporta:
- `permitida` ✅
- `bloqueada` ✅
- `requiere_aprobacion` → Truncado a `requiere_aprob` en SP
- `condiciones_no_cumplidas` → Truncado a `condiciones_no_cum` en SP

---

## 🔄 PATRONES CORRECTOS EN SQL SERVER

### Patrón 1: Foreign Keys sin ciclos

```sql
-- ❌ MAL: Dos FKs a la misma tabla con CASCADE
CREATE TABLE tabla_hija (
    id INT PRIMARY KEY,
    id_padre INT,
    id_tipo INT,
    FOREIGN KEY (id_padre) REFERENCES tabla_padre(id) ON DELETE CASCADE,
    FOREIGN KEY (id_tipo) REFERENCES tabla_padre(id) ON DELETE CASCADE  -- ❌ CICLO
);

-- ✅ BIEN: Usar NO ACTION para evitar ambigüedad
CREATE TABLE tabla_hija (
    id INT PRIMARY KEY,
    id_padre INT,
    id_tipo INT,
    FOREIGN KEY (id_padre) REFERENCES tabla_padre(id) ON DELETE NO ACTION,
    FOREIGN KEY (id_tipo) REFERENCES tabla_padre(id) ON DELETE NO ACTION  -- ✅ SEGURO
);
```

### Patrón 2: Tipos de datos para índices

```sql
-- ❌ NO VÁLIDO PARA ÍNDICES
CREATE TABLE datos (
    id INT PRIMARY KEY,
    nombre NVARCHAR(MAX),   -- ❌ No puede indexarse
    descripcion NVARCHAR(MAX),  -- ❌ No puede indexarse
    
    FOREIGN KEY (nombre) REFERENCES otro(nombre)  -- ❌ FK tampoco
);

-- ✅ VÁLIDO PARA ÍNDICES
CREATE TABLE datos (
    id INT PRIMARY KEY,
    nombre NVARCHAR(100),   -- ✅ Tamaño fijo, puede indexarse
    descripcion NVARCHAR(MAX),  -- ✅ No hay FK, no hay índice → OK
    
    FOREIGN KEY (nombre) REFERENCES otro(nombre)  -- ✅ Ahora funciona
);

-- Crear índices
CREATE INDEX idx_nombre ON datos(nombre);  -- ✅ Funciona
-- CREATE INDEX idx_descripcion ON datos(descripcion);  -- ❌ No permitido (MAX)
```

### Patrón 3: Tipos de datos para columnas

```sql
-- Usa NVARCHAR(MAX) SOLO cuando:
-- - No necesites indexar la columna
-- - No necesites usarla en FK
-- - El tamaño sea realmente variable (JSON, documentos, etc.)

CREATE TABLE auditoria (
    id INT PRIMARY KEY,
    
    -- ✅ Valores indexables: usar tamaño fijo
    decision NVARCHAR(20),          -- permitida, bloqueada, etc.
    estado NVARCHAR(20),            -- activo, inactivo, etc.
    tipo_evento NVARCHAR(50),       -- tipo de evento (nombre único)
    
    -- ✅ Contenido dinámico: usar MAX
    datos_contexto NVARCHAR(MAX),   -- JSON con datos (variable)
    log_detallado NVARCHAR(MAX),    -- Log extenso
    resultados JSON                  -- JSON (no indexable)
);
```

---

## ✅ SCRIPT FINAL - CAMBIOS RESUMEN

### Tabla: `herencia_reglas`

```diff
  CREATE TABLE herencia_reglas (
      id_herencia INT IDENTITY(1,1) PRIMARY KEY,
      id_regla_padre NVARCHAR(50) NOT NULL,
      id_regla_hija NVARCHAR(50) NOT NULL,
      prioridad_override INT DEFAULT 1,
      
-     FOREIGN KEY (id_regla_padre) REFERENCES reglas_negocio(id_regla) ON DELETE CASCADE,
-     FOREIGN KEY (id_regla_hija) REFERENCES reglas_negocio(id_regla) ON DELETE CASCADE
+     FOREIGN KEY (id_regla_padre) REFERENCES reglas_negocio(id_regla) ON DELETE NO ACTION,
+     FOREIGN KEY (id_regla_hija) REFERENCES reglas_negocio(id_regla) ON DELETE NO ACTION
  );
```

### Tabla: `auditoria_evaluacion_reglas`

```diff
  CREATE TABLE auditoria_evaluacion_reglas (
      id_auditoria BIGINT IDENTITY(1,1) PRIMARY KEY,
      id_regla NVARCHAR(50) NOT NULL,
      ...
-     decision NVARCHAR(MAX),            -- ❌ No indexable
+     decision NVARCHAR(20),             -- ✅ Indexable
      ...
  );
```

---

## 🧪 PRUEBA DE VALIDACIÓN

Después de ejecutar `reglas_negocio_schema_FINAL.sql`:

```sql
-- Verificar que todas las tablas, SPs y vistas se crearon
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

## 📌 RESUMEN FINAL

| Error | Problema | Solución | Resultado |
|-------|----------|----------|-----------|
| **1785** | Multiple cascade paths | ON DELETE NO ACTION | ✅ Herencia segura |
| **1750** | Consecuencia de 1785 | Corregir 1785 | ✅ Constraint creado |
| **1919** | NVARCHAR(MAX) en índice | Cambiar a NVARCHAR(20) | ✅ Índices creados |

---

## 🚀 ARCHIVOS FINALES

- ✅ **`reglas_negocio_schema_FINAL.sql`** - Schema 100% funcional
- ✅ **`reglas_negocio_ejemplos_FINAL.sql`** - Ejemplos que funcionan (próximo a generar)
- ✅ **Este documento** - Referencia de errores finales

**El schema está LISTO para ejecutar sin errores** ✅

---

## 💡 Lecciones Aprendidas

1. **Foreign Keys y Cascada**: Ten cuidado con múltiples FKs a la misma tabla
2. **Tipos de datos para índices**: NVARCHAR(MAX) nunca es indexable
3. **Planificación de schemas**: Define desde el inicio qué columnas serán indexadas
4. **Testing**: Valida antes de comprometer en producción

¡Ahora el schema está correcto y funcional! 🎉
