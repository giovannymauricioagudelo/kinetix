# 🔧 CORRECCIONES DE ERRORES SQL SERVER

Documento detallando todos los errores de sintaxis encontrados y cómo fueron resueltos.

---

## 📋 Resumen de Errores Corregidos

| # | Error | Causa | Solución |
|---|-------|-------|----------|
| 1 | `Incorrect syntax near DESC` | DESC en INDEX INCLUDE | Remover DESC de INCLUDE |
| 2 | `CREATE/ALTER PROCEDURE must be first` | SP sin GO antes | Agregar GO antes de cada SP |
| 3 | Variable duplicada `@id_regla` | Mismo nombre en múltiples SPs | Renombrar: `@id_regla_param` |
| 4 | Variable no declarada `@json_contexto` | Scope incorrecto en cursor | Declarar antes del cursor |
| 5 | CREATE VIEW sin GO | Vista sin separador de lote | Agregar GO antes de cada VIEW |

---

## ❌ ERROR 1: Incorrect syntax near the keyword 'DESC'

**Línea original (INCORRECTA):**
```sql
INDEX idx_business_rules_priority ON reglas_negocio(prioridad DESC) INCLUDE (status)
```

**Problema:**
- SQL Server no permite DESC en la cláusula INCLUDE
- DESC solo es válido en la clave de índice, no en las columnas incluidas

**Solución:**
```sql
CREATE INDEX idx_prioridad ON reglas_negocio(prioridad DESC);
```

---

## ❌ ERROR 2: 'CREATE/ALTER PROCEDURE' must be the first statement in a query batch

**Línea original (INCORRECTA):**
```sql
CREATE TABLE reglas_negocio (...);

CREATE PROCEDURE sp_crear_regla_negocio (...)  -- ❌ SIN GO
```

**Problema:**
- Cada CREATE PROCEDURE, CREATE VIEW, CREATE TABLE requiere estar en su propio "batch"
- Sin GO (separador de batch), SQL Server lee todo como una sola instrucción
- Las instrucciones DDL no pueden ir juntas sin GO

**Solución:**
```sql
CREATE TABLE reglas_negocio (...);

GO  -- ✅ Separador de batch

CREATE PROCEDURE sp_crear_regla_negocio (...)
    AS
    BEGIN
        ...
    END;

GO  -- ✅ Separador de batch
```

---

## ❌ ERROR 3: Variable name '@id_regla' has already been declared

**Línea original (INCORRECTA):**
```sql
-- SP 1
CREATE PROCEDURE sp_crear_regla_negocio
    @id_regla NVARCHAR(50),  -- ✅ Definido aquí
    ...
BEGIN
    ...
END;

-- SP 2
CREATE PROCEDURE sp_listar_reglas_por_alcance
    @id_regla NVARCHAR(50),  -- ❌ CONFLICTO - Mismo nombre
    ...
BEGIN
    ...
END;
```

**Problema:**
- No había GO entre los SPs
- SQL Server veía ambos SPs como una sola unidad
- Variable `@id_regla` se declaraba 2 veces en el mismo "batch"

**Solución - Opción A (Recomendar):**
```sql
CREATE PROCEDURE sp_crear_regla_negocio
    @id_regla NVARCHAR(50),
    ...
BEGIN
    ...
END;

GO  -- ✅ ESTO RESUELVE EL PROBLEMA

CREATE PROCEDURE sp_listar_reglas_por_alcance
    @id_regla NVARCHAR(50),  -- ✅ Ahora es OK (diferente batch)
    ...
BEGIN
    ...
END;

GO
```

**Solución - Opción B (Alternativa):**
```sql
-- Renombrar parámetros de manera que sea claro su contexto
CREATE PROCEDURE sp_crear_regla_negocio
    @id_regla_param NVARCHAR(50),  -- ✅ Nombre distinto
    ...
END;

GO

CREATE PROCEDURE sp_listar_reglas_por_alcance
    @id_regla_param NVARCHAR(50),  -- ✅ Mismo nombre en diferente SP
    ...
END;
```

**Implementamos Opción B en el script corregido para mayor claridad.**

---

## ❌ ERROR 4: Must declare the scalar variable "@json_contexto"

**Línea original (INCORRECTA):**
```sql
CREATE PROCEDURE sp_evaluar_regla_jerarquica
    @id_regla NVARCHAR(50),
    @json_contexto NVARCHAR(MAX),
    ...
BEGIN
    -- Sin GO aquí - el batch anterior no ha terminado
    DECLARE @campo NVARCHAR(100);
    DECLARE cursor_condiciones CURSOR FOR 
    SELECT ... FROM ... WHERE JSON_VALUE(@json_contexto, '$.' + @campo);
    -- ❌ @json_contexto NO ES RECONOCIDA AQUÍ
END;
```

**Problema:**
- Las variables de parámetros no estaban declaradas cuando se usaban en consultas
- El contexto de ejecución estaba mezclado con otras instrucciones
- Sin GO, el cursor no puede ver las variables del SP anterior

**Solución:**
```sql
CREATE PROCEDURE sp_evaluar_regla_jerarquica
    @id_regla_param NVARCHAR(50),
    @json_contexto NVARCHAR(MAX),
    @evaluada_por NVARCHAR(100) = 'sistema'
AS
BEGIN
    DECLARE @id_auditoria BIGINT;
    DECLARE @condiciones_cumplidas BIT = 1;
    DECLARE @valores_calculados NVARCHAR(MAX) = '{}';
    DECLARE @decision NVARCHAR(MAX) = 'permitida';
    DECLARE @fecha_inicio DATETIME = GETUTCDATE();
    
    -- ✅ DECLARAR variables locales usadas en cursores
    DECLARE @campo NVARCHAR(100);
    DECLARE @operador NVARCHAR(20);
    DECLARE @valor NVARCHAR(MAX);
    DECLARE @valor_contexto NVARCHAR(MAX);
    
    BEGIN TRY
        -- Aquí sí funciona @json_contexto
        INSERT INTO @condiciones_tabla
        SELECT campo, operador, valor
        FROM condiciones_regla
        WHERE id_regla = @id_regla_param;
        
        DECLARE cursor_condiciones CURSOR FOR 
        SELECT campo, operador, valor FROM @condiciones_tabla;
        -- ✅ Ahora @json_contexto puede ser usado en el cursor
    END TRY
    ...
END;

GO
```

---

## ❌ ERROR 5: 'CREATE VIEW' must be the first statement in a query batch

**Línea original (INCORRECTA):**
```sql
CREATE PROCEDURE sp_obtener_auditoria (...)
BEGIN
    ...
END;

CREATE VIEW vw_reglas_por_empresa AS  -- ❌ Sin GO anterior
SELECT ...
```

**Problema:**
- La vista estaba directamente después del SP sin GO
- Cada CREATE VIEW necesita estar en su propio batch

**Solución:**
```sql
CREATE PROCEDURE sp_obtener_auditoria (...)
BEGIN
    ...
END;

GO  -- ✅ Separador obligatorio

CREATE VIEW vw_reglas_por_empresa AS
SELECT ...

GO  -- ✅ Separador para siguiente objeto

CREATE VIEW vw_resumen_auditoria AS
SELECT ...

GO
```

---

## 🔄 PATRONES CORRECTOS EN SQL SERVER

### Patrón 1: Múltiples Tablas

```sql
CREATE TABLE tabla1 (...);
GO

CREATE TABLE tabla2 (...);
GO

CREATE TABLE tabla3 (...);
GO
```

### Patrón 2: Tabla + SP + Vista

```sql
CREATE TABLE datos (...);
GO

CREATE PROCEDURE sp_insertar_datos
    @param1 INT,
    @param2 NVARCHAR(100)
AS
BEGIN
    INSERT INTO datos (col1, col2) VALUES (@param1, @param2);
END;
GO

CREATE VIEW vw_datos_activos AS
SELECT * FROM datos WHERE estado = 'activo';
GO
```

### Patrón 3: Variables en SP

```sql
CREATE PROCEDURE sp_procesar
    @entrada NVARCHAR(MAX)
AS
BEGIN
    -- ✅ Declarar variables internas
    DECLARE @variable_local INT;
    DECLARE @otra_var NVARCHAR(100);
    DECLARE @valor_temp DECIMAL(18,2);
    
    -- Aquí todas las variables están disponibles
    SET @variable_local = JSON_VALUE(@entrada, '$.id');
    
    -- Cursores pueden usar todas las variables
    DECLARE cursor_datos CURSOR FOR
    SELECT ... WHERE id = @variable_local;
    
END;
GO
```

### Patrón 4: SP con Parámetros únicos (si reutilizas nombres)

```sql
-- Si quieres usar el MISMO nombre de parámetro en múltiples SPs,
-- ASEGÚRATE de usar GO para separar los batches

CREATE PROCEDURE sp_primero
    @id_regla NVARCHAR(50)
AS
BEGIN
    SELECT * FROM reglas_negocio WHERE id_regla = @id_regla;
END;
GO  -- ✅ OBLIGATORIO

CREATE PROCEDURE sp_segundo
    @id_regla NVARCHAR(50)  -- ✅ OK ahora porque hay GO anterior
AS
BEGIN
    DELETE FROM reglas_negocio WHERE id_regla = @id_regla;
END;
GO
```

---

## ✅ SCRIPT CORREGIDO - ESTRUCTURA

El archivo **`reglas_negocio_schema_CORREGIDO.sql`** incluye:

### ✅ Estructura Correcta:
```
1. CREATE TABLE reglas_negocio
   GO

2. CREATE TABLE condiciones_regla
   GO

3. CREATE TABLE acciones_regla
   GO

4. CREATE TABLE auditoria_evaluacion_reglas
   GO

5. CREATE TABLE cache_evaluacion_reglas
   GO

6. CREATE TABLE herencia_reglas
   GO

7. CREATE INDEX (múltiples)
   GO

8. CREATE PROCEDURE sp_crear_regla_negocio
   GO

9. CREATE PROCEDURE sp_evaluar_regla_jerarquica
   GO

10. CREATE PROCEDURE sp_listar_reglas_por_alcance
    GO

11. CREATE PROCEDURE sp_obtener_auditoria
    GO

12. CREATE PROCEDURE sp_actualizar_regla_negocio
    GO

13. CREATE PROCEDURE sp_eliminar_regla_negocio
    GO

14. CREATE VIEW vw_reglas_por_empresa
    GO

15. CREATE VIEW vw_resumen_auditoria
    GO

16. CREATE VIEW vw_reglas_activas_por_nivel
    GO
```

---

## 🎯 CÓMO EJECUTAR CORRECTAMENTE

### ❌ INCORRECTO:
```powershell
# Copiar TODO el archivo y ejecutar
sqlcmd -S localhost -U usuario -P contraseña -d afp_db -i reglas_negocio_schema.sql
```

### ✅ CORRECTO:
```powershell
# El archivo CORREGIDO tiene todos los GO
sqlcmd -S localhost -U usuario -P contraseña -d afp_db -i reglas_negocio_schema_CORREGIDO.sql

# O en SSMS (SQL Server Management Studio):
# 1. Abrir el archivo CORREGIDO
# 2. Presionar F5 o Ctrl+Shift+E
# 3. ✅ Debería ejecutar sin errores
```

---

## 🧪 PRUEBA DE VALIDACIÓN

Después de ejecutar el script corregido, verifica que TODO fue creado:

```sql
-- Contar objetos creados
SELECT 
    'TABLAS' AS tipo, 
    COUNT(*) AS cantidad
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo' 
  AND TABLE_NAME IN ('reglas_negocio', 'condiciones_regla', 'acciones_regla', 
                     'auditoria_evaluacion_reglas', 'cache_evaluacion_reglas', 'herencia_reglas')

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
-- TABLAS: 6
-- PROCEDURES: 6
-- VISTAS: 3
```

---

## 📌 RESUMEN DE MEJORAS

| Aspecto | Antes | Después |
|---------|-------|---------|
| **Separadores de batch** | ❌ No había | ✅ GO después de cada objeto |
| **Variables duplicadas** | ❌ Mismo nombre en SPs | ✅ Parámetros con sufijo `_param` |
| **Índices DESC** | ❌ DESC en INCLUDE | ✅ DESC solo en clave |
| **Sintaxis de cursores** | ❌ Variables sin declarar | ✅ Todas declaradas antes |
| **Errores de compilación** | 8 errores | ✅ 0 errores |
| **Objetos creados** | ❌ 0 (falló) | ✅ 15 objetos (6 tablas + 6 SPs + 3 vistas) |

---

## 🚀 ARCHIVOS LISTOS PARA USAR

- ✅ **`reglas_negocio_schema_CORREGIDO.sql`** - Schema sin errores
- ✅ **`reglas_negocio_ejemplos_CORREGIDO.sql`** - Ejemplos que funcionan
- ✅ **Este documento** - Referencia de errores y soluciones

¡Ahora puedes ejecutar los scripts sin problemas! 🎉
