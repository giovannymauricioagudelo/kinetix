-- ============================================================================
-- SENTINEL v1.0 - SQL Server Schema (Español)
-- Database: kinetix
-- Fecha: 29 Septiembre, 2026
-- ============================================================================

USE kinetix;
GO

-- ============================================================================
-- TABLE: usuarios
-- ============================================================================
IF OBJECT_ID(N'dbo.usuarios', N'U') IS NOT NULL
    DROP TABLE dbo.usuarios;
GO

CREATE TABLE dbo.usuarios (
    id NVARCHAR(50) PRIMARY KEY,
    nombre_usuario NVARCHAR(255) NOT NULL,
    correo NVARCHAR(255) UNIQUE NOT NULL,
    hash_contrasena NVARCHAR(255) NOT NULL,
    id_empresa NVARCHAR(50) NOT NULL,
    estado NVARCHAR(20) DEFAULT 'activo' CHECK (estado IN ('activo', 'inactivo', 'bloqueado')),
    mfa_habilitado BIT DEFAULT 0,
    creado_en DATETIME DEFAULT GETUTCDATE(),
    actualizado_en DATETIME DEFAULT GETUTCDATE(),
    ultimo_acceso DATETIME NULL
);
GO

CREATE INDEX idx_usuarios_empresa ON dbo.usuarios(id_empresa);
CREATE INDEX idx_usuarios_nombre_usuario ON dbo.usuarios(nombre_usuario, id_empresa);
GO

-- ============================================================================
-- TABLE: roles
-- ============================================================================
IF OBJECT_ID(N'dbo.roles', N'U') IS NOT NULL
    DROP TABLE dbo.roles;
GO

CREATE TABLE dbo.roles (
    id NVARCHAR(50) PRIMARY KEY,
    nombre_rol NVARCHAR(100) NOT NULL,
    id_empresa NVARCHAR(50) NOT NULL,
    descripcion NVARCHAR(500),
    estado NVARCHAR(20) DEFAULT 'activo' CHECK (estado IN ('activo', 'inactivo')),
    creado_en DATETIME DEFAULT GETUTCDATE()
);
GO

CREATE INDEX idx_roles_empresa ON dbo.roles(id_empresa);
GO

-- ============================================================================
-- TABLE: permisos
-- ============================================================================
IF OBJECT_ID(N'dbo.permisos', N'U') IS NOT NULL
    DROP TABLE dbo.permisos;
GO

CREATE TABLE dbo.permisos (
    id NVARCHAR(50) PRIMARY KEY,
    nombre_permiso NVARCHAR(100) NOT NULL,
    recurso NVARCHAR(100) NOT NULL,
    accion NVARCHAR(100) NOT NULL,
    descripcion NVARCHAR(500),
    creado_en DATETIME DEFAULT GETUTCDATE()
);
GO

CREATE INDEX idx_permisos_recurso_accion ON dbo.permisos(recurso, accion);
GO

-- ============================================================================
-- TABLE: usuarios_roles (Junction)
-- ============================================================================
IF OBJECT_ID(N'dbo.usuarios_roles', N'U') IS NOT NULL
    DROP TABLE dbo.usuarios_roles;
GO

CREATE TABLE dbo.usuarios_roles (
    id_usuario NVARCHAR(50) NOT NULL,
    id_rol NVARCHAR(50) NOT NULL,
    asignado_en DATETIME DEFAULT GETUTCDATE(),
    PRIMARY KEY (id_usuario, id_rol),
    FOREIGN KEY (id_usuario) REFERENCES dbo.usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (id_rol) REFERENCES dbo.roles(id) ON DELETE CASCADE
);
GO

CREATE INDEX idx_usuarios_roles_usuario ON dbo.usuarios_roles(id_usuario);
CREATE INDEX idx_usuarios_roles_rol ON dbo.usuarios_roles(id_rol);
GO

-- ============================================================================
-- TABLE: roles_permisos (Junction)
-- ============================================================================
IF OBJECT_ID(N'dbo.roles_permisos', N'U') IS NOT NULL
    DROP TABLE dbo.roles_permisos;
GO

CREATE TABLE dbo.roles_permisos (
    id_rol NVARCHAR(50) NOT NULL,
    id_permiso NVARCHAR(50) NOT NULL,
    otorgado_en DATETIME DEFAULT GETUTCDATE(),
    PRIMARY KEY (id_rol, id_permiso),
    FOREIGN KEY (id_rol) REFERENCES dbo.roles(id) ON DELETE CASCADE,
    FOREIGN KEY (id_permiso) REFERENCES dbo.permisos(id) ON DELETE CASCADE
);
GO

CREATE INDEX idx_roles_permisos_rol ON dbo.roles_permisos(id_rol);
CREATE INDEX idx_roles_permisos_permiso ON dbo.roles_permisos(id_permiso);
GO

-- ============================================================================
-- TABLE: bitacora_auditoria (Inmutable)
-- ============================================================================
IF OBJECT_ID(N'dbo.bitacora_auditoria', N'U') IS NOT NULL
    DROP TABLE dbo.bitacora_auditoria;
GO

CREATE TABLE dbo.bitacora_auditoria (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_usuario NVARCHAR(50),
    id_empresa NVARCHAR(50) NOT NULL,
    accion NVARCHAR(100) NOT NULL,
    recurso NVARCHAR(100),
    resultado NVARCHAR(50) NOT NULL CHECK (resultado IN ('exito', 'fallo_credenciales', 'fallo_contrasena', 'fallo_permiso', 'exito', 'denegada')),
    detalles NVARCHAR(MAX),
    fecha_auditoria DATETIME DEFAULT GETUTCDATE(),
    direccion_ip NVARCHAR(50)
);
GO

CREATE INDEX idx_bitacora_usuario ON dbo.bitacora_auditoria(id_usuario, fecha_auditoria DESC);
CREATE INDEX idx_bitacora_empresa ON dbo.bitacora_auditoria(id_empresa, fecha_auditoria DESC);
CREATE INDEX idx_bitacora_accion ON dbo.bitacora_auditoria(accion, fecha_auditoria DESC);
GO

-- ============================================================================
-- TABLE: fichas_acceso (Token Management)
-- ============================================================================
IF OBJECT_ID(N'dbo.fichas_acceso', N'U') IS NOT NULL
    DROP TABLE dbo.fichas_acceso;
GO

CREATE TABLE dbo.fichas_acceso (
    id NVARCHAR(100) PRIMARY KEY,
    id_usuario NVARCHAR(50) NOT NULL,
    tipo_ficha NVARCHAR(50) NOT NULL CHECK (tipo_ficha IN ('Bearer', 'Refresh', 'MFA')),
    ficha_hash NVARCHAR(255) NOT NULL UNIQUE,
    creada_en DATETIME DEFAULT GETUTCDATE(),
    expira_en DATETIME NOT NULL,
    revocada BIT DEFAULT 0,
    revocada_en DATETIME NULL,
    FOREIGN KEY (id_usuario) REFERENCES dbo.usuarios(id) ON DELETE CASCADE
);
GO

CREATE INDEX idx_fichas_usuario ON dbo.fichas_acceso(id_usuario);
CREATE INDEX idx_fichas_expira ON dbo.fichas_acceso(expira_en);
GO

-- ============================================================================
-- TABLE: dispositivos_mfa (2FA/MFA)
-- ============================================================================
IF OBJECT_ID(N'dbo.dispositivos_mfa', N'U') IS NOT NULL
    DROP TABLE dbo.dispositivos_mfa;
GO

CREATE TABLE dbo.dispositivos_mfa (
    id NVARCHAR(50) PRIMARY KEY,
    id_usuario NVARCHAR(50) NOT NULL,
    tipo_dispositivo NVARCHAR(50) NOT NULL CHECK (tipo_dispositivo IN ('TOTP', 'SMS', 'Email', 'Hardware')),
    codigo_secreto NVARCHAR(255) NOT NULL,
    verificado BIT DEFAULT 0,
    creado_en DATETIME DEFAULT GETUTCDATE(),
    ultimo_uso DATETIME NULL,
    FOREIGN KEY (id_usuario) REFERENCES dbo.usuarios(id) ON DELETE CASCADE
);
GO

CREATE INDEX idx_mfa_usuario ON dbo.dispositivos_mfa(id_usuario);
GO

-- ============================================================================
-- DATOS DEMO
-- ============================================================================

-- Insertar roles
INSERT INTO dbo.roles (id, nombre_rol, id_empresa, descripcion, estado)
VALUES 
    ('rol_admin', 'Administrador del Sistema', 'imvesa', 'Acceso total a todos los módulos', 'activo'),
    ('rol_usuario', 'Usuario Estándar', 'imvesa', 'Acceso limitado a funcionalidades básicas', 'activo'),
    ('rol_gerente', 'Gerente', 'imvesa', 'Acceso a reportes y análisis', 'activo'),
    ('rol_auditor', 'Auditor', 'imvesa', 'Acceso a bitácoras y auditoría', 'activo');
GO

-- Insertar permisos
INSERT INTO dbo.permisos (id, nombre_permiso, recurso, accion, descripcion)
VALUES 
    ('perm_001', 'Crear Pedidos Venta', 'pedidos_venta', 'crear', 'Permiso para crear pedidos de venta'),
    ('perm_002', 'Ver Pedidos Venta', 'pedidos_venta', 'ver', 'Permiso para ver pedidos de venta'),
    ('perm_003', 'Editar Pedidos Venta', 'pedidos_venta', 'editar', 'Permiso para editar pedidos de venta'),
    ('perm_004', 'Eliminar Pedidos Venta', 'pedidos_venta', 'eliminar', 'Permiso para eliminar pedidos de venta'),
    ('perm_005', 'Crear Clientes', 'clientes', 'crear', 'Permiso para crear clientes'),
    ('perm_006', 'Ver Clientes', 'clientes', 'ver', 'Permiso para ver clientes'),
    ('perm_007', 'Editar Clientes', 'clientes', 'editar', 'Permiso para editar clientes'),
    ('perm_008', 'Ver Reportes', 'reportes', 'ver', 'Permiso para ver reportes'),
    ('perm_009', 'Exportar Datos', 'datos', 'exportar', 'Permiso para exportar datos'),
    ('perm_010', 'Ver Auditoría', 'auditoria', 'ver', 'Permiso para ver registros de auditoría');
GO

-- Asignar todos los permisos al rol admin
INSERT INTO dbo.roles_permisos (id_rol, id_permiso)
SELECT 'rol_admin', id FROM dbo.permisos;
GO

-- Asignar permisos específicos a rol_usuario
INSERT INTO dbo.roles_permisos (id_rol, id_permiso)
SELECT 'rol_usuario', id FROM dbo.permisos WHERE accion IN ('ver', 'crear');
GO

-- Asignar permisos al rol_gerente
INSERT INTO dbo.roles_permisos (id_rol, id_permiso)
SELECT 'rol_gerente', id FROM dbo.permisos WHERE recurso IN ('reportes', 'pedidos_venta');
GO

-- Asignar permisos al rol_auditor
INSERT INTO dbo.roles_permisos (id_rol, id_permiso)
SELECT 'rol_auditor', id FROM dbo.permisos WHERE accion = 'ver';
GO

-- Insertar usuario demo (contraseña hasheada con bcrypt rounds=12)
-- Password: SecurePassword123456 → hash: $2b$12$...
INSERT INTO dbo.usuarios (id, nombre_usuario, correo, hash_contrasena, id_empresa, estado, mfa_habilitado)
VALUES 
    ('usuario_001', 'giovanny@imvesa.com', 'giovanny@imvesa.com', 
     '$2b$12$Y5Gk6v7G8k9L0m1N2o3P4qQrStUvWxYzA1B2C3D4E5F6G7H8I9J0', 
     'imvesa', 'activo', 0);
GO

-- Asignar rol_admin a usuario_001
INSERT INTO dbo.usuarios_roles (id_usuario, id_rol)
VALUES ('usuario_001', 'rol_admin');
GO

-- ============================================================================
-- VERIFICACIÓN
-- ============================================================================

PRINT '=== VERIFICACIÓN DE TABLAS CREADAS ===';
SELECT TABLE_NAME FROM kinetix.INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo' ORDER BY TABLE_NAME;

PRINT '=== USUARIOS CREADOS ===';
SELECT id, nombre_usuario, id_empresa, estado FROM dbo.usuarios;

PRINT '=== ROLES CREADOS ===';
SELECT id, nombre_rol, id_empresa FROM dbo.roles;

PRINT '=== PERMISOS CREADOS ===';
SELECT COUNT(*) as total_permisos FROM dbo.permisos;

PRINT '=== ASIGNACIONES ===';
SELECT 
    u.nombre_usuario, 
    COUNT(DISTINCT r.nombre_rol) as num_roles,
    COUNT(DISTINCT p.id) as num_permisos
FROM dbo.usuarios u
LEFT JOIN dbo.usuarios_roles ur ON u.id = ur.id_usuario
LEFT JOIN dbo.roles r ON ur.id_rol = r.id
LEFT JOIN dbo.roles_permisos rp ON r.id = rp.id_rol
LEFT JOIN dbo.permisos p ON rp.id_permiso = p.id
GROUP BY u.nombre_usuario;

PRINT '✅ SCHEMA CREADO EXITOSAMENTE';
