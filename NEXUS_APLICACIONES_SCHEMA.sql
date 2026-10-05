--| ============================================================================ |
--| NEXUS - Registro de aplicaciones generadas y sus bases de datos independientes |
--| por_empresa: una base por empresa ({app}_{empresa})                            |
--| multiempresa: una base compartida ({app}) con id_empresa y seguridad por fila  |
--| Idempotente: se puede ejecutar varias veces y no borra datos                   |
--| ============================================================================ |

USE kinetix;
GO

--| Aplicaciones registradas: el modelo de datos decide cuántas bases se crean |
IF OBJECT_ID(N'dbo.nexus_aplicaciones', N'U') IS NULL
    CREATE TABLE dbo.nexus_aplicaciones (
        id_aplicacion NVARCHAR(30) NOT NULL CONSTRAINT PK_nexus_aplicaciones PRIMARY KEY CLUSTERED,
        nombre NVARCHAR(100) NOT NULL,
        modelo_datos NVARCHAR(20) NOT NULL CONSTRAINT CK_nexus_aplicaciones_modelo CHECK (modelo_datos IN (N'por_empresa', N'multiempresa')),
        propietario NVARCHAR(50) NOT NULL,
        seguridad_por_fila BIT NOT NULL CONSTRAINT DF_nexus_aplicaciones_rls DEFAULT 1,
        descripcion NVARCHAR(500) NULL,
        id_solicitud NVARCHAR(50) NULL,
        estado NVARCHAR(20) NOT NULL CONSTRAINT DF_nexus_aplicaciones_estado DEFAULT N'activa'
            CONSTRAINT CK_nexus_aplicaciones_estado CHECK (estado IN (N'activa', N'inactiva')),
        creado_por NVARCHAR(100) NOT NULL,
        fecha_creacion DATETIME2 NOT NULL CONSTRAINT DF_nexus_aplicaciones_creacion DEFAULT SYSUTCDATETIME(),
        fecha_modificacion DATETIME2 NOT NULL CONSTRAINT DF_nexus_aplicaciones_modificacion DEFAULT SYSUTCDATETIME()
    );
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_nexus_aplicaciones_propietario' AND object_id = OBJECT_ID('dbo.nexus_aplicaciones'))
    CREATE INDEX idx_nexus_aplicaciones_propietario ON dbo.nexus_aplicaciones(propietario);
GO

--| Empresas cliente de cada aplicación |
IF OBJECT_ID(N'dbo.nexus_aplicacion_empresas', N'U') IS NULL
    CREATE TABLE dbo.nexus_aplicacion_empresas (
        id_aplicacion NVARCHAR(30) NOT NULL CONSTRAINT FK_nexus_aplicacion_empresas_app REFERENCES dbo.nexus_aplicaciones(id_aplicacion),
        id_empresa NVARCHAR(30) NOT NULL,
        nombre NVARCHAR(200) NOT NULL,
        estado NVARCHAR(20) NOT NULL CONSTRAINT DF_nexus_aplicacion_empresas_estado DEFAULT N'activa',
        fecha_registro DATETIME2 NOT NULL CONSTRAINT DF_nexus_aplicacion_empresas_fecha DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_nexus_aplicacion_empresas PRIMARY KEY CLUSTERED (id_aplicacion, id_empresa)
    );
GO

--| Bases de datos independientes: una por aplicación (multiempresa) o una por empresa (por_empresa) |
IF OBJECT_ID(N'dbo.nexus_bases_datos', N'U') IS NULL
    CREATE TABLE dbo.nexus_bases_datos (
        nombre_base NVARCHAR(128) NOT NULL CONSTRAINT PK_nexus_bases_datos PRIMARY KEY CLUSTERED,
        id_aplicacion NVARCHAR(30) NOT NULL CONSTRAINT FK_nexus_bases_datos_app REFERENCES dbo.nexus_aplicaciones(id_aplicacion),
        id_empresa NVARCHAR(30) NULL,
        estado NVARCHAR(20) NOT NULL CONSTRAINT DF_nexus_bases_datos_estado DEFAULT N'pendiente'
            CONSTRAINT CK_nexus_bases_datos_estado CHECK (estado IN (N'pendiente', N'desplegada', N'error')),
        version INT NOT NULL CONSTRAINT DF_nexus_bases_datos_version DEFAULT 0,
        fecha_creacion DATETIME2 NOT NULL CONSTRAINT DF_nexus_bases_datos_creacion DEFAULT SYSUTCDATETIME(),
        fecha_despliegue DATETIME2 NULL,
        ultimo_error NVARCHAR(1000) NULL
    );
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_nexus_bases_datos_app' AND object_id = OBJECT_ID('dbo.nexus_bases_datos'))
    CREATE INDEX idx_nexus_bases_datos_app ON dbo.nexus_bases_datos(id_aplicacion, id_empresa);
GO

--| Migraciones numeradas e inmutables de cada aplicación (checksum SHA-256 del script) |
IF OBJECT_ID(N'dbo.nexus_migraciones', N'U') IS NULL
    CREATE TABLE dbo.nexus_migraciones (
        id_aplicacion NVARCHAR(30) NOT NULL CONSTRAINT FK_nexus_migraciones_app REFERENCES dbo.nexus_aplicaciones(id_aplicacion),
        numero INT NOT NULL,
        nombre NVARCHAR(250) NOT NULL,
        tipo NVARCHAR(10) NOT NULL CONSTRAINT CK_nexus_migraciones_tipo CHECK (tipo IN (N'base', N'tabla', N'sql')),
        descripcion NVARCHAR(500) NULL,
        script NVARCHAR(MAX) NOT NULL,
        checksum CHAR(64) NOT NULL,
        creado_por NVARCHAR(100) NOT NULL,
        fecha_creacion DATETIME2 NOT NULL CONSTRAINT DF_nexus_migraciones_fecha DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_nexus_migraciones PRIMARY KEY CLUSTERED (id_aplicacion, numero),
        CONSTRAINT UQ_nexus_migraciones_nombre UNIQUE (id_aplicacion, nombre)
    );
GO

--| Bitácora de despliegues por base |
IF OBJECT_ID(N'dbo.nexus_despliegues', N'U') IS NULL
    CREATE TABLE dbo.nexus_despliegues (
        id_despliegue NVARCHAR(50) NOT NULL CONSTRAINT PK_nexus_despliegues PRIMARY KEY CLUSTERED,
        id_aplicacion NVARCHAR(30) NOT NULL CONSTRAINT FK_nexus_despliegues_app REFERENCES dbo.nexus_aplicaciones(id_aplicacion),
        nombre_base NVARCHAR(128) NOT NULL,
        id_empresa NVARCHAR(30) NULL,
        estado NVARCHAR(20) NOT NULL CONSTRAINT CK_nexus_despliegues_estado CHECK (estado IN (N'exitoso', N'sin_cambios', N'fallido')),
        migraciones_aplicadas NVARCHAR(MAX) NOT NULL CONSTRAINT CK_nexus_despliegues_json CHECK (ISJSON(migraciones_aplicadas) = 1),
        version_resultante INT NOT NULL,
        detalle NVARCHAR(1000) NULL,
        ejecutado_por NVARCHAR(100) NOT NULL,
        fecha_inicio DATETIME2 NOT NULL,
        fecha_fin DATETIME2 NOT NULL
    );
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_nexus_despliegues_app_fecha' AND object_id = OBJECT_ID('dbo.nexus_despliegues'))
    CREATE INDEX idx_nexus_despliegues_app_fecha ON dbo.nexus_despliegues(id_aplicacion, fecha_inicio DESC);
GO

--| Permisos de Sentinel para el registro de aplicaciones |
--| nombre_permiso solo existe en algunas bases: se inserta con SQL dinámico cuando está |
DECLARE @permisos TABLE (id NVARCHAR(50), nombre NVARCHAR(100), recurso NVARCHAR(100), accion NVARCHAR(100), descripcion NVARCHAR(500));
INSERT INTO @permisos VALUES
    ('perm_nexus_005', N'Ver Aplicaciones',       'aplicaciones', 'ver',       N'Consultar aplicaciones, bases, migraciones y despliegues con Nexus'),
    ('perm_nexus_006', N'Gestionar Aplicaciones', 'aplicaciones', 'gestionar', N'Registrar aplicaciones, empresas, tablas y migraciones con Nexus'),
    ('perm_nexus_007', N'Desplegar Aplicaciones', 'aplicaciones', 'desplegar', N'Crear las bases de las aplicaciones y aplicarles las migraciones con Nexus');

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

--| rol_admin recibe todos; rol_auditor puede consultar |
INSERT INTO dbo.roles_permisos (id_rol, id_permiso)
SELECT asignacion.id_rol, asignacion.id_permiso
FROM (VALUES
    ('rol_admin',   'perm_nexus_005'),
    ('rol_admin',   'perm_nexus_006'),
    ('rol_admin',   'perm_nexus_007'),
    ('rol_auditor', 'perm_nexus_005')
) AS asignacion (id_rol, id_permiso)
WHERE EXISTS (SELECT 1 FROM dbo.roles r WHERE r.id = asignacion.id_rol)
  AND NOT EXISTS (
      SELECT 1 FROM dbo.roles_permisos rp
      WHERE rp.id_rol = asignacion.id_rol AND rp.id_permiso = asignacion.id_permiso
  );
GO

PRINT 'NEXUS APLICACIONES: migración aplicada';
