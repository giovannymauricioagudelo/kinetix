"""Plantilla de licencias por empresa (asientos y/o módulos) que Nexus agrega a toda aplicación.

Monetización fundamental: el tenant tiene una suscripción a un plan con cupo de usuarios y funciones
(feature flags). Permiso RBAC ≠ licencia (pagó / tiene cupo). Errores propios: 52101–52199.
Ver .cursor/rules/licencias-por-empresa.mdc.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from src.agents.database_agent.database_agent import ColumnDefinition, ColumnType, TableDefinition

LICENSES_KIND = "licencias"
LICENSES_VERSION = 1
LICENSES_MIGRATION = "licencias_por_empresa"
ADMIN_OPTION = "suscripcion"
COMPANY_COLUMN = "id_empresa"

# Catálogo de módulos monetizables (código → nombre). Las apps pueden ampliarlo en funciones JSON.
MODULOS_ESTANDAR = (
    ("contratos", "Contratos"),
    ("mensajeria", "Mensajería / WhatsApp"),
    ("destacados", "Destacados / promociones"),
    ("ia", "Asistente / IA"),
    ("reportes", "Reportes avanzados"),
    ("integraciones", "Integraciones"),
)

RECURSOS_LIMITE = (
    "usuarios",
    "almacenamiento_mb",
    "consultas_ia",
    "mensajes_whatsapp",
    "registros_activos",
)


def definition(multi: bool, rls: bool) -> Dict[str, Any]:
    return {
        "tipo": LICENSES_KIND,
        "version": LICENSES_VERSION,
        "multiempresa": bool(multi),
        "seguridad_por_fila": bool(rls),
    }


def catalogo_opcion() -> Dict[str, Any]:
    """Opción de menú que toda app debe declarar en security/permisos_catalogo.json."""
    return {
        "codigo": ADMIN_OPTION,
        "nombre": "Suscripción y licencias",
        "ruta": "/suscripcion",
        "icono": "suscripcion",
        "orden": 910,
        "es_menu": True,
        "eventos": ["acceder", "consultar", "actualizar"],
        "eventos_mfa": ["actualizar"],
    }


def catalogo_modulos() -> List[Dict[str, str]]:
    return [{"codigo": c, "nombre": n} for c, n in MODULOS_ESTANDAR]


# ============================================================================ tablas portables


def _col(name: str, kind: ColumnType, nullable: bool = True, default: str = None, pk: bool = False) -> ColumnDefinition:
    return ColumnDefinition(name=name, type=kind, nullable=nullable and not pk, default=default, primary_key=pk)


V, I, B, D, J, N = (
    ColumnType.VARCHAR,
    ColumnType.INT,
    ColumnType.BOOLEAN,
    ColumnType.DATETIME,
    ColumnType.JSON,
    ColumnType.DECIMAL,
)

_TABLES = (
    (
        "plan_suscripcion",
        "Catálogo de planes: precio, prueba y funciones (módulos licensiados)",
        True,
        [
            _col("id_plan", V, pk=True),
            _col("codigo", V, False),
            _col("nombre", V, False),
            _col("descripcion", V),
            _col("precio_mensual", N, False, "0"),
            _col("precio_anual", N),
            _col("moneda", V, False, "'COP'"),
            _col("dias_prueba", I, False, "0"),
            _col("es_gratuito", B, False, "false"),
            _col("es_personalizado", B, False, "false"),
            _col("publico", B, False, "true"),
            _col("funciones", J),
            _col("orden", I, False, "0"),
            _col("estado", V, False, "'activo'"),
            _col("version", I, False, "1"),
        ],
    ),
    (
        "limite_plan",
        "Límites del plan: usuarios (asientos) y otros recursos monetizables",
        True,
        [
            _col("id_limite_plan", V, pk=True),
            _col("id_plan", V, False),
            _col("recurso", V, False),
            _col("valor", I),
            _col("es_ilimitado", B, False, "false"),
            _col("periodo", V, False, "'total'"),
            _col("accion_al_superar", V, False, "'bloquear'"),
            _col("porcentaje_alerta", I, False, "80"),
            _col("precio_adicional", N),
        ],
    ),
    (
        "suscripcion",
        "Suscripción del tenant: plan, estado, periodo y personalizaciones de límites/funciones",
        True,
        [
            _col("id_suscripcion", V, pk=True),
            _col("id_plan", V, False),
            _col("estado", V, False, "'prueba'"),
            _col("ciclo", V, False, "'mensual'"),
            _col("precio_acordado", N, False, "0"),
            _col("moneda", V, False, "'COP'"),
            _col("fecha_inicio", D, False),
            _col("fecha_fin_prueba", D),
            _col("periodo_inicio", D),
            _col("periodo_fin", D),
            _col("proximo_cobro", D),
            _col("dias_gracia", I, False, "5"),
            _col("fecha_gracia_hasta", D),
            _col("limites_personalizados", J),
            _col("funciones_personalizadas", J),
            _col("version", I, False, "1"),
        ],
    ),
)
TABLE_NAMES = tuple(name for name, *_ in _TABLES)


def tables(multi: bool) -> List[TableDefinition]:
    company = [_col(COMPANY_COLUMN, V, False)] if multi else []
    return [
        TableDefinition(
            name=name,
            columns=[*company, *columns],
            company_column=False,
            warehouse_column=False,
            audit_columns=audit,
            description=description,
        )
        for name, description, audit, columns in _TABLES
    ]


# ============================================================================ SQL Server

_EMP_DECL = (
    "DECLARE @id_empresa NVARCHAR(255) = CAST(SESSION_CONTEXT(N'id_empresa') AS NVARCHAR(255));\n"
    "    IF @id_empresa IS NULL THROW 51000, N'La sesión no tiene empresa (SESSION_CONTEXT id_empresa).', 1;"
)


def _adapt(sql: str, multi: bool) -> str:
    if multi:
        sql = sql.replace("«EMP»", _EMP_DECL)
        sql = re.sub(r"«E:(\w+)»", r"\1.id_empresa = @id_empresa AND ", sql)
        return (
            sql.replace("«EC»", "id_empresa, ")
            .replace("«EV»", "@id_empresa, ")
            .replace("«EK»", "id_empresa, ")
        )
    sql = re.sub(r"«EMP»\n\s*", "", sql)
    sql = re.sub(r"«E:[\w]+»", "", sql)
    for mark in ("«EC»", "«EV»", "«EK»"):
        sql = sql.replace(mark, "")
    return sql


def _once(kind: str, name: str, statement: str) -> str:
    lookup = {
        "index": f"SELECT 1 FROM sys.indexes WHERE name = N'{name}'",
        "constraint": f"SELECT 1 FROM sys.objects WHERE name = N'{name}'",
    }[kind]
    return f"IF NOT EXISTS ({lookup})\n    {statement}"


_KEYS = [
    (
        "index",
        "ux_plan_suscripcion_codigo",
        "CREATE UNIQUE INDEX ux_plan_suscripcion_codigo ON dbo.plan_suscripcion («EK»codigo);",
    ),
    (
        "index",
        "ux_limite_plan_recurso",
        "CREATE UNIQUE INDEX ux_limite_plan_recurso ON dbo.limite_plan («EK»id_plan, recurso);",
    ),
    (
        "index",
        "idx_suscripcion_estado",
        "CREATE INDEX idx_suscripcion_estado ON dbo.suscripcion («EK»estado, fecha_inicio DESC);",
    ),
    (
        "constraint",
        "fk_limite_plan_plan",
        "ALTER TABLE dbo.limite_plan ADD CONSTRAINT fk_limite_plan_plan "
        "FOREIGN KEY (id_plan) REFERENCES dbo.plan_suscripcion (id_plan);",
    ),
    (
        "constraint",
        "fk_suscripcion_plan",
        "ALTER TABLE dbo.suscripcion ADD CONSTRAINT fk_suscripcion_plan "
        "FOREIGN KEY (id_plan) REFERENCES dbo.plan_suscripcion (id_plan);",
    ),
    (
        "constraint",
        "ck_limite_plan_recurso",
        "ALTER TABLE dbo.limite_plan ADD CONSTRAINT ck_limite_plan_recurso "
        "CHECK (recurso IN (N'usuarios', N'almacenamiento_mb', N'consultas_ia', "
        "N'mensajes_whatsapp', N'registros_activos'));",
    ),
    (
        "constraint",
        "ck_limite_plan_accion",
        "ALTER TABLE dbo.limite_plan ADD CONSTRAINT ck_limite_plan_accion "
        "CHECK (accion_al_superar IN (N'bloquear', N'cobrar_adicional', N'avisar'));",
    ),
    (
        "constraint",
        "ck_limite_plan_valor",
        "ALTER TABLE dbo.limite_plan ADD CONSTRAINT ck_limite_plan_valor "
        "CHECK (es_ilimitado = 1 OR (valor IS NOT NULL AND valor >= 0));",
    ),
    (
        "constraint",
        "ck_suscripcion_estado",
        "ALTER TABLE dbo.suscripcion ADD CONSTRAINT ck_suscripcion_estado "
        "CHECK (estado IN (N'prueba', N'activa', N'en_gracia', N'solo_lectura', "
        "N'suspendida', N'cancelada', N'vencida'));",
    ),
    (
        "constraint",
        "ck_plan_suscripcion_estado",
        "ALTER TABLE dbo.plan_suscripcion ADD CONSTRAINT ck_plan_suscripcion_estado "
        "CHECK (estado IN (N'activo', N'inactivo'));",
    ),
]

_PROCEDURES = [
    """--| Resumen de licencia del tenant: asientos y funciones efectivas (br_lic_*) |
CREATE OR ALTER PROCEDURE app.licencia_resumen
AS
BEGIN
    SET NOCOUNT ON;
    «EMP»
    DECLARE @id_plan NVARCHAR(255) = NULL;
    DECLARE @estado NVARCHAR(40) = NULL;
    DECLARE @codigo NVARCHAR(80) = NULL;
    DECLARE @func_plan NVARCHAR(MAX) = NULL;
    DECLARE @func_pers NVARCHAR(MAX) = NULL;
    DECLARE @lim_pers NVARCHAR(MAX) = NULL;
    DECLARE @cupo INT = NULL;
    DECLARE @ilimitado BIT = 0;

    SELECT TOP (1)
        @id_plan = s.id_plan,
        @estado = s.estado,
        @func_pers = s.funciones_personalizadas,
        @lim_pers = s.limites_personalizados
    FROM dbo.suscripcion AS s
    WHERE «E:s»s.estado IN (N'prueba', N'activa', N'en_gracia', N'solo_lectura', N'suspendida')
    ORDER BY s.fecha_inicio DESC;

    SELECT TOP (1)
        @codigo = p.codigo,
        @func_plan = p.funciones
    FROM dbo.plan_suscripcion AS p
    WHERE «E:p»p.id_plan = @id_plan;

    SELECT TOP (1)
        @cupo = lp.valor,
        @ilimitado = lp.es_ilimitado
    FROM dbo.limite_plan AS lp
    WHERE «E:lp»lp.id_plan = @id_plan AND lp.recurso = N'usuarios';

    SELECT
        @codigo AS codigo_plan,
        @estado AS estado,
        @cupo AS cupo_usuarios,
        @ilimitado AS usuarios_ilimitados,
        @func_plan AS funciones_plan,
        @func_pers AS funciones_personalizadas,
        @lim_pers AS limites_personalizados,
        @id_plan AS id_plan;
END;""",
    """--| Bloquea si el cupo de asientos (usuarios) está agotado; @usados y @pendientes los calcula la app o el caller |
CREATE OR ALTER PROCEDURE app.licencia_assert_asiento
    @usados INT,
    @pendientes INT = 0
AS
BEGIN
    SET NOCOUNT ON;
    «EMP»
    DECLARE @id_plan NVARCHAR(255) = NULL;
    DECLARE @estado NVARCHAR(40) = NULL;
    DECLARE @cupo INT = NULL;
    DECLARE @ilimitado BIT = 0;
    DECLARE @lim_pers NVARCHAR(MAX) = NULL;

    SELECT TOP (1)
        @id_plan = s.id_plan,
        @estado = s.estado,
        @lim_pers = s.limites_personalizados
    FROM dbo.suscripcion AS s
    WHERE «E:s»s.estado IN (N'prueba', N'activa', N'en_gracia', N'solo_lectura', N'suspendida')
    ORDER BY s.fecha_inicio DESC;

    IF @estado IS NOT NULL AND @estado NOT IN (N'prueba', N'activa', N'en_gracia')
        THROW 52101, N'Tu suscripción no permite altas de usuarios ahora.', 1;

    SELECT TOP (1) @cupo = lp.valor, @ilimitado = lp.es_ilimitado
    FROM dbo.limite_plan AS lp
    WHERE «E:lp»lp.id_plan = @id_plan AND lp.recurso = N'usuarios';

    IF @lim_pers IS NOT NULL AND ISJSON(@lim_pers) = 1
    BEGIN
        IF JSON_VALUE(@lim_pers, N'$.usuarios.es_ilimitado') IN (N'true', N'1')
            SET @ilimitado = 1;
        ELSE IF JSON_VALUE(@lim_pers, N'$.usuarios.valor') IS NOT NULL
        BEGIN
            SET @cupo = TRY_CAST(JSON_VALUE(@lim_pers, N'$.usuarios.valor') AS INT);
            SET @ilimitado = 0;
        END
    END

    IF @ilimitado = 1 RETURN;
    IF @cupo IS NULL SET @cupo = 3;
    IF (ISNULL(@usados, 0) + ISNULL(@pendientes, 0)) >= @cupo
        THROW 52102, N'Tu plan permite hasta el máximo de usuarios de equipo.', 1;
END;""",
    """--| Exige que el módulo esté en funciones del plan o en personalización del tenant |
CREATE OR ALTER PROCEDURE app.licencia_assert_modulo
    @modulo NVARCHAR(80)
AS
BEGIN
    SET NOCOUNT ON;
    «EMP»
    DECLARE @id_plan NVARCHAR(255) = NULL;
    DECLARE @estado NVARCHAR(40) = NULL;
    DECLARE @func_plan NVARCHAR(MAX) = NULL;
    DECLARE @func_pers NVARCHAR(MAX) = NULL;
    DECLARE @incluido BIT = 0;

    SELECT TOP (1)
        @id_plan = s.id_plan,
        @estado = s.estado,
        @func_pers = s.funciones_personalizadas
    FROM dbo.suscripcion AS s
    WHERE «E:s»s.estado IN (N'prueba', N'activa', N'en_gracia', N'solo_lectura', N'suspendida')
    ORDER BY s.fecha_inicio DESC;

    IF @estado IS NOT NULL AND @estado NOT IN (N'prueba', N'activa', N'en_gracia')
        THROW 52101, N'Tu suscripción no permite usar módulos de pago ahora.', 1;

    SELECT TOP (1) @func_plan = p.funciones
    FROM dbo.plan_suscripcion AS p
    WHERE «E:p»p.id_plan = @id_plan;

    IF @func_pers IS NOT NULL AND ISJSON(@func_pers) = 1
       AND JSON_VALUE(@func_pers, N'$.' + @modulo) IN (N'true', N'1')
        SET @incluido = 1;
    ELSE IF @func_plan IS NOT NULL AND ISJSON(@func_plan) = 1
       AND JSON_VALUE(@func_plan, N'$.' + @modulo) IN (N'true', N'1')
        SET @incluido = 1;

    IF @incluido = 0
        THROW 52103, N'Tu plan no incluye ese módulo. Mejora el plan para activarlo.', 1;
END;""",
    """--| Personaliza límites y/o funciones de la suscripción vigente del tenant |
CREATE OR ALTER PROCEDURE app.licencia_personalizar
    @funciones_personalizadas NVARCHAR(MAX) = NULL,
    @limites_personalizados NVARCHAR(MAX) = NULL,
    @actualizar_funciones BIT = 0,
    @actualizar_limites BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    «EMP»
    DECLARE @ahora DATETIME2 = SYSUTCDATETIME();
    DECLARE @id_suscripcion NVARCHAR(255) = (
        SELECT TOP (1) s.id_suscripcion FROM dbo.suscripcion AS s
        WHERE «E:s»s.estado IN (N'prueba', N'activa', N'en_gracia', N'solo_lectura', N'suspendida')
        ORDER BY s.fecha_inicio DESC
    );
    UPDATE s
    SET funciones_personalizadas = CASE WHEN @actualizar_funciones = 1 THEN @funciones_personalizadas
                                        ELSE s.funciones_personalizadas END,
        limites_personalizados = CASE WHEN @actualizar_limites = 1 THEN @limites_personalizados
                                      ELSE s.limites_personalizados END,
        updated_at = @ahora
    FROM dbo.suscripcion AS s
    WHERE «E:s»s.id_suscripcion = @id_suscripcion;
    SELECT @@ROWCOUNT AS afectadas;
END;""",
]

PROCEDURE_NAMES = tuple(re.search(r"PROCEDURE app\.(\w+)", p).group(1) for p in _PROCEDURES)


def sqlserver_extras(multi: bool) -> List[str]:
    keys = [_adapt(_once(kind, name, stmt), multi) for kind, name, stmt in _KEYS]
    procs = [_adapt(p, multi) for p in _PROCEDURES]
    return [*keys, *procs]
