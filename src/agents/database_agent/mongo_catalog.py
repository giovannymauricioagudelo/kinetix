"""Catálogo de Nexus sobre MongoDB (pymongo): colecciones como tablas, su validador $jsonSchema como columnas,
índices, DDL como lista JSON de comandos (create, createIndexes, collMod) y respaldos con mongodump.
MongoDB no tiene esquemas ni procedimientos almacenados."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.agents.database_agent.catalog import DatabaseCatalog, ProcedureParameter, ProcedureResult
from src.agents.database_agent.dialects import MongoDialect
from src.agents.database_agent.engines import MongoSettings
from src.agents.database_agent.file_backups import backup_entry, backup_target, list_backup_files, run_tool, tool_path
from src.agents.security_agent.models import InvalidInputError

NAMESPACE_EXISTS = 48


def columns_from_validator(validator: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    schema = (validator or {}).get("$jsonSchema") or {}
    required = set(schema.get("required") or [])
    columns = []
    for name, spec in (schema.get("properties") or {}).items():
        types = spec.get("bsonType", spec.get("type", "any"))
        types = types if isinstance(types, list) else [types]
        columns.append({
            "nombre": name, "tipo": ", ".join(t for t in types if t != "null") or "null", "longitud": spec.get("maxLength"),
            "precision": None, "escala": None, "nulable": "null" in types or name not in required, "identidad": False,
            "default": None, "descripcion": spec.get("description"),
        })
    return columns


def parse_commands(script: str) -> List[Dict[str, Any]]:
    """Solo comandos de definición permitidos; el nombre del comando es la primera llave (como exige MongoDB)."""
    try:
        commands = json.loads(script)
    except ValueError as e:
        raise InvalidInputError(f"El DDL de MongoDB debe ser una lista JSON de comandos: {e}") from None
    if not isinstance(commands, list) or not commands or not all(isinstance(c, dict) and c for c in commands):
        raise InvalidInputError("El DDL de MongoDB debe ser una lista JSON no vacía de comandos")
    for command in commands:
        name = next(iter(command))
        if name not in MongoDialect.ALLOWED_COMMANDS:
            raise InvalidInputError(f"Comando de MongoDB no permitido: {name} (solo {', '.join(sorted(MongoDialect.ALLOWED_COMMANDS))})")
    return commands


class MongoCatalog(DatabaseCatalog):
    motor = "mongodb"

    def __init__(self, settings: MongoSettings, timeout_seconds: int = 30, backup_timeout_seconds: int = 600,
                 database: Any = None) -> None:
        self._settings = settings
        self._timeout = timeout_seconds
        self._backup_timeout = backup_timeout_seconds
        self._database = database

    @property
    def _db(self):
        if self._database is None:
            from pymongo import MongoClient

            client = MongoClient(self._settings.uri, appname="kinetix-nexus", tz_aware=True,
                                 serverSelectionTimeoutMS=self._timeout * 1000, socketTimeoutMS=self._timeout * 1000)
            self._database = client[self._settings.database]
        return self._database

    def ping(self) -> None:
        self._db.command("ping")

    def list_tables(self) -> List[Dict[str, Any]]:
        names = sorted(c["name"] for c in self._db.list_collections(filter={"type": "collection"})
                       if not c["name"].startswith("system."))
        return [{"esquema": None, "tabla": name, "filas": int(self._db[name].estimated_document_count()),
                 "creada": None, "modificada": None} for name in names]

    def describe_table(self, schema: Optional[str], table: str) -> Optional[Dict[str, Any]]:
        info = next(iter(self._db.list_collections(filter={"name": table, "type": "collection"})), None)
        if info is None:
            return None
        collection = self._db[table]
        validator = (info.get("options") or {}).get("validator")
        indexes = [
            {"nombre": name, "tipo": ", ".join(f"{field}:{direction}" for field, direction in spec["key"]),
             "unico": bool(spec.get("unique")) or name == "_id_", "clave_primaria": name == "_id_",
             "columnas": [field for field, _ in spec["key"]]}
            for name, spec in collection.index_information().items()
        ]
        return {
            "esquema": None, "tabla": table, "filas": int(collection.estimated_document_count()), "filas_estimadas": True,
            "columnas": columns_from_validator(validator), "validador": validator is not None,
            "clave_primaria": ["_id"], "indices": indexes, "claves_foraneas": [],
        }

    def list_procedures(self) -> List[Dict[str, Any]]:
        return []

    def procedure_parameters(self, schema: Optional[str], name: str) -> Optional[List[ProcedureParameter]]:
        return None

    def procedure_definition(self, schema: Optional[str], name: str) -> Optional[str]:
        return None

    def execute_procedure(self, schema: Optional[str], name: str, arguments: Dict[str, Any], max_rows: int) -> ProcedureResult:
        raise InvalidInputError("MongoDB no tiene procedimientos almacenados")

    def apply_ddl(self, script: str) -> None:
        from pymongo.errors import OperationFailure

        for command in parse_commands(script):
            name = next(iter(command))
            try:
                self._db.command(command)
            except OperationFailure as e:
                if name == "create" and e.code == NAMESPACE_EXISTS:
                    continue
                message = (e.details or {}).get("errmsg") or str(e)
                raise InvalidInputError(f"MongoDB rechazó {name}: {message[:500]}") from None

    def _run_with_config(self, args: List[str]) -> None:
        """La URI (con la clave) va en un archivo --config temporal, no en la línea de comandos."""
        handle, config = tempfile.mkstemp(prefix="nexus_mongo_", suffix=".yaml")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as f:
                f.write(f"uri: {json.dumps(self._settings.uri)}\n")
            run_tool([*args[:1], f"--config={config}", *args[1:]], None, self._backup_timeout)
        finally:
            os.remove(config)

    def backup(self, directory: Optional[str], label: str) -> Dict[str, Any]:
        database = self._settings.database
        path = backup_target(directory, database, label, ".archive.gz")
        started = datetime.now(timezone.utc)
        self._run_with_config([tool_path("mongodump"), f"--db={database}", f"--archive={path}", "--gzip"])
        self._run_with_config([tool_path("mongorestore"), f"--archive={path}", "--gzip", "--dryRun",
                               f"--nsInclude={database}.*"])
        return backup_entry(path, database, started, verified=True)

    def list_backups(self, directory: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return list_backup_files(directory, self._settings.database, ".archive.gz", limit)
