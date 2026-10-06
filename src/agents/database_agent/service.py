"""Casos de uso de Nexus sobre una conexión (SQL Server, PostgreSQL, Firebird o MongoDB): esquema, procedimientos, DDL y respaldos."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from src.agents.database_agent.catalog import BACKUPS, PROCEDURES, DatabaseCatalog
from src.agents.database_agent.database_agent import IDENTIFIER, SchemaManager, TableDefinition
from src.agents.database_agent.dialects import get_dialect
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError

VERSION = "1.1.0"
PARAMETER = re.compile(r"^@[A-Za-z0-9_]{1,127}$")
LABEL = re.compile(r"^[A-Za-z0-9_\-]{1,50}$")
SCALARS = (str, int, float, bool, type(None))
CAPABILITY_LABELS = {PROCEDURES: "procedimientos almacenados", BACKUPS: "respaldos"}


def split_name(nombre: str, default_schema: Optional[str] = "dbo") -> Tuple[Optional[str], str]:
    """'esquema.objeto' u 'objeto' (esquema por defecto del motor); solo identificadores simples."""
    parts = (nombre or "").split(".")
    if len(parts) == 1:
        parts = [default_schema, parts[0]]
    if len(parts) != 2 or not all(IDENTIFIER.match(p) for p in parts if p is not None):
        raise InvalidInputError(f"Nombre inválido: {nombre!r} (usa esquema.objeto con letras, números y '_')")
    return parts[0], parts[1]


def _qualified(schema: Optional[str], name: str) -> str:
    return f"{schema}.{name}" if schema else name


class NexusService:
    def __init__(self, catalog: DatabaseCatalog, backup_dir: Optional[str] = None, max_rows: int = 1000) -> None:
        self._catalog = catalog
        self._dialect = catalog.dialect
        self._schema = SchemaManager(self._dialect)
        self._backup_dir = backup_dir
        self._max_rows = max_rows

    @property
    def max_rows(self) -> int:
        return self._max_rows

    @property
    def motor(self) -> str:
        return self._dialect.motor

    def ping(self) -> None:
        self._catalog.ping()

    def info(self) -> Dict[str, Any]:
        return {
            "motor": self._dialect.motor,
            "nombre_motor": self._dialect.nombre,
            "lenguaje_ddl": self._dialect.lenguaje,
            "esquema_por_defecto": self._dialect.default_schema,
            "capacidades": sorted(self._catalog.capacidades),
        }

    def _require(self, capability: str) -> None:
        if capability not in self._catalog.capacidades:
            raise InvalidInputError(f"{self._dialect.nombre} no admite {CAPABILITY_LABELS[capability]}")

    def _split(self, nombre: str) -> Tuple[Optional[str], str]:
        schema, name = split_name(nombre, self._dialect.default_schema)
        return self._dialect.resolve_schema(schema), name

    # ================================================================ esquema

    def tables(self) -> Dict[str, Any]:
        tables = self._catalog.list_tables()
        return {"motor": self.motor, "total": len(tables), "tablas": tables}

    def table(self, nombre: str) -> Dict[str, Any]:
        schema, table = self._split(nombre)
        detail = self._catalog.describe_table(schema, table)
        if detail is None:
            raise NotFoundError(f"Tabla no encontrada: {_qualified(schema, table)}")
        return detail

    def _manager(self, motor: Optional[str]) -> SchemaManager:
        if not motor:
            return self._schema
        try:
            return SchemaManager(get_dialect(motor))
        except ValueError as e:
            raise InvalidInputError(str(e))

    def generate_ddl(self, definition: TableDefinition, motor: Optional[str] = None) -> Dict[str, Any]:
        """DDL en el motor de la conexión, o en otro motor (de MOTORES) sin tocar ninguna base."""
        manager = self._manager(motor)
        valid, error = manager.validate_schema(definition)
        if not valid:
            raise InvalidInputError(f"Definición de tabla inválida: {error}")
        try:
            ddl = manager.create_table(definition)
        except ValueError as e:
            raise InvalidInputError(f"Definición de tabla inválida: {e}")
        return {
            "motor": manager.dialect.motor,
            "lenguaje_ddl": manager.dialect.lenguaje,
            "tabla": manager.dialect.qualified_name(definition.schema, definition.name),
            "ddl": ddl,
            "hash_esquema": manager.get_schema_hash(definition),
        }

    def create_table(self, definition: TableDefinition) -> Dict[str, Any]:
        generated = self.generate_ddl(definition)
        if self._catalog.describe_table(self._dialect.resolve_schema(definition.schema), definition.name) is not None:
            raise ConflictError(f"La tabla {generated['tabla']} ya existe")
        self._catalog.apply_ddl(generated["ddl"])
        return {**generated, "creada": True}

    # ================================================================ procedimientos

    def procedures(self) -> Dict[str, Any]:
        self._require(PROCEDURES)
        procedures = self._catalog.list_procedures()
        return {"total": len(procedures), "procedimientos": procedures}

    def _parameters(self, schema: Optional[str], name: str):
        parameters = self._catalog.procedure_parameters(schema, name)
        if parameters is None:
            raise NotFoundError(f"Procedimiento no encontrado: {_qualified(schema, name)}")
        return parameters

    def procedure(self, nombre: str) -> Dict[str, Any]:
        self._require(PROCEDURES)
        schema, name = self._split(nombre)
        parameters = self._parameters(schema, name)
        return {
            "esquema": schema,
            "nombre": name,
            "parametros": [
                {"nombre": p.nombre, "tipo": p.tipo, "longitud": p.longitud, "salida": p.salida} for p in parameters
            ],
            "definicion": self._catalog.procedure_definition(schema, name),
        }

    def execute_procedure(self, nombre: str, parametros: Dict[str, Any], max_filas: Optional[int] = None) -> Dict[str, Any]:
        self._require(PROCEDURES)
        schema, name = self._split(nombre)
        declared = {p.nombre.lower(): p for p in self._parameters(schema, name)}
        arguments: Dict[str, Any] = {}
        for key, value in (parametros or {}).items():
            param = declared.get(("@" + key.lstrip("@")).lower())
            if param is None:
                raise InvalidInputError(f"El procedimiento {_qualified(schema, name)} no tiene el parámetro {key!r}")
            if param.salida:
                raise InvalidInputError(f"El parámetro de salida {param.nombre} no se admite")
            if not isinstance(value, SCALARS):
                raise InvalidInputError(f"El parámetro {param.nombre} debe ser texto, número, booleano o null")
            if not PARAMETER.match(param.nombre):
                raise InvalidInputError(f"Nombre de parámetro no soportado: {param.nombre}")
            arguments[param.nombre] = value
        limit = max(1, min(max_filas or self._max_rows, self._max_rows))
        result = self._catalog.execute_procedure(schema, name, arguments, limit)
        return {
            "procedimiento": _qualified(schema, name),
            "parametros": list(arguments),
            "max_filas": limit,
            "conjuntos_resultado": result.conjuntos,
        }

    # ================================================================ respaldos

    def backup(self, etiqueta: str = "manual") -> Dict[str, Any]:
        self._require(BACKUPS)
        if not LABEL.match(etiqueta or ""):
            raise InvalidInputError("etiqueta solo admite letras, números, '_' y '-' (máx. 50)")
        return self._catalog.backup(self._backup_dir, etiqueta)

    def backups(self, limite: int = 20) -> Dict[str, Any]:
        self._require(BACKUPS)
        entries = self._catalog.list_backups(self._backup_dir, max(1, min(limite, 200)))
        return {"total": len(entries), "respaldos": entries}
