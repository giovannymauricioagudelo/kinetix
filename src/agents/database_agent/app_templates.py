"""Plantillas por motor de las migraciones de las aplicaciones de Nexus.

Las tablas y la base multiempresa se guardan como definición neutral (JSON canónico, con su checksum) y el
script se genera para el motor que tenga la aplicación al desplegar: así una aplicación puede pasar, por
ejemplo, de MongoDB a SQL Server. El SQL escrito a mano queda atado a su motor y necesita equivalentes.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Optional

from src.agents.database_agent.database_agent import ColumnDefinition, ColumnType, TableDefinition, quote_identifier, sql_string
from src.agents.database_agent.dialects import (
    MOTORES,
    FirebirdDialect,
    MongoDialect,
    PostgresDialect,
    SqlServerDialect,
)
from src.agents.database_agent.mongo_catalog import parse_commands
from src.agents.security_agent.models import InvalidInputError

BASE_KIND = "base_multiempresa"
TABLE_KIND = "tabla"
COMPANY_COLUMN = "id_empresa"
RLS_ENGINES = frozenset({"sqlserver", "postgresql"})
FK_ENGINES = frozenset({"sqlserver", "postgresql", "firebird"})
MAX_SCRIPT_CHARS = 200_000

BASE_MULTIEMPRESA = """--| Base multiempresa: catálogo de empresas y función de filtro para seguridad por fila |
IF OBJECT_ID(N'dbo.empresas', N'U') IS NULL
    CREATE TABLE dbo.empresas (
        id_empresa NVARCHAR(255) NOT NULL CONSTRAINT PK_empresas PRIMARY KEY CLUSTERED,
        nombre NVARCHAR(200) NOT NULL,
        estado NVARCHAR(20) NOT NULL CONSTRAINT DF_empresas_estado DEFAULT N'activa',
        fecha_creacion DATETIME2 NOT NULL CONSTRAINT DF_empresas_fecha DEFAULT SYSUTCDATETIME()
    );
GO
IF SCHEMA_ID(N'seguridad') IS NULL EXEC(N'CREATE SCHEMA seguridad');
GO
IF OBJECT_ID(N'seguridad.fn_filtro_empresa', N'IF') IS NULL
    EXEC(N'CREATE FUNCTION seguridad.fn_filtro_empresa(@id_empresa NVARCHAR(255))
RETURNS TABLE WITH SCHEMABINDING AS
RETURN SELECT 1 AS permitido
WHERE @id_empresa = CAST(SESSION_CONTEXT(N''id_empresa'') AS NVARCHAR(255)) OR IS_ROLEMEMBER(N''db_owner'') = 1');
"""

POSTGRES_BASE = """--| Base multiempresa: catálogo de empresas (la seguridad por fila usa current_setting('app.id_empresa')) |
CREATE TABLE IF NOT EXISTS "public"."empresas" (
    "id_empresa" VARCHAR(255) NOT NULL CONSTRAINT "pk_empresas" PRIMARY KEY,
    "nombre" VARCHAR(200) NOT NULL,
    "estado" VARCHAR(20) NOT NULL DEFAULT 'activa',
    "fecha_creacion" TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);
"""


def canonical(definition: Dict[str, Any]) -> str:
    return json.dumps(definition, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def base_definition(rls: bool) -> Dict[str, Any]:
    return {"tipo": BASE_KIND, "version": 1, "seguridad_por_fila": bool(rls)}


def table_definition(table: TableDefinition, multi: bool, rls: bool) -> Dict[str, Any]:
    return {"tipo": TABLE_KIND, "version": 1, "multiempresa": bool(multi), "seguridad_por_fila": bool(rls),
            "tabla": table.model_dump(mode="json")}


def definition_table(definition: Dict[str, Any]) -> TableDefinition:
    return TableDefinition.model_validate(definition["tabla"])


def _companies_table() -> TableDefinition:
    return TableDefinition(name="empresas", columns=[
        ColumnDefinition(name=COMPANY_COLUMN, type=ColumnType.VARCHAR, nullable=False, primary_key=True),
        ColumnDefinition(name="nombre", type=ColumnType.VARCHAR, nullable=False),
        ColumnDefinition(name="estado", type=ColumnType.VARCHAR, nullable=False, default="activa"),
        ColumnDefinition(name="fecha_creacion", type=ColumnType.DATETIME, nullable=False, default="CURRENT_TIMESTAMP"),
    ], company_column=False, warehouse_column=False, audit_columns=False, description="Empresas de la aplicación")


# ============================================================================ SQL Server


def _sqlserver_table(table: TableDefinition, multi: bool, rls: bool) -> str:
    quoted_schema, quoted_table = quote_identifier(table.schema), quote_identifier(table.name)
    parts = []
    if table.schema != "dbo":
        parts.append(f"IF SCHEMA_ID({sql_string(table.schema)}) IS NULL EXEC(N'CREATE SCHEMA {quoted_schema}');")
    parts.append(SqlServerDialect().create_table(table))
    if multi:
        name = table.name
        object_name = sql_string(f"{table.schema}.{name}")
        index, fk, policy = f"idx_{name}_{COMPANY_COLUMN}", f"FK_{name}_empresas", f"politica_{name}"
        parts.append(
            f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = {sql_string(index)} AND object_id = OBJECT_ID({object_name}))\n"
            f"    CREATE INDEX [{index}] ON {quoted_schema}.{quoted_table} ([{COMPANY_COLUMN}]);\n"
            f"IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = {sql_string(fk)})\n"
            f"    ALTER TABLE {quoted_schema}.{quoted_table} ADD CONSTRAINT [{fk}] FOREIGN KEY ([{COMPANY_COLUMN}]) "
            "REFERENCES dbo.empresas (id_empresa);"
        )
        if rls:
            target = f"{quoted_schema}.{quoted_table}"
            predicate = f"seguridad.fn_filtro_empresa({COMPANY_COLUMN})"
            statement = (f"CREATE SECURITY POLICY seguridad.[{policy}] ADD FILTER PREDICATE {predicate} ON {target}, "
                         f"ADD BLOCK PREDICATE {predicate} ON {target} AFTER INSERT, "
                         f"ADD BLOCK PREDICATE {predicate} ON {target} AFTER UPDATE WITH (STATE = ON);")
            parts.append(
                f"IF NOT EXISTS (SELECT 1 FROM sys.security_policies WHERE name = {sql_string(policy)})\n"
                f"    EXEC({sql_string(statement)});"
            )
    return "\nGO\n".join(parts) + "\n"


# ============================================================================ PostgreSQL


def _pg_once(condition: str, statement: str) -> str:
    return f"DO $nexus$ BEGIN\n    IF NOT EXISTS ({condition}) THEN\n        {statement};\n    END IF;\nEND $nexus$;"


def _postgres_table(table: TableDefinition, multi: bool, rls: bool) -> str:
    dialect = PostgresDialect()
    schema, name = dialect.resolve_schema(table.schema), table.name
    target = f'"{schema}"."{name}"'
    parts = [dialect.create_table(table)]
    if multi:
        parts.append(f'CREATE INDEX IF NOT EXISTS "idx_{name}_{COMPANY_COLUMN}" ON {target} ("{COMPANY_COLUMN}");')
        parts.append(_pg_once(
            f"SELECT 1 FROM pg_constraint WHERE conname = 'fk_{name}_empresas'",
            f'ALTER TABLE {target} ADD CONSTRAINT "fk_{name}_empresas" FOREIGN KEY ("{COMPANY_COLUMN}") '
            f'REFERENCES "public"."empresas" ("{COMPANY_COLUMN}")',
        ))
        if rls:
            predicate = f"\"{COMPANY_COLUMN}\" = current_setting('app.id_empresa', true)"
            parts.append(f"ALTER TABLE {target} ENABLE ROW LEVEL SECURITY;")
            parts.append(_pg_once(
                f"SELECT 1 FROM pg_policies WHERE schemaname = '{schema}' AND tablename = '{name}' "
                f"AND policyname = 'politica_{name}'",
                f'CREATE POLICY "politica_{name}" ON {target} USING ({predicate}) WITH CHECK ({predicate})',
            ))
    return "\n".join(parts) + "\n"


# ============================================================================ Firebird


def _firebird_extra(blocks) -> str:
    return "\n".join(["SET TERM ^ ;", *blocks, "SET TERM ; ^"])


def _firebird_table(table: TableDefinition, multi: bool, rls: bool) -> str:
    dialect = FirebirdDialect()
    script = dialect.create_table(table)
    if not multi:
        return script + "\n"
    name, column = table.name.upper(), COMPANY_COLUMN.upper()
    index, fk = f"IDX_{name}_{column}", f"FK_{name}_EMPRESAS"
    return script + "\n" + _firebird_extra([
        dialect.if_missing("RDB$INDICES", "RDB$INDEX_NAME", index, f'CREATE INDEX "{index}" ON "{name}" ("{column}")'),
        dialect.if_missing("RDB$RELATION_CONSTRAINTS", "RDB$CONSTRAINT_NAME", fk,
                           f'ALTER TABLE "{name}" ADD CONSTRAINT "{fk}" FOREIGN KEY ("{column}") REFERENCES "EMPRESAS" ("{column}")'),
    ]) + "\n"


# ============================================================================ MongoDB


def _mongo_table(table: TableDefinition, multi: bool, rls: bool) -> str:
    commands = json.loads(MongoDialect().create_table(table))
    if multi:
        commands.append({"createIndexes": table.name,
                         "indexes": [{"key": {COMPANY_COLUMN: 1}, "name": f"idx_{table.name}_{COMPANY_COLUMN}"}]})
    return json.dumps(commands, indent=2, ensure_ascii=False)


TABLE_RENDERERS: Dict[str, Callable[[TableDefinition, bool, bool], str]] = {
    "sqlserver": _sqlserver_table,
    "postgresql": _postgres_table,
    "firebird": _firebird_table,
    "mongodb": _mongo_table,
}
BASE_RENDERERS: Dict[str, Callable[[], str]] = {
    "sqlserver": lambda: BASE_MULTIEMPRESA,
    "postgresql": lambda: POSTGRES_BASE,
    "firebird": lambda: FirebirdDialect().create_table(_companies_table()) + "\n",
    "mongodb": lambda: MongoDialect().create_table(_companies_table()),
}


def render(definition: Dict[str, Any], motor: str) -> str:
    """Script de la definición neutral para el motor; ValueError si el motor no admite algo de la tabla."""
    if definition["tipo"] == BASE_KIND:
        return BASE_RENDERERS[motor]()
    return TABLE_RENDERERS[motor](definition_table(definition), definition["multiempresa"], definition["seguridad_por_fila"])


# ============================================================================ SQL escrito a mano


_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
COMMON_FORBIDDEN = (
    (r"\bUSE\s+\[?\w", "USE (la base la elige Nexus)"),
    (r"\b(CREATE|ALTER|DROP)\s+DATABASE\b", "CREATE/ALTER/DROP DATABASE"),
    (r"\b(CREATE|ALTER|DROP)\s+LOGIN\b", "CREATE/ALTER/DROP LOGIN"),
    (r"\b(ALTER|CONTROL)\s+SERVER\b|\bSERVER\s+ROLE\b", "permisos de servidor"),
    (r"\bxp_\w+|\bsp_configure\b|\bRECONFIGURE\b|\bSHUTDOWN\b", "procedimientos de sistema"),
    (r"\bOPEN(ROWSET|DATASOURCE|QUERY)\b", "acceso a datos externos"),
    (r"\b(BACKUP|RESTORE)\b", "BACKUP/RESTORE (usa los respaldos de Nexus)"),
    (r"\bEXEC(UTE)?\s*\(|\bsp_executesql\b|\bEXECUTE\s+AS\b|\bIMPERSONATE\b", "SQL dinámico o suplantación"),
    (r"\bDROP\s+(TABLE|SCHEMA|SECURITY\s+POLICY|POLICY)\b|\bTRUNCATE\b", "borrado de objetos (las migraciones solo agregan)"),
    (r"\bdespliegue\s*\.|\bseguridad\s*\.|\bdespliegue_migraciones\b", "objetos internos de Nexus (despliegue, seguridad)"),
)
ENGINE_FORBIDDEN = {
    "postgresql": (
        (r"\bCOPY\b[^;]*\bPROGRAM\b", "COPY ... PROGRAM"),
        (r"\bpg_(read|write|ls|stat)_\w*|\blo_(import|export)\b", "archivos del servidor"),
        (r"\bdblink\w*|\bpostgres_fdw\b|\bCREATE\s+(SERVER|EXTENSION)\b", "acceso a otras bases o extensiones"),
        (r"\bALTER\s+SYSTEM\b|\bSET\s+(ROLE|SESSION\s+AUTHORIZATION)\b|\b(CREATE|ALTER|DROP)\s+(ROLE|USER)\b",
         "roles o configuración del servidor"),
        (r"\b(DISABLE|NO\s+FORCE)\s+ROW\s+LEVEL\s+SECURITY\b", "desactivar la seguridad por fila"),
        (r"\bLANGUAGE\s+(plpython\w*|plperlu|c)\b", "lenguajes no confiables"),
    ),
    "firebird": (
        (r"\bEXTERNAL\s+(FILE|NAME|FUNCTION)\b|\bON\s+EXTERNAL\b|\bDECLARE\s+EXTERNAL\b|\bENGINE\s+\w+",
         "acceso externo o funciones externas"),
        (r"\b(CREATE|ALTER|DROP)\s+(USER|ROLE)\b", "usuarios o roles"),
    ),
}


def validate_script(script: str, motor: str = "sqlserver") -> str:
    """Script de una migración manual para el motor dado; rechaza instrucciones peligrosas o que borran objetos."""
    if motor not in MOTORES:
        raise InvalidInputError(f"Motor no soportado: {motor!r}")
    if not script or not script.strip():
        raise InvalidInputError("El script está vacío")
    if len(script) > MAX_SCRIPT_CHARS:
        raise InvalidInputError(f"El script supera {MAX_SCRIPT_CHARS} caracteres")
    if motor == "mongodb":
        for command in parse_commands(script):
            target = str(command[next(iter(command))])
            if target.startswith(("_nexus_", "system.")):
                raise InvalidInputError(f"La colección {target} es interna")
        return script.replace("\r\n", "\n").lstrip("\ufeff")
    code = _COMMENTS.sub(" ", script)
    for pattern, label in (*COMMON_FORBIDDEN, *ENGINE_FORBIDDEN.get(motor, ())):
        if re.search(pattern, code, re.IGNORECASE):
            raise InvalidInputError(f"El script contiene una instrucción no permitida: {label}")
    return script.replace("\r\n", "\n").lstrip("\ufeff")


def engine_warnings(motor: str, multi: bool, rls: bool) -> list:
    warnings = []
    if multi and rls and motor not in RLS_ENGINES:
        warnings.append(f"{motor} no tiene seguridad por fila: la aplicación debe filtrar siempre por {COMPANY_COLUMN}")
    if multi and motor not in FK_ENGINES:
        warnings.append(f"{motor} no aplica llaves foráneas: la aplicación debe validar {COMPANY_COLUMN} contra empresas")
    return warnings


def default_engine_reason(motor: Optional[str]) -> str:
    return {
        "sqlserver": "estándar corporativo; seguridad por fila y transacciones ACID",
        "postgresql": "relacional de código abierto; seguridad por fila y JSONB",
        "firebird": "relacional embebible y liviano; sin seguridad por fila",
        "mongodb": "documentos con esquema flexible; sin llaves foráneas ni seguridad por fila",
    }.get(motor or "", "")
