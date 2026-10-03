--| ============================================================================ |
--| SYNAPSE + GENESIS - Tablas y permisos de Sentinel                            |
--| Idempotente: se puede ejecutar varias veces y no borra datos                 |
--| ============================================================================ |

USE kinetix;
GO

--| Synapse: integraciones con APIs externas por empresa (credenciales cifradas con Fernet) |
IF OBJECT_ID('dbo.synapse_integraciones', 'U') IS NULL
CREATE TABLE dbo.synapse_integraciones (
    id_integracion       NVARCHAR(40)   NOT NULL,
    id_empresa           NVARCHAR(50)   NOT NULL,
    nombre               NVARCHAR(60)   NOT NULL,
    descripcion          NVARCHAR(500)  NULL,
    url_base             NVARCHAR(500)  NOT NULL,
    tipo_auth            NVARCHAR(10)   NOT NULL,
    auth_meta            NVARCHAR(500)  NOT NULL,
    credencial_cifrada   NVARCHAR(MAX)  NULL,
    encabezados          NVARCHAR(MAX)  NOT NULL,
    timeout_s            DECIMAL(5, 2)  NOT NULL,
    reintentos           TINYINT        NOT NULL,
    limite_por_minuto    SMALLINT       NOT NULL,
    estado               NVARCHAR(10)   NOT NULL CONSTRAINT df_synapse_integraciones_estado DEFAULT 'activa',
    especificacion       NVARCHAR(MAX)  NULL,
    version              INT            NOT NULL CONSTRAINT df_synapse_integraciones_version DEFAULT 1,
    creado_por           NVARCHAR(200)  NULL,
    fecha_creacion       DATETIME2(3)   NOT NULL,
    fecha_modificacion   DATETIME2(3)   NOT NULL,
    ultimo_estado_salud  NVARCHAR(20)   NULL,
    ultima_verificacion  DATETIME2(3)   NULL,
    CONSTRAINT pk_synapse_integraciones PRIMARY KEY CLUSTERED (id_integracion),
    CONSTRAINT uq_synapse_integraciones_empresa_nombre UNIQUE (id_empresa, nombre),
    CONSTRAINT ck_synapse_integraciones_auth CHECK (tipo_auth IN ('none', 'bearer', 'api_key', 'basic')),
    CONSTRAINT ck_synapse_integraciones_estado CHECK (estado IN ('activa', 'inactiva')),
    CONSTRAINT ck_synapse_integraciones_meta CHECK (ISJSON(auth_meta) = 1),
    CONSTRAINT ck_synapse_integraciones_encabezados CHECK (ISJSON(encabezados) = 1),
    CONSTRAINT ck_synapse_integraciones_especificacion CHECK (especificacion IS NULL OR ISJSON(especificacion) = 1)
);
GO

--| Synapse: bitácora de llamadas salientes (sin cuerpos ni credenciales) |
IF OBJECT_ID('dbo.synapse_llamadas', 'U') IS NULL
CREATE TABLE dbo.synapse_llamadas (
    id_llamada      NVARCHAR(40)   NOT NULL,
    id_integracion  NVARCHAR(40)   NOT NULL,
    id_empresa      NVARCHAR(50)   NOT NULL,
    metodo          NVARCHAR(10)   NOT NULL,
    ruta            NVARCHAR(500)  NOT NULL,
    id_operacion    NVARCHAR(100)  NULL,
    codigo_http     SMALLINT       NULL,
    exito           BIT            NOT NULL,
    duracion_ms     DECIMAL(10, 2) NOT NULL,
    intentos        TINYINT        NOT NULL,
    error           NVARCHAR(500)  NULL,
    origen          NVARCHAR(10)   NOT NULL,
    usuario         NVARCHAR(200)  NULL,
    fecha           DATETIME2(3)   NOT NULL,
    CONSTRAINT pk_synapse_llamadas PRIMARY KEY CLUSTERED (id_llamada),
    CONSTRAINT fk_synapse_llamadas_integracion FOREIGN KEY (id_integracion)
        REFERENCES dbo.synapse_integraciones (id_integracion) ON DELETE CASCADE,
    CONSTRAINT ck_synapse_llamadas_origen CHECK (origen IN ('llamada', 'prueba'))
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_synapse_llamadas_empresa_fecha' AND object_id = OBJECT_ID('dbo.synapse_llamadas'))
    CREATE INDEX idx_synapse_llamadas_empresa_fecha ON dbo.synapse_llamadas (id_empresa, fecha DESC) INCLUDE (id_integracion, exito, duracion_ms);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_synapse_llamadas_integracion' AND object_id = OBJECT_ID('dbo.synapse_llamadas'))
    CREATE INDEX idx_synapse_llamadas_integracion ON dbo.synapse_llamadas (id_integracion, fecha DESC);
GO

--| Genesis: agentes de IA personalizados por empresa |
IF OBJECT_ID('dbo.genesis_agentes', 'U') IS NULL
CREATE TABLE dbo.genesis_agentes (
    id_agente           NVARCHAR(40)   NOT NULL,
    id_empresa          NVARCHAR(50)   NOT NULL,
    nombre              NVARCHAR(60)   NOT NULL,
    descripcion         NVARCHAR(500)  NULL,
    prompt_sistema      NVARCHAR(MAX)  NOT NULL,
    proveedor           NVARCHAR(10)   NOT NULL,
    nivel               NVARCHAR(10)   NOT NULL,
    temperatura         DECIMAL(3, 2)  NULL,
    max_tokens          INT            NOT NULL,
    estado              NVARCHAR(10)   NOT NULL CONSTRAINT df_genesis_agentes_estado DEFAULT 'activo',
    version             INT            NOT NULL CONSTRAINT df_genesis_agentes_version DEFAULT 1,
    creado_por          NVARCHAR(200)  NULL,
    fecha_creacion      DATETIME2(3)   NOT NULL,
    fecha_modificacion  DATETIME2(3)   NOT NULL,
    CONSTRAINT pk_genesis_agentes PRIMARY KEY CLUSTERED (id_agente),
    CONSTRAINT uq_genesis_agentes_empresa_nombre UNIQUE (id_empresa, nombre),
    CONSTRAINT ck_genesis_agentes_proveedor CHECK (proveedor IN ('auto', 'anthropic', 'openai')),
    CONSTRAINT ck_genesis_agentes_nivel CHECK (nivel IN ('auto', 'economico', 'premium')),
    CONSTRAINT ck_genesis_agentes_estado CHECK (estado IN ('activo', 'archivado')),
    CONSTRAINT ck_genesis_agentes_tokens CHECK (max_tokens BETWEEN 64 AND 8192)
);
GO

--| Genesis: invocaciones a modelos (consumo de tokens, costo estimado y contenido opcional) |
IF OBJECT_ID('dbo.genesis_invocaciones', 'U') IS NULL
CREATE TABLE dbo.genesis_invocaciones (
    id_invocacion   NVARCHAR(40)    NOT NULL,
    id_empresa      NVARCHAR(50)    NOT NULL,
    id_agente       NVARCHAR(40)    NULL,
    tipo            NVARCHAR(12)    NOT NULL,
    proveedor       NVARCHAR(10)    NULL,
    modelo          NVARCHAR(100)   NULL,
    nivel           NVARCHAR(10)    NULL,
    tokens_entrada  INT             NOT NULL CONSTRAINT df_genesis_invocaciones_entrada DEFAULT 0,
    tokens_salida   INT             NOT NULL CONSTRAINT df_genesis_invocaciones_salida DEFAULT 0,
    costo_usd       DECIMAL(12, 6)  NULL,
    duracion_ms     DECIMAL(10, 2)  NOT NULL CONSTRAINT df_genesis_invocaciones_duracion DEFAULT 0,
    estado          NVARCHAR(10)    NOT NULL,
    error           NVARCHAR(1000)  NULL,
    usuario         NVARCHAR(200)   NULL,
    fecha           DATETIME2(3)    NOT NULL,
    prompt          NVARCHAR(MAX)   NULL,
    respuesta       NVARCHAR(MAX)   NULL,
    CONSTRAINT pk_genesis_invocaciones PRIMARY KEY CLUSTERED (id_invocacion),
    CONSTRAINT fk_genesis_invocaciones_agente FOREIGN KEY (id_agente) REFERENCES dbo.genesis_agentes (id_agente),
    CONSTRAINT ck_genesis_invocaciones_tipo CHECK (tipo IN ('agente', 'generacion')),
    CONSTRAINT ck_genesis_invocaciones_estado CHECK (estado IN ('exito', 'error', 'rechazada'))
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_genesis_invocaciones_empresa_fecha' AND object_id = OBJECT_ID('dbo.genesis_invocaciones'))
    CREATE INDEX idx_genesis_invocaciones_empresa_fecha ON dbo.genesis_invocaciones (id_empresa, fecha DESC)
        INCLUDE (proveedor, modelo, estado, tokens_entrada, tokens_salida, costo_usd);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_genesis_invocaciones_agente' AND object_id = OBJECT_ID('dbo.genesis_invocaciones'))
    CREATE INDEX idx_genesis_invocaciones_agente ON dbo.genesis_invocaciones (id_agente, fecha DESC);
GO

--| Genesis: código, SQL o documentos generados con su análisis y el commit si se aplicó |
IF OBJECT_ID('dbo.genesis_generaciones', 'U') IS NULL
CREATE TABLE dbo.genesis_generaciones (
    id_generacion  NVARCHAR(40)   NOT NULL,
    id_empresa     NVARCHAR(50)   NOT NULL,
    id_invocacion  NVARCHAR(40)   NOT NULL,
    tipo           NVARCHAR(10)   NOT NULL,
    lenguaje       NVARCHAR(12)   NOT NULL,
    descripcion    NVARCHAR(2000) NOT NULL,
    ruta_sugerida  NVARCHAR(200)  NOT NULL,
    contenido      NVARCHAR(MAX)  NOT NULL,
    analisis       NVARCHAR(MAX)  NOT NULL,
    puntuacion     DECIMAL(4, 2)  NULL,
    criticos       INT            NOT NULL CONSTRAINT df_genesis_generaciones_criticos DEFAULT 0,
    estado         NVARCHAR(12)   NOT NULL CONSTRAINT df_genesis_generaciones_estado DEFAULT 'generada',
    rama           NVARCHAR(100)  NULL,
    commit_git     CHAR(40)       NULL,
    usuario        NVARCHAR(200)  NULL,
    fecha          DATETIME2(3)   NOT NULL,
    CONSTRAINT pk_genesis_generaciones PRIMARY KEY CLUSTERED (id_generacion),
    CONSTRAINT fk_genesis_generaciones_invocacion FOREIGN KEY (id_invocacion) REFERENCES dbo.genesis_invocaciones (id_invocacion),
    CONSTRAINT ck_genesis_generaciones_tipo CHECK (tipo IN ('codigo', 'sql', 'documento')),
    CONSTRAINT ck_genesis_generaciones_estado CHECK (estado IN ('generada', 'commiteada')),
    CONSTRAINT ck_genesis_generaciones_analisis CHECK (ISJSON(analisis) = 1)
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_genesis_generaciones_empresa_fecha' AND object_id = OBJECT_ID('dbo.genesis_generaciones'))
    CREATE INDEX idx_genesis_generaciones_empresa_fecha ON dbo.genesis_generaciones (id_empresa, fecha DESC);
GO

--| Genesis: presupuesto mensual de tokens por empresa (sin fila = GENESIS_PRESUPUESTO_TOKENS_MENSUAL) |
IF OBJECT_ID('dbo.genesis_presupuestos', 'U') IS NULL
CREATE TABLE dbo.genesis_presupuestos (
    id_empresa          NVARCHAR(50)   NOT NULL,
    tokens_mensuales    BIGINT         NOT NULL,
    actualizado_por     NVARCHAR(200)  NULL,
    fecha_modificacion  DATETIME2(3)   NOT NULL,
    CONSTRAINT pk_genesis_presupuestos PRIMARY KEY CLUSTERED (id_empresa),
    CONSTRAINT ck_genesis_presupuestos_tokens CHECK (tokens_mensuales > 0)
);
GO

--| Permisos de Synapse y Genesis |
--| nombre_permiso solo existe en algunas bases: se inserta con SQL dinámico cuando está |
DECLARE @permisos TABLE (id NVARCHAR(50), nombre NVARCHAR(100), recurso NVARCHAR(100), accion NVARCHAR(100), descripcion NVARCHAR(500));
INSERT INTO @permisos VALUES
    ('perm_synapse_001', N'Ver Integraciones',       'integraciones', 'ver',       N'Consultar integraciones, operaciones, llamadas y métricas de Synapse'),
    ('perm_synapse_002', N'Gestionar Integraciones', 'integraciones', 'gestionar', N'Crear, modificar y eliminar integraciones y credenciales con Synapse'),
    ('perm_synapse_003', N'Invocar Integraciones',   'integraciones', 'invocar',   N'Llamar APIs externas y probar conexiones a través de Synapse'),
    ('perm_genesis_001', N'Ver IA',                  'ia',            'ver',       N'Consultar agentes de IA, invocaciones, generaciones y uso de Genesis'),
    ('perm_genesis_002', N'Gestionar IA',            'ia',            'gestionar', N'Crear y modificar agentes de IA y el presupuesto de tokens de Genesis'),
    ('perm_genesis_003', N'Invocar IA',              'ia',            'invocar',   N'Invocar agentes y generar código, SQL o documentos con Genesis');

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
    ('rol_admin',   'perm_synapse_001'),
    ('rol_admin',   'perm_synapse_002'),
    ('rol_admin',   'perm_synapse_003'),
    ('rol_admin',   'perm_genesis_001'),
    ('rol_admin',   'perm_genesis_002'),
    ('rol_admin',   'perm_genesis_003'),
    ('rol_auditor', 'perm_synapse_001'),
    ('rol_auditor', 'perm_genesis_001')
) AS asignacion (id_rol, id_permiso)
WHERE EXISTS (SELECT 1 FROM dbo.roles r WHERE r.id = asignacion.id_rol)
  AND NOT EXISTS (
      SELECT 1 FROM dbo.roles_permisos rp
      WHERE rp.id_rol = asignacion.id_rol AND rp.id_permiso = asignacion.id_permiso
  );
GO

PRINT 'SYNAPSE + GENESIS: migración aplicada';
