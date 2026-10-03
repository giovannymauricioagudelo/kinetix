"""Casos de uso de Nexus sobre SQL Server: esquema, procedimientos almacenados, DDL y respaldos."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from src.agents.database_agent.catalog import DatabaseCatalog
from src.agents.database_agent.database_agent import IDENTIFIER, SchemaManager, TableDefinition
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError

VERSION = "1.0.0"
PARAMETER = re.compile(r"^@[A-Za-z0-9_]{1,127}$")
LABEL = re.compile(r"^[A-Za-z0-9_\-]{1,50}$")
SCALARS = (str, int, float, bool, type(None))


def split_name(nombre: str) -> Tuple[str, str]:
    """'esquema.objeto' u 'objeto' (dbo por defecto); solo identificadores simples."""
    parts = (nombre or "").split(".")
    if len(parts) == 1:
        parts = ["dbo", parts[0]]
    if len(parts) != 2 or not all(IDENTIFIER.match(p) for p in parts):
        raise InvalidInputError(f"Nombre inválido: {nombre!r} (usa esquema.objeto con letras, números y '_')")
    return parts[0], parts[1]


class NexusService:
    def __init__(self, catalog: DatabaseCatalog, backup_dir: Optional[str] = None, max_rows: int = 1000) -> None:
        self._catalog = catalog
        self._schema = SchemaManager()
        self._backup_dir = backup_dir
        self._max_rows = max_rows

    @property
    def max_rows(self) -> int:
        return self._max_rows

    def ping(self) -> None:
        self._catalog.ping()

    # ================================================================ esquema

    def tables(self) -> Dict[str, Any]:
        tables = self._catalog.list_tables()
        return {"total": len(tables), "tablas": tables}

    def table(self, nombre: str) -> Dict[str, Any]:
        schema, table = split_name(nombre)
        detail = self._catalog.describe_table(schema, table)
        if detail is None:
            raise NotFoundError(f"Tabla no encontrada: {schema}.{table}")
        return detail

    def _validated(self, definition: TableDefinition) -> None:
        valid, error = self._schema.validate_schema(definition)
        if not valid:
            raise InvalidInputError(f"Definición de tabla inválida: {error}")

    def generate_ddl(self, definition: TableDefinition) -> Dict[str, Any]:
        self._validated(definition)
        return {
            "tabla": f"{definition.schema}.{definition.name}",
            "ddl": self._schema.create_table(definition),
            "hash_esquema": self._schema.get_schema_hash(definition),
        }

    def create_table(self, definition: TableDefinition) -> Dict[str, Any]:
        generated = self.generate_ddl(definition)
        if self._catalog.describe_table(definition.schema, definition.name) is not None:
            raise ConflictError(f"La tabla {generated['tabla']} ya existe")
        self._catalog.apply_ddl(generated["ddl"])
        return {**generated, "creada": True}

    # ================================================================ procedimientos

    def procedures(self) -> Dict[str, Any]:
        procedures = self._catalog.list_procedures()
        return {"total": len(procedures), "procedimientos": procedures}

    def _parameters(self, schema: str, name: str):
        parameters = self._catalog.procedure_parameters(schema, name)
        if parameters is None:
            raise NotFoundError(f"Procedimiento no encontrado: {schema}.{name}")
        return parameters

    def procedure(self, nombre: str) -> Dict[str, Any]:
        schema, name = split_name(nombre)
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
        schema, name = split_name(nombre)
        declared = {p.nombre.lower(): p for p in self._parameters(schema, name)}
        arguments: Dict[str, Any] = {}
        for key, value in (parametros or {}).items():
            param = declared.get(("@" + key.lstrip("@")).lower())
            if param is None:
                raise InvalidInputError(f"El procedimiento {schema}.{name} no tiene el parámetro {key!r}")
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
            "procedimiento": f"{schema}.{name}",
            "parametros": list(arguments),
            "max_filas": limit,
            "conjuntos_resultado": result.conjuntos,
        }

    # ================================================================ respaldos

    def backup(self, etiqueta: str = "manual") -> Dict[str, Any]:
        if not LABEL.match(etiqueta or ""):
            raise InvalidInputError("etiqueta solo admite letras, números, '_' y '-' (máx. 50)")
        return self._catalog.backup(self._backup_dir, etiqueta)

    def backups(self, limite: int = 20) -> Dict[str, Any]:
        entries = self._catalog.list_backups(max(1, min(limite, 200)))
        return {"total": len(entries), "respaldos": entries}
