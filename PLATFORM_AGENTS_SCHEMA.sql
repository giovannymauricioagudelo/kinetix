--| ============================================================================ |
--| AURORA + VECTOR + PRISM + ORBIT + INSIGHT - Tablas y permisos de Sentinel    |
--| Idempotente: se puede ejecutar varias veces y no borra datos                 |
--| ============================================================================ |

USE kinetix;
GO

--| Aurora: sistemas de diseño por empresa (tokens en JSON, versión para concurrencia optimista) |
IF OBJECT_ID('dbo.aurora_sistemas', 'U') IS NULL
CREATE TABLE dbo.aurora_sistemas (
    id_sistema          NVARCHAR(40)  NOT NULL,
    nombre              NVARCHAR(100) NOT NULL,
    id_empresa          NVARCHAR(50)  NOT NULL,
    nivel_wcag          NVARCHAR(3)   NOT NULL CONSTRAINT df_aurora_sistemas_nivel DEFAULT 'AA',
    tokens              NVARCHAR(MAX) NOT NULL,
    version             INT           NOT NULL CONSTRAINT df_aurora_sistemas_version DEFAULT 1,
    estado              NVARCHAR(20)  NOT NULL CONSTRAINT df_aurora_sistemas_estado DEFAULT 'activo',
    creado_por          NVARCHAR(200) NULL,
    fecha_creacion      DATETIME2(3)  NOT NULL,
    fecha_modificacion  DATETIME2(3)  NOT NULL,
    CONSTRAINT pk_aurora_sistemas PRIMARY KEY CLUSTERED (id_sistema),
    CONSTRAINT uq_aurora_sistemas_empresa_nombre UNIQUE (id_empresa, nombre),
    CONSTRAINT ck_aurora_sistemas_nivel CHECK (nivel_wcag IN ('AA', 'AAA')),
    CONSTRAINT ck_aurora_sistemas_tokens CHECK (ISJSON(tokens) = 1)
);
GO

--| Aurora: especificación de componentes de cada sistema |
IF OBJECT_ID('dbo.aurora_componentes', 'U') IS NULL
CREATE TABLE dbo.aurora_componentes (
    id_sistema          NVARCHAR(40)  NOT NULL,
    nombre              NVARCHAR(60)  NOT NULL,
    tipo                NVARCHAR(30)  NOT NULL,
    especificacion      NVARCHAR(MAX) NOT NULL,
    fecha_modificacion  DATETIME2(3)  NOT NULL,
    CONSTRAINT pk_aurora_componentes PRIMARY KEY CLUSTERED (id_sistema, nombre),
    CONSTRAINT fk_aurora_componentes_sistema FOREIGN KEY (id_sistema)
        REFERENCES dbo.aurora_sistemas (id_sistema) ON DELETE CASCADE,
    CONSTRAINT ck_aurora_componentes_especificacion CHECK (ISJSON(especificacion) = 1)
);
GO

--| Vector: historial de análisis estáticos |
IF OBJECT_ID('dbo.vector_analisis', 'U') IS NULL
CREATE TABLE dbo.vector_analisis (
    id_analisis    NVARCHAR(40)  NOT NULL,
    objetivo       NVARCHAR(500) NOT NULL,
    archivos       INT           NOT NULL,
    lineas         INT           NOT NULL,
    puntuacion     DECIMAL(4, 2) NOT NULL,
    criticos       INT           NOT NULL,
    altos          INT           NOT NULL,
    resumen        NVARCHAR(MAX) NULL,
    analizado_por  NVARCHAR(200) NULL,
    fecha          DATETIME2(3)  NOT NULL,
    CONSTRAINT pk_vector_analisis PRIMARY KEY CLUSTERED (id_analisis)
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_vector_analisis_fecha' AND object_id = OBJECT_ID('dbo.vector_analisis'))
    CREATE INDEX idx_vector_analisis_fecha ON dbo.vector_analisis (fecha DESC);
GO

--| Prism: ejecuciones de pruebas (pytest + cobertura) |
IF OBJECT_ID('dbo.prism_ejecuciones', 'U') IS NULL
CREATE TABLE dbo.prism_ejecuciones (
    id_ejecucion    NVARCHAR(40)  NOT NULL,
    objetivos       NVARCHAR(MAX) NOT NULL,
    filtro          NVARCHAR(200) NULL,
    con_cobertura   BIT           NOT NULL,
    suite_completa  BIT           NOT NULL,
    estado          NVARCHAR(20)  NOT NULL,
    commit_git      CHAR(40)      NULL,
    arbol_limpio    BIT           NOT NULL,
    iniciada_por    NVARCHAR(200) NULL,
    fecha_inicio    DATETIME2(3)  NOT NULL,
    total           INT           NOT NULL CONSTRAINT df_prism_total DEFAULT 0,
    pasadas         INT           NOT NULL CONSTRAINT df_prism_pasadas DEFAULT 0,
    fallidas        INT           NOT NULL CONSTRAINT df_prism_fallidas DEFAULT 0,
    omitidas        INT           NOT NULL CONSTRAINT df_prism_omitidas DEFAULT 0,
    errores         INT           NOT NULL CONSTRAINT df_prism_errores DEFAULT 0,
    cobertura       DECIMAL(5, 2) NULL,
    duracion_s      DECIMAL(9, 2) NOT NULL CONSTRAINT df_prism_duracion DEFAULT 0,
    fecha_fin       DATETIME2(3)  NULL,
    detalle         NVARCHAR(MAX) NULL,
    CONSTRAINT pk_prism_ejecuciones PRIMARY KEY CLUSTERED (id_ejecucion),
    CONSTRAINT ck_prism_ejecuciones_estado CHECK (estado IN ('en_cola', 'ejecutando', 'aprobada', 'fallida', 'error'))
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_prism_ejecuciones_commit' AND object_id = OBJECT_ID('dbo.prism_ejecuciones'))
    CREATE INDEX idx_prism_ejecuciones_commit ON dbo.prism_ejecuciones (commit_git, suite_completa, fecha_inicio DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_prism_ejecuciones_fecha' AND object_id = OBJECT_ID('dbo.prism_ejecuciones'))
    CREATE INDEX idx_prism_ejecuciones_fecha ON dbo.prism_ejecuciones (fecha_inicio DESC);
GO

--| Orbit: despliegues y reversiones (un tag anotado por despliegue) |
IF OBJECT_ID('dbo.orbit_despliegues', 'U') IS NULL
CREATE TABLE dbo.orbit_despliegues (
    id_despliegue  NVARCHAR(40)  NOT NULL,
    entorno        NVARCHAR(20)  NOT NULL,
    tipo           NVARCHAR(20)  NOT NULL,
    commit_git     CHAR(40)      NOT NULL,
    estado         NVARCHAR(20)  NOT NULL,
    iniciado_por   NVARCHAR(200) NULL,
    fecha_inicio   DATETIME2(3)  NOT NULL,
    tag            NVARCHAR(200) NULL,
    tag_publicado  BIT           NOT NULL CONSTRAINT df_orbit_tag_publicado DEFAULT 0,
    id_origen      NVARCHAR(40)  NULL,
    notas          NVARCHAR(500) NULL,
    fecha_fin      DATETIME2(3)  NULL,
    compuerta      NVARCHAR(MAX) NULL,
    workflow       NVARCHAR(MAX) NULL,
    bitacora       NVARCHAR(MAX) NULL,
    CONSTRAINT pk_orbit_despliegues PRIMARY KEY CLUSTERED (id_despliegue),
    CONSTRAINT fk_orbit_despliegues_origen FOREIGN KEY (id_origen) REFERENCES dbo.orbit_despliegues (id_despliegue),
    CONSTRAINT ck_orbit_despliegues_entorno CHECK (entorno IN ('staging', 'produccion')),
    CONSTRAINT ck_orbit_despliegues_tipo CHECK (tipo IN ('despliegue', 'reversion')),
    CONSTRAINT ck_orbit_despliegues_estado CHECK (estado IN ('exitoso', 'fallido', 'rechazado'))
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_orbit_despliegues_entorno' AND object_id = OBJECT_ID('dbo.orbit_despliegues'))
    CREATE INDEX idx_orbit_despliegues_entorno ON dbo.orbit_despliegues (entorno, estado, fecha_inicio DESC) INCLUDE (commit_git);
GO

--| Insight: programaciones de reportes (se ejecutan con la identidad de quien las creó) |
IF OBJECT_ID('dbo.insight_programaciones', 'U') IS NULL
CREATE TABLE dbo.insight_programaciones (
    id_programacion    NVARCHAR(40)   NOT NULL,
    id_empresa         NVARCHAR(50)   NOT NULL,
    nombre             NVARCHAR(200)  NOT NULL,
    tipo               NVARCHAR(50)   NOT NULL,
    parametros         NVARCHAR(MAX)  NOT NULL,
    frecuencia         NVARCHAR(10)   NOT NULL,
    hora_utc           TINYINT        NOT NULL,
    activa             BIT            NOT NULL CONSTRAINT df_insight_programaciones_activa DEFAULT 1,
    proxima_ejecucion  DATETIME2(3)   NOT NULL,
    id_usuario         NVARCHAR(50)   NOT NULL,
    nombre_usuario     NVARCHAR(200)  NULL,
    fecha_creacion     DATETIME2(3)   NOT NULL,
    ultima_ejecucion   DATETIME2(3)   NULL,
    ultimo_estado      NVARCHAR(10)   NULL,
    ultimo_error       NVARCHAR(1000) NULL,
    CONSTRAINT pk_insight_programaciones PRIMARY KEY CLUSTERED (id_programacion),
    CONSTRAINT ck_insight_programaciones_frecuencia CHECK (frecuencia IN ('diaria', 'semanal', 'mensual')),
    CONSTRAINT ck_insight_programaciones_hora CHECK (hora_utc BETWEEN 0 AND 23),
    CONSTRAINT ck_insight_programaciones_parametros CHECK (ISJSON(parametros) = 1)
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_insight_programaciones_proxima' AND object_id = OBJECT_ID('dbo.insight_programaciones'))
    CREATE INDEX idx_insight_programaciones_proxima ON dbo.insight_programaciones (activa, proxima_ejecucion);
GO

--| Insight: reportes guardados (resultado completo en JSON) |
IF OBJECT_ID('dbo.insight_reportes', 'U') IS NULL
CREATE TABLE dbo.insight_reportes (
    id_reporte       NVARCHAR(40)  NOT NULL,
    id_empresa       NVARCHAR(50)  NOT NULL,
    tipo             NVARCHAR(50)  NOT NULL,
    nombre           NVARCHAR(200) NOT NULL,
    parametros       NVARCHAR(MAX) NOT NULL,
    filas            INT           NOT NULL,
    origen           NVARCHAR(20)  NOT NULL,
    generado_por     NVARCHAR(200) NULL,
    fecha            DATETIME2(3)  NOT NULL,
    id_programacion  NVARCHAR(40)  NULL,
    resultado        NVARCHAR(MAX) NOT NULL,
    CONSTRAINT pk_insight_reportes PRIMARY KEY CLUSTERED (id_reporte),
    CONSTRAINT fk_insight_reportes_programacion FOREIGN KEY (id_programacion)
        REFERENCES dbo.insight_programaciones (id_programacion) ON DELETE SET NULL,
    CONSTRAINT ck_insight_reportes_origen CHECK (origen IN ('manual', 'programado'))
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_insight_reportes_empresa_fecha' AND object_id = OBJECT_ID('dbo.insight_reportes'))
    CREATE INDEX idx_insight_reportes_empresa_fecha ON dbo.insight_reportes (id_empresa, fecha DESC) INCLUDE (tipo);
GO

--| Permisos de los cinco agentes |
--| nombre_permiso solo existe en algunas bases: se inserta con SQL dinámico cuando está |
DECLARE @permisos TABLE (id NVARCHAR(50), nombre NVARCHAR(100), recurso NVARCHAR(100), accion NVARCHAR(100), descripcion NVARCHAR(500));
INSERT INTO @permisos VALUES
    ('perm_aurora_001',  N'Ver Diseño',            'diseno',      'ver',       N'Consultar sistemas de diseño, exportar tokens y auditar accesibilidad con Aurora'),
    ('perm_aurora_002',  N'Gestionar Diseño',      'diseno',      'gestionar', N'Crear y modificar sistemas de diseño y componentes con Aurora'),
    ('perm_vector_001',  N'Ver Código',            'codigo',      'ver',       N'Analizar código, ver ramas, commits y diffs con Vector'),
    ('perm_vector_002',  N'Escribir Código',       'codigo',      'escribir',  N'Crear ramas de trabajo y commits (nunca en master/main) con Vector'),
    ('perm_prism_001',   N'Ver Calidad',           'calidad',     'ver',       N'Consultar pruebas, ejecuciones, lint, conflictos y compuerta de Prism'),
    ('perm_prism_002',   N'Ejecutar Pruebas',      'calidad',     'ejecutar',  N'Lanzar ejecuciones de pruebas con Prism'),
    ('perm_orbit_001',   N'Ver Despliegues',       'despliegues', 'ver',       N'Consultar releases, despliegues y GitHub Actions con Orbit'),
    ('perm_orbit_002',   N'Ejecutar Despliegues',  'despliegues', 'ejecutar',  N'Desplegar y revertir releases con Orbit'),
    ('perm_insight_001', N'Ver Reportes',          'reportes',    'ver',       N'Consultar catálogo, KPIs y reportes guardados de Insight'),
    ('perm_insight_002', N'Generar Reportes',      'reportes',    'generar',   N'Generar, exportar, guardar y eliminar reportes con Insight'),
    ('perm_insight_003', N'Programar Reportes',    'reportes',    'programar', N'Crear y administrar programaciones de reportes de Insight');

DECLARE @id NVARCHAR(50), @nombre NVARCHAR(100), @recurso NVARCHAR(100), @accion NVARCHAR(100), @descripcion NVARCHAR(500);
DECLARE @con_nombre BIT = CASE WHEN COL_LENGTH('dbo.permisos', 'nombre_permiso') IS NULL THEN 0 ELSE 1 END;
DECLARE cursor_permisos CURSOR LOCAL FAST_FORWARD FOR
    SELECT p.id, p.nombre, p.recurso, p.accion, p.descripcion FROM @permisos p
    WHERE NOT EXISTS (SELECT 1 FROM dbo.permisos e WHERE e.id = p.id);
OPEN cursor_permisos;
FETCH NEXT FROM cursor_permisos INTO @id, @nombre, @recurso, @accion, @descripcion;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF @con_nombre = 1
        EXEC sp_executesql
            N'INSERT INTO dbo.permisos (id, nombre_permiso, recurso, accion, descripcion) VALUES (@id, @nombre, @recurso, @accion, @descripcion)',
            N'@id NVARCHAR(50), @nombre NVARCHAR(100), @recurso NVARCHAR(100), @accion NVARCHAR(100), @descripcion NVARCHAR(500)',
            @id, @nombre, @recurso, @accion, @descripcion;
    ELSE
        INSERT INTO dbo.permisos (id, recurso, accion, descripcion) VALUES (@id, @recurso, @accion, @descripcion);
    FETCH NEXT FROM cursor_permisos INTO @id, @nombre, @recurso, @accion, @descripcion;
END
CLOSE cursor_permisos;
DEALLOCATE cursor_permisos;
GO

--| rol_admin recibe todos los permisos nuevos; rol_auditor los de consulta |
INSERT INTO dbo.roles_permisos (id_rol, id_permiso)
SELECT asignacion.id_rol, asignacion.id_permiso
FROM (VALUES
    ('rol_admin',   'perm_aurora_001'),
    ('rol_admin',   'perm_aurora_002'),
    ('rol_admin',   'perm_vector_001'),
    ('rol_admin',   'perm_vector_002'),
    ('rol_admin',   'perm_prism_001'),
    ('rol_admin',   'perm_prism_002'),
    ('rol_admin',   'perm_orbit_001'),
    ('rol_admin',   'perm_orbit_002'),
    ('rol_admin',   'perm_insight_001'),
    ('rol_admin',   'perm_insight_002'),
    ('rol_admin',   'perm_insight_003'),
    ('rol_auditor', 'perm_aurora_001'),
    ('rol_auditor', 'perm_vector_001'),
    ('rol_auditor', 'perm_prism_001'),
    ('rol_auditor', 'perm_orbit_001'),
    ('rol_auditor', 'perm_insight_001')
) AS asignacion (id_rol, id_permiso)
WHERE EXISTS (SELECT 1 FROM dbo.roles r WHERE r.id = asignacion.id_rol)
  AND NOT EXISTS (
      SELECT 1 FROM dbo.roles_permisos rp
      WHERE rp.id_rol = asignacion.id_rol AND rp.id_permiso = asignacion.id_permiso
  );
GO

PRINT 'AURORA + VECTOR + PRISM + ORBIT + INSIGHT: migración aplicada';
