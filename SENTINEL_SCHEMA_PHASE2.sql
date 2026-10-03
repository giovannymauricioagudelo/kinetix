--| ============================================================================ |
--| SENTINEL v2 + ARGUS - Migración incremental sobre SENTINEL_SCHEMA_SPANISH.sql |
--| Idempotente: se puede ejecutar varias veces y no borra datos                 |
--| ============================================================================ |

USE kinetix;
GO

--| TABLA mfa_secrets: secreto TOTP por usuario y último paso aceptado (anti-repetición) |
IF OBJECT_ID(N'dbo.mfa_secrets', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mfa_secrets (
        id_usuario            NVARCHAR(50) NOT NULL,
        secret_totp           NVARCHAR(64) NOT NULL,
        habilitado            BIT          NOT NULL CONSTRAINT df_mfa_secrets_habilitado DEFAULT 0,
        ultimo_paso_totp      BIGINT       NULL,
        fecha_creacion        DATETIME     NOT NULL CONSTRAINT df_mfa_secrets_creacion DEFAULT GETUTCDATE(),
        fecha_confirmacion    DATETIME     NULL,
        fecha_deshabilitacion DATETIME     NULL,
        CONSTRAINT pk_mfa_secrets PRIMARY KEY CLUSTERED (id_usuario),
        CONSTRAINT fk_mfa_secrets_usuario FOREIGN KEY (id_usuario) REFERENCES dbo.usuarios(id) ON DELETE CASCADE
    );
END
GO

--| Si mfa_secrets se creó a mano en la fase 2, agrega las columnas que falten |
IF COL_LENGTH('dbo.mfa_secrets', 'ultimo_paso_totp') IS NULL
    ALTER TABLE dbo.mfa_secrets ADD ultimo_paso_totp BIGINT NULL;
IF COL_LENGTH('dbo.mfa_secrets', 'fecha_confirmacion') IS NULL
    ALTER TABLE dbo.mfa_secrets ADD fecha_confirmacion DATETIME NULL;
IF COL_LENGTH('dbo.mfa_secrets', 'fecha_deshabilitacion') IS NULL
    ALTER TABLE dbo.mfa_secrets ADD fecha_deshabilitacion DATETIME NULL;
GO

--| Índice para contar intentos fallidos por cuenta (bloqueo temporal) |
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_bitacora_recurso' AND object_id = OBJECT_ID('dbo.bitacora_auditoria'))
    CREATE INDEX idx_bitacora_recurso ON dbo.bitacora_auditoria(recurso, resultado, fecha_auditoria DESC);
GO

--| Índice para revocar todas las fichas de refresco de un usuario |
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_fichas_usuario_tipo' AND object_id = OBJECT_ID('dbo.fichas_acceso'))
    CREATE INDEX idx_fichas_usuario_tipo ON dbo.fichas_acceso(id_usuario, tipo_ficha, revocada);
GO

--| Permisos de administración de Sentinel y de monitoreo de Argus |
MERGE dbo.permisos AS destino
USING (VALUES
    ('perm_sentinel_001', N'Asignar Roles',     'roles',     'asignar',   N'Asignar roles a usuarios de la empresa'),
    ('perm_sentinel_002', N'Otorgar Permisos',  'permisos',  'otorgar',   N'Otorgar permisos a roles de la empresa'),
    ('perm_argus_001',    N'Ver Monitoreo',     'monitoreo', 'ver',       N'Consultar métricas, salud, alertas y reportes de Argus'),
    ('perm_argus_002',    N'Reconocer Alertas', 'alertas',   'reconocer', N'Reconocer alertas activas de Argus')
) AS origen (id, nombre_permiso, recurso, accion, descripcion)
ON destino.id = origen.id
WHEN NOT MATCHED THEN
    INSERT (id, nombre_permiso, recurso, accion, descripcion)
    VALUES (origen.id, origen.nombre_permiso, origen.recurso, origen.accion, origen.descripcion);
GO

--| rol_admin recibe todos los permisos nuevos; rol_auditor puede ver el monitoreo |
INSERT INTO dbo.roles_permisos (id_rol, id_permiso)
SELECT asignacion.id_rol, asignacion.id_permiso
FROM (VALUES
    ('rol_admin',   'perm_sentinel_001'),
    ('rol_admin',   'perm_sentinel_002'),
    ('rol_admin',   'perm_argus_001'),
    ('rol_admin',   'perm_argus_002'),
    ('rol_auditor', 'perm_argus_001')
) AS asignacion (id_rol, id_permiso)
WHERE EXISTS (SELECT 1 FROM dbo.roles r WHERE r.id = asignacion.id_rol)
  AND NOT EXISTS (
      SELECT 1 FROM dbo.roles_permisos rp
      WHERE rp.id_rol = asignacion.id_rol AND rp.id_permiso = asignacion.id_permiso
  );
GO

PRINT 'SENTINEL v2 + ARGUS: migración aplicada';
