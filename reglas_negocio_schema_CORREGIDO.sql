-- ============================================================================
-- ESQUEMA DE REGLAS DE NEGOCIO - SQL SERVER (CORREGIDO)
-- Motor de evaluación jerárquico con soporte para 3 niveles de scope
-- ============================================================================

-- ============================================================================
-- 1. TABLA PRINCIPAL - REGLAS DE NEGOCIO
-- ============================================================================

CREATE TABLE reglas_negocio (
    id_regla NVARCHAR(50) PRIMARY KEY,
    nombre NVARCHAR(255) NOT NULL,
    descripcion NVARCHAR(MAX),
    
    -- ALCANCE/NIVEL DE LA REGLA
    nivel_alcance NVARCHAR(20) NOT NULL,  -- 'global', 'linea_negocio', 'empresa'
    linea_negocio NVARCHAR(50),          -- Si nivel_alcance='linea_negocio'
    id_empresa INT,                      -- Si nivel_alcance='empresa'
    
    -- JERARQUÍA Y PRIORIDAD
    prioridad INT DEFAULT 50,            -- 1-100 (100=máxima prioridad)
    permite_override BIT DEFAULT 1,      -- ¿Puede ser sobrescrita?
    hereda_de NVARCHAR(MAX),             -- JSON array de id_regla heredadas
    
    -- ESTADO Y METADATOS
    estado NVARCHAR(20) DEFAULT 'activa',   -- 'activa', 'inactiva', 'prueba', 'archivada'
    version INT DEFAULT 1,
    
    -- AUDITORÍA
    fecha_creacion DATETIME DEFAULT GETUTCDATE(),
    creada_por NVARCHAR(100),
    fecha_actualizacion DATETIME,
    actualizada_por NVARCHAR(100)
);

GO

-- ============================================================================
-- 2. TABLA DE CONDICIONES
-- ============================================================================

CREATE TABLE condiciones_regla (
    id_condicion INT IDENTITY(1,1) PRIMARY KEY,
    id_regla NVARCHAR(50) NOT NULL,
    
    -- CONDICIÓN
    campo NVARCHAR(100) NOT NULL,       -- Campo a evaluar
    operador NVARCHAR(20) NOT NULL,     -- 'eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'en', 'no_en', 'contiene', 'regex'
    valor NVARCHAR(MAX),                -- Valor (puede ser JSON para arrays)
    
    -- LÓGICA
    orden_evaluacion INT,               -- Orden de evaluación
    operador_logico NVARCHAR(10) DEFAULT 'Y',  -- 'Y', 'O'
    
    FOREIGN KEY (id_regla) REFERENCES reglas_negocio(id_regla) ON DELETE CASCADE
);

GO

-- ============================================================================
-- 3. TABLA DE ACCIONES
-- ============================================================================

CREATE TABLE acciones_regla (
    id_accion INT IDENTITY(1,1) PRIMARY KEY,
    id_regla NVARCHAR(50) NOT NULL,
    
    -- ACCIÓN
    tipo_accion NVARCHAR(50) NOT NULL,  -- 'calcular', 'asignar_campo', 'bloquear', 'permitir', 'notificar', 'registrar'
    detalles NVARCHAR(MAX),             -- JSON con detalles específicos
    
    -- EJECUCIÓN
    orden_ejecucion INT,                -- Orden de ejecución
    es_critica BIT DEFAULT 0,           -- ¿Si falla, falla la regla?
    
    FOREIGN KEY (id_regla) REFERENCES reglas_negocio(id_regla) ON DELETE CASCADE
);

GO

-- ============================================================================
-- 4. TABLA DE AUDITORÍA - EVALUACIONES DE REGLAS
-- ============================================================================

CREATE TABLE auditoria_evaluacion_reglas (
    id_auditoria BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_regla NVARCHAR(50) NOT NULL,
    
    -- CONTEXTO
    nivel_alcance NVARCHAR(20),
    linea_negocio NVARCHAR(50),
    id_empresa INT,
    
    -- EVALUACIÓN
    datos_contexto NVARCHAR(MAX),       -- JSON con datos de contexto
    condiciones_cumplidas BIT,          -- ¿Coincidieron condiciones?
    acciones_ejecutadas NVARCHAR(MAX),  -- JSON array de acciones ejecutadas
    valores_calculados NVARCHAR(MAX),   -- JSON con valores calculados
    
    -- DECISIÓN
    decision NVARCHAR(MAX),             -- 'permitida', 'bloqueada', 'requiere_aprobacion', etc
    log_decisiones NVARCHAR(MAX),       -- JSON array de decisiones
    
    -- AUDITORÍA
    fecha_evaluacion DATETIME DEFAULT GETUTCDATE(),
    evaluada_por NVARCHAR(100),
    tiempo_ejecucion_ms INT            -- Tiempo de ejecución en ms
);

GO

-- ============================================================================
-- 5. TABLA DE CACHÉ - REGLAS EVALUADAS RECIENTEMENTE
-- ============================================================================

CREATE TABLE cache_evaluacion_reglas (
    id_cache BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_regla NVARCHAR(50),
    hash_contexto NVARCHAR(64),         -- SHA-256 del contexto
    resultado_cache NVARCHAR(MAX),      -- JSON con resultado
    fecha_cache DATETIME DEFAULT GETUTCDATE(),
    fecha_expiracion DATETIME           -- TTL
);

GO

-- ============================================================================
-- 6. TABLA DE HERENCIA - RELACIONES ENTRE REGLAS
-- ============================================================================

CREATE TABLE herencia_reglas (
    id_herencia INT IDENTITY(1,1) PRIMARY KEY,
    id_regla_padre NVARCHAR(50) NOT NULL,    -- Regla padre (nivel superior)
    id_regla_hija NVARCHAR(50) NOT NULL,     -- Regla hija (nivel inferior)
    prioridad_override INT DEFAULT 1,        -- Prioridad del override
    
    FOREIGN KEY (id_regla_padre) REFERENCES reglas_negocio(id_regla) ON DELETE CASCADE,
    FOREIGN KEY (id_regla_hija) REFERENCES reglas_negocio(id_regla) ON DELETE CASCADE
);

GO

-- ============================================================================
-- CREAR ÍNDICES
-- ============================================================================

CREATE INDEX idx_alcance ON reglas_negocio(nivel_alcance, linea_negocio, id_empresa);
CREATE INDEX idx_estado ON reglas_negocio(estado);
CREATE INDEX idx_prioridad ON reglas_negocio(prioridad DESC);

CREATE INDEX idx_cond_regla ON condiciones_regla(id_regla);
CREATE INDEX idx_acc_regla ON acciones_regla(id_regla);

CREATE INDEX idx_audit_regla ON auditoria_evaluacion_reglas(id_regla, fecha_evaluacion DESC);
CREATE INDEX idx_audit_empresa ON auditoria_evaluacion_reglas(id_empresa, fecha_evaluacion DESC);
CREATE INDEX idx_audit_decision ON auditoria_evaluacion_reglas(decision, fecha_evaluacion DESC);

CREATE INDEX idx_cache_regla ON cache_evaluacion_reglas(id_regla, hash_contexto);

CREATE INDEX idx_her_padre ON herencia_reglas(id_regla_padre);
CREATE INDEX idx_her_hija ON herencia_reglas(id_regla_hija);

GO

-- ============================================================================
-- SP 1: Crear Regla de Negocio
-- ============================================================================

CREATE PROCEDURE sp_crear_regla_negocio
    @id_regla NVARCHAR(50),
    @nombre NVARCHAR(255),
    @descripcion NVARCHAR(MAX),
    @nivel_alcance NVARCHAR(20),
    @linea_negocio NVARCHAR(50) = NULL,
    @id_empresa INT = NULL,
    @prioridad INT = 50,
    @creada_por NVARCHAR(100),
    @json_condiciones NVARCHAR(MAX),
    @json_acciones NVARCHAR(MAX)
AS
BEGIN
    BEGIN TRY
        BEGIN TRANSACTION;
        
        -- 1. Insertar regla principal
        INSERT INTO reglas_negocio (
            id_regla, nombre, descripcion, nivel_alcance, linea_negocio, id_empresa,
            prioridad, creada_por
        )
        VALUES (
            @id_regla, @nombre, @descripcion, @nivel_alcance, @linea_negocio, @id_empresa,
            @prioridad, @creada_por
        );
        
        -- 2. Insertar condiciones desde JSON
        INSERT INTO condiciones_regla (id_regla, campo, operador, valor, orden_evaluacion)
        SELECT
            @id_regla,
            JSON_VALUE(value, '$.campo'),
            JSON_VALUE(value, '$.operador'),
            JSON_VALUE(value, '$.valor'),
            JSON_VALUE(value, '$.orden')
        FROM OPENJSON(@json_condiciones) AS condiciones;
        
        -- 3. Insertar acciones desde JSON
        INSERT INTO acciones_regla (id_regla, tipo_accion, detalles, orden_ejecucion)
        SELECT
            @id_regla,
            JSON_VALUE(value, '$.tipo'),
            JSON_QUERY(value, '$.detalles'),
            JSON_VALUE(value, '$.orden')
        FROM OPENJSON(@json_acciones) AS acciones;
        
        COMMIT TRANSACTION;
        
        SELECT 'EXITO' AS resultado, @id_regla AS id_regla;
    END TRY
    BEGIN CATCH
        ROLLBACK TRANSACTION;
        SELECT 'ERROR' AS resultado, ERROR_MESSAGE() AS mensaje_error;
    END CATCH
END;

GO

-- ============================================================================
-- SP 2: Evaluar Regla Completa (Jerárquica - 3 Niveles)
-- ============================================================================

CREATE PROCEDURE sp_evaluar_regla_jerarquica
    @id_regla_param NVARCHAR(50),
    @id_empresa_param INT,
    @linea_negocio_param NVARCHAR(50),
    @json_contexto NVARCHAR(MAX),
    @evaluada_por NVARCHAR(100) = 'sistema'
AS
BEGIN
    DECLARE @id_auditoria BIGINT;
    DECLARE @condiciones_cumplidas BIT = 1;
    DECLARE @valores_calculados NVARCHAR(MAX) = '{}';
    DECLARE @decision NVARCHAR(MAX) = 'permitida';
    DECLARE @fecha_inicio DATETIME = GETUTCDATE();
    
    DECLARE @campo NVARCHAR(100);
    DECLARE @operador NVARCHAR(20);
    DECLARE @valor NVARCHAR(MAX);
    DECLARE @valor_contexto NVARCHAR(MAX);
    DECLARE @resultado_condicion BIT = 1;
    
    DECLARE @tipo_accion NVARCHAR(50);
    DECLARE @detalles_accion NVARCHAR(MAX);
    DECLARE @nombre_var NVARCHAR(50);
    DECLARE @formula NVARCHAR(MAX);
    DECLARE @monto_calc DECIMAL(18,2);
    DECLARE @resultado_calc DECIMAL(18,2);
    
    BEGIN TRY
        -- 1. EVALUAR CONDICIONES
        DECLARE @condiciones_tabla TABLE (
            campo NVARCHAR(100),
            operador NVARCHAR(20),
            valor NVARCHAR(MAX)
        );
        
        INSERT INTO @condiciones_tabla
        SELECT campo, operador, valor
        FROM condiciones_regla
        WHERE id_regla = @id_regla_param
        ORDER BY orden_evaluacion;
        
        -- 2. EVALUAR CADA CONDICIÓN
        DECLARE cursor_condiciones CURSOR FOR 
        SELECT campo, operador, valor FROM @condiciones_tabla;
        
        OPEN cursor_condiciones;
        
        FETCH NEXT FROM cursor_condiciones INTO @campo, @operador, @valor;
        WHILE @@FETCH_STATUS = 0
        BEGIN
            SET @valor_contexto = JSON_VALUE(@json_contexto, '$.' + @campo);
            SET @resultado_condicion = 1;
            
            -- Evaluar según operador
            IF @operador = 'eq'
                SET @resultado_condicion = CASE WHEN @valor_contexto = @valor THEN 1 ELSE 0 END;
            ELSE IF @operador = 'gte'
                SET @resultado_condicion = CASE WHEN CAST(@valor_contexto AS DECIMAL(18,2)) >= CAST(@valor AS DECIMAL(18,2)) THEN 1 ELSE 0 END;
            ELSE IF @operador = 'lte'
                SET @resultado_condicion = CASE WHEN CAST(@valor_contexto AS DECIMAL(18,2)) <= CAST(@valor AS DECIMAL(18,2)) THEN 1 ELSE 0 END;
            ELSE IF @operador = 'en'
                SET @resultado_condicion = CASE WHEN @valor_contexto IN (SELECT value FROM STRING_SPLIT(@valor, ',')) THEN 1 ELSE 0 END;
            
            -- Si condición falla, marcar como no coincide
            IF @resultado_condicion = 0
                SET @condiciones_cumplidas = 0;
            
            FETCH NEXT FROM cursor_condiciones INTO @campo, @operador, @valor;
        END;
        
        CLOSE cursor_condiciones;
        DEALLOCATE cursor_condiciones;
        
        -- 3. SI CONDICIONES SE CUMPLEN, EJECUTAR ACCIONES
        IF @condiciones_cumplidas = 1
        BEGIN
            DECLARE cursor_acciones CURSOR FOR
            SELECT tipo_accion, detalles FROM acciones_regla WHERE id_regla = @id_regla_param ORDER BY orden_ejecucion;
            
            OPEN cursor_acciones;
            FETCH NEXT FROM cursor_acciones INTO @tipo_accion, @detalles_accion;
            
            WHILE @@FETCH_STATUS = 0
            BEGIN
                IF @tipo_accion = 'calcular'
                BEGIN
                    SET @nombre_var = JSON_VALUE(@detalles_accion, '$.variable');
                    SET @formula = JSON_VALUE(@detalles_accion, '$.formula');
                    SET @monto_calc = JSON_VALUE(@json_contexto, '$.monto');
                    
                    IF @formula LIKE '%* 0.025%'
                        SET @resultado_calc = @monto_calc * 0.025;
                    ELSE IF @formula LIKE '%* 0.03%'
                        SET @resultado_calc = @monto_calc * 0.03;
                    ELSE IF @formula LIKE '%* 0.05%'
                        SET @resultado_calc = @monto_calc * 0.05;
                    ELSE IF @formula LIKE '%* 0.15%'
                        SET @resultado_calc = @monto_calc * 0.15;
                    ELSE IF @formula LIKE '%* 0.25%'
                        SET @resultado_calc = @monto_calc * 0.25;
                    
                    SET @valores_calculados = JSON_MODIFY(@valores_calculados, '$.' + @nombre_var, @resultado_calc);
                END
                ELSE IF @tipo_accion = 'bloquear'
                BEGIN
                    SET @decision = 'bloqueada';
                END
                ELSE IF @tipo_accion = 'permitir'
                BEGIN
                    SET @decision = 'permitida';
                END;
                
                FETCH NEXT FROM cursor_acciones INTO @tipo_accion, @detalles_accion;
            END;
            
            CLOSE cursor_acciones;
            DEALLOCATE cursor_acciones;
        END;
        ELSE
        BEGIN
            SET @decision = 'condiciones_no_cumplidas';
        END;
        
        -- 4. REGISTRAR AUDITORÍA
        INSERT INTO auditoria_evaluacion_reglas (
            id_regla, nivel_alcance, linea_negocio, id_empresa, datos_contexto,
            condiciones_cumplidas, valores_calculados, decision, evaluada_por,
            tiempo_ejecucion_ms
        )
        VALUES (
            @id_regla_param,
            (SELECT nivel_alcance FROM reglas_negocio WHERE id_regla = @id_regla_param),
            @linea_negocio_param,
            @id_empresa_param,
            @json_contexto,
            @condiciones_cumplidas,
            @valores_calculados,
            @decision,
            @evaluada_por,
            DATEDIFF(MILLISECOND, @fecha_inicio, GETUTCDATE())
        );
        
        SET @id_auditoria = SCOPE_IDENTITY();
        
        -- 5. RETORNAR RESULTADO
        SELECT
            'EXITO' AS resultado,
            @id_regla_param AS id_regla,
            @condiciones_cumplidas AS condiciones_cumplidas,
            @decision AS decision,
            @valores_calculados AS valores_calculados,
            @id_auditoria AS id_auditoria;
            
    END TRY
    BEGIN CATCH
        SELECT
            'ERROR' AS resultado,
            ERROR_MESSAGE() AS mensaje_error;
    END CATCH
END;

GO

-- ============================================================================
-- SP 3: Listar Reglas por Alcance
-- ============================================================================

CREATE PROCEDURE sp_listar_reglas_por_alcance
    @nivel_alcance_param NVARCHAR(20) = NULL,
    @linea_negocio_param NVARCHAR(50) = NULL,
    @id_empresa_param INT = NULL,
    @estado_param NVARCHAR(20) = 'activa'
AS
BEGIN
    SELECT
        id_regla,
        nombre,
        descripcion,
        nivel_alcance,
        linea_negocio,
        id_empresa,
        prioridad,
        estado,
        fecha_creacion,
        creada_por,
        (SELECT COUNT(*) FROM condiciones_regla WHERE id_regla = reglas_negocio.id_regla) AS total_condiciones,
        (SELECT COUNT(*) FROM acciones_regla WHERE id_regla = reglas_negocio.id_regla) AS total_acciones
    FROM reglas_negocio
    WHERE
        (@nivel_alcance_param IS NULL OR nivel_alcance = @nivel_alcance_param)
        AND (@linea_negocio_param IS NULL OR linea_negocio = @linea_negocio_param)
        AND (@id_empresa_param IS NULL OR id_empresa = @id_empresa_param)
        AND (@estado_param IS NULL OR estado = @estado_param)
    ORDER BY prioridad DESC, fecha_creacion DESC;
END;

GO

-- ============================================================================
-- SP 4: Obtener Auditoría
-- ============================================================================

CREATE PROCEDURE sp_obtener_auditoria
    @id_regla_param NVARCHAR(50) = NULL,
    @id_empresa_param INT = NULL,
    @dias_param INT = 30,
    @limite_param INT = 100
AS
BEGIN
    SELECT TOP (@limite_param)
        id_auditoria,
        id_regla,
        nivel_alcance,
        linea_negocio,
        id_empresa,
        condiciones_cumplidas,
        decision,
        valores_calculados,
        fecha_evaluacion,
        evaluada_por,
        tiempo_ejecucion_ms
    FROM auditoria_evaluacion_reglas
    WHERE
        (@id_regla_param IS NULL OR id_regla = @id_regla_param)
        AND (@id_empresa_param IS NULL OR id_empresa = @id_empresa_param)
        AND fecha_evaluacion >= DATEADD(DAY, -@dias_param, GETUTCDATE())
    ORDER BY fecha_evaluacion DESC;
END;

GO

-- ============================================================================
-- SP 5: Actualizar Regla
-- ============================================================================

CREATE PROCEDURE sp_actualizar_regla_negocio
    @id_regla_param NVARCHAR(50),
    @nombre_param NVARCHAR(255) = NULL,
    @descripcion_param NVARCHAR(MAX) = NULL,
    @prioridad_param INT = NULL,
    @estado_param NVARCHAR(20) = NULL,
    @actualizada_por NVARCHAR(100),
    @json_condiciones NVARCHAR(MAX) = NULL,
    @json_acciones NVARCHAR(MAX) = NULL
AS
BEGIN
    BEGIN TRY
        BEGIN TRANSACTION;
        
        -- Actualizar datos principales
        UPDATE reglas_negocio
        SET
            nombre = ISNULL(@nombre_param, nombre),
            descripcion = ISNULL(@descripcion_param, descripcion),
            prioridad = ISNULL(@prioridad_param, prioridad),
            estado = ISNULL(@estado_param, estado),
            fecha_actualizacion = GETUTCDATE(),
            actualizada_por = @actualizada_por,
            version = version + 1
        WHERE id_regla = @id_regla_param;
        
        -- Si se proporcionan condiciones nuevas, reemplazar
        IF @json_condiciones IS NOT NULL
        BEGIN
            DELETE FROM condiciones_regla WHERE id_regla = @id_regla_param;
            
            INSERT INTO condiciones_regla (id_regla, campo, operador, valor, orden_evaluacion)
            SELECT
                @id_regla_param,
                JSON_VALUE(value, '$.campo'),
                JSON_VALUE(value, '$.operador'),
                JSON_VALUE(value, '$.valor'),
                JSON_VALUE(value, '$.orden')
            FROM OPENJSON(@json_condiciones);
        END;
        
        -- Si se proporcionan acciones nuevas, reemplazar
        IF @json_acciones IS NOT NULL
        BEGIN
            DELETE FROM acciones_regla WHERE id_regla = @id_regla_param;
            
            INSERT INTO acciones_regla (id_regla, tipo_accion, detalles, orden_ejecucion)
            SELECT
                @id_regla_param,
                JSON_VALUE(value, '$.tipo'),
                JSON_QUERY(value, '$.detalles'),
                JSON_VALUE(value, '$.orden')
            FROM OPENJSON(@json_acciones);
        END;
        
        COMMIT TRANSACTION;
        
        SELECT 'EXITO' AS resultado, @id_regla_param AS id_regla;
    END TRY
    BEGIN CATCH
        ROLLBACK TRANSACTION;
        SELECT 'ERROR' AS resultado, ERROR_MESSAGE() AS mensaje_error;
    END CATCH
END;

GO

-- ============================================================================
-- SP 6: Eliminar Regla (Soft Delete)
-- ============================================================================

CREATE PROCEDURE sp_eliminar_regla_negocio
    @id_regla_param NVARCHAR(50),
    @eliminada_por NVARCHAR(100)
AS
BEGIN
    UPDATE reglas_negocio
    SET
        estado = 'archivada',
        fecha_actualizacion = GETUTCDATE(),
        actualizada_por = @eliminada_por
    WHERE id_regla = @id_regla_param;
    
    IF @@ROWCOUNT > 0
        SELECT 'EXITO' AS resultado, @id_regla_param AS id_regla;
    ELSE
        SELECT 'ERROR' AS resultado, 'Regla no encontrada' AS mensaje_error;
END;

GO

-- ============================================================================
-- VISTA 1: Reglas por Empresa
-- ============================================================================

CREATE VIEW vw_reglas_por_empresa AS
SELECT
    r.id_regla,
    r.nombre,
    r.nivel_alcance,
    r.linea_negocio,
    r.id_empresa,
    r.prioridad,
    r.estado,
    COUNT(DISTINCT rc.id_condicion) AS total_condiciones,
    COUNT(DISTINCT ra.id_accion) AS total_acciones,
    r.fecha_creacion
FROM reglas_negocio r
LEFT JOIN condiciones_regla rc ON r.id_regla = rc.id_regla
LEFT JOIN acciones_regla ra ON r.id_regla = ra.id_regla
GROUP BY r.id_regla, r.nombre, r.nivel_alcance, r.linea_negocio, r.id_empresa, 
         r.prioridad, r.estado, r.fecha_creacion;

GO

-- ============================================================================
-- VISTA 2: Resumen de Auditoría
-- ============================================================================

CREATE VIEW vw_resumen_auditoria AS
SELECT
    id_regla,
    id_empresa,
    CAST(fecha_evaluacion AS DATE) AS fecha_evaluacion,
    COUNT(*) AS total_evaluaciones,
    SUM(CASE WHEN decision = 'permitida' THEN 1 ELSE 0 END) AS cantidad_permitidas,
    SUM(CASE WHEN decision = 'bloqueada' THEN 1 ELSE 0 END) AS cantidad_bloqueadas,
    AVG(CAST(tiempo_ejecucion_ms AS FLOAT)) AS tiempo_promedio_ms
FROM auditoria_evaluacion_reglas
GROUP BY id_regla, id_empresa, CAST(fecha_evaluacion AS DATE);

GO

-- ============================================================================
-- VISTA 3: Reglas Activas por Nivel
-- ============================================================================

CREATE VIEW vw_reglas_activas_por_nivel AS
SELECT
    nivel_alcance,
    linea_negocio,
    id_empresa,
    COUNT(*) AS total_reglas,
    MAX(prioridad) AS prioridad_maxima,
    MIN(prioridad) AS prioridad_minima
FROM reglas_negocio
WHERE estado = 'activa'
GROUP BY nivel_alcance, linea_negocio, id_empresa;

GO

-- ============================================================================
-- CONFIRMACIÓN DE CREACIÓN
-- ============================================================================

SELECT 'SCHEMA CREADO EXITOSAMENTE' AS mensaje;
SELECT COUNT(*) AS total_objetos_creados FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME LIKE 'reglas%' OR TABLE_NAME LIKE 'condiciones%' OR TABLE_NAME LIKE 'acciones%' OR TABLE_NAME LIKE 'auditoria%' OR TABLE_NAME LIKE 'cache%' OR TABLE_NAME LIKE 'herencia%';

GO
