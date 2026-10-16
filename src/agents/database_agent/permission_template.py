"""Plantilla de permisos por empresa, rol y usuario que Nexus agrega a toda aplicación (permisos-por-empresa.mdc).

Las tablas son portables (se generan para el motor de la aplicación); las llaves, el historial inalterable y los
procedimientos app.permisos_* son de SQL Server. Permiso efectivo = (rol + concesiones) − restricciones; la base
rechaza concesiones redundantes y restricciones contradictorias y revoca sola lo que pierde sentido al cambiar el rol.
Errores propios: 51000 sin empresa en la sesión y 52001–52099 de la plantilla.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from src.agents.database_agent.database_agent import ColumnDefinition, ColumnType, TableDefinition

PERMISSIONS_KIND = "permisos"
PERMISSIONS_VERSION = 1
PERMISSIONS_MIGRATION = "permisos_por_empresa"
ADMIN_OPTION = "permisos"
COMPANY_COLUMN = "id_empresa"

EVENTOS_ESTANDAR = (
    ("acceder", "Acceder (ver en el menú y entrar)"),
    ("consultar", "Consultar"),
    ("ingresar", "Ingresar"),
    ("actualizar", "Actualizar"),
    ("borrar", "Borrar"),
    ("enviar", "Enviar"),
    ("aprobar", "Aprobar"),
    ("anular", "Anular"),
    ("exportar", "Exportar"),
    ("imprimir", "Imprimir"),
    ("publicar", "Publicar"),
)
EVENTOS_ADMINISTRACION = ("acceder", "consultar", "ingresar", "actualizar", "borrar")
EVENTOS_CON_MFA = ("ingresar", "actualizar", "borrar")
TIPOS_PERMISO_USUARIO = ("concesion", "restriccion")


def definition(multi: bool, rls: bool) -> Dict[str, Any]:
    return {"tipo": PERMISSIONS_KIND, "version": PERMISSIONS_VERSION, "multiempresa": bool(multi),
            "seguridad_por_fila": bool(rls)}


def catalogo_base(nombre_rol_admin: str = "Administrador") -> Dict[str, Any]:
    """Catálogo mínimo de toda aplicación: eventos estándar, la opción de permisos y el rol administrador."""
    eventos = [{"codigo": c, "nombre": n, "orden": i} for i, (c, n) in enumerate(EVENTOS_ESTANDAR, start=1)]
    opcion = {"codigo": ADMIN_OPTION, "nombre": "Permisos", "ruta": "/permisos", "icono": "permisos", "orden": 900,
              "es_menu": True, "eventos": list(EVENTOS_ADMINISTRACION), "eventos_mfa": list(EVENTOS_CON_MFA)}
    admin = {"codigo": "administrador", "nombre": nombre_rol_admin, "descripcion": "Administra la empresa y sus permisos",
             "permisos": [{"opcion": ADMIN_OPTION, "evento": e, "alcance": "empresa"} for e in EVENTOS_ADMINISTRACION]}
    return {"eventos": eventos, "opciones": [opcion], "roles": [admin]}


# ============================================================================ tablas portables


def _col(name: str, kind: ColumnType, nullable: bool = True, default: str = None, pk: bool = False) -> ColumnDefinition:
    return ColumnDefinition(name=name, type=kind, nullable=nullable and not pk, default=default, primary_key=pk)


V, I, B, D, J = ColumnType.VARCHAR, ColumnType.INT, ColumnType.BOOLEAN, ColumnType.DATETIME, ColumnType.JSON

_TABLES = (
    ("opcion_aplicacion", "Opciones de la aplicación (pantallas y módulos) que arman el menú", True, [
        _col("id_opcion", V, pk=True), _col("codigo", V, False), _col("nombre", V, False), _col("descripcion", V),
        _col("id_opcion_padre", V), _col("ruta", V), _col("icono", V), _col("orden", I, False, "0"),
        _col("es_menu", B, False, "true"), _col("activo", B, False, "true"),
    ]),
    ("evento_permiso", "Eventos que se autorizan sobre las opciones (acceder, consultar, ingresar...)", True, [
        _col("id_evento", V, pk=True), _col("codigo", V, False), _col("nombre", V, False),
        _col("es_sistema", B, False, "true"), _col("orden", I, False, "0"), _col("activo", B, False, "true"),
    ]),
    ("opcion_evento", "Eventos que aplican a cada opción y si exigen MFA reciente", True, [
        _col("id_opcion_evento", V, pk=True), _col("id_opcion", V, False), _col("id_evento", V, False),
        _col("requiere_mfa", B, False, "false"), _col("activo", B, False, "true"),
    ]),
    ("rol", "Roles de la empresa: de sistema (catálogo de la aplicación) o propios a partir de un rol base", True, [
        _col("id_rol", V, pk=True), _col("codigo", V, False), _col("nombre", V, False), _col("descripcion", V),
        _col("rol_base", V), _col("es_sistema", B, False, "false"), _col("activo", B, False, "true"),
    ]),
    ("usuario_rol", "Rol de cada usuario en la empresa", True, [
        _col("id_usuario_rol", V, pk=True), _col("id_usuario", V, False), _col("id_rol", V, False),
    ]),
    ("permiso_rol", "Permisos del rol: opción + evento + alcance", True, [
        _col("id_permiso_rol", V, pk=True), _col("id_rol", V, False), _col("id_opcion_evento", V, False),
        _col("alcance", V, False, "empresa"),
    ]),
    ("permiso_usuario", "Concesiones y restricciones de un usuario sobre su rol", True, [
        _col("id_permiso_usuario", V, pk=True), _col("id_usuario", V, False), _col("id_opcion_evento", V, False),
        _col("tipo", V, False), _col("alcance", V), _col("vigente_hasta", D), _col("estado", V, False, "vigente"),
        _col("motivo", V, False), _col("otorgado_por", V, False), _col("fecha_revocacion", D),
        _col("revocado_por", V), _col("motivo_revocacion", V),
    ]),
    ("historial_permiso", "Historial inalterable de asignaciones y revocaciones de permisos", False, [
        _col("id_historial", V, pk=True), _col("fecha", D, False), _col("actor", V, False),
        _col("accion", V, False), _col("sujeto_tipo", V, False), _col("id_sujeto", V), _col("id_opcion_evento", V),
        _col("tipo", V), _col("motivo", V), _col("detalle", J),
    ]),
)
TABLE_NAMES = tuple(name for name, *_ in _TABLES)


def tables(multi: bool) -> List[TableDefinition]:
    company = [_col(COMPANY_COLUMN, V, False)] if multi else []
    return [TableDefinition(name=name, columns=[*company, *columns], company_column=False, warehouse_column=False,
                            audit_columns=audit, description=description)
            for name, description, audit, columns in _TABLES]


# ============================================================================ SQL Server

_EMP_DECL = ("DECLARE @id_empresa NVARCHAR(255) = CAST(SESSION_CONTEXT(N'id_empresa') AS NVARCHAR(255));\n"
             "    IF @id_empresa IS NULL THROW 51000, N'La sesión no tiene empresa (SESSION_CONTEXT id_empresa).', 1;")


def _adapt(sql: str, multi: bool) -> str:
    """Marcas de empresa: «EMP» declara @id_empresa, «E:x» filtra x, «EJ:x:y» une por empresa, «EC»/«EV» columna y
    valor al insertar, «EK» primera columna de los índices y «ER» sufijo del recurso de bloqueo."""
    if multi:
        sql = sql.replace("«EMP»", _EMP_DECL)
        sql = re.sub(r"«E:(\w+)»", r"\1.id_empresa = @id_empresa AND ", sql)
        sql = re.sub(r"«EJ:(\w+):(\w+)»", r"\1.id_empresa = \2.id_empresa AND ", sql)
        return (sql.replace("«EC»", "id_empresa, ").replace("«EV»", "@id_empresa, ").replace("«EK»", "id_empresa, ")
                .replace("«ER»", " + N':' + @id_empresa"))
    sql = re.sub(r"«EMP»\n\s*", "", sql)
    sql = re.sub(r"«EJ?:[\w:]+»", "", sql)
    for mark in ("«EC»", "«EV»", "«EK»", "«ER»"):
        sql = sql.replace(mark, "")
    return sql


def _once(kind: str, name: str, statement: str) -> str:
    lookup = {"index": f"SELECT 1 FROM sys.indexes WHERE name = N'{name}'",
              "constraint": f"SELECT 1 FROM sys.objects WHERE name = N'{name}'"}[kind]
    return f"IF NOT EXISTS ({lookup})\n    {statement}"


_KEYS = [
    ("index", "ux_opcion_aplicacion_codigo", "CREATE UNIQUE INDEX ux_opcion_aplicacion_codigo ON dbo.opcion_aplicacion («EK»codigo);"),
    ("index", "ux_evento_permiso_codigo", "CREATE UNIQUE INDEX ux_evento_permiso_codigo ON dbo.evento_permiso («EK»codigo);"),
    ("index", "ux_opcion_evento", "CREATE UNIQUE INDEX ux_opcion_evento ON dbo.opcion_evento («EK»id_opcion, id_evento);"),
    ("index", "ux_rol_codigo", "CREATE UNIQUE INDEX ux_rol_codigo ON dbo.rol («EK»codigo);"),
    ("index", "ux_usuario_rol_usuario", "CREATE UNIQUE INDEX ux_usuario_rol_usuario ON dbo.usuario_rol («EK»id_usuario);"),
    ("index", "idx_usuario_rol_rol", "CREATE INDEX idx_usuario_rol_rol ON dbo.usuario_rol («EK»id_rol);"),
    ("index", "ux_permiso_rol", "CREATE UNIQUE INDEX ux_permiso_rol ON dbo.permiso_rol («EK»id_rol, id_opcion_evento);"),
    ("index", "ux_permiso_usuario_vigente", "CREATE UNIQUE INDEX ux_permiso_usuario_vigente ON dbo.permiso_usuario "
                                            "(«EK»id_usuario, id_opcion_evento) WHERE estado = N'vigente';"),
    ("index", "idx_permiso_usuario_opcion_evento", "CREATE INDEX idx_permiso_usuario_opcion_evento ON dbo.permiso_usuario "
                                                   "(«EK»id_opcion_evento, estado);"),
    ("index", "idx_historial_permiso_fecha", "CREATE INDEX idx_historial_permiso_fecha ON dbo.historial_permiso («EK»fecha DESC);"),
    ("index", "idx_historial_permiso_sujeto", "CREATE INDEX idx_historial_permiso_sujeto ON dbo.historial_permiso "
                                              "(«EK»sujeto_tipo, id_sujeto, fecha DESC);"),
    ("constraint", "fk_opcion_aplicacion_padre", "ALTER TABLE dbo.opcion_aplicacion ADD CONSTRAINT fk_opcion_aplicacion_padre "
                                                 "FOREIGN KEY (id_opcion_padre) REFERENCES dbo.opcion_aplicacion (id_opcion);"),
    ("constraint", "fk_opcion_evento_opcion", "ALTER TABLE dbo.opcion_evento ADD CONSTRAINT fk_opcion_evento_opcion "
                                              "FOREIGN KEY (id_opcion) REFERENCES dbo.opcion_aplicacion (id_opcion);"),
    ("constraint", "fk_opcion_evento_evento", "ALTER TABLE dbo.opcion_evento ADD CONSTRAINT fk_opcion_evento_evento "
                                              "FOREIGN KEY (id_evento) REFERENCES dbo.evento_permiso (id_evento);"),
    ("constraint", "fk_usuario_rol_rol", "ALTER TABLE dbo.usuario_rol ADD CONSTRAINT fk_usuario_rol_rol "
                                         "FOREIGN KEY (id_rol) REFERENCES dbo.rol (id_rol);"),
    ("constraint", "fk_permiso_rol_rol", "ALTER TABLE dbo.permiso_rol ADD CONSTRAINT fk_permiso_rol_rol "
                                         "FOREIGN KEY (id_rol) REFERENCES dbo.rol (id_rol);"),
    ("constraint", "fk_permiso_rol_opcion_evento", "ALTER TABLE dbo.permiso_rol ADD CONSTRAINT fk_permiso_rol_opcion_evento "
                                                   "FOREIGN KEY (id_opcion_evento) REFERENCES dbo.opcion_evento (id_opcion_evento);"),
    ("constraint", "fk_permiso_usuario_opcion_evento", "ALTER TABLE dbo.permiso_usuario ADD CONSTRAINT "
                                                       "fk_permiso_usuario_opcion_evento FOREIGN KEY (id_opcion_evento) "
                                                       "REFERENCES dbo.opcion_evento (id_opcion_evento);"),
    ("constraint", "ck_permiso_usuario_tipo", "ALTER TABLE dbo.permiso_usuario ADD CONSTRAINT ck_permiso_usuario_tipo "
                                              "CHECK (tipo IN (N'concesion', N'restriccion'));"),
    ("constraint", "ck_permiso_usuario_estado", "ALTER TABLE dbo.permiso_usuario ADD CONSTRAINT ck_permiso_usuario_estado "
                                                "CHECK (estado IN (N'vigente', N'revocado', N'revocado_automatico', N'vencido'));"),
    ("constraint", "ck_permiso_usuario_alcance", "ALTER TABLE dbo.permiso_usuario ADD CONSTRAINT ck_permiso_usuario_alcance "
                                                 "CHECK (tipo = N'concesion' OR alcance IS NULL);"),
    ("constraint", "ck_historial_permiso_sujeto", "ALTER TABLE dbo.historial_permiso ADD CONSTRAINT ck_historial_permiso_sujeto "
                                                  "CHECK (sujeto_tipo IN (N'rol', N'usuario', N'catalogo'));"),
]

_TRIGGER = """--| El historial de permisos no se modifica ni se borra |
CREATE OR ALTER TRIGGER dbo.trg_historial_permiso_inalterable ON dbo.historial_permiso
INSTEAD OF UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;
    THROW 52001, N'El historial de permisos es inalterable: no se modifica ni se borra.', 1;
END;"""

# Rol del usuario: el asignado en usuario_rol o, si no tiene, el rol de sistema de su rol base (@rol_respaldo).
_RESOLVER_ROL = """DECLARE @id_rol NVARCHAR(255) = (SELECT ur.id_rol FROM dbo.usuario_rol AS ur WHERE «E:ur»ur.id_usuario = @id_usuario);
    IF @id_rol IS NULL AND @rol_respaldo IS NOT NULL
        SELECT @id_rol = r.id_rol FROM dbo.rol AS r WHERE «E:r»r.codigo = @rol_respaldo AND r.es_sistema = 1 AND r.activo = 1;"""

_PAR_CATALOGO = """DECLARE @id_opcion_evento NVARCHAR(255) = (
        SELECT oe.id_opcion_evento FROM dbo.opcion_evento AS oe
        JOIN dbo.opcion_aplicacion AS o ON «EJ:o:oe»o.id_opcion = oe.id_opcion
        JOIN dbo.evento_permiso AS e ON «EJ:e:oe»e.id_evento = oe.id_evento
        WHERE «E:oe»o.codigo = @opcion AND e.codigo = @evento AND oe.activo = 1 AND o.activo = 1 AND e.activo = 1);
    IF @id_opcion_evento IS NULL THROW 52009, N'La opción o el evento no existen en el catálogo de permisos.', 1;"""

_HISTORIAL = ("INSERT INTO dbo.historial_permiso («EC»id_historial, fecha, actor, accion, sujeto_tipo, id_sujeto, "
              "id_opcion_evento, tipo, motivo, detalle)")

_PROCEDURES = [
    # ------------------------------------------------------------------ conciliar
    """--| Revoca las entradas de usuario que perdieron sentido (rol que ya concede, rol que ya no tiene) y vence las caducadas |
CREATE OR ALTER PROCEDURE app.permisos_conciliar
    @id_usuario NVARCHAR(255) = NULL,
    @actor NVARCHAR(255),
    @motivo NVARCHAR(500) = NULL,
    @devolver BIT = 1,
    @revocados INT = 0 OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    «EMP»
    DECLARE @ahora DATETIME2 = SYSUTCDATETIME();
    DECLARE @cambios TABLE (id_permiso_usuario NVARCHAR(255), id_usuario NVARCHAR(255), id_opcion_evento NVARCHAR(255),
                            tipo NVARCHAR(20), estado NVARCHAR(30), motivo NVARCHAR(500));
    UPDATE p SET estado = N'vencido', fecha_revocacion = @ahora, revocado_por = @actor,
                 motivo_revocacion = N'Terminó la vigencia', updated_at = @ahora
    OUTPUT inserted.id_permiso_usuario, inserted.id_usuario, inserted.id_opcion_evento, inserted.tipo, inserted.estado,
           inserted.motivo_revocacion INTO @cambios
    FROM dbo.permiso_usuario AS p
    WHERE «E:p»p.estado = N'vigente' AND p.vigente_hasta IS NOT NULL AND p.vigente_hasta <= @ahora
      AND (@id_usuario IS NULL OR p.id_usuario = @id_usuario);
    UPDATE p SET estado = N'revocado_automatico', fecha_revocacion = @ahora, revocado_por = @actor,
                 motivo_revocacion = COALESCE(@motivo, CASE WHEN p.tipo = N'concesion'
                     THEN N'El rol del usuario ya concede este permiso' ELSE N'El rol del usuario ya no tiene este permiso' END),
                 updated_at = @ahora
    OUTPUT inserted.id_permiso_usuario, inserted.id_usuario, inserted.id_opcion_evento, inserted.tipo, inserted.estado,
           inserted.motivo_revocacion INTO @cambios
    FROM dbo.permiso_usuario AS p
    JOIN dbo.usuario_rol AS ur ON «EJ:ur:p»ur.id_usuario = p.id_usuario
    LEFT JOIN dbo.permiso_rol AS pr ON «EJ:pr:p»pr.id_rol = ur.id_rol AND pr.id_opcion_evento = p.id_opcion_evento
    WHERE «E:p»p.estado = N'vigente' AND (@id_usuario IS NULL OR p.id_usuario = @id_usuario)
      AND ((p.tipo = N'concesion' AND pr.id_permiso_rol IS NOT NULL) OR (p.tipo = N'restriccion' AND pr.id_permiso_rol IS NULL));
    """ + _HISTORIAL + """
    SELECT «EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor,
           CASE WHEN c.estado = N'vencido' THEN N'vencer_usuario' ELSE N'revocacion_automatica' END,
           N'usuario', c.id_usuario, c.id_opcion_evento, c.tipo, c.motivo,
           (SELECT c.id_permiso_usuario AS id_permiso_usuario FOR JSON PATH, WITHOUT_ARRAY_WRAPPER)
    FROM @cambios AS c;
    SET @revocados = (SELECT COUNT(*) FROM @cambios);
    IF @devolver = 1 SELECT @revocados AS revocados;
END;""",
    # ------------------------------------------------------------------ sincronizar
    """--| Sincroniza el catálogo de la aplicación en la empresa (eventos, opciones, opción + evento) y los roles de sistema. |
--| Idempotente; los permisos de los roles de sistema se agregan salvo que la empresa los haya revocado explícitamente. |
CREATE OR ALTER PROCEDURE app.permisos_sincronizar
    @catalogo NVARCHAR(MAX),
    @actor NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    «EMP»
    IF ISJSON(@catalogo) = 0 THROW 52002, N'El catálogo de permisos no es JSON válido.', 1;
    DECLARE @eventos TABLE (codigo NVARCHAR(100) PRIMARY KEY, nombre NVARCHAR(255) NOT NULL, orden INT NOT NULL);
    INSERT INTO @eventos (codigo, nombre, orden)
    SELECT codigo, nombre, COALESCE(orden, 0)
    FROM OPENJSON(@catalogo, N'$.eventos') WITH (codigo NVARCHAR(100), nombre NVARCHAR(255), orden INT);
    DECLARE @opciones TABLE (codigo NVARCHAR(100) PRIMARY KEY, nombre NVARCHAR(255) NOT NULL, descripcion NVARCHAR(255),
                             padre NVARCHAR(100), ruta NVARCHAR(255), icono NVARCHAR(100), orden INT NOT NULL,
                             es_menu BIT NOT NULL, eventos NVARCHAR(MAX), eventos_mfa NVARCHAR(MAX));
    INSERT INTO @opciones (codigo, nombre, descripcion, padre, ruta, icono, orden, es_menu, eventos, eventos_mfa)
    SELECT codigo, nombre, descripcion, padre, ruta, icono, COALESCE(orden, 0), COALESCE(es_menu, 1), eventos, eventos_mfa
    FROM OPENJSON(@catalogo, N'$.opciones') WITH (
        codigo NVARCHAR(100), nombre NVARCHAR(255), descripcion NVARCHAR(255), padre NVARCHAR(100), ruta NVARCHAR(255),
        icono NVARCHAR(100), orden INT, es_menu BIT, eventos NVARCHAR(MAX) AS JSON, eventos_mfa NVARCHAR(MAX) AS JSON);
    DECLARE @pares TABLE (opcion NVARCHAR(100), evento NVARCHAR(100), requiere_mfa BIT NOT NULL, PRIMARY KEY (opcion, evento));
    INSERT INTO @pares (opcion, evento, requiere_mfa)
    SELECT o.codigo, e.value,
           CASE WHEN EXISTS (SELECT 1 FROM OPENJSON(o.eventos_mfa) AS m WHERE m.value = e.value) THEN 1 ELSE 0 END
    FROM @opciones AS o CROSS APPLY OPENJSON(o.eventos) AS e;
    DECLARE @roles TABLE (codigo NVARCHAR(100) PRIMARY KEY, nombre NVARCHAR(255) NOT NULL, descripcion NVARCHAR(255),
                          permisos NVARCHAR(MAX));
    INSERT INTO @roles (codigo, nombre, descripcion, permisos)
    SELECT codigo, nombre, descripcion, permisos
    FROM OPENJSON(@catalogo, N'$.roles') WITH (codigo NVARCHAR(100), nombre NVARCHAR(255), descripcion NVARCHAR(255),
                                               permisos NVARCHAR(MAX) AS JSON);
    DECLARE @por_rol TABLE (rol NVARCHAR(100), opcion NVARCHAR(100), evento NVARCHAR(100), alcance NVARCHAR(50),
                            PRIMARY KEY (rol, opcion, evento));
    INSERT INTO @por_rol (rol, opcion, evento, alcance)
    SELECT r.codigo, p.opcion, p.evento, COALESCE(p.alcance, N'empresa')
    FROM @roles AS r CROSS APPLY OPENJSON(r.permisos) WITH (opcion NVARCHAR(100), evento NVARCHAR(100), alcance NVARCHAR(50)) AS p;
    IF NOT EXISTS (SELECT 1 FROM @eventos) OR NOT EXISTS (SELECT 1 FROM @opciones)
        THROW 52003, N'El catálogo de permisos necesita eventos y opciones.', 1;
    IF EXISTS (SELECT 1 FROM @pares AS p WHERE NOT EXISTS (SELECT 1 FROM @eventos AS e WHERE e.codigo = p.evento))
        OR EXISTS (SELECT 1 FROM @opciones WHERE padre IS NOT NULL AND padre NOT IN (SELECT codigo FROM @opciones))
        OR EXISTS (SELECT 1 FROM @por_rol AS r WHERE NOT EXISTS (
            SELECT 1 FROM @pares AS p WHERE p.opcion = r.opcion AND p.evento = r.evento))
        THROW 52004, N'El catálogo usa un evento, una opción padre o un permiso de rol que no está declarado.', 1;

    DECLARE @ahora DATETIME2 = SYSUTCDATETIME(), @cambios INT = 0, @roles_creados INT = 0, @permisos_agregados INT = 0,
            @revocados INT = 0, @bloqueo INT, @recurso NVARCHAR(255) = N'permisos_sincronizar'«ER»;
    BEGIN TRANSACTION;
    EXEC @bloqueo = sp_getapplock @Resource = @recurso, @LockMode = N'Exclusive', @LockOwner = N'Transaction',
                                  @LockTimeout = 15000;
    IF @bloqueo < 0 THROW 52005, N'Otra sincronización de permisos está en curso; reintenta.', 1;

    UPDATE ev SET nombre = e.nombre, orden = e.orden, activo = 1, updated_at = @ahora
    FROM dbo.evento_permiso AS ev JOIN @eventos AS e ON e.codigo = ev.codigo
    WHERE «E:ev»EXISTS (SELECT ev.nombre, ev.orden, ev.activo EXCEPT SELECT e.nombre, e.orden, CAST(1 AS BIT));
    SET @cambios += @@ROWCOUNT;
    INSERT INTO dbo.evento_permiso («EC»id_evento, codigo, nombre, es_sistema, orden, activo, created_by)
    SELECT «EV»CONVERT(NVARCHAR(36), NEWID()), e.codigo, e.nombre, 1, e.orden, 1, @actor
    FROM @eventos AS e WHERE NOT EXISTS (SELECT 1 FROM dbo.evento_permiso AS ev WHERE «E:ev»ev.codigo = e.codigo);
    SET @cambios += @@ROWCOUNT;
    UPDATE ev SET activo = 0, updated_at = @ahora FROM dbo.evento_permiso AS ev
    WHERE «E:ev»ev.activo = 1 AND NOT EXISTS (SELECT 1 FROM @eventos AS e WHERE e.codigo = ev.codigo);
    SET @cambios += @@ROWCOUNT;

    UPDATE o SET nombre = s.nombre, descripcion = s.descripcion, ruta = s.ruta, icono = s.icono, orden = s.orden,
                 es_menu = s.es_menu, activo = 1, updated_at = @ahora
    FROM dbo.opcion_aplicacion AS o JOIN @opciones AS s ON s.codigo = o.codigo
    WHERE «E:o»EXISTS (SELECT o.nombre, o.descripcion, o.ruta, o.icono, o.orden, o.es_menu, o.activo
                        EXCEPT SELECT s.nombre, s.descripcion, s.ruta, s.icono, s.orden, s.es_menu, CAST(1 AS BIT));
    SET @cambios += @@ROWCOUNT;
    INSERT INTO dbo.opcion_aplicacion («EC»id_opcion, codigo, nombre, descripcion, ruta, icono, orden, es_menu, activo, created_by)
    SELECT «EV»CONVERT(NVARCHAR(36), NEWID()), s.codigo, s.nombre, s.descripcion, s.ruta, s.icono, s.orden, s.es_menu, 1, @actor
    FROM @opciones AS s WHERE NOT EXISTS (SELECT 1 FROM dbo.opcion_aplicacion AS o WHERE «E:o»o.codigo = s.codigo);
    SET @cambios += @@ROWCOUNT;
    UPDATE o SET id_opcion_padre = p.id_opcion, updated_at = @ahora
    FROM dbo.opcion_aplicacion AS o JOIN @opciones AS s ON s.codigo = o.codigo
    LEFT JOIN dbo.opcion_aplicacion AS p ON «EJ:p:o»p.codigo = s.padre
    WHERE «E:o»EXISTS (SELECT o.id_opcion_padre EXCEPT SELECT p.id_opcion);
    SET @cambios += @@ROWCOUNT;
    UPDATE o SET activo = 0, updated_at = @ahora FROM dbo.opcion_aplicacion AS o
    WHERE «E:o»o.activo = 1 AND NOT EXISTS (SELECT 1 FROM @opciones AS s WHERE s.codigo = o.codigo);
    SET @cambios += @@ROWCOUNT;

    UPDATE oe SET requiere_mfa = p.requiere_mfa, activo = 1, updated_at = @ahora
    FROM dbo.opcion_evento AS oe
    JOIN dbo.opcion_aplicacion AS o ON «EJ:o:oe»o.id_opcion = oe.id_opcion
    JOIN dbo.evento_permiso AS e ON «EJ:e:oe»e.id_evento = oe.id_evento
    JOIN @pares AS p ON p.opcion = o.codigo AND p.evento = e.codigo
    WHERE «E:oe»(oe.requiere_mfa <> p.requiere_mfa OR oe.activo = 0);
    SET @cambios += @@ROWCOUNT;
    INSERT INTO dbo.opcion_evento («EC»id_opcion_evento, id_opcion, id_evento, requiere_mfa, activo, created_by)
    SELECT «EV»CONVERT(NVARCHAR(36), NEWID()), o.id_opcion, e.id_evento, p.requiere_mfa, 1, @actor
    FROM @pares AS p
    JOIN dbo.opcion_aplicacion AS o ON «E:o»o.codigo = p.opcion
    JOIN dbo.evento_permiso AS e ON «E:e»e.codigo = p.evento
    WHERE NOT EXISTS (SELECT 1 FROM dbo.opcion_evento AS oe WHERE «E:oe»oe.id_opcion = o.id_opcion AND oe.id_evento = e.id_evento);
    SET @cambios += @@ROWCOUNT;
    UPDATE oe SET activo = 0, updated_at = @ahora FROM dbo.opcion_evento AS oe
    WHERE «E:oe»oe.activo = 1 AND NOT EXISTS (
        SELECT 1 FROM @pares AS p
        JOIN dbo.opcion_aplicacion AS o ON «E:o»o.codigo = p.opcion
        JOIN dbo.evento_permiso AS e ON «E:e»e.codigo = p.evento
        WHERE o.id_opcion = oe.id_opcion AND e.id_evento = oe.id_evento);
    SET @cambios += @@ROWCOUNT;
    IF @cambios > 0
        """ + _HISTORIAL + """
        VALUES («EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor, N'sincronizar_catalogo', N'catalogo', NULL, NULL, NULL, NULL,
                (SELECT @cambios AS cambios FOR JSON PATH, WITHOUT_ARRAY_WRAPPER));

    DECLARE @nuevos TABLE (id_rol NVARCHAR(255), codigo NVARCHAR(100));
    INSERT INTO dbo.rol («EC»id_rol, codigo, nombre, descripcion, rol_base, es_sistema, activo, created_by)
    OUTPUT inserted.id_rol, inserted.codigo INTO @nuevos
    SELECT «EV»CONVERT(NVARCHAR(36), NEWID()), r.codigo, r.nombre, r.descripcion, r.codigo, 1, 1, @actor
    FROM @roles AS r WHERE NOT EXISTS (SELECT 1 FROM dbo.rol AS x WHERE «E:x»x.codigo = r.codigo);
    SET @roles_creados = @@ROWCOUNT;
    """ + _HISTORIAL + """
    SELECT «EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor, N'crear_rol', N'rol', n.id_rol, NULL, NULL, N'Rol de sistema del catálogo',
           (SELECT n.codigo AS codigo FOR JSON PATH, WITHOUT_ARRAY_WRAPPER)
    FROM @nuevos AS n;

    DECLARE @agregados TABLE (id_rol NVARCHAR(255), id_opcion_evento NVARCHAR(255), alcance NVARCHAR(50));
    INSERT INTO dbo.permiso_rol («EC»id_permiso_rol, id_rol, id_opcion_evento, alcance, created_by)
    OUTPUT inserted.id_rol, inserted.id_opcion_evento, inserted.alcance INTO @agregados
    SELECT «EV»CONVERT(NVARCHAR(36), NEWID()), x.id_rol, oe.id_opcion_evento, pr.alcance, @actor
    FROM @por_rol AS pr
    JOIN dbo.rol AS x ON «E:x»x.codigo = pr.rol AND x.es_sistema = 1
    JOIN dbo.opcion_aplicacion AS o ON «EJ:o:x»o.codigo = pr.opcion
    JOIN dbo.evento_permiso AS e ON «EJ:e:x»e.codigo = pr.evento
    JOIN dbo.opcion_evento AS oe ON «EJ:oe:x»oe.id_opcion = o.id_opcion AND oe.id_evento = e.id_evento
    WHERE NOT EXISTS (SELECT 1 FROM dbo.permiso_rol AS y WHERE «EJ:y:x»y.id_rol = x.id_rol AND y.id_opcion_evento = oe.id_opcion_evento)
      AND NOT EXISTS (SELECT 1 FROM dbo.historial_permiso AS h WHERE «EJ:h:x»h.sujeto_tipo = N'rol' AND h.id_sujeto = x.id_rol
                      AND h.id_opcion_evento = oe.id_opcion_evento AND h.accion = N'revocar_rol');
    SET @permisos_agregados = @@ROWCOUNT;
    """ + _HISTORIAL + """
    SELECT «EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor, N'conceder_rol', N'rol', a.id_rol, a.id_opcion_evento, NULL,
           N'Permiso por defecto del rol de sistema', (SELECT a.alcance AS alcance FOR JSON PATH, WITHOUT_ARRAY_WRAPPER)
    FROM @agregados AS a;
    IF @permisos_agregados > 0
        EXEC app.permisos_conciliar @actor = @actor, @devolver = 0, @revocados = @revocados OUTPUT;
    COMMIT TRANSACTION;
    SELECT @cambios AS cambios_catalogo, @roles_creados AS roles_creados, @permisos_agregados AS permisos_agregados,
           @revocados AS revocados_automaticos;
END;""",
    # ------------------------------------------------------------------ consultas
    """--| Opciones y eventos activos del catálogo (matriz de la pantalla de permisos) |
CREATE OR ALTER PROCEDURE app.permisos_catalogo_listar
AS
BEGIN
    SET NOCOUNT ON;
    «EMP»
    SELECT o.codigo AS opcion, o.nombre AS nombre_opcion, p.codigo AS opcion_padre, o.ruta, o.icono, o.orden, o.es_menu,
           e.codigo AS evento, e.nombre AS nombre_evento, e.orden AS orden_evento, oe.requiere_mfa
    FROM dbo.opcion_evento AS oe
    JOIN dbo.opcion_aplicacion AS o ON «EJ:o:oe»o.id_opcion = oe.id_opcion
    JOIN dbo.evento_permiso AS e ON «EJ:e:oe»e.id_evento = oe.id_evento
    LEFT JOIN dbo.opcion_aplicacion AS p ON «EJ:p:o»p.id_opcion = o.id_opcion_padre
    WHERE «E:oe»oe.activo = 1 AND o.activo = 1 AND e.activo = 1
    ORDER BY o.orden, o.codigo, e.orden, e.codigo;
END;""",
    """--| Roles de la empresa con cuántos permisos y usuarios tienen |
CREATE OR ALTER PROCEDURE app.permisos_rol_listar
AS
BEGIN
    SET NOCOUNT ON;
    «EMP»
    SELECT r.id_rol, r.codigo, r.nombre, r.descripcion, r.rol_base, r.es_sistema, r.activo,
           (SELECT COUNT(*) FROM dbo.permiso_rol AS pr WHERE «EJ:pr:r»pr.id_rol = r.id_rol) AS permisos,
           (SELECT COUNT(*) FROM dbo.usuario_rol AS ur WHERE «EJ:ur:r»ur.id_rol = r.id_rol) AS usuarios
    FROM dbo.rol AS r
    WHERE «E:r»1 = 1
    ORDER BY r.es_sistema DESC, r.nombre;
END;""",
    """--| Permisos del rol (opción, evento, alcance) |
CREATE OR ALTER PROCEDURE app.permisos_rol_matriz
    @id_rol NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;
    «EMP»
    SELECT o.codigo AS opcion, e.codigo AS evento, pr.alcance, pr.created_at, pr.created_by
    FROM dbo.permiso_rol AS pr
    JOIN dbo.opcion_evento AS oe ON «EJ:oe:pr»oe.id_opcion_evento = pr.id_opcion_evento
    JOIN dbo.opcion_aplicacion AS o ON «EJ:o:oe»o.id_opcion = oe.id_opcion
    JOIN dbo.evento_permiso AS e ON «EJ:e:oe»e.id_evento = oe.id_evento
    WHERE «E:pr»pr.id_rol = @id_rol
    ORDER BY o.orden, o.codigo, e.orden;
END;""",
    # ------------------------------------------------------------------ roles
    """--| Crea un rol propio de la empresa, opcionalmente copiando los permisos y el rol base de otro |
CREATE OR ALTER PROCEDURE app.permisos_rol_crear
    @codigo NVARCHAR(100),
    @nombre NVARCHAR(255),
    @descripcion NVARCHAR(255) = NULL,
    @copiar_de NVARCHAR(255) = NULL,
    @actor NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    «EMP»
    IF EXISTS (SELECT 1 FROM dbo.rol AS r WHERE «E:r»r.codigo = @codigo)
        THROW 52006, N'Ya existe un rol con ese código en la empresa.', 1;
    DECLARE @rol_base NVARCHAR(100) = NULL;
    IF @copiar_de IS NOT NULL
    BEGIN
        SELECT @rol_base = COALESCE(r.rol_base, r.codigo) FROM dbo.rol AS r WHERE «E:r»r.id_rol = @copiar_de;
        IF @rol_base IS NULL THROW 52007, N'El rol no existe en la empresa.', 1;
    END;
    DECLARE @id_rol NVARCHAR(255) = CONVERT(NVARCHAR(36), NEWID());
    BEGIN TRANSACTION;
    INSERT INTO dbo.rol («EC»id_rol, codigo, nombre, descripcion, rol_base, es_sistema, activo, created_by)
    VALUES («EV»@id_rol, @codigo, @nombre, @descripcion, @rol_base, 0, 1, @actor);
    """ + _HISTORIAL + """
    VALUES («EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor, N'crear_rol', N'rol', @id_rol, NULL, NULL, NULL,
            (SELECT @codigo AS codigo, @copiar_de AS copiado_de FOR JSON PATH, WITHOUT_ARRAY_WRAPPER));
    DECLARE @copiados TABLE (id_opcion_evento NVARCHAR(255), alcance NVARCHAR(50));
    INSERT INTO dbo.permiso_rol («EC»id_permiso_rol, id_rol, id_opcion_evento, alcance, created_by)
    OUTPUT inserted.id_opcion_evento, inserted.alcance INTO @copiados
    SELECT «EV»CONVERT(NVARCHAR(36), NEWID()), @id_rol, pr.id_opcion_evento, pr.alcance, @actor
    FROM dbo.permiso_rol AS pr WHERE «E:pr»pr.id_rol = @copiar_de;
    """ + _HISTORIAL + """
    SELECT «EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor, N'conceder_rol', N'rol', @id_rol, c.id_opcion_evento, NULL,
           N'Copiado del rol de origen', (SELECT c.alcance AS alcance FOR JSON PATH, WITHOUT_ARRAY_WRAPPER)
    FROM @copiados AS c;
    COMMIT TRANSACTION;
    SELECT @id_rol AS id_rol;
END;""",
    """--| Renombra, describe o activa/desactiva un rol; los de sistema y los que tienen usuarios no se desactivan |
CREATE OR ALTER PROCEDURE app.permisos_rol_actualizar
    @id_rol NVARCHAR(255),
    @nombre NVARCHAR(255),
    @descripcion NVARCHAR(255) = NULL,
    @activo BIT = 1,
    @motivo NVARCHAR(500) = NULL,
    @actor NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    «EMP»
    DECLARE @es_sistema BIT, @antes NVARCHAR(MAX);
    SELECT @es_sistema = r.es_sistema,
           @antes = (SELECT r.nombre, r.descripcion, r.activo FOR JSON PATH, WITHOUT_ARRAY_WRAPPER)
    FROM dbo.rol AS r WHERE «E:r»r.id_rol = @id_rol;
    IF @es_sistema IS NULL THROW 52007, N'El rol no existe en la empresa.', 1;
    IF @activo = 0 AND @es_sistema = 1 THROW 52008, N'Los roles de sistema no se desactivan.', 1;
    IF @activo = 0 AND EXISTS (SELECT 1 FROM dbo.usuario_rol AS ur WHERE «E:ur»ur.id_rol = @id_rol)
        THROW 52008, N'El rol tiene usuarios asignados: cámbiales el rol antes de desactivarlo.', 1;
    BEGIN TRANSACTION;
    UPDATE r SET nombre = @nombre, descripcion = @descripcion, activo = @activo, updated_at = SYSUTCDATETIME()
    FROM dbo.rol AS r WHERE «E:r»r.id_rol = @id_rol;
    """ + _HISTORIAL + """
    VALUES («EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor, N'actualizar_rol', N'rol', @id_rol, NULL, NULL, @motivo,
            (SELECT JSON_QUERY(@antes) AS antes, @nombre AS nombre, @descripcion AS descripcion, @activo AS activo
             FOR JSON PATH, WITHOUT_ARRAY_WRAPPER));
    COMMIT TRANSACTION;
    SELECT 1 AS afectadas;
END;""",
    """--| Concede (o cambia el alcance de) un permiso a un rol y revoca las concesiones de usuario que quedan redundantes |
CREATE OR ALTER PROCEDURE app.permisos_rol_conceder
    @id_rol NVARCHAR(255),
    @opcion NVARCHAR(100),
    @evento NVARCHAR(100),
    @alcance NVARCHAR(50) = N'empresa',
    @motivo NVARCHAR(500) = NULL,
    @actor NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    «EMP»
    """ + _PAR_CATALOGO + """
    IF NOT EXISTS (SELECT 1 FROM dbo.rol AS r WHERE «E:r»r.id_rol = @id_rol AND r.activo = 1)
        THROW 52007, N'El rol no existe o está inactivo.', 1;
    DECLARE @alcance_actual NVARCHAR(50) = (SELECT pr.alcance FROM dbo.permiso_rol AS pr
                                            WHERE «E:pr»pr.id_rol = @id_rol AND pr.id_opcion_evento = @id_opcion_evento);
    IF @alcance_actual = COALESCE(@alcance, N'empresa') THROW 52010, N'El rol ya tiene este permiso con ese alcance.', 1;
    DECLARE @revocados INT = 0;
    BEGIN TRANSACTION;
    IF @alcance_actual IS NULL
        INSERT INTO dbo.permiso_rol («EC»id_permiso_rol, id_rol, id_opcion_evento, alcance, created_by)
        VALUES («EV»CONVERT(NVARCHAR(36), NEWID()), @id_rol, @id_opcion_evento, COALESCE(@alcance, N'empresa'), @actor);
    ELSE
        UPDATE pr SET alcance = COALESCE(@alcance, N'empresa'), updated_at = SYSUTCDATETIME()
        FROM dbo.permiso_rol AS pr WHERE «E:pr»pr.id_rol = @id_rol AND pr.id_opcion_evento = @id_opcion_evento;
    """ + _HISTORIAL + """
    VALUES («EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor,
            CASE WHEN @alcance_actual IS NULL THEN N'conceder_rol' ELSE N'cambiar_alcance_rol' END,
            N'rol', @id_rol, @id_opcion_evento, NULL, @motivo,
            (SELECT @alcance_actual AS alcance_anterior, COALESCE(@alcance, N'empresa') AS alcance FOR JSON PATH, WITHOUT_ARRAY_WRAPPER));
    EXEC app.permisos_conciliar @actor = @actor, @devolver = 0, @revocados = @revocados OUTPUT;
    COMMIT TRANSACTION;
    SELECT @revocados AS revocados_automaticos;
END;""",
    """--| Revoca un permiso de un rol y revoca las restricciones de usuario que quedan sin sentido |
CREATE OR ALTER PROCEDURE app.permisos_rol_revocar
    @id_rol NVARCHAR(255),
    @opcion NVARCHAR(100),
    @evento NVARCHAR(100),
    @motivo NVARCHAR(500) = NULL,
    @actor NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    «EMP»
    """ + _PAR_CATALOGO + """
    DECLARE @alcance NVARCHAR(50) = (SELECT pr.alcance FROM dbo.permiso_rol AS pr
                                     WHERE «E:pr»pr.id_rol = @id_rol AND pr.id_opcion_evento = @id_opcion_evento);
    IF @alcance IS NULL THROW 52011, N'El rol no tiene este permiso.', 1;
    IF @opcion = N'""" + ADMIN_OPTION + """' AND EXISTS (SELECT 1 FROM dbo.rol AS r WHERE «E:r»r.id_rol = @id_rol AND r.es_sistema = 1)
        THROW 52012, N'Los roles de sistema conservan la administración de permisos: la empresa no puede quedar sin quien la administre.', 1;
    DECLARE @revocados INT = 0;
    BEGIN TRANSACTION;
    DELETE pr FROM dbo.permiso_rol AS pr WHERE «E:pr»pr.id_rol = @id_rol AND pr.id_opcion_evento = @id_opcion_evento;
    """ + _HISTORIAL + """
    VALUES («EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor, N'revocar_rol', N'rol', @id_rol, @id_opcion_evento, NULL, @motivo,
            (SELECT @alcance AS alcance FOR JSON PATH, WITHOUT_ARRAY_WRAPPER));
    EXEC app.permisos_conciliar @actor = @actor, @devolver = 0, @revocados = @revocados OUTPUT;
    COMMIT TRANSACTION;
    SELECT @revocados AS revocados_automaticos;
END;""",
    # ------------------------------------------------------------------ usuarios
    """--| Asigna el rol del usuario y revoca sus concesiones o restricciones que pierden sentido con el rol nuevo |
CREATE OR ALTER PROCEDURE app.permisos_usuario_asignar_rol
    @id_usuario NVARCHAR(255),
    @id_rol NVARCHAR(255),
    @rol_base_requerido NVARCHAR(100) = NULL,
    @motivo NVARCHAR(500) = NULL,
    @actor NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    «EMP»
    DECLARE @rol_base NVARCHAR(100), @existe BIT = 0;
    SELECT @existe = 1, @rol_base = COALESCE(r.rol_base, r.codigo) FROM dbo.rol AS r
    WHERE «E:r»r.id_rol = @id_rol AND r.activo = 1;
    IF @existe = 0 THROW 52007, N'El rol no existe o está inactivo.', 1;
    IF @rol_base_requerido IS NOT NULL AND @rol_base <> @rol_base_requerido
        THROW 52013, N'El rol no corresponde al rol base del usuario.', 1;
    DECLARE @anterior NVARCHAR(255) = (SELECT ur.id_rol FROM dbo.usuario_rol AS ur WHERE «E:ur»ur.id_usuario = @id_usuario);
    IF @anterior = @id_rol THROW 52014, N'El usuario ya tiene ese rol.', 1;
    DECLARE @revocados INT = 0;
    BEGIN TRANSACTION;
    IF @anterior IS NULL
        INSERT INTO dbo.usuario_rol («EC»id_usuario_rol, id_usuario, id_rol, created_by)
        VALUES («EV»CONVERT(NVARCHAR(36), NEWID()), @id_usuario, @id_rol, @actor);
    ELSE
        UPDATE ur SET id_rol = @id_rol, updated_at = SYSUTCDATETIME()
        FROM dbo.usuario_rol AS ur WHERE «E:ur»ur.id_usuario = @id_usuario;
    """ + _HISTORIAL + """
    VALUES («EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor, N'asignar_rol_usuario', N'usuario', @id_usuario, NULL, NULL, @motivo,
            (SELECT @anterior AS id_rol_anterior, @id_rol AS id_rol FOR JSON PATH, WITHOUT_ARRAY_WRAPPER));
    EXEC app.permisos_conciliar @id_usuario = @id_usuario, @actor = @actor, @devolver = 0, @revocados = @revocados OUTPUT;
    COMMIT TRANSACTION;
    SELECT @revocados AS revocados_automaticos;
END;""",
    """--| Concesión (algo que el rol no da) o restricción (algo que el rol sí da) para un usuario |
CREATE OR ALTER PROCEDURE app.permisos_usuario_ajustar
    @id_usuario NVARCHAR(255),
    @tipo NVARCHAR(20),
    @opcion NVARCHAR(100),
    @evento NVARCHAR(100),
    @alcance NVARCHAR(50) = NULL,
    @vigente_hasta DATETIME2 = NULL,
    @motivo NVARCHAR(500),
    @actor NVARCHAR(255),
    @rol_respaldo NVARCHAR(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    «EMP»
    IF @tipo NOT IN (N'concesion', N'restriccion') THROW 52015, N'El tipo debe ser concesion o restriccion.', 1;
    IF NULLIF(LTRIM(RTRIM(@motivo)), N'') IS NULL THROW 52015, N'Indica el motivo del permiso del usuario.', 1;
    IF @vigente_hasta IS NOT NULL AND @vigente_hasta <= SYSUTCDATETIME() THROW 52015, N'La vigencia debe ser futura.', 1;
    IF @tipo = N'restriccion' AND @alcance IS NOT NULL THROW 52015, N'Una restricción no lleva alcance.', 1;
    IF @tipo = N'restriccion' AND @opcion = N'""" + ADMIN_OPTION + """' AND @id_usuario = @actor
        THROW 52012, N'No puedes restringirte la administración de permisos.', 1;
    """ + _PAR_CATALOGO + """
    """ + _RESOLVER_ROL + """
    IF @id_rol IS NULL THROW 52016, N'El usuario no tiene rol en la empresa: asígnale uno antes.', 1;
    DECLARE @revocados INT = 0, @id_permiso_usuario NVARCHAR(255) = CONVERT(NVARCHAR(36), NEWID());
    BEGIN TRANSACTION;
    IF NOT EXISTS (SELECT 1 FROM dbo.usuario_rol AS ur WHERE «E:ur»ur.id_usuario = @id_usuario)
    BEGIN
        INSERT INTO dbo.usuario_rol («EC»id_usuario_rol, id_usuario, id_rol, created_by)
        VALUES («EV»CONVERT(NVARCHAR(36), NEWID()), @id_usuario, @id_rol, @actor);
        """ + _HISTORIAL + """
        VALUES («EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor, N'asignar_rol_usuario', N'usuario', @id_usuario, NULL, NULL,
                N'Rol base del usuario', (SELECT @id_rol AS id_rol FOR JSON PATH, WITHOUT_ARRAY_WRAPPER));
    END;
    EXEC app.permisos_conciliar @id_usuario = @id_usuario, @actor = @actor, @devolver = 0, @revocados = @revocados OUTPUT;
    DECLARE @rol_concede BIT = CASE WHEN EXISTS (SELECT 1 FROM dbo.permiso_rol AS pr
        WHERE «E:pr»pr.id_rol = @id_rol AND pr.id_opcion_evento = @id_opcion_evento) THEN 1 ELSE 0 END;
    IF @tipo = N'concesion' AND @rol_concede = 1
        THROW 52017, N'Concesión redundante: el rol del usuario ya tiene este permiso.', 1;
    IF @tipo = N'restriccion' AND @rol_concede = 0
        THROW 52018, N'Restricción contradictoria: el rol del usuario no tiene este permiso.', 1;
    IF EXISTS (SELECT 1 FROM dbo.permiso_usuario AS p
               WHERE «E:p»p.id_usuario = @id_usuario AND p.id_opcion_evento = @id_opcion_evento AND p.estado = N'vigente')
        THROW 52019, N'El usuario ya tiene una concesión o restricción vigente sobre este permiso: revócala primero.', 1;
    INSERT INTO dbo.permiso_usuario («EC»id_permiso_usuario, id_usuario, id_opcion_evento, tipo, alcance, vigente_hasta,
                                     estado, motivo, otorgado_por, created_by)
    VALUES («EV»@id_permiso_usuario, @id_usuario, @id_opcion_evento, @tipo,
            CASE WHEN @tipo = N'concesion' THEN COALESCE(@alcance, N'empresa') END, @vigente_hasta,
            N'vigente', @motivo, @actor, @actor);
    """ + _HISTORIAL + """
    VALUES («EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor,
            CASE WHEN @tipo = N'concesion' THEN N'conceder_usuario' ELSE N'restringir_usuario' END,
            N'usuario', @id_usuario, @id_opcion_evento, @tipo, @motivo,
            (SELECT @id_permiso_usuario AS id_permiso_usuario, @vigente_hasta AS vigente_hasta FOR JSON PATH, WITHOUT_ARRAY_WRAPPER));
    COMMIT TRANSACTION;
    SELECT @id_permiso_usuario AS id_permiso_usuario;
END;""",
    """--| Revoca una concesión o restricción vigente del usuario |
CREATE OR ALTER PROCEDURE app.permisos_usuario_revocar
    @id_permiso_usuario NVARCHAR(255),
    @motivo NVARCHAR(500),
    @actor NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    «EMP»
    IF NULLIF(LTRIM(RTRIM(@motivo)), N'') IS NULL THROW 52015, N'Indica el motivo de la revocación.', 1;
    DECLARE @id_usuario NVARCHAR(255), @id_opcion_evento NVARCHAR(255), @tipo NVARCHAR(20);
    SELECT @id_usuario = p.id_usuario, @id_opcion_evento = p.id_opcion_evento, @tipo = p.tipo
    FROM dbo.permiso_usuario AS p WHERE «E:p»p.id_permiso_usuario = @id_permiso_usuario AND p.estado = N'vigente';
    IF @id_usuario IS NULL THROW 52020, N'No hay una concesión o restricción vigente con ese identificador.', 1;
    BEGIN TRANSACTION;
    UPDATE p SET estado = N'revocado', fecha_revocacion = SYSUTCDATETIME(), revocado_por = @actor,
                 motivo_revocacion = @motivo, updated_at = SYSUTCDATETIME()
    FROM dbo.permiso_usuario AS p WHERE «E:p»p.id_permiso_usuario = @id_permiso_usuario;
    """ + _HISTORIAL + """
    VALUES («EV»CONVERT(NVARCHAR(36), NEWID()), SYSUTCDATETIME(), @actor, N'revocar_usuario', N'usuario', @id_usuario, @id_opcion_evento, @tipo,
            @motivo, (SELECT @id_permiso_usuario AS id_permiso_usuario FOR JSON PATH, WITHOUT_ARRAY_WRAPPER));
    COMMIT TRANSACTION;
    SELECT 1 AS afectadas;
END;""",
    """--| Rol asignado de los usuarios de la empresa |
CREATE OR ALTER PROCEDURE app.permisos_usuario_rol_listar
    @id_usuario NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    «EMP»
    SELECT ur.id_usuario, r.id_rol, r.codigo, r.nombre, r.rol_base, r.es_sistema
    FROM dbo.usuario_rol AS ur JOIN dbo.rol AS r ON «EJ:r:ur»r.id_rol = ur.id_rol
    WHERE «E:ur»(@id_usuario IS NULL OR ur.id_usuario = @id_usuario);
END;""",
    """--| Concesiones y restricciones del usuario (vigentes o todas) |
CREATE OR ALTER PROCEDURE app.permisos_usuario_listar
    @id_usuario NVARCHAR(255),
    @incluir_inactivos BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    «EMP»
    SELECT p.id_permiso_usuario, o.codigo AS opcion, e.codigo AS evento, p.tipo, p.alcance, p.vigente_hasta, p.estado,
           p.motivo, p.otorgado_por, p.created_at, p.fecha_revocacion, p.revocado_por, p.motivo_revocacion
    FROM dbo.permiso_usuario AS p
    JOIN dbo.opcion_evento AS oe ON «EJ:oe:p»oe.id_opcion_evento = p.id_opcion_evento
    JOIN dbo.opcion_aplicacion AS o ON «EJ:o:oe»o.id_opcion = oe.id_opcion
    JOIN dbo.evento_permiso AS e ON «EJ:e:oe»e.id_evento = oe.id_evento
    WHERE «E:p»p.id_usuario = @id_usuario AND (@incluir_inactivos = 1 OR p.estado = N'vigente')
    ORDER BY p.created_at DESC;
END;""",
    """--| Permisos efectivos del usuario: (rol + concesiones) − restricciones; sin acceder, la opción no cuenta |
CREATE OR ALTER PROCEDURE app.permisos_efectivos
    @id_usuario NVARCHAR(255),
    @rol_respaldo NVARCHAR(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    «EMP»
    DECLARE @ahora DATETIME2 = SYSUTCDATETIME();
    """ + _RESOLVER_ROL + """
    WITH base AS (
        SELECT pr.id_opcion_evento, pr.alcance, N'rol' AS origen
        FROM dbo.permiso_rol AS pr WHERE «E:pr»pr.id_rol = @id_rol
        UNION ALL
        SELECT p.id_opcion_evento, p.alcance, N'concesion'
        FROM dbo.permiso_usuario AS p
        WHERE «E:p»p.id_usuario = @id_usuario AND p.tipo = N'concesion' AND p.estado = N'vigente'
          AND (p.vigente_hasta IS NULL OR p.vigente_hasta > @ahora)
    ), detalle AS (
        SELECT o.id_opcion, o.codigo AS opcion, e.codigo AS evento, b.alcance, b.origen, oe.requiere_mfa,
               o.nombre AS nombre_opcion, padre.codigo AS opcion_padre, o.ruta, o.icono, o.orden, o.es_menu
        FROM base AS b
        JOIN dbo.opcion_evento AS oe ON «E:oe»oe.id_opcion_evento = b.id_opcion_evento AND oe.activo = 1
        JOIN dbo.opcion_aplicacion AS o ON «EJ:o:oe»o.id_opcion = oe.id_opcion AND o.activo = 1
        JOIN dbo.evento_permiso AS e ON «EJ:e:oe»e.id_evento = oe.id_evento AND e.activo = 1
        LEFT JOIN dbo.opcion_aplicacion AS padre ON «EJ:padre:o»padre.id_opcion = o.id_opcion_padre
        WHERE NOT EXISTS (SELECT 1 FROM dbo.permiso_usuario AS r
                          WHERE «E:r»r.id_usuario = @id_usuario AND r.id_opcion_evento = b.id_opcion_evento
                            AND r.tipo = N'restriccion' AND r.estado = N'vigente'
                            AND (r.vigente_hasta IS NULL OR r.vigente_hasta > @ahora))
    )
    SELECT d.opcion, d.evento, d.alcance, d.origen, d.requiere_mfa, d.nombre_opcion, d.opcion_padre, d.ruta, d.icono,
           d.orden, d.es_menu
    FROM detalle AS d
    WHERE d.evento = N'acceder' OR EXISTS (SELECT 1 FROM detalle AS a WHERE a.id_opcion = d.id_opcion AND a.evento = N'acceder')
    ORDER BY d.orden, d.opcion, d.evento;
END;""",
    """--| Historial de permisos, del más reciente al más antiguo, por rol, usuario o completo |
CREATE OR ALTER PROCEDURE app.permisos_historial_listar
    @sujeto_tipo NVARCHAR(20) = NULL,
    @id_sujeto NVARCHAR(255) = NULL,
    @limite INT = 100
AS
BEGIN
    SET NOCOUNT ON;
    «EMP»
    SELECT TOP (CASE WHEN @limite BETWEEN 1 AND 1000 THEN @limite ELSE 100 END)
           h.id_historial, h.fecha, h.actor, h.accion, h.sujeto_tipo, h.id_sujeto, o.codigo AS opcion, e.codigo AS evento,
           h.tipo, h.motivo, h.detalle
    FROM dbo.historial_permiso AS h
    LEFT JOIN dbo.opcion_evento AS oe ON «EJ:oe:h»oe.id_opcion_evento = h.id_opcion_evento
    LEFT JOIN dbo.opcion_aplicacion AS o ON «EJ:o:oe»o.id_opcion = oe.id_opcion
    LEFT JOIN dbo.evento_permiso AS e ON «EJ:e:oe»e.id_evento = oe.id_evento
    WHERE «E:h»(@sujeto_tipo IS NULL OR h.sujeto_tipo = @sujeto_tipo) AND (@id_sujeto IS NULL OR h.id_sujeto = @id_sujeto)
    ORDER BY h.fecha DESC;
END;""",
]
PROCEDURE_NAMES = tuple(re.search(r"PROCEDURE app\.(\w+)", p).group(1) for p in _PROCEDURES)


def sqlserver_extras(multi: bool) -> List[str]:
    """Lotes de SQL Server después de las tablas: llaves, historial inalterable y procedimientos app.permisos_*."""
    keys = "--| Plantilla de permisos: llaves únicas, llaves foráneas y reglas de consistencia |\n" + "\n".join(
        _once(kind, name, _adapt(statement, multi)) for kind, name, statement in _KEYS)
    return [keys, _TRIGGER, *(_adapt(p, multi) for p in _PROCEDURES)]
