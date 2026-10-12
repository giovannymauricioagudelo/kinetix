--| KINETIX - ACCESO A DATOS SOLO POR PROCEDIMIENTOS ALMACENADOS                         |
--| Un esquema por agente (sentinel, nexus, matrix, synapse, genesis, insight, aurora,   |
--| prism, orbit, vector) con los procedimientos que usan sus repositorios.              |
--| El rol kinetix_app_rol solo tiene EXECUTE sobre esos esquemas: sin SELECT, INSERT,   |
--| UPDATE ni DELETE sobre dbo. Idempotente (CREATE OR ALTER) y sin borrar datos.        |
--| Aplicar: venv\Scripts\python.exe scripts\apply_sql_migration.py KINETIX_PROCEDIMIENTOS.sql |

--| ESQUEMAS DE PROCEDIMIENTOS (propiedad de dbo: encadenamiento de propiedad con las tablas) |
IF SCHEMA_ID(N'sentinel') IS NULL EXEC(N'CREATE SCHEMA sentinel AUTHORIZATION dbo');
IF SCHEMA_ID(N'nexus') IS NULL EXEC(N'CREATE SCHEMA nexus AUTHORIZATION dbo');
IF SCHEMA_ID(N'matrix') IS NULL EXEC(N'CREATE SCHEMA matrix AUTHORIZATION dbo');
IF SCHEMA_ID(N'synapse') IS NULL EXEC(N'CREATE SCHEMA synapse AUTHORIZATION dbo');
IF SCHEMA_ID(N'genesis') IS NULL EXEC(N'CREATE SCHEMA genesis AUTHORIZATION dbo');
IF SCHEMA_ID(N'insight') IS NULL EXEC(N'CREATE SCHEMA insight AUTHORIZATION dbo');
IF SCHEMA_ID(N'aurora') IS NULL EXEC(N'CREATE SCHEMA aurora AUTHORIZATION dbo');
IF SCHEMA_ID(N'prism') IS NULL EXEC(N'CREATE SCHEMA prism AUTHORIZATION dbo');
IF SCHEMA_ID(N'orbit') IS NULL EXEC(N'CREATE SCHEMA orbit AUTHORIZATION dbo');
IF SCHEMA_ID(N'vector') IS NULL EXEC(N'CREATE SCHEMA vector AUTHORIZATION dbo');
GO

--| SENTINEL: columnas que antes se detectaban en tiempo de ejecución (bases antiguas)   |
IF COL_LENGTH(N'dbo.roles', N'estado') IS NULL ALTER TABLE dbo.roles ADD estado NVARCHAR(20) NULL;
IF COL_LENGTH(N'dbo.fichas_acceso', N'ficha_hash') IS NULL ALTER TABLE dbo.fichas_acceso ADD ficha_hash CHAR(64) NULL;
IF COL_LENGTH(N'dbo.fichas_acceso', N'revocada_en') IS NULL ALTER TABLE dbo.fichas_acceso ADD revocada_en DATETIME NULL;
IF COL_LENGTH(N'dbo.usuarios_roles', N'expira_en') IS NULL ALTER TABLE dbo.usuarios_roles ADD expira_en DATETIME NULL;
IF COL_LENGTH(N'dbo.usuarios', N'mfa_habilitado') IS NULL ALTER TABLE dbo.usuarios ADD mfa_habilitado BIT NULL;
IF COL_LENGTH(N'dbo.usuarios', N'actualizado_en') IS NULL ALTER TABLE dbo.usuarios ADD actualizado_en DATETIME NULL;
GO

--| SENTINEL: usuarios |
CREATE OR ALTER PROCEDURE sentinel.usuario_por_nombre @nombre_usuario NVARCHAR(255), @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id, nombre_usuario, id_empresa, hash_contrasena, estado FROM dbo.usuarios
    WHERE nombre_usuario = @nombre_usuario AND id_empresa = @id_empresa;
END
GO

CREATE OR ALTER PROCEDURE sentinel.usuario_obtener @id_usuario NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id, nombre_usuario, id_empresa, hash_contrasena, estado FROM dbo.usuarios WHERE id = @id_usuario;
END
GO

CREATE OR ALTER PROCEDURE sentinel.usuarios_mfa_contar @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT COUNT(*) AS total, SUM(CASE WHEN m.habilitado = 1 THEN 1 ELSE 0 END) AS con_mfa
    FROM dbo.usuarios u LEFT JOIN dbo.mfa_secrets m ON m.id_usuario = u.id
    WHERE u.id_empresa = @id_empresa AND COALESCE(u.estado, N'activo') = N'activo';
END
GO

--| SENTINEL: MFA |
CREATE OR ALTER PROCEDURE sentinel.mfa_obtener @id_usuario NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_usuario, secret_totp, habilitado, ultimo_paso_totp FROM dbo.mfa_secrets WHERE id_usuario = @id_usuario;
END
GO

CREATE OR ALTER PROCEDURE sentinel.mfa_guardar_pendiente @id_usuario NVARCHAR(50), @secreto NVARCHAR(255), @ahora DATETIME
AS
BEGIN
    SET NOCOUNT ON;
    MERGE dbo.mfa_secrets WITH (HOLDLOCK) AS destino
    USING (SELECT @id_usuario AS id_usuario) AS origen ON destino.id_usuario = origen.id_usuario
    WHEN MATCHED AND COALESCE(destino.habilitado, 0) = 0 THEN
        UPDATE SET secret_totp = @secreto, ultimo_paso_totp = NULL, fecha_creacion = @ahora, fecha_confirmacion = NULL
    WHEN NOT MATCHED THEN
        INSERT (id_usuario, secret_totp, habilitado, fecha_creacion) VALUES (@id_usuario, @secreto, 0, @ahora);
END
GO

CREATE OR ALTER PROCEDURE sentinel.mfa_cambiar @id_usuario NVARCHAR(50), @habilitado BIT, @ahora DATETIME
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.mfa_secrets
    SET habilitado = @habilitado,
        fecha_confirmacion = CASE WHEN @habilitado = 1 THEN @ahora ELSE fecha_confirmacion END,
        fecha_deshabilitacion = CASE WHEN @habilitado = 0 THEN @ahora ELSE fecha_deshabilitacion END
    WHERE id_usuario = @id_usuario;
    UPDATE dbo.usuarios SET mfa_habilitado = @habilitado, actualizado_en = @ahora WHERE id = @id_usuario;
END
GO

CREATE OR ALTER PROCEDURE sentinel.mfa_reclamar_paso @id_usuario NVARCHAR(50), @paso BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.mfa_secrets SET ultimo_paso_totp = @paso
    WHERE id_usuario = @id_usuario AND (ultimo_paso_totp IS NULL OR ultimo_paso_totp < @paso);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

--| SENTINEL: fichas (refresh y revocación de access tokens) |
CREATE OR ALTER PROCEDURE sentinel.ficha_insertar
    @id NVARCHAR(255), @id_usuario NVARCHAR(50), @tipo_ficha NVARCHAR(50), @expira_en DATETIME, @ficha_hash CHAR(64),
    @revocada_en DATETIME = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.fichas_acceso (id, id_usuario, tipo_ficha, expira_en, revocada, ficha_hash, revocada_en)
    SELECT @id, @id_usuario, @tipo_ficha, @expira_en, CASE WHEN @revocada_en IS NULL THEN 0 ELSE 1 END, @ficha_hash, @revocada_en
    WHERE NOT EXISTS (SELECT 1 FROM dbo.fichas_acceso WITH (UPDLOCK, HOLDLOCK) WHERE id = @id);
END
GO

CREATE OR ALTER PROCEDURE sentinel.ficha_refresco_obtener @id NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_usuario, revocada FROM dbo.fichas_acceso WHERE id = @id AND tipo_ficha = N'Refresh';
END
GO

CREATE OR ALTER PROCEDURE sentinel.ficha_refresco_revocar @id NVARCHAR(255), @ahora DATETIME
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.fichas_acceso SET revocada = 1, revocada_en = @ahora
    WHERE id = @id AND tipo_ficha = N'Refresh' AND COALESCE(revocada, 0) = 0;
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE sentinel.fichas_refresco_revocar_usuario @id_usuario NVARCHAR(50), @ahora DATETIME
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.fichas_acceso SET revocada = 1, revocada_en = @ahora
    WHERE id_usuario = @id_usuario AND tipo_ficha = N'Refresh' AND COALESCE(revocada, 0) = 0;
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE sentinel.ficha_acceso_revocada @id NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT 1 AS revocada FROM dbo.fichas_acceso WHERE id = @id AND tipo_ficha = N'Bearer' AND revocada = 1;
END
GO

--| SENTINEL: RBAC |
CREATE OR ALTER PROCEDURE sentinel.roles_y_permisos @id_usuario NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT r.id, p.recurso, p.accion
    FROM dbo.usuarios_roles ur
    JOIN dbo.roles r ON r.id = ur.id_rol AND COALESCE(r.estado, N'activo') = N'activo'
    LEFT JOIN dbo.roles_permisos rp ON rp.id_rol = r.id
    LEFT JOIN dbo.permisos p ON p.id = rp.id_permiso
    WHERE ur.id_usuario = @id_usuario AND (ur.expira_en IS NULL OR ur.expira_en > GETUTCDATE());
END
GO

CREATE OR ALTER PROCEDURE sentinel.rol_empresa @id_rol NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_empresa FROM dbo.roles WHERE id = @id_rol AND COALESCE(estado, N'activo') = N'activo';
END
GO

CREATE OR ALTER PROCEDURE sentinel.permiso_existe @id_permiso NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT 1 AS existe FROM dbo.permisos WHERE id = @id_permiso;
END
GO

CREATE OR ALTER PROCEDURE sentinel.rol_asignar @id_usuario NVARCHAR(50), @id_rol NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.usuarios_roles (id_usuario, id_rol) SELECT @id_usuario, @id_rol
    WHERE NOT EXISTS (SELECT 1 FROM dbo.usuarios_roles WITH (UPDLOCK, HOLDLOCK) WHERE id_usuario = @id_usuario AND id_rol = @id_rol);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE sentinel.permiso_conceder @id_rol NVARCHAR(50), @id_permiso NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.roles_permisos (id_rol, id_permiso) SELECT @id_rol, @id_permiso
    WHERE NOT EXISTS (SELECT 1 FROM dbo.roles_permisos WITH (UPDLOCK, HOLDLOCK) WHERE id_rol = @id_rol AND id_permiso = @id_permiso);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

--| SENTINEL: bitácora de auditoría (sin procedimiento de borrado) |
CREATE OR ALTER PROCEDURE sentinel.auditoria_insertar
    @id_usuario NVARCHAR(50), @id_empresa NVARCHAR(50), @accion NVARCHAR(255), @recurso NVARCHAR(255), @resultado NVARCHAR(50),
    @detalles NVARCHAR(MAX), @fecha DATETIME, @direccion_ip NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.bitacora_auditoria (id_usuario, id_empresa, accion, recurso, resultado, detalles, fecha_auditoria, direccion_ip)
    VALUES (@id_usuario, @id_empresa, @accion, @recurso, @resultado, @detalles, @fecha, @direccion_ip);
END
GO

CREATE OR ALTER PROCEDURE sentinel.auditoria_fallos_acceso
    @recurso NVARCHAR(255), @resultado_fallo NVARCHAR(50), @desde DATETIME, @accion_sesion NVARCHAR(255), @resultado_exito NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT fecha_auditoria FROM dbo.bitacora_auditoria
    WHERE recurso = @recurso AND resultado = @resultado_fallo AND fecha_auditoria > @desde
      AND id > COALESCE((SELECT MAX(id) FROM dbo.bitacora_auditoria
                         WHERE recurso = @recurso AND accion = @accion_sesion AND resultado = @resultado_exito), 0)
    ORDER BY fecha_auditoria;
END
GO

CREATE OR ALTER PROCEDURE sentinel.auditoria_listar
    @id_empresa NVARCHAR(50), @desde DATETIME = NULL, @hasta DATETIME = NULL, @accion NVARCHAR(255) = NULL,
    @id_usuario NVARCHAR(50) = NULL, @resultado NVARCHAR(50) = NULL, @limite INT, @desplazamiento INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT COUNT(*) AS total FROM dbo.bitacora_auditoria
    WHERE id_empresa = @id_empresa AND (@desde IS NULL OR fecha_auditoria >= @desde) AND (@hasta IS NULL OR fecha_auditoria <= @hasta)
      AND (@accion IS NULL OR accion = @accion) AND (@id_usuario IS NULL OR id_usuario = @id_usuario)
      AND (@resultado IS NULL OR resultado = @resultado)
    OPTION (RECOMPILE);
    SELECT id_empresa, accion, resultado, id_usuario, recurso, detalles, direccion_ip, fecha_auditoria FROM dbo.bitacora_auditoria
    WHERE id_empresa = @id_empresa AND (@desde IS NULL OR fecha_auditoria >= @desde) AND (@hasta IS NULL OR fecha_auditoria <= @hasta)
      AND (@accion IS NULL OR accion = @accion) AND (@id_usuario IS NULL OR id_usuario = @id_usuario)
      AND (@resultado IS NULL OR resultado = @resultado)
    ORDER BY fecha_auditoria DESC OFFSET @desplazamiento ROWS FETCH NEXT @limite ROWS ONLY
    OPTION (RECOMPILE);
END
GO

CREATE OR ALTER PROCEDURE sentinel.auditoria_resumen @id_empresa NVARCHAR(50), @desde DATETIME
AS
BEGIN
    SET NOCOUNT ON;
    SELECT accion, resultado, COUNT(*) AS total FROM dbo.bitacora_auditoria
    WHERE id_empresa = @id_empresa AND fecha_auditoria >= @desde
    GROUP BY accion, resultado ORDER BY accion, resultado;
END
GO

--| NEXUS: registro de aplicaciones |
CREATE OR ALTER PROCEDURE nexus.aplicacion_insertar
    @id_aplicacion NVARCHAR(30), @nombre NVARCHAR(100), @modelo_datos NVARCHAR(20), @propietario NVARCHAR(50), @seguridad_por_fila BIT,
    @descripcion NVARCHAR(500), @id_solicitud NVARCHAR(50), @estado NVARCHAR(20), @creado_por NVARCHAR(100),
    @fecha_creacion DATETIME2, @fecha_modificacion DATETIME2, @motor NVARCHAR(20), @conexion NVARCHAR(40)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.nexus_aplicaciones (id_aplicacion, nombre, modelo_datos, propietario, seguridad_por_fila, descripcion, id_solicitud,
                                        estado, creado_por, fecha_creacion, fecha_modificacion, motor, conexion)
    SELECT @id_aplicacion, @nombre, @modelo_datos, @propietario, @seguridad_por_fila, @descripcion, @id_solicitud,
           @estado, @creado_por, @fecha_creacion, @fecha_modificacion, @motor, @conexion
    WHERE NOT EXISTS (SELECT 1 FROM dbo.nexus_aplicaciones WITH (UPDLOCK, HOLDLOCK) WHERE id_aplicacion = @id_aplicacion);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE nexus.aplicacion_obtener @id_aplicacion NVARCHAR(30), @propietario NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_aplicacion, nombre, modelo_datos, propietario, seguridad_por_fila, descripcion, id_solicitud,
           estado, creado_por, fecha_creacion, fecha_modificacion, motor, conexion
    FROM dbo.nexus_aplicaciones WHERE id_aplicacion = @id_aplicacion AND propietario = @propietario;
END
GO

CREATE OR ALTER PROCEDURE nexus.aplicacion_listar @propietario NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_aplicacion, nombre, modelo_datos, propietario, seguridad_por_fila, descripcion, id_solicitud,
           estado, creado_por, fecha_creacion, fecha_modificacion, motor, conexion
    FROM dbo.nexus_aplicaciones WHERE propietario = @propietario ORDER BY id_aplicacion;
END
GO

CREATE OR ALTER PROCEDURE nexus.empresa_insertar
    @id_aplicacion NVARCHAR(30), @id_empresa NVARCHAR(30), @nombre NVARCHAR(200), @estado NVARCHAR(20), @fecha_registro DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.nexus_aplicacion_empresas (id_aplicacion, id_empresa, nombre, estado, fecha_registro)
    SELECT @id_aplicacion, @id_empresa, @nombre, @estado, @fecha_registro
    WHERE NOT EXISTS (SELECT 1 FROM dbo.nexus_aplicacion_empresas WITH (UPDLOCK, HOLDLOCK)
                      WHERE id_aplicacion = @id_aplicacion AND id_empresa = @id_empresa);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE nexus.empresa_listar @id_aplicacion NVARCHAR(30)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_aplicacion, id_empresa, nombre, estado, fecha_registro FROM dbo.nexus_aplicacion_empresas
    WHERE id_aplicacion = @id_aplicacion ORDER BY id_empresa;
END
GO

--| NEXUS: bases de datos registradas |
CREATE OR ALTER PROCEDURE nexus.base_datos_insertar
    @nombre_base NVARCHAR(128), @id_aplicacion NVARCHAR(30), @id_empresa NVARCHAR(30), @estado NVARCHAR(20), @version INT,
    @fecha_creacion DATETIME2, @fecha_despliegue DATETIME2, @ultimo_error NVARCHAR(1000)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.nexus_bases_datos (nombre_base, id_aplicacion, id_empresa, estado, version, fecha_creacion, fecha_despliegue, ultimo_error)
    SELECT @nombre_base, @id_aplicacion, @id_empresa, @estado, @version, @fecha_creacion, @fecha_despliegue, @ultimo_error
    WHERE NOT EXISTS (SELECT 1 FROM dbo.nexus_bases_datos WITH (UPDLOCK, HOLDLOCK) WHERE nombre_base = @nombre_base);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE nexus.base_datos_registrada @nombre_base NVARCHAR(128)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT 1 AS registrada FROM dbo.nexus_bases_datos WHERE nombre_base = @nombre_base;
END
GO

CREATE OR ALTER PROCEDURE nexus.base_datos_listar @id_aplicacion NVARCHAR(30)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT nombre_base, id_aplicacion, id_empresa, estado, version, fecha_creacion, fecha_despliegue, ultimo_error
    FROM dbo.nexus_bases_datos WHERE id_aplicacion = @id_aplicacion ORDER BY nombre_base;
END
GO

CREATE OR ALTER PROCEDURE nexus.base_datos_actualizar
    @nombre_base NVARCHAR(128), @estado NVARCHAR(20), @version INT, @ultimo_error NVARCHAR(1000), @ahora DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.nexus_bases_datos
    SET estado = @estado, version = COALESCE(@version, version), ultimo_error = @ultimo_error,
        fecha_despliegue = CASE WHEN @estado = N'desplegada' THEN @ahora ELSE fecha_despliegue END
    WHERE nombre_base = @nombre_base;
END
GO

--| NEXUS: migraciones y equivalentes por motor (inmutables) |
CREATE OR ALTER PROCEDURE nexus.migracion_insertar
    @id_aplicacion NVARCHAR(30), @numero INT, @nombre NVARCHAR(250), @tipo NVARCHAR(10), @descripcion NVARCHAR(500),
    @script NVARCHAR(MAX), @checksum CHAR(64), @creado_por NVARCHAR(100), @fecha_creacion DATETIME2, @definicion NVARCHAR(MAX),
    @motor NVARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.nexus_migraciones (id_aplicacion, numero, nombre, tipo, descripcion, script, checksum, creado_por, fecha_creacion,
                                       definicion, motor)
    VALUES (@id_aplicacion, @numero, @nombre, @tipo, @descripcion, @script, @checksum, @creado_por, @fecha_creacion, @definicion, @motor);
END
GO

CREATE OR ALTER PROCEDURE nexus.migracion_agregar
    @id_aplicacion NVARCHAR(30), @nombre NVARCHAR(250), @tipo NVARCHAR(10), @descripcion NVARCHAR(500), @script NVARCHAR(MAX),
    @checksum CHAR(64), @creado_por NVARCHAR(100), @fecha_creacion DATETIME2, @definicion NVARCHAR(MAX), @motor NVARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @numero INT, @duplicadas INT;
    SELECT @numero = ISNULL(MAX(numero), 0) + 1, @duplicadas = SUM(CASE WHEN nombre = @nombre THEN 1 ELSE 0 END)
    FROM dbo.nexus_migraciones WITH (UPDLOCK, HOLDLOCK) WHERE id_aplicacion = @id_aplicacion;
    IF @duplicadas > 0
    BEGIN
        SELECT CAST(NULL AS INT) AS numero;
        RETURN;
    END
    INSERT INTO dbo.nexus_migraciones (id_aplicacion, numero, nombre, tipo, descripcion, script, checksum, creado_por, fecha_creacion,
                                       definicion, motor)
    VALUES (@id_aplicacion, @numero, @nombre, @tipo, @descripcion, @script, @checksum, @creado_por, @fecha_creacion, @definicion, @motor);
    SELECT @numero AS numero;
END
GO

CREATE OR ALTER PROCEDURE nexus.migracion_listar @id_aplicacion NVARCHAR(30), @con_script BIT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_aplicacion, nombre, tipo, CASE WHEN @con_script = 1 THEN script ELSE N'' END AS script, checksum, numero, descripcion,
           creado_por, fecha_creacion, definicion, motor
    FROM dbo.nexus_migraciones WHERE id_aplicacion = @id_aplicacion ORDER BY numero;
    SELECT numero, motor, CASE WHEN @con_script = 1 THEN script ELSE N'' END AS script
    FROM dbo.nexus_migracion_equivalentes WHERE id_aplicacion = @id_aplicacion;
END
GO

CREATE OR ALTER PROCEDURE nexus.equivalente_insertar
    @id_aplicacion NVARCHAR(30), @numero INT, @motor NVARCHAR(20), @script NVARCHAR(MAX), @checksum CHAR(64), @creado_por NVARCHAR(100),
    @fecha_creacion DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.nexus_migracion_equivalentes (id_aplicacion, numero, motor, script, checksum, creado_por, fecha_creacion)
    SELECT @id_aplicacion, @numero, @motor, @script, @checksum, @creado_por, @fecha_creacion
    WHERE NOT EXISTS (SELECT 1 FROM dbo.nexus_migracion_equivalentes WITH (UPDLOCK, HOLDLOCK)
                      WHERE id_aplicacion = @id_aplicacion AND numero = @numero AND motor = @motor);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

--| NEXUS: despliegues (historial, sin borrado) |
CREATE OR ALTER PROCEDURE nexus.despliegue_insertar
    @id_despliegue NVARCHAR(50), @id_aplicacion NVARCHAR(30), @nombre_base NVARCHAR(128), @estado NVARCHAR(20), @id_empresa NVARCHAR(30),
    @migraciones_aplicadas NVARCHAR(MAX), @version_resultante INT, @detalle NVARCHAR(1000), @ejecutado_por NVARCHAR(100),
    @fecha_inicio DATETIME2, @fecha_fin DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.nexus_despliegues (id_despliegue, id_aplicacion, nombre_base, estado, id_empresa, migraciones_aplicadas,
                                       version_resultante, detalle, ejecutado_por, fecha_inicio, fecha_fin)
    VALUES (@id_despliegue, @id_aplicacion, @nombre_base, @estado, @id_empresa, @migraciones_aplicadas,
            @version_resultante, @detalle, @ejecutado_por, @fecha_inicio, @fecha_fin);
END
GO

CREATE OR ALTER PROCEDURE nexus.despliegue_listar @id_aplicacion NVARCHAR(30), @limite INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@limite) id_despliegue, id_aplicacion, nombre_base, estado, id_empresa, migraciones_aplicadas,
           version_resultante, detalle, ejecutado_por, fecha_inicio, fecha_fin
    FROM dbo.nexus_despliegues WHERE id_aplicacion = @id_aplicacion ORDER BY fecha_inicio DESC;
END
GO

--| NEXUS: cambios de motor |
CREATE OR ALTER PROCEDURE nexus.cambio_motor_iniciar
    @id_cambio NVARCHAR(50), @id_aplicacion NVARCHAR(30), @motor_origen NVARCHAR(20), @conexion_origen NVARCHAR(40),
    @motor_destino NVARCHAR(20), @conexion_destino NVARCHAR(40), @version_origen INT, @bases_origen NVARCHAR(MAX), @estado NVARCHAR(30),
    @detalle NVARCHAR(MAX), @solicitado_por NVARCHAR(100), @fecha_inicio DATETIME2, @fecha_fin DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.nexus_cambios_motor (id_cambio, id_aplicacion, motor_origen, conexion_origen, motor_destino, conexion_destino,
                                         version_origen, bases_origen, estado, detalle, solicitado_por, fecha_inicio, fecha_fin)
    SELECT @id_cambio, @id_aplicacion, @motor_origen, @conexion_origen, @motor_destino, @conexion_destino,
           @version_origen, @bases_origen, @estado, @detalle, @solicitado_por, @fecha_inicio, @fecha_fin
    WHERE NOT EXISTS (SELECT 1 FROM dbo.nexus_cambios_motor WITH (UPDLOCK, HOLDLOCK)
                      WHERE id_aplicacion = @id_aplicacion AND estado NOT IN (N'completado', N'revertido'));
    DECLARE @afectadas INT = @@ROWCOUNT;
    IF @afectadas = 1
    BEGIN
        UPDATE dbo.nexus_aplicaciones SET motor = @motor_destino, conexion = @conexion_destino, fecha_modificacion = @fecha_inicio
        WHERE id_aplicacion = @id_aplicacion;
        UPDATE dbo.nexus_bases_datos SET estado = N'pendiente', version = 0, ultimo_error = NULL WHERE id_aplicacion = @id_aplicacion;
    END
    SELECT @afectadas AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE nexus.cambio_motor_actualizar
    @id_cambio NVARCHAR(50), @estado NVARCHAR(30), @detalle NVARCHAR(MAX), @fecha_fin DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.nexus_cambios_motor SET estado = @estado, detalle = @detalle, fecha_fin = @fecha_fin WHERE id_cambio = @id_cambio;
END
GO

CREATE OR ALTER PROCEDURE nexus.cambio_motor_revertir
    @id_cambio NVARCHAR(50), @id_aplicacion NVARCHAR(30), @motor_origen NVARCHAR(20), @conexion_origen NVARCHAR(40),
    @bases_origen NVARCHAR(MAX), @ahora DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.nexus_cambios_motor SET estado = N'revertido', fecha_fin = @ahora
    WHERE id_cambio = @id_cambio AND estado NOT IN (N'completado', N'revertido');
    DECLARE @afectadas INT = @@ROWCOUNT;
    IF @afectadas = 1
    BEGIN
        UPDATE dbo.nexus_aplicaciones SET motor = @motor_origen, conexion = @conexion_origen, fecha_modificacion = @ahora
        WHERE id_aplicacion = @id_aplicacion;
        UPDATE b
        SET estado = COALESCE(JSON_VALUE(o.value, N'$.estado'), N'pendiente'),
            version = COALESCE(TRY_CAST(JSON_VALUE(o.value, N'$.version') AS INT), 0),
            ultimo_error = JSON_VALUE(o.value, N'$.ultimo_error')
        FROM dbo.nexus_bases_datos b
        LEFT JOIN OPENJSON(COALESCE(@bases_origen, N'{}')) o ON o.[key] COLLATE DATABASE_DEFAULT = b.nombre_base
        WHERE b.id_aplicacion = @id_aplicacion;
    END
    SELECT @afectadas AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE nexus.cambio_motor_listar @id_aplicacion NVARCHAR(30), @limite INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@limite) id_cambio, id_aplicacion, motor_origen, conexion_origen, motor_destino, conexion_destino, version_origen,
           bases_origen, estado, detalle, solicitado_por, fecha_inicio, fecha_fin
    FROM dbo.nexus_cambios_motor WHERE id_aplicacion = @id_aplicacion ORDER BY fecha_inicio DESC;
END
GO

--| MATRIX: reglas de negocio (condiciones y acciones en cascada) |
CREATE OR ALTER PROCEDURE matrix.regla_listar
    @id_regla VARCHAR(100) = NULL, @nivel_alcance VARCHAR(20) = NULL, @id_empresa INT = NULL, @linea_negocio VARCHAR(50) = NULL,
    @estado VARCHAR(20) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @reglas TABLE (id_regla VARCHAR(100) PRIMARY KEY);
    INSERT INTO @reglas (id_regla)
    SELECT id_regla FROM dbo.reglas_negocio
    WHERE (@id_regla IS NULL OR id_regla = @id_regla) AND (@nivel_alcance IS NULL OR nivel_alcance = @nivel_alcance)
      AND (@id_empresa IS NULL OR id_empresa = @id_empresa) AND (@linea_negocio IS NULL OR linea_negocio = @linea_negocio)
      AND (@estado IS NULL OR COALESCE(estado, 'activa') = @estado)
    OPTION (RECOMPILE);
    SELECT r.id_regla, r.nombre, r.descripcion, r.nivel_alcance, r.linea_negocio, r.id_empresa, r.estado, r.prioridad,
           r.fecha_creacion, r.modificada_por
    FROM dbo.reglas_negocio r JOIN @reglas f ON f.id_regla = r.id_regla
    ORDER BY COALESCE(r.prioridad, 0) DESC, r.id_regla;
    SELECT c.id_regla, c.campo, c.operador, c.valor, c.operador_logico
    FROM dbo.condiciones_regla c JOIN @reglas f ON f.id_regla = c.id_regla
    ORDER BY c.id_regla, c.orden, c.id_condicion;
    SELECT a.id_regla, a.tipo_accion, a.detalles, a.es_critica
    FROM dbo.acciones_regla a JOIN @reglas f ON f.id_regla = a.id_regla
    ORDER BY a.id_regla, a.orden, a.id_accion;
END
GO

CREATE OR ALTER PROCEDURE matrix.regla_insertar
    @id_regla VARCHAR(100), @nombre NVARCHAR(255), @descripcion NVARCHAR(MAX), @nivel_alcance VARCHAR(20), @linea_negocio VARCHAR(50),
    @id_empresa INT, @estado VARCHAR(20), @prioridad INT, @ahora DATETIME, @actor NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.reglas_negocio (id_regla, nombre, descripcion, nivel_alcance, linea_negocio, id_empresa, estado, prioridad,
                                    fecha_creacion, fecha_modificacion, modificada_por)
    SELECT @id_regla, @nombre, @descripcion, @nivel_alcance, @linea_negocio, @id_empresa, @estado, @prioridad, @ahora, @ahora, @actor
    WHERE NOT EXISTS (SELECT 1 FROM dbo.reglas_negocio WITH (UPDLOCK, HOLDLOCK) WHERE id_regla = @id_regla);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE matrix.regla_actualizar
    @id_regla VARCHAR(100), @nombre NVARCHAR(255), @descripcion NVARCHAR(MAX), @nivel_alcance VARCHAR(20), @linea_negocio VARCHAR(50),
    @id_empresa INT, @estado VARCHAR(20), @prioridad INT, @ahora DATETIME, @actor NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.reglas_negocio
    SET nombre = @nombre, descripcion = @descripcion, nivel_alcance = @nivel_alcance, linea_negocio = @linea_negocio,
        id_empresa = @id_empresa, estado = @estado, prioridad = @prioridad, fecha_modificacion = @ahora, modificada_por = @actor
    WHERE id_regla = @id_regla;
    DECLARE @afectadas INT = @@ROWCOUNT;
    IF @afectadas = 1
    BEGIN
        DELETE FROM dbo.condiciones_regla WHERE id_regla = @id_regla;
        DELETE FROM dbo.acciones_regla WHERE id_regla = @id_regla;
    END
    SELECT @afectadas AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE matrix.condicion_insertar
    @id_regla VARCHAR(100), @campo NVARCHAR(100), @operador VARCHAR(20), @valor NVARCHAR(MAX), @orden INT, @operador_logico VARCHAR(5)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.condiciones_regla (id_regla, campo, operador, valor, orden, operador_logico)
    VALUES (@id_regla, @campo, @operador, @valor, @orden, @operador_logico);
END
GO

CREATE OR ALTER PROCEDURE matrix.accion_insertar
    @id_regla VARCHAR(100), @tipo_accion VARCHAR(50), @detalles NVARCHAR(MAX), @orden INT, @es_critica BIT
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.acciones_regla (id_regla, tipo_accion, detalles, orden, es_critica)
    VALUES (@id_regla, @tipo_accion, @detalles, @orden, @es_critica);
END
GO

CREATE OR ALTER PROCEDURE matrix.regla_cambiar_estado @id_regla VARCHAR(100), @estado VARCHAR(20), @ahora DATETIME, @actor NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.reglas_negocio SET estado = @estado, fecha_modificacion = @ahora, modificada_por = @actor WHERE id_regla = @id_regla;
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE matrix.evaluacion_insertar
    @id_regla VARCHAR(100), @nivel_alcance VARCHAR(20), @linea_negocio VARCHAR(50), @id_empresa INT, @condiciones_cumplidas BIT,
    @decision NVARCHAR(20), @valores_calculados NVARCHAR(MAX), @fecha DATETIME, @evaluada_por NVARCHAR(100),
    @tiempo_ejecucion_ms DECIMAL(10, 2)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.auditoria_evaluacion_reglas (id_regla, nivel_alcance, linea_negocio, id_empresa, condiciones_cumplidas, decision,
                                                 valores_calculados, fecha_evaluacion, evaluada_por, tiempo_ejecucion_ms)
    VALUES (@id_regla, @nivel_alcance, @linea_negocio, @id_empresa, @condiciones_cumplidas, @decision,
            @valores_calculados, @fecha, @evaluada_por, @tiempo_ejecucion_ms);
END
GO

CREATE OR ALTER PROCEDURE matrix.evaluacion_listar @id_regla VARCHAR(100) = NULL, @desde DATETIME, @limite INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@limite) id_auditoria, id_regla, nivel_alcance, linea_negocio, id_empresa, condiciones_cumplidas, decision,
           valores_calculados, evaluada_por, tiempo_ejecucion_ms, fecha_evaluacion
    FROM dbo.auditoria_evaluacion_reglas
    WHERE fecha_evaluacion >= @desde AND (@id_regla IS NULL OR id_regla = @id_regla)
    ORDER BY id_auditoria DESC
    OPTION (RECOMPILE);
END
GO

--| SYNAPSE: integraciones y llamadas |
CREATE OR ALTER PROCEDURE synapse.integracion_insertar
    @id_integracion NVARCHAR(40), @id_empresa NVARCHAR(50), @nombre NVARCHAR(60), @descripcion NVARCHAR(500), @url_base NVARCHAR(500),
    @tipo_auth NVARCHAR(10), @auth_meta NVARCHAR(500), @credencial_cifrada NVARCHAR(MAX), @encabezados NVARCHAR(MAX),
    @timeout_s DECIMAL(5, 2), @reintentos TINYINT, @limite_por_minuto SMALLINT, @estado NVARCHAR(10), @especificacion NVARCHAR(MAX),
    @version INT, @creado_por NVARCHAR(200), @fecha_creacion DATETIME2, @fecha_modificacion DATETIME2,
    @ultimo_estado_salud NVARCHAR(20), @ultima_verificacion DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.synapse_integraciones (id_integracion, id_empresa, nombre, descripcion, url_base, tipo_auth, auth_meta,
                                           credencial_cifrada, encabezados, timeout_s, reintentos, limite_por_minuto, estado,
                                           especificacion, version, creado_por, fecha_creacion, fecha_modificacion,
                                           ultimo_estado_salud, ultima_verificacion)
    SELECT @id_integracion, @id_empresa, @nombre, @descripcion, @url_base, @tipo_auth, @auth_meta,
           @credencial_cifrada, @encabezados, @timeout_s, @reintentos, @limite_por_minuto, @estado,
           @especificacion, @version, @creado_por, @fecha_creacion, @fecha_modificacion, @ultimo_estado_salud, @ultima_verificacion
    WHERE NOT EXISTS (SELECT 1 FROM dbo.synapse_integraciones WITH (UPDLOCK, HOLDLOCK) WHERE id_empresa = @id_empresa AND nombre = @nombre);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE synapse.integracion_obtener @id_integracion NVARCHAR(40), @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_integracion, id_empresa, nombre, descripcion, url_base, tipo_auth, auth_meta, credencial_cifrada, encabezados,
           timeout_s, reintentos, limite_por_minuto, estado, especificacion, version, creado_por, fecha_creacion,
           fecha_modificacion, ultimo_estado_salud, ultima_verificacion
    FROM dbo.synapse_integraciones WHERE id_integracion = @id_integracion AND id_empresa = @id_empresa;
END
GO

CREATE OR ALTER PROCEDURE synapse.integracion_listar @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_integracion, id_empresa, nombre, descripcion, url_base, tipo_auth, auth_meta, credencial_cifrada, encabezados,
           timeout_s, reintentos, limite_por_minuto, estado, especificacion, version, creado_por, fecha_creacion,
           fecha_modificacion, ultimo_estado_salud, ultima_verificacion
    FROM dbo.synapse_integraciones WHERE id_empresa = @id_empresa ORDER BY nombre;
END
GO

CREATE OR ALTER PROCEDURE synapse.integracion_contar @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT COUNT(*) AS total FROM dbo.synapse_integraciones WHERE id_empresa = @id_empresa;
END
GO

CREATE OR ALTER PROCEDURE synapse.integracion_actualizar
    @id_integracion NVARCHAR(40), @id_empresa NVARCHAR(50), @nombre NVARCHAR(60), @descripcion NVARCHAR(500), @url_base NVARCHAR(500),
    @tipo_auth NVARCHAR(10), @auth_meta NVARCHAR(500), @credencial_cifrada NVARCHAR(MAX), @encabezados NVARCHAR(MAX),
    @timeout_s DECIMAL(5, 2), @reintentos TINYINT, @limite_por_minuto SMALLINT, @estado NVARCHAR(10), @especificacion NVARCHAR(MAX),
    @fecha_modificacion DATETIME2, @version_esperada INT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.synapse_integraciones
    SET nombre = @nombre, descripcion = @descripcion, url_base = @url_base, tipo_auth = @tipo_auth, auth_meta = @auth_meta,
        credencial_cifrada = @credencial_cifrada, encabezados = @encabezados, timeout_s = @timeout_s, reintentos = @reintentos,
        limite_por_minuto = @limite_por_minuto, estado = @estado, especificacion = @especificacion, version = version + 1,
        fecha_modificacion = @fecha_modificacion
    WHERE id_integracion = @id_integracion AND id_empresa = @id_empresa AND version = @version_esperada
      AND NOT EXISTS (SELECT 1 FROM dbo.synapse_integraciones o
                      WHERE o.id_empresa = @id_empresa AND o.nombre = @nombre AND o.id_integracion <> @id_integracion);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE synapse.integracion_eliminar @id_integracion NVARCHAR(40), @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM dbo.synapse_integraciones WHERE id_integracion = @id_integracion AND id_empresa = @id_empresa;
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE synapse.integracion_salud @id_integracion NVARCHAR(40), @estado NVARCHAR(20), @fecha DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.synapse_integraciones SET ultimo_estado_salud = @estado, ultima_verificacion = @fecha WHERE id_integracion = @id_integracion;
END
GO

CREATE OR ALTER PROCEDURE synapse.llamada_insertar
    @id_llamada NVARCHAR(40), @id_integracion NVARCHAR(40), @id_empresa NVARCHAR(50), @metodo NVARCHAR(10), @ruta NVARCHAR(500),
    @id_operacion NVARCHAR(100), @codigo_http SMALLINT, @exito BIT, @duracion_ms DECIMAL(10, 2), @intentos TINYINT, @error NVARCHAR(500),
    @origen NVARCHAR(10), @usuario NVARCHAR(200), @fecha DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.synapse_llamadas (id_llamada, id_integracion, id_empresa, metodo, ruta, id_operacion, codigo_http, exito, duracion_ms,
                                      intentos, error, origen, usuario, fecha)
    VALUES (@id_llamada, @id_integracion, @id_empresa, @metodo, @ruta, @id_operacion, @codigo_http, @exito, @duracion_ms,
            @intentos, @error, @origen, @usuario, @fecha);
END
GO

CREATE OR ALTER PROCEDURE synapse.llamada_listar
    @id_empresa NVARCHAR(50), @id_integracion NVARCHAR(40) = NULL, @desde DATETIME2 = NULL, @limite INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@limite) id_llamada, id_integracion, id_empresa, metodo, ruta, id_operacion, codigo_http, exito, duracion_ms, intentos,
           error, origen, usuario, fecha
    FROM dbo.synapse_llamadas
    WHERE id_empresa = @id_empresa AND (@id_integracion IS NULL OR id_integracion = @id_integracion) AND (@desde IS NULL OR fecha >= @desde)
    ORDER BY fecha DESC
    OPTION (RECOMPILE);
END
GO

--| GENESIS: agentes personalizados, invocaciones, generaciones y presupuesto |
CREATE OR ALTER PROCEDURE genesis.agente_insertar
    @id_agente NVARCHAR(40), @id_empresa NVARCHAR(50), @nombre NVARCHAR(60), @descripcion NVARCHAR(500), @prompt_sistema NVARCHAR(MAX),
    @proveedor NVARCHAR(10), @nivel NVARCHAR(10), @temperatura DECIMAL(3, 2), @max_tokens INT, @estado NVARCHAR(10), @version INT,
    @creado_por NVARCHAR(200), @fecha_creacion DATETIME2, @fecha_modificacion DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.genesis_agentes (id_agente, id_empresa, nombre, descripcion, prompt_sistema, proveedor, nivel, temperatura, max_tokens,
                                     estado, version, creado_por, fecha_creacion, fecha_modificacion)
    SELECT @id_agente, @id_empresa, @nombre, @descripcion, @prompt_sistema, @proveedor, @nivel, @temperatura, @max_tokens,
           @estado, @version, @creado_por, @fecha_creacion, @fecha_modificacion
    WHERE NOT EXISTS (SELECT 1 FROM dbo.genesis_agentes WITH (UPDLOCK, HOLDLOCK) WHERE id_empresa = @id_empresa AND nombre = @nombre);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE genesis.agente_obtener @id_agente NVARCHAR(40), @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_agente, id_empresa, nombre, descripcion, prompt_sistema, proveedor, nivel, temperatura, max_tokens, estado, version,
           creado_por, fecha_creacion, fecha_modificacion
    FROM dbo.genesis_agentes WHERE id_agente = @id_agente AND id_empresa = @id_empresa;
END
GO

CREATE OR ALTER PROCEDURE genesis.agente_listar @id_empresa NVARCHAR(50), @incluir_archivados BIT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_agente, id_empresa, nombre, descripcion, prompt_sistema, proveedor, nivel, temperatura, max_tokens, estado, version,
           creado_por, fecha_creacion, fecha_modificacion
    FROM dbo.genesis_agentes WHERE id_empresa = @id_empresa AND (@incluir_archivados = 1 OR estado = N'activo')
    ORDER BY nombre;
END
GO

CREATE OR ALTER PROCEDURE genesis.agente_actualizar
    @id_agente NVARCHAR(40), @id_empresa NVARCHAR(50), @nombre NVARCHAR(60), @descripcion NVARCHAR(500), @prompt_sistema NVARCHAR(MAX),
    @proveedor NVARCHAR(10), @nivel NVARCHAR(10), @temperatura DECIMAL(3, 2), @max_tokens INT, @estado NVARCHAR(10),
    @fecha_modificacion DATETIME2, @version_esperada INT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.genesis_agentes
    SET nombre = @nombre, descripcion = @descripcion, prompt_sistema = @prompt_sistema, proveedor = @proveedor, nivel = @nivel,
        temperatura = @temperatura, max_tokens = @max_tokens, estado = @estado, version = version + 1, fecha_modificacion = @fecha_modificacion
    WHERE id_agente = @id_agente AND id_empresa = @id_empresa AND version = @version_esperada
      AND NOT EXISTS (SELECT 1 FROM dbo.genesis_agentes o WHERE o.id_empresa = @id_empresa AND o.nombre = @nombre AND o.id_agente <> @id_agente);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE genesis.invocacion_insertar
    @id_invocacion NVARCHAR(40), @id_empresa NVARCHAR(50), @id_agente NVARCHAR(40), @tipo NVARCHAR(12), @proveedor NVARCHAR(10),
    @modelo NVARCHAR(100), @nivel NVARCHAR(10), @tokens_entrada INT, @tokens_salida INT, @costo_usd DECIMAL(12, 6),
    @duracion_ms DECIMAL(10, 2), @estado NVARCHAR(10), @error NVARCHAR(1000), @usuario NVARCHAR(200), @fecha DATETIME2,
    @prompt NVARCHAR(MAX), @respuesta NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.genesis_invocaciones (id_invocacion, id_empresa, id_agente, tipo, proveedor, modelo, nivel, tokens_entrada,
                                          tokens_salida, costo_usd, duracion_ms, estado, error, usuario, fecha, prompt, respuesta)
    VALUES (@id_invocacion, @id_empresa, @id_agente, @tipo, @proveedor, @modelo, @nivel, @tokens_entrada,
            @tokens_salida, @costo_usd, @duracion_ms, @estado, @error, @usuario, @fecha, @prompt, @respuesta);
END
GO

CREATE OR ALTER PROCEDURE genesis.invocacion_listar @id_empresa NVARCHAR(50), @id_agente NVARCHAR(40) = NULL, @limite INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@limite) id_invocacion, id_empresa, id_agente, tipo, proveedor, modelo, nivel, tokens_entrada, tokens_salida, costo_usd,
           duracion_ms, estado, error, usuario, fecha, prompt, respuesta
    FROM dbo.genesis_invocaciones WHERE id_empresa = @id_empresa AND (@id_agente IS NULL OR id_agente = @id_agente)
    ORDER BY fecha DESC
    OPTION (RECOMPILE);
END
GO

CREATE OR ALTER PROCEDURE genesis.consumo @id_empresa NVARCHAR(50), @desde DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    SELECT proveedor, modelo, estado, COUNT(*) AS invocaciones, SUM(tokens_entrada) AS tokens_entrada, SUM(tokens_salida) AS tokens_salida,
           SUM(COALESCE(costo_usd, 0)) AS costo_usd
    FROM dbo.genesis_invocaciones WHERE id_empresa = @id_empresa AND fecha >= @desde
    GROUP BY proveedor, modelo, estado;
END
GO

CREATE OR ALTER PROCEDURE genesis.generacion_insertar
    @id_generacion NVARCHAR(40), @id_empresa NVARCHAR(50), @id_invocacion NVARCHAR(40), @tipo NVARCHAR(10), @lenguaje NVARCHAR(12),
    @descripcion NVARCHAR(2000), @ruta_sugerida NVARCHAR(200), @contenido NVARCHAR(MAX), @analisis NVARCHAR(MAX),
    @puntuacion DECIMAL(4, 2), @criticos INT, @estado NVARCHAR(12), @rama NVARCHAR(100), @commit_git CHAR(40), @usuario NVARCHAR(200),
    @fecha DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.genesis_generaciones (id_generacion, id_empresa, id_invocacion, tipo, lenguaje, descripcion, ruta_sugerida, contenido,
                                          analisis, puntuacion, criticos, estado, rama, commit_git, usuario, fecha)
    VALUES (@id_generacion, @id_empresa, @id_invocacion, @tipo, @lenguaje, @descripcion, @ruta_sugerida, @contenido,
            @analisis, @puntuacion, @criticos, @estado, @rama, @commit_git, @usuario, @fecha);
END
GO

CREATE OR ALTER PROCEDURE genesis.generacion_obtener @id_generacion NVARCHAR(40), @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_generacion, id_empresa, id_invocacion, tipo, lenguaje, descripcion, ruta_sugerida, contenido, analisis,
           puntuacion, criticos, estado, rama, commit_git, usuario, fecha
    FROM dbo.genesis_generaciones WHERE id_generacion = @id_generacion AND id_empresa = @id_empresa;
END
GO

CREATE OR ALTER PROCEDURE genesis.generacion_listar @id_empresa NVARCHAR(50), @limite INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@limite) id_generacion, id_empresa, id_invocacion, tipo, lenguaje, descripcion, ruta_sugerida, contenido, analisis,
           puntuacion, criticos, estado, rama, commit_git, usuario, fecha
    FROM dbo.genesis_generaciones WHERE id_empresa = @id_empresa ORDER BY fecha DESC;
END
GO

CREATE OR ALTER PROCEDURE genesis.generacion_marcar_commit
    @id_generacion NVARCHAR(40), @id_empresa NVARCHAR(50), @rama NVARCHAR(100), @commit_git CHAR(40)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.genesis_generaciones SET estado = N'commiteada', rama = @rama, commit_git = @commit_git
    WHERE id_generacion = @id_generacion AND id_empresa = @id_empresa AND estado = N'generada';
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE genesis.presupuesto_obtener @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT tokens_mensuales FROM dbo.genesis_presupuestos WHERE id_empresa = @id_empresa;
END
GO

CREATE OR ALTER PROCEDURE genesis.presupuesto_fijar @id_empresa NVARCHAR(50), @tokens BIGINT, @actor NVARCHAR(200), @ahora DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.genesis_presupuestos WITH (UPDLOCK, HOLDLOCK)
    SET tokens_mensuales = @tokens, actualizado_por = @actor, fecha_modificacion = @ahora
    WHERE id_empresa = @id_empresa;
    IF @@ROWCOUNT = 0
        INSERT INTO dbo.genesis_presupuestos (id_empresa, tokens_mensuales, actualizado_por, fecha_modificacion)
        VALUES (@id_empresa, @tokens, @actor, @ahora);
END
GO

--| INSIGHT: reportes guardados y programaciones |
CREATE OR ALTER PROCEDURE insight.reporte_insertar
    @id_reporte NVARCHAR(40), @id_empresa NVARCHAR(50), @tipo NVARCHAR(50), @nombre NVARCHAR(200), @parametros NVARCHAR(MAX), @filas INT,
    @origen NVARCHAR(20), @generado_por NVARCHAR(200), @fecha DATETIME2, @id_programacion NVARCHAR(40), @resultado NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.insight_reportes (id_reporte, id_empresa, tipo, nombre, parametros, filas, origen, generado_por, fecha, id_programacion,
                                      resultado)
    VALUES (@id_reporte, @id_empresa, @tipo, @nombre, @parametros, @filas, @origen, @generado_por, @fecha, @id_programacion, @resultado);
END
GO

CREATE OR ALTER PROCEDURE insight.reporte_obtener @id_reporte NVARCHAR(40), @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_reporte, id_empresa, tipo, nombre, parametros, filas, origen, generado_por, fecha, id_programacion, resultado
    FROM dbo.insight_reportes WHERE id_reporte = @id_reporte AND id_empresa = @id_empresa;
END
GO

CREATE OR ALTER PROCEDURE insight.reporte_listar @id_empresa NVARCHAR(50), @tipo NVARCHAR(50) = NULL, @limite INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@limite) id_reporte, id_empresa, tipo, nombre, parametros, filas, origen, generado_por, fecha, id_programacion
    FROM dbo.insight_reportes WHERE id_empresa = @id_empresa AND (@tipo IS NULL OR tipo = @tipo)
    ORDER BY fecha DESC
    OPTION (RECOMPILE);
END
GO

CREATE OR ALTER PROCEDURE insight.reporte_eliminar @id_reporte NVARCHAR(40), @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM dbo.insight_reportes WHERE id_reporte = @id_reporte AND id_empresa = @id_empresa;
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE insight.reporte_purgar @antes DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM dbo.insight_reportes WHERE fecha < @antes;
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE insight.programacion_insertar
    @id_programacion NVARCHAR(40), @id_empresa NVARCHAR(50), @nombre NVARCHAR(200), @tipo NVARCHAR(50), @parametros NVARCHAR(MAX),
    @frecuencia NVARCHAR(10), @hora_utc TINYINT, @activa BIT, @proxima_ejecucion DATETIME2, @id_usuario NVARCHAR(50),
    @nombre_usuario NVARCHAR(200), @fecha_creacion DATETIME2, @ultima_ejecucion DATETIME2, @ultimo_estado NVARCHAR(10),
    @ultimo_error NVARCHAR(1000)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.insight_programaciones (id_programacion, id_empresa, nombre, tipo, parametros, frecuencia, hora_utc, activa,
                                            proxima_ejecucion, id_usuario, nombre_usuario, fecha_creacion, ultima_ejecucion,
                                            ultimo_estado, ultimo_error)
    VALUES (@id_programacion, @id_empresa, @nombre, @tipo, @parametros, @frecuencia, @hora_utc, @activa,
            @proxima_ejecucion, @id_usuario, @nombre_usuario, @fecha_creacion, @ultima_ejecucion, @ultimo_estado, @ultimo_error);
END
GO

CREATE OR ALTER PROCEDURE insight.programacion_obtener @id_programacion NVARCHAR(40), @id_empresa NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_programacion, id_empresa, nombre, tipo, parametros, frecuencia, hora_utc, activa, proxima_ejecucion,
           id_usuario, nombre_usuario, fecha_creacion, ultima_ejecucion, ultimo_estado, ultimo_error
    FROM dbo.insight_programaciones
    WHERE id_programacion = @id_programacion AND (@id_empresa IS NULL OR id_empresa = @id_empresa);
END
GO

CREATE OR ALTER PROCEDURE insight.programacion_listar @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_programacion, id_empresa, nombre, tipo, parametros, frecuencia, hora_utc, activa, proxima_ejecucion,
           id_usuario, nombre_usuario, fecha_creacion, ultima_ejecucion, ultimo_estado, ultimo_error
    FROM dbo.insight_programaciones WHERE id_empresa = @id_empresa ORDER BY fecha_creacion;
END
GO

CREATE OR ALTER PROCEDURE insight.programacion_actualizar
    @id_programacion NVARCHAR(40), @id_empresa NVARCHAR(50), @nombre NVARCHAR(200), @parametros NVARCHAR(MAX), @frecuencia NVARCHAR(10),
    @hora_utc TINYINT, @activa BIT, @proxima_ejecucion DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.insight_programaciones
    SET nombre = @nombre, parametros = @parametros, frecuencia = @frecuencia, hora_utc = @hora_utc, activa = @activa,
        proxima_ejecucion = @proxima_ejecucion
    WHERE id_programacion = @id_programacion AND id_empresa = @id_empresa;
END
GO

CREATE OR ALTER PROCEDURE insight.programacion_eliminar @id_programacion NVARCHAR(40), @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM dbo.insight_programaciones WHERE id_programacion = @id_programacion AND id_empresa = @id_empresa;
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE insight.programacion_vencidas @ahora DATETIME2, @limite INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@limite) id_programacion, id_empresa, nombre, tipo, parametros, frecuencia, hora_utc, activa, proxima_ejecucion,
           id_usuario, nombre_usuario, fecha_creacion, ultima_ejecucion, ultimo_estado, ultimo_error
    FROM dbo.insight_programaciones WHERE activa = 1 AND proxima_ejecucion <= @ahora ORDER BY proxima_ejecucion;
END
GO

CREATE OR ALTER PROCEDURE insight.programacion_reclamar
    @id_programacion NVARCHAR(40), @proxima_esperada DATETIME2, @proxima_nueva DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.insight_programaciones SET proxima_ejecucion = @proxima_nueva
    WHERE id_programacion = @id_programacion AND proxima_ejecucion = @proxima_esperada AND activa = 1;
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE insight.programacion_registrar_ejecucion
    @id_programacion NVARCHAR(40), @fecha DATETIME2, @estado NVARCHAR(10), @error NVARCHAR(1000)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.insight_programaciones SET ultima_ejecucion = @fecha, ultimo_estado = @estado, ultimo_error = @error
    WHERE id_programacion = @id_programacion;
END
GO

--| AURORA: sistemas de diseño y componentes |
CREATE OR ALTER PROCEDURE aurora.sistema_insertar
    @id_sistema NVARCHAR(40), @nombre NVARCHAR(100), @id_empresa NVARCHAR(50), @nivel_wcag NVARCHAR(3), @tokens NVARCHAR(MAX),
    @version INT, @estado NVARCHAR(20), @creado_por NVARCHAR(200), @fecha_creacion DATETIME2, @fecha_modificacion DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.aurora_sistemas (id_sistema, nombre, id_empresa, nivel_wcag, tokens, version, estado, creado_por, fecha_creacion,
                                     fecha_modificacion)
    SELECT @id_sistema, @nombre, @id_empresa, @nivel_wcag, @tokens, @version, @estado, @creado_por, @fecha_creacion, @fecha_modificacion
    WHERE NOT EXISTS (SELECT 1 FROM dbo.aurora_sistemas WITH (UPDLOCK, HOLDLOCK) WHERE id_empresa = @id_empresa AND nombre = @nombre);
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE aurora.componente_insertar
    @id_sistema NVARCHAR(40), @nombre NVARCHAR(60), @tipo NVARCHAR(30), @especificacion NVARCHAR(MAX), @fecha_modificacion DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.aurora_componentes (id_sistema, nombre, tipo, especificacion, fecha_modificacion)
    VALUES (@id_sistema, @nombre, @tipo, @especificacion, @fecha_modificacion);
END
GO

CREATE OR ALTER PROCEDURE aurora.sistema_obtener @id_sistema NVARCHAR(40), @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_sistema, nombre, id_empresa, nivel_wcag, tokens, version, estado, creado_por, fecha_creacion, fecha_modificacion
    FROM dbo.aurora_sistemas WHERE id_sistema = @id_sistema AND id_empresa = @id_empresa;
    SELECT c.especificacion
    FROM dbo.aurora_componentes c JOIN dbo.aurora_sistemas s ON s.id_sistema = c.id_sistema
    WHERE c.id_sistema = @id_sistema AND s.id_empresa = @id_empresa
    ORDER BY c.nombre;
END
GO

CREATE OR ALTER PROCEDURE aurora.sistema_listar @id_empresa NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT s.id_sistema, s.nombre, s.id_empresa, s.nivel_wcag, s.tokens, s.version, s.estado, s.creado_por, s.fecha_creacion,
           s.fecha_modificacion, (SELECT COUNT(*) FROM dbo.aurora_componentes c WHERE c.id_sistema = s.id_sistema) AS componentes
    FROM dbo.aurora_sistemas s WHERE s.id_empresa = @id_empresa ORDER BY s.fecha_modificacion DESC;
END
GO

CREATE OR ALTER PROCEDURE aurora.sistema_actualizar_tokens
    @id_sistema NVARCHAR(40), @id_empresa NVARCHAR(50), @tokens NVARCHAR(MAX), @nivel_wcag NVARCHAR(3), @ahora DATETIME2,
    @version_esperada INT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.aurora_sistemas SET tokens = @tokens, version = version + 1, nivel_wcag = @nivel_wcag, fecha_modificacion = @ahora
    WHERE id_sistema = @id_sistema AND id_empresa = @id_empresa AND version = @version_esperada;
    SELECT @@ROWCOUNT AS afectadas;
END
GO

CREATE OR ALTER PROCEDURE aurora.componente_guardar
    @id_sistema NVARCHAR(40), @nombre NVARCHAR(60), @tipo NVARCHAR(30), @especificacion NVARCHAR(MAX), @ahora DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.aurora_componentes WITH (UPDLOCK, HOLDLOCK) SET tipo = @tipo, especificacion = @especificacion, fecha_modificacion = @ahora
    WHERE id_sistema = @id_sistema AND nombre = @nombre;
    DECLARE @creado BIT = CASE WHEN @@ROWCOUNT = 0 THEN 1 ELSE 0 END;
    IF @creado = 1
        INSERT INTO dbo.aurora_componentes (id_sistema, nombre, tipo, especificacion, fecha_modificacion)
        VALUES (@id_sistema, @nombre, @tipo, @especificacion, @ahora);
    UPDATE dbo.aurora_sistemas SET fecha_modificacion = @ahora WHERE id_sistema = @id_sistema;
    SELECT @creado AS creado;
END
GO

CREATE OR ALTER PROCEDURE aurora.componente_eliminar @id_sistema NVARCHAR(40), @nombre NVARCHAR(60)
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM dbo.aurora_componentes WHERE id_sistema = @id_sistema AND nombre = @nombre;
    SELECT @@ROWCOUNT AS afectadas;
END
GO

--| PRISM: ejecuciones de pruebas |
CREATE OR ALTER PROCEDURE prism.ejecucion_insertar
    @id_ejecucion NVARCHAR(40), @objetivos NVARCHAR(MAX), @filtro NVARCHAR(200), @con_cobertura BIT, @suite_completa BIT,
    @estado NVARCHAR(20), @commit_git CHAR(40), @arbol_limpio BIT, @iniciada_por NVARCHAR(200), @fecha_inicio DATETIME2, @total INT,
    @pasadas INT, @fallidas INT, @omitidas INT, @errores INT, @cobertura DECIMAL(5, 2), @duracion_s DECIMAL(9, 2), @fecha_fin DATETIME2,
    @detalle NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.prism_ejecuciones (id_ejecucion, objetivos, filtro, con_cobertura, suite_completa, estado, commit_git, arbol_limpio,
                                       iniciada_por, fecha_inicio, total, pasadas, fallidas, omitidas, errores, cobertura, duracion_s,
                                       fecha_fin, detalle)
    VALUES (@id_ejecucion, @objetivos, @filtro, @con_cobertura, @suite_completa, @estado, @commit_git, @arbol_limpio,
            @iniciada_por, @fecha_inicio, @total, @pasadas, @fallidas, @omitidas, @errores, @cobertura, @duracion_s, @fecha_fin, @detalle);
END
GO

CREATE OR ALTER PROCEDURE prism.ejecucion_actualizar
    @id_ejecucion NVARCHAR(40), @estado NVARCHAR(20), @total INT, @pasadas INT, @fallidas INT, @omitidas INT, @errores INT,
    @cobertura DECIMAL(5, 2), @duracion_s DECIMAL(9, 2), @fecha_fin DATETIME2, @detalle NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.prism_ejecuciones
    SET estado = @estado, total = @total, pasadas = @pasadas, fallidas = @fallidas, omitidas = @omitidas, errores = @errores,
        cobertura = @cobertura, duracion_s = @duracion_s, fecha_fin = @fecha_fin, detalle = @detalle
    WHERE id_ejecucion = @id_ejecucion;
END
GO

CREATE OR ALTER PROCEDURE prism.ejecucion_obtener @id_ejecucion NVARCHAR(40)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_ejecucion, objetivos, filtro, con_cobertura, suite_completa, estado, commit_git, arbol_limpio, iniciada_por, fecha_inicio,
           total, pasadas, fallidas, omitidas, errores, cobertura, duracion_s, fecha_fin, detalle
    FROM dbo.prism_ejecuciones WHERE id_ejecucion = @id_ejecucion;
END
GO

CREATE OR ALTER PROCEDURE prism.ejecucion_listar @estado NVARCHAR(20) = NULL, @limite INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@limite) id_ejecucion, objetivos, filtro, con_cobertura, suite_completa, estado, commit_git, arbol_limpio, iniciada_por,
           fecha_inicio, total, pasadas, fallidas, omitidas, errores, cobertura, duracion_s, fecha_fin, detalle
    FROM dbo.prism_ejecuciones WHERE (@estado IS NULL OR estado = @estado)
    ORDER BY fecha_inicio DESC
    OPTION (RECOMPILE);
END
GO

CREATE OR ALTER PROCEDURE prism.ejecucion_completa_ultima @commit_git CHAR(40)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 id_ejecucion, objetivos, filtro, con_cobertura, suite_completa, estado, commit_git, arbol_limpio, iniciada_por,
           fecha_inicio, total, pasadas, fallidas, omitidas, errores, cobertura, duracion_s, fecha_fin, detalle
    FROM dbo.prism_ejecuciones
    WHERE commit_git = @commit_git AND suite_completa = 1 AND con_cobertura = 1 AND estado IN (N'aprobada', N'fallida', N'error')
    ORDER BY fecha_inicio DESC;
END
GO

CREATE OR ALTER PROCEDURE prism.ejecucion_abandonar @ahora DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.prism_ejecuciones
    SET estado = N'error', fecha_fin = @ahora,
        detalle = JSON_MODIFY(COALESCE(detalle, N'{}'), N'$.mensaje', N'Ejecución interrumpida por reinicio')
    WHERE estado IN (N'en_cola', N'ejecutando');
    SELECT @@ROWCOUNT AS afectadas;
END
GO

--| ORBIT: historial de despliegues (sin borrado) |
CREATE OR ALTER PROCEDURE orbit.despliegue_insertar
    @id_despliegue NVARCHAR(40), @entorno NVARCHAR(20), @tipo NVARCHAR(20), @commit_git CHAR(40), @estado NVARCHAR(20),
    @iniciado_por NVARCHAR(200), @fecha_inicio DATETIME2, @tag NVARCHAR(200), @tag_publicado BIT, @id_origen NVARCHAR(40),
    @notas NVARCHAR(500), @fecha_fin DATETIME2, @compuerta NVARCHAR(MAX), @workflow NVARCHAR(MAX), @bitacora NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.orbit_despliegues (id_despliegue, entorno, tipo, commit_git, estado, iniciado_por, fecha_inicio, tag, tag_publicado,
                                       id_origen, notas, fecha_fin, compuerta, workflow, bitacora)
    VALUES (@id_despliegue, @entorno, @tipo, @commit_git, @estado, @iniciado_por, @fecha_inicio, @tag, @tag_publicado,
            @id_origen, @notas, @fecha_fin, @compuerta, @workflow, @bitacora);
END
GO

CREATE OR ALTER PROCEDURE orbit.despliegue_obtener @id_despliegue NVARCHAR(40)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id_despliegue, entorno, tipo, commit_git, estado, iniciado_por, fecha_inicio, tag, tag_publicado, id_origen, notas, fecha_fin,
           compuerta, workflow, bitacora
    FROM dbo.orbit_despliegues WHERE id_despliegue = @id_despliegue;
END
GO

CREATE OR ALTER PROCEDURE orbit.despliegue_listar @entorno NVARCHAR(20) = NULL, @estado NVARCHAR(20) = NULL, @limite INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@limite) id_despliegue, entorno, tipo, commit_git, estado, iniciado_por, fecha_inicio, tag, tag_publicado, id_origen,
           notas, fecha_fin, compuerta, workflow, bitacora
    FROM dbo.orbit_despliegues WHERE (@entorno IS NULL OR entorno = @entorno) AND (@estado IS NULL OR estado = @estado)
    ORDER BY fecha_inicio DESC
    OPTION (RECOMPILE);
END
GO

CREATE OR ALTER PROCEDURE orbit.despliegue_exitoso_con @entorno NVARCHAR(20), @commit_git CHAR(40)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 1 AS exitoso FROM dbo.orbit_despliegues WHERE entorno = @entorno AND commit_git = @commit_git AND estado = N'exitoso';
END
GO

--| VECTOR: análisis de código |
CREATE OR ALTER PROCEDURE vector.analisis_insertar
    @id_analisis NVARCHAR(40), @objetivo NVARCHAR(500), @archivos INT, @lineas INT, @puntuacion DECIMAL(4, 2), @criticos INT, @altos INT,
    @resumen NVARCHAR(MAX), @analizado_por NVARCHAR(200), @fecha DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.vector_analisis (id_analisis, objetivo, archivos, lineas, puntuacion, criticos, altos, resumen, analizado_por, fecha)
    VALUES (@id_analisis, @objetivo, @archivos, @lineas, @puntuacion, @criticos, @altos, @resumen, @analizado_por, @fecha);
END
GO

CREATE OR ALTER PROCEDURE vector.analisis_listar @limite INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@limite) id_analisis, objetivo, archivos, lineas, puntuacion, criticos, altos, analizado_por, fecha, resumen
    FROM dbo.vector_analisis ORDER BY fecha DESC;
END
GO

--| ROL DE LA APLICACIÓN: solo EXECUTE sobre los esquemas de procedimientos |
IF DATABASE_PRINCIPAL_ID(N'kinetix_app_rol') IS NULL CREATE ROLE kinetix_app_rol AUTHORIZATION dbo;
GO
GRANT EXECUTE ON SCHEMA::sentinel TO kinetix_app_rol;
GRANT EXECUTE ON SCHEMA::nexus TO kinetix_app_rol;
GRANT EXECUTE ON SCHEMA::matrix TO kinetix_app_rol;
GRANT EXECUTE ON SCHEMA::synapse TO kinetix_app_rol;
GRANT EXECUTE ON SCHEMA::genesis TO kinetix_app_rol;
GRANT EXECUTE ON SCHEMA::insight TO kinetix_app_rol;
GRANT EXECUTE ON SCHEMA::aurora TO kinetix_app_rol;
GRANT EXECUTE ON SCHEMA::prism TO kinetix_app_rol;
GRANT EXECUTE ON SCHEMA::orbit TO kinetix_app_rol;
GRANT EXECUTE ON SCHEMA::vector TO kinetix_app_rol;
REVOKE SELECT, INSERT, UPDATE, DELETE, EXECUTE ON SCHEMA::dbo FROM kinetix_app_rol;
GO
