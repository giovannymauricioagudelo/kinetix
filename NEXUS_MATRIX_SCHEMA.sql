--| ============================================================================ |
--| NEXUS + MATRIX - Permisos de Sentinel e índices para los agentes conectados  |
--| Idempotente: se puede ejecutar varias veces y no borra datos                 |
--| ============================================================================ |

USE kinetix;
GO

--| Índice para la auditoría y analítica de evaluaciones de reglas de Matrix |
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_auditoria_reglas_regla_fecha' AND object_id = OBJECT_ID('dbo.auditoria_evaluacion_reglas'))
    CREATE INDEX idx_auditoria_reglas_regla_fecha ON dbo.auditoria_evaluacion_reglas(id_regla, fecha_evaluacion DESC);
GO

--| Índice para listar reglas activas por prioridad |
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_reglas_estado_prioridad' AND object_id = OBJECT_ID('dbo.reglas_negocio'))
    CREATE INDEX idx_reglas_estado_prioridad ON dbo.reglas_negocio(estado, prioridad DESC);
GO

--| Permisos de Nexus (esquema, procedimientos, respaldos) y Matrix (reglas) |
--| nombre_permiso solo existe en algunas bases: se inserta con SQL dinámico cuando está |
DECLARE @permisos TABLE (id NVARCHAR(50), nombre NVARCHAR(100), recurso NVARCHAR(100), accion NVARCHAR(100), descripcion NVARCHAR(500));
INSERT INTO @permisos VALUES
    ('perm_nexus_001',  N'Ver Esquema',              'esquema',         'ver',       N'Consultar tablas, columnas, índices y procedimientos con Nexus'),
    ('perm_nexus_002',  N'Modificar Esquema',        'esquema',         'modificar', N'Crear tablas en SQL Server con Nexus'),
    ('perm_nexus_003',  N'Ejecutar Procedimientos',  'procedimientos',  'ejecutar',  N'Ejecutar procedimientos almacenados con Nexus'),
    ('perm_nexus_004',  N'Gestionar Respaldos',      'respaldos',       'gestionar', N'Crear y listar respaldos de la base con Nexus'),
    ('perm_matrix_001', N'Ver Reglas',               'reglas',          'ver',       N'Consultar reglas, auditoría y analítica de Matrix'),
    ('perm_matrix_002', N'Gestionar Reglas',         'reglas',          'gestionar', N'Crear, actualizar y archivar reglas de Matrix'),
    ('perm_matrix_003', N'Evaluar Reglas',           'reglas',          'evaluar',   N'Evaluar y probar reglas de Matrix');

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

--| rol_admin recibe todos los permisos nuevos; rol_auditor puede ver esquema y reglas |
INSERT INTO dbo.roles_permisos (id_rol, id_permiso)
SELECT asignacion.id_rol, asignacion.id_permiso
FROM (VALUES
    ('rol_admin',   'perm_nexus_001'),
    ('rol_admin',   'perm_nexus_002'),
    ('rol_admin',   'perm_nexus_003'),
    ('rol_admin',   'perm_nexus_004'),
    ('rol_admin',   'perm_matrix_001'),
    ('rol_admin',   'perm_matrix_002'),
    ('rol_admin',   'perm_matrix_003'),
    ('rol_auditor', 'perm_nexus_001'),
    ('rol_auditor', 'perm_matrix_001')
) AS asignacion (id_rol, id_permiso)
WHERE EXISTS (SELECT 1 FROM dbo.roles r WHERE r.id = asignacion.id_rol)
  AND NOT EXISTS (
      SELECT 1 FROM dbo.roles_permisos rp
      WHERE rp.id_rol = asignacion.id_rol AND rp.id_permiso = asignacion.id_permiso
  );
GO

PRINT 'NEXUS + MATRIX: migración aplicada';
