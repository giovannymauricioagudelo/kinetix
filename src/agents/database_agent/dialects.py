"""Dialectos de Nexus: traducen una TableDefinition al DDL de cada motor (SQL Server, PostgreSQL, Firebird y MongoDB)."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.agents.database_agent.database_agent import (
    IDENTIFIER,
    NUMERIC_TYPES,
    SQL_FUNCTION_DEFAULTS,
    ColumnDefinition,
    ColumnType,
    TableDefinition,
    quote_identifier,
    sql_string,
)

_NUMBER = re.compile(r"-?\d+(\.\d+)?")
_BOOLEANS = {"true": True, "1": True, "false": False, "0": False}
UTC_FUNCTIONS = frozenset({"GETUTCDATE()", "SYSUTCDATETIME()"})
LOCAL_FUNCTIONS = frozenset({"GETDATE()", "SYSDATETIME()", "CURRENT_TIMESTAMP"})


def _description(table_def: TableDefinition) -> str:
    return table_def.description.replace("|", "/").replace("\n", " ") if table_def.description else table_def.name


def _indexed_tenant_columns(table_def: TableDefinition) -> List[str]:
    return [column for flag, column in ((table_def.company_column, "empresa_id"), (table_def.warehouse_column, "bodega_id")) if flag]


def _ansi_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ansi_quote(name: str) -> str:
    if not IDENTIFIER.match(name or ""):
        raise ValueError(f"Identificador inválido: {name!r}")
    return f'"{name}"'


class Dialect(ABC):
    motor: str
    nombre: str
    lenguaje: str = "sql"
    default_schema: Optional[str] = None

    def resolve_schema(self, schema: Optional[str]) -> Optional[str]:
        """Esquema real en el motor; None si el motor no tiene esquemas."""
        return None

    def qualified_name(self, schema: Optional[str], name: str) -> str:
        resolved = self.resolve_schema(schema)
        return f"{resolved}.{name}" if resolved else name

    def default_literal(self, column: ColumnDefinition) -> str:
        """Default traducido al literal del motor; ValueError si no es válido para el tipo o el motor."""
        raw = column.default.strip()
        if raw.upper() in SQL_FUNCTION_DEFAULTS:
            return self.function_default(raw.upper(), column)
        if column.type == ColumnType.BOOLEAN:
            if raw.lower() not in _BOOLEANS:
                raise ValueError(f"Default inválido para BOOLEAN en {column.name}: {raw}")
            return self.boolean(_BOOLEANS[raw.lower()])
        if column.type in NUMERIC_TYPES:
            if not _NUMBER.fullmatch(raw):
                raise ValueError(f"Default numérico inválido en {column.name}: {raw}")
            return raw
        if len(raw) >= 2 and raw[0] == raw[-1] == "'":
            raw = raw[1:-1]
        return self.string(raw)

    @abstractmethod
    def function_default(self, function: str, column: ColumnDefinition) -> str: ...

    @abstractmethod
    def boolean(self, value: bool) -> str: ...

    @abstractmethod
    def string(self, value: str) -> str: ...

    @abstractmethod
    def create_table(self, table_def: TableDefinition) -> str: ...


# ============================================================================ SQL Server


class SqlServerDialect(Dialect):
    motor, nombre = "sqlserver", "SQL Server"
    default_schema = "dbo"
    TYPES = {
        ColumnType.VARCHAR: "NVARCHAR(255)",
        ColumnType.INT: "INT",
        ColumnType.BIGINT: "BIGINT",
        ColumnType.DECIMAL: "DECIMAL(18,2)",
        ColumnType.BOOLEAN: "BIT",
        ColumnType.DATETIME: "DATETIME2",
        ColumnType.TEXT: "NVARCHAR(MAX)",
        ColumnType.JSON: "NVARCHAR(MAX)",
    }

    def resolve_schema(self, schema: Optional[str]) -> Optional[str]:
        return schema or self.default_schema

    def function_default(self, function: str, column: ColumnDefinition) -> str:
        return function

    def boolean(self, value: bool) -> str:
        return "1" if value else "0"

    def string(self, value: str) -> str:
        return sql_string(value)

    def create_table(self, table_def: TableDefinition) -> str:
        """Script T-SQL idempotente en un solo lote (PK CLUSTERED, índices multisector)."""
        schema, table = quote_identifier(table_def.schema), quote_identifier(table_def.name)
        object_name = sql_string(f"{table_def.schema}.{table_def.name}")

        column_lines = []
        for col in table_def.columns:
            name = quote_identifier(col.name)
            nullable = col.nullable and not col.primary_key
            col_def = f"        {name} {self.TYPES[col.type]} {'NULL' if nullable else 'NOT NULL'}"
            if col.default:
                col_def += f" CONSTRAINT [DF_{table_def.name}_{col.name}] DEFAULT {self.default_literal(col)}"
            if col.primary_key:
                col_def += f" CONSTRAINT [PK_{table_def.name}] PRIMARY KEY CLUSTERED"
            elif col.unique:
                col_def += f" CONSTRAINT [UQ_{table_def.name}_{col.name}] UNIQUE"
            if col.type == ColumnType.JSON:
                col_def += f" CONSTRAINT [CK_{table_def.name}_{col.name}_json] CHECK (ISJSON({name}) = 1)"
            column_lines.append(col_def)

        if table_def.audit_columns:
            column_lines.extend([
                f"        [created_at] DATETIME2 NOT NULL CONSTRAINT [DF_{table_def.name}_created_at] DEFAULT SYSUTCDATETIME()",
                f"        [updated_at] DATETIME2 NOT NULL CONSTRAINT [DF_{table_def.name}_updated_at] DEFAULT SYSUTCDATETIME()",
                "        [created_by] NVARCHAR(100) NULL",
            ])

        ddl_lines = [
            f"--| Tabla {table_def.schema}.{table_def.name}: {_description(table_def)} |",
            f"IF OBJECT_ID({object_name}, N'U') IS NULL",
            "BEGIN",
            f"    CREATE TABLE {schema}.{table} (",
            ",\n".join(column_lines),
            "    );",
            "END;",
        ]

        for column in _indexed_tenant_columns(table_def):
            index = f"idx_{table_def.name}_{column}"
            ddl_lines.extend([
                f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = {sql_string(index)} AND object_id = OBJECT_ID({object_name}))",
                f"    CREATE INDEX [{index}] ON {schema}.{table} ([{column}]);",
            ])

        if table_def.description:
            ddl_lines.append(
                "IF NOT EXISTS (SELECT 1 FROM sys.extended_properties WHERE major_id = OBJECT_ID("
                f"{object_name}) AND minor_id = 0 AND name = N'MS_Description')\n"
                f"    EXEC sys.sp_addextendedproperty @name = N'MS_Description', @value = {sql_string(table_def.description)}, "
                f"@level0type = N'SCHEMA', @level0name = {sql_string(table_def.schema)}, "
                f"@level1type = N'TABLE', @level1name = {sql_string(table_def.name)};"
            )
        return "\n".join(ddl_lines)


# ============================================================================ PostgreSQL


class PostgresDialect(Dialect):
    motor, nombre = "postgresql", "PostgreSQL"
    default_schema = "public"
    TYPES = {
        ColumnType.VARCHAR: "VARCHAR(255)",
        ColumnType.INT: "INTEGER",
        ColumnType.BIGINT: "BIGINT",
        ColumnType.DECIMAL: "NUMERIC(18,2)",
        ColumnType.BOOLEAN: "BOOLEAN",
        ColumnType.DATETIME: "TIMESTAMP",
        ColumnType.TEXT: "TEXT",
        ColumnType.JSON: "JSONB",
    }
    UTC_NOW = "(NOW() AT TIME ZONE 'utc')"

    def resolve_schema(self, schema: Optional[str]) -> Optional[str]:
        return self.default_schema if not schema or schema == SqlServerDialect.default_schema else schema

    def function_default(self, function: str, column: ColumnDefinition) -> str:
        if function == "NULL":
            return "NULL"
        if function in UTC_FUNCTIONS:
            return self.UTC_NOW
        if function in LOCAL_FUNCTIONS:
            return "LOCALTIMESTAMP"
        return "gen_random_uuid()::text"

    def boolean(self, value: bool) -> str:
        return "TRUE" if value else "FALSE"

    def string(self, value: str) -> str:
        return _ansi_string(value)

    def create_table(self, table_def: TableDefinition) -> str:
        """Script idempotente (IF NOT EXISTS) con PK, UNIQUE, índices multisector y COMMENT ON TABLE."""
        schema = self.resolve_schema(table_def.schema)
        target = f"{_ansi_quote(schema)}.{_ansi_quote(table_def.name)}"
        name = table_def.name

        column_lines = []
        for col in table_def.columns:
            nullable = col.nullable and not col.primary_key
            col_def = f"    {_ansi_quote(col.name)} {self.TYPES[col.type]} {'NULL' if nullable else 'NOT NULL'}"
            if col.default:
                col_def += f" DEFAULT {self.default_literal(col)}"
            if col.primary_key:
                col_def += f' CONSTRAINT "pk_{name}" PRIMARY KEY'
            elif col.unique:
                col_def += f' CONSTRAINT "uq_{name}_{col.name}" UNIQUE'
            column_lines.append(col_def)
        if table_def.audit_columns:
            column_lines.extend([
                f'    "created_at" TIMESTAMP NOT NULL DEFAULT {self.UTC_NOW}',
                f'    "updated_at" TIMESTAMP NOT NULL DEFAULT {self.UTC_NOW}',
                '    "created_by" VARCHAR(100) NULL',
            ])

        lines = [f"--| Tabla {schema}.{name}: {_description(table_def)} |"]
        if schema != self.default_schema:
            lines.append(f"CREATE SCHEMA IF NOT EXISTS {_ansi_quote(schema)};")
        lines.extend([f"CREATE TABLE IF NOT EXISTS {target} (", ",\n".join(column_lines), ");"])
        for column in _indexed_tenant_columns(table_def):
            lines.append(f'CREATE INDEX IF NOT EXISTS "idx_{name}_{column}" ON {target} ("{column}");')
        if table_def.description:
            lines.append(f"COMMENT ON TABLE {target} IS {self.string(table_def.description)};")
        return "\n".join(lines)


# ============================================================================ Firebird


_SET_TERM = re.compile(r"^\s*SET\s+TERM\b.*$", re.IGNORECASE | re.MULTILINE)
_LINE_COMMENT = re.compile(r"^\s*--.*$", re.MULTILINE)
_TERMINATOR = re.compile(r"\^\s*$", re.MULTILINE)


def firebird_statements(script: str) -> List[str]:
    """Sentencias de un script isql con 'SET TERM ^ ;' (el formato que genera FirebirdDialect)."""
    code = _LINE_COMMENT.sub("", _SET_TERM.sub("", script.replace("\r\n", "\n")))
    return [statement.strip() for statement in _TERMINATOR.split(code) if statement.strip()]


class FirebirdDialect(Dialect):
    """Firebird 3+: sin esquemas; los identificadores sin comillas se guardan en mayúsculas."""

    motor, nombre = "firebird", "Firebird"
    TYPES = {
        ColumnType.VARCHAR: "VARCHAR(255) CHARACTER SET UTF8",
        ColumnType.INT: "INTEGER",
        ColumnType.BIGINT: "BIGINT",
        ColumnType.DECIMAL: "DECIMAL(18,2)",
        ColumnType.BOOLEAN: "BOOLEAN",
        ColumnType.DATETIME: "TIMESTAMP",
        ColumnType.TEXT: "BLOB SUB_TYPE TEXT CHARACTER SET UTF8",
        ColumnType.JSON: "BLOB SUB_TYPE TEXT CHARACTER SET UTF8",
    }

    @staticmethod
    def quote(name: str) -> str:
        return _ansi_quote(name).upper()

    def qualified_name(self, schema: Optional[str], name: str) -> str:
        return name.upper()

    def function_default(self, function: str, column: ColumnDefinition) -> str:
        if function == "NULL":
            return "NULL"
        if function in LOCAL_FUNCTIONS:
            return "CURRENT_TIMESTAMP"
        if function in UTC_FUNCTIONS:
            raise ValueError(f"Firebird solo admite variables de contexto como DEFAULT: usa CURRENT_TIMESTAMP en {column.name}")
        raise ValueError(f"Firebird no admite {function} como DEFAULT en {column.name}")

    def boolean(self, value: bool) -> str:
        return "TRUE" if value else "FALSE"

    def string(self, value: str) -> str:
        return _ansi_string(value)

    def if_missing(self, system_table: str, column: str, object_name: str, statement: str) -> str:
        return (
            "EXECUTE BLOCK AS\nBEGIN\n"
            f"    IF (NOT EXISTS (SELECT 1 FROM {system_table} WHERE {column} = {self.string(object_name)})) THEN\n"
            f"        EXECUTE STATEMENT {self.string(statement)};\n"
            "END^\nCOMMIT^"
        )

    def create_table(self, table_def: TableDefinition) -> str:
        """Script isql con SET TERM: cada objeto se crea solo si falta y se confirma antes del siguiente."""
        table = table_def.name.upper()
        column_lines = []
        for col in table_def.columns:
            nullable = col.nullable and not col.primary_key
            col_def = f"    {self.quote(col.name)} {self.TYPES[col.type]}"
            if col.default:
                col_def += f" DEFAULT {self.default_literal(col)}"
            if not nullable:
                col_def += " NOT NULL"
            if col.primary_key:
                col_def += f' CONSTRAINT "PK_{table}" PRIMARY KEY'
            elif col.unique:
                col_def += f' CONSTRAINT "UQ_{table}_{col.name.upper()}" UNIQUE'
            column_lines.append(col_def)
        if table_def.audit_columns:
            column_lines.extend([
                '    "CREATED_AT" TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL',
                '    "UPDATED_AT" TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL',
                '    "CREATED_BY" VARCHAR(100) CHARACTER SET UTF8',
            ])
        create = f'CREATE TABLE "{table}" (\n' + ",\n".join(column_lines) + "\n)"

        parts = [
            f"--| Tabla {table}: {_description(table_def)} |",
            "SET TERM ^ ;",
            self.if_missing("RDB$RELATIONS", "RDB$RELATION_NAME", table, create),
        ]
        for column in _indexed_tenant_columns(table_def):
            index = f"IDX_{table}_{column.upper()}"
            parts.append(self.if_missing("RDB$INDICES", "RDB$INDEX_NAME", index,
                                          f'CREATE INDEX "{index}" ON "{table}" ("{column.upper()}")'))
        if table_def.description:
            parts.append(f'COMMENT ON TABLE "{table}" IS {self.string(_description(table_def))}^\nCOMMIT^')
        parts.append("SET TERM ; ^")
        return "\n".join(parts)


# ============================================================================ MongoDB


class MongoDialect(Dialect):
    """Colección con validador $jsonSchema e índices; MongoDB no aplica defaults, se documentan en el validador."""

    motor, nombre = "mongodb", "MongoDB"
    lenguaje = "json"
    BSON_TYPES: Dict[ColumnType, Any] = {
        ColumnType.VARCHAR: "string",
        ColumnType.INT: "int",
        ColumnType.BIGINT: ["long", "int"],
        ColumnType.DECIMAL: "number",
        ColumnType.BOOLEAN: "bool",
        ColumnType.DATETIME: "date",
        ColumnType.TEXT: "string",
        ColumnType.JSON: ["object", "array"],
    }
    ALLOWED_COMMANDS = frozenset({"create", "createIndexes", "collMod"})

    def function_default(self, function: str, column: ColumnDefinition) -> str:
        return function

    def boolean(self, value: bool) -> str:
        return "true" if value else "false"

    def string(self, value: str) -> str:
        return value

    def _property(self, col: ColumnDefinition, nullable: bool) -> Dict[str, Any]:
        types = self.BSON_TYPES[col.type]
        types = list(types) if isinstance(types, list) else [types]
        if nullable:
            types.append("null")
        spec: Dict[str, Any] = {"bsonType": types[0] if len(types) == 1 else types}
        if col.type == ColumnType.VARCHAR:
            spec["maxLength"] = 255
        if col.default:
            spec["description"] = f"default: {self.default_literal(col)}"
        return spec

    def _index(self, name: str, column: ColumnDefinition, unique: bool) -> Dict[str, Any]:
        index: Dict[str, Any] = {"key": {column.name: 1}, "name": name}
        if unique:
            index["unique"] = True
            if column.nullable and not column.primary_key:
                bson = "number" if column.type in NUMERIC_TYPES else self.BSON_TYPES[column.type]
                index["partialFilterExpression"] = {column.name: {"$type": bson}}
        return index

    def create_table(self, table_def: TableDefinition) -> str:
        """Lista JSON de comandos de base de datos: create (con validador) y createIndexes."""
        for name in (table_def.name, *(c.name for c in table_def.columns)):
            _ansi_quote(name)
        name = table_def.name
        properties: Dict[str, Any] = {}
        required: List[str] = []
        indexes: List[Dict[str, Any]] = []
        by_name = {c.name: c for c in table_def.columns}
        for col in table_def.columns:
            nullable = col.nullable and not col.primary_key
            properties[col.name] = self._property(col, nullable)
            if not nullable:
                required.append(col.name)
            if col.primary_key:
                indexes.append(self._index(f"pk_{name}", col, unique=True))
            elif col.unique:
                indexes.append(self._index(f"uq_{name}_{col.name}", col, unique=True))
        if table_def.audit_columns:
            properties.update({
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
                "created_by": {"bsonType": ["string", "null"], "maxLength": 100},
            })
            required.extend(["created_at", "updated_at"])
        for column in _indexed_tenant_columns(table_def):
            indexes.append(self._index(f"idx_{name}_{column}", by_name[column], unique=False))

        schema: Dict[str, Any] = {"bsonType": "object", "title": name, "properties": properties}
        if required:
            schema["required"] = required
        if table_def.description:
            schema["description"] = table_def.description
        commands: List[Dict[str, Any]] = [
            {"create": name, "validator": {"$jsonSchema": schema}, "validationLevel": "strict", "validationAction": "error"}
        ]
        if indexes:
            commands.append({"createIndexes": name, "indexes": indexes})
        return json.dumps(commands, indent=2, ensure_ascii=False)


# ============================================================================ registro


DIALECTS: Dict[str, Dialect] = {d.motor: d for d in (SqlServerDialect(), PostgresDialect(), FirebirdDialect(), MongoDialect())}
MOTORES = tuple(DIALECTS)


def get_dialect(motor: Optional[str]) -> Dialect:
    key = (motor or SqlServerDialect.motor).strip().lower()
    if key not in DIALECTS:
        raise ValueError(f"Motor no soportado: {motor!r} (usa {', '.join(MOTORES)})")
    return DIALECTS[key]
