"""Acceso de Nexus al catálogo y operaciones de SQL Server: contrato, implementación real y doble en memoria."""

from __future__ import annotations

import base64
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pyodbc

from src.agents.security_agent.models import InvalidInputError
from src.agents.sqlserver import SqlServerClient, is_statement_error, server_message


@dataclass(frozen=True)
class ProcedureParameter:
    nombre: str
    tipo: str
    longitud: Optional[int]
    salida: bool
    tiene_default: bool


@dataclass
class ProcedureResult:
    conjuntos: List[Dict[str, Any]] = field(default_factory=list)


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value) if abs(value) < Decimal("1e15") else str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode()
    return value


def _length(type_name: str, max_length: int) -> Optional[int]:
    if max_length == -1:
        return None
    return max_length // 2 if type_name in ("nvarchar", "nchar") else max_length


class DatabaseCatalog(ABC):
    @abstractmethod
    def ping(self) -> None: ...

    @abstractmethod
    def list_tables(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def describe_table(self, schema: str, table: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def list_procedures(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def procedure_parameters(self, schema: str, name: str) -> Optional[List[ProcedureParameter]]:
        """None si el procedimiento no existe."""

    @abstractmethod
    def procedure_definition(self, schema: str, name: str) -> Optional[str]: ...

    @abstractmethod
    def execute_procedure(self, schema: str, name: str, arguments: Dict[str, Any], max_rows: int) -> ProcedureResult: ...

    @abstractmethod
    def apply_ddl(self, script: str) -> None: ...

    @abstractmethod
    def backup(self, directory: Optional[str], label: str) -> Dict[str, Any]: ...

    @abstractmethod
    def list_backups(self, limit: int) -> List[Dict[str, Any]]: ...


class SqlServerCatalog(DatabaseCatalog):
    def __init__(self, client: SqlServerClient, backup_timeout_seconds: int = 600) -> None:
        self._db = client
        self._backup_timeout = backup_timeout_seconds

    def ping(self) -> None:
        self._db.ping()

    def list_tables(self) -> List[Dict[str, Any]]:
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT s.name, t.name, SUM(CASE WHEN p.index_id IN (0, 1) THEN p.rows ELSE 0 END), t.create_date, t.modify_date "
                "FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id "
                "LEFT JOIN sys.partitions p ON p.object_id = t.object_id "
                "WHERE t.is_ms_shipped = 0 GROUP BY s.name, t.name, t.create_date, t.modify_date ORDER BY s.name, t.name"
            )
            return [
                {"esquema": r[0], "tabla": r[1], "filas": int(r[2] or 0), "creada": json_value(r[3]), "modificada": json_value(r[4])}
                for r in cur.fetchall()
            ]

    def describe_table(self, schema: str, table: str) -> Optional[Dict[str, Any]]:
        with self._db.cursor() as cur:
            cur.execute("SELECT OBJECT_ID(QUOTENAME(?) + '.' + QUOTENAME(?), 'U')", (schema, table))
            object_id = cur.fetchone()[0]
            if object_id is None:
                return None
            cur.execute(
                "SELECT c.name, ty.name, c.max_length, c.precision, c.scale, c.is_nullable, c.is_identity, dc.definition "
                "FROM sys.columns c JOIN sys.types ty ON ty.user_type_id = c.user_type_id "
                "LEFT JOIN sys.default_constraints dc ON dc.object_id = c.default_object_id "
                "WHERE c.object_id = ? ORDER BY c.column_id",
                (object_id,),
            )
            columns = [
                {
                    "nombre": r[0], "tipo": r[1], "longitud": _length(r[1], r[2]),
                    "precision": r[3] if r[1] in ("decimal", "numeric") else None,
                    "escala": r[4] if r[1] in ("decimal", "numeric") else None,
                    "nulable": bool(r[5]), "identidad": bool(r[6]), "default": r[7],
                }
                for r in cur.fetchall()
            ]
            cur.execute(
                "SELECT i.name, i.type_desc, i.is_unique, i.is_primary_key, c.name "
                "FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id "
                "JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id "
                "WHERE i.object_id = ? AND i.name IS NOT NULL AND ic.is_included_column = 0 ORDER BY i.index_id, ic.key_ordinal",
                (object_id,),
            )
            indexes: Dict[str, Dict[str, Any]] = {}
            for name, kind, unique, primary, column in cur.fetchall():
                entry = indexes.setdefault(name, {"nombre": name, "tipo": kind, "unico": bool(unique), "clave_primaria": bool(primary), "columnas": []})
                entry["columnas"].append(column)
            cur.execute(
                "SELECT fk.name, pc.name, rs.name, rt.name, rc.name "
                "FROM sys.foreign_keys fk JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id "
                "JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id "
                "JOIN sys.tables rt ON rt.object_id = fkc.referenced_object_id JOIN sys.schemas rs ON rs.schema_id = rt.schema_id "
                "JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id "
                "WHERE fk.parent_object_id = ? ORDER BY fk.name, fkc.constraint_column_id",
                (object_id,),
            )
            foreign_keys = [
                {"nombre": r[0], "columna": r[1], "referencia": f"{r[2]}.{r[3]}", "columna_referenciada": r[4]}
                for r in cur.fetchall()
            ]
            cur.execute("SELECT SUM(rows) FROM sys.partitions WHERE object_id = ? AND index_id IN (0, 1)", (object_id,))
            rows = int(cur.fetchone()[0] or 0)
        primary = next((i["columnas"] for i in indexes.values() if i["clave_primaria"]), [])
        return {
            "esquema": schema, "tabla": table, "filas": rows, "columnas": columns, "clave_primaria": primary,
            "indices": list(indexes.values()), "claves_foraneas": foreign_keys,
        }

    def _parameters(self, cur, object_id: int) -> List[ProcedureParameter]:
        cur.execute(
            "SELECT p.name, t.name, p.max_length, p.is_output, p.has_default_value FROM sys.parameters p "
            "JOIN sys.types t ON t.user_type_id = p.user_type_id WHERE p.object_id = ? AND p.parameter_id > 0 ORDER BY p.parameter_id",
            (object_id,),
        )
        return [ProcedureParameter(r[0], r[1], _length(r[1], r[2]), bool(r[3]), bool(r[4])) for r in cur.fetchall()]

    def _procedure_id(self, cur, schema: str, name: str) -> Optional[int]:
        cur.execute(
            "SELECT p.object_id FROM sys.procedures p JOIN sys.schemas s ON s.schema_id = p.schema_id "
            "WHERE s.name = ? AND p.name = ? AND p.is_ms_shipped = 0",
            (schema, name),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def list_procedures(self) -> List[Dict[str, Any]]:
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT p.object_id, s.name, p.name, p.create_date, p.modify_date FROM sys.procedures p "
                "JOIN sys.schemas s ON s.schema_id = p.schema_id WHERE p.is_ms_shipped = 0 ORDER BY s.name, p.name"
            )
            procedures = cur.fetchall()
            cur.execute(
                "SELECT p.object_id, p.name FROM sys.parameters p JOIN sys.procedures pr ON pr.object_id = p.object_id "
                "WHERE pr.is_ms_shipped = 0 AND p.parameter_id > 0 ORDER BY p.object_id, p.parameter_id"
            )
            params: Dict[int, List[str]] = {}
            for object_id, name in cur.fetchall():
                params.setdefault(object_id, []).append(name)
        return [
            {"esquema": r[1], "nombre": r[2], "parametros": params.get(r[0], []), "creado": json_value(r[3]), "modificado": json_value(r[4])}
            for r in procedures
        ]

    def procedure_parameters(self, schema: str, name: str) -> Optional[List[ProcedureParameter]]:
        with self._db.cursor() as cur:
            object_id = self._procedure_id(cur, schema, name)
            return None if object_id is None else self._parameters(cur, object_id)

    def procedure_definition(self, schema: str, name: str) -> Optional[str]:
        with self._db.cursor() as cur:
            object_id = self._procedure_id(cur, schema, name)
            if object_id is None:
                return None
            cur.execute("SELECT OBJECT_DEFINITION(?)", (object_id,))
            return cur.fetchone()[0]

    def execute_procedure(self, schema: str, name: str, arguments: Dict[str, Any], max_rows: int) -> ProcedureResult:
        assignments = ", ".join(f"{param} = ?" for param in arguments)
        sql = f"SET NOCOUNT ON; EXEC [{schema}].[{name}] {assignments}".rstrip()
        result = ProcedureResult()
        try:
            with self._db.cursor(commit=True) as cur:
                cur.execute(sql, tuple(arguments.values()))
                while True:
                    if cur.description:
                        columns = [d[0] for d in cur.description]
                        rows = cur.fetchmany(max_rows + 1)
                        result.conjuntos.append({
                            "columnas": columns,
                            "filas": [[json_value(v) for v in row] for row in rows[:max_rows]],
                            "truncado": len(rows) > max_rows,
                        })
                    if not cur.nextset():
                        break
        except pyodbc.Error as e:
            if is_statement_error(e):
                raise InvalidInputError(f"El procedimiento falló: {server_message(e)}") from None
            raise
        return result

    def apply_ddl(self, script: str) -> None:
        try:
            with self._db.cursor(commit=True) as cur:
                cur.execute(script)
                while cur.nextset():
                    pass
        except pyodbc.Error as e:
            if is_statement_error(e):
                raise InvalidInputError(f"SQL Server rechazó el DDL: {server_message(e)}") from None
            raise

    def backup(self, directory: Optional[str], label: str) -> Dict[str, Any]:
        with self._db.cursor(autocommit=True, timeout=self._backup_timeout) as cur:
            cur.execute("SELECT DB_NAME(), CAST(SERVERPROPERTY('InstanceDefaultBackupPath') AS NVARCHAR(4000))")
            database, default_dir = cur.fetchone()
            target_dir = (directory or default_dir or "").rstrip("\\/")
            if not target_dir:
                raise InvalidInputError("Define NEXUS_BACKUP_DIR: SQL Server no reporta carpeta de respaldos por defecto")
            separator = "/" if target_dir.startswith("/") else "\\"
            stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            path = f"{target_dir}{separator}{database}_{stamp}_{label}.bak"
            backup_name = f"Nexus {database} {label} {stamp}"[:128]
            try:
                cur.execute(
                    "DECLARE @db SYSNAME = DB_NAME(), @ruta NVARCHAR(4000) = ?, @nombre NVARCHAR(128) = ?; "
                    "BACKUP DATABASE @db TO DISK = @ruta WITH COPY_ONLY, CHECKSUM, INIT, NAME = @nombre;",
                    (path, backup_name),
                )
                while cur.nextset():
                    pass
                cur.execute("DECLARE @ruta NVARCHAR(4000) = ?; RESTORE VERIFYONLY FROM DISK = @ruta WITH CHECKSUM;", (path,))
                while cur.nextset():
                    pass
            except pyodbc.Error as e:
                if is_statement_error(e):
                    raise InvalidInputError(f"El respaldo falló: {server_message(e)}") from None
                raise
            cur.execute(
                "SELECT TOP 1 b.backup_size, b.backup_start_date, b.backup_finish_date FROM msdb.dbo.backupset b "
                "JOIN msdb.dbo.backupmediafamily m ON m.media_set_id = b.media_set_id "
                "WHERE m.physical_device_name = ? ORDER BY b.backup_set_id DESC",
                (path,),
            )
            row = cur.fetchone()
        return {
            "base_datos": database,
            "archivo": path,
            "nombre": backup_name,
            "tamano_bytes": int(row[0]) if row and row[0] is not None else None,
            "inicio": json_value(row[1]) if row else None,
            "fin": json_value(row[2]) if row else None,
            "verificado": True,
            "solo_copia": True,
        }

    def list_backups(self, limit: int) -> List[Dict[str, Any]]:
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT TOP (?) b.backup_set_id, b.name, b.type, b.is_copy_only, b.backup_start_date, b.backup_finish_date, "
                "b.backup_size, m.physical_device_name FROM msdb.dbo.backupset b "
                "JOIN msdb.dbo.backupmediafamily m ON m.media_set_id = b.media_set_id "
                "WHERE b.database_name = DB_NAME() ORDER BY b.backup_set_id DESC",
                (limit,),
            )
            kinds = {"D": "completo", "I": "diferencial", "L": "log"}
            return [
                {
                    "id": r[0], "nombre": r[1], "tipo": kinds.get(r[2], r[2]), "solo_copia": bool(r[3]),
                    "inicio": json_value(r[4]), "fin": json_value(r[5]),
                    "tamano_bytes": int(r[6]) if r[6] is not None else None, "archivo": r[7],
                }
                for r in cur.fetchall()
            ]


class InMemoryCatalog(DatabaseCatalog):
    """Doble de pruebas: tablas y procedimientos declarados a mano; los procedimientos devuelven sus argumentos."""

    def __init__(self) -> None:
        self.tables: Dict[tuple, Dict[str, Any]] = {}
        self.procedures: Dict[tuple, Dict[str, Any]] = {}
        self.applied_scripts: List[str] = []
        self.backups: List[Dict[str, Any]] = []

    def add_table(self, schema: str, table: str, columns: List[str], rows: int = 0) -> None:
        self.tables[(schema, table)] = {
            "esquema": schema, "tabla": table, "filas": rows,
            "columnas": [{"nombre": c, "tipo": "nvarchar", "longitud": 255, "precision": None, "escala": None,
                          "nulable": True, "identidad": False, "default": None} for c in columns],
            "clave_primaria": [], "indices": [], "claves_foraneas": [],
        }

    def add_procedure(self, schema: str, name: str, parameters: List[ProcedureParameter], definition: str = "") -> None:
        self.procedures[(schema, name)] = {"parametros": parameters, "definicion": definition}

    def ping(self) -> None:
        return None

    def list_tables(self) -> List[Dict[str, Any]]:
        return [{"esquema": t["esquema"], "tabla": t["tabla"], "filas": t["filas"], "creada": None, "modificada": None}
                for t in self.tables.values()]

    def describe_table(self, schema: str, table: str) -> Optional[Dict[str, Any]]:
        return self.tables.get((schema, table))

    def list_procedures(self) -> List[Dict[str, Any]]:
        return [{"esquema": s, "nombre": n, "parametros": [p.nombre for p in v["parametros"]], "creado": None, "modificado": None}
                for (s, n), v in self.procedures.items()]

    def procedure_parameters(self, schema: str, name: str) -> Optional[List[ProcedureParameter]]:
        entry = self.procedures.get((schema, name))
        return None if entry is None else entry["parametros"]

    def procedure_definition(self, schema: str, name: str) -> Optional[str]:
        entry = self.procedures.get((schema, name))
        return None if entry is None else entry["definicion"]

    def execute_procedure(self, schema: str, name: str, arguments: Dict[str, Any], max_rows: int) -> ProcedureResult:
        return ProcedureResult([{"columnas": list(arguments), "filas": [list(arguments.values())], "truncado": False}])

    def apply_ddl(self, script: str) -> None:
        self.applied_scripts.append(script)
        match = re.search(r"CREATE TABLE \[(\w+)\]\.\[(\w+)\]", script)
        if match:
            self.add_table(match.group(1), match.group(2), [])

    def backup(self, directory: Optional[str], label: str) -> Dict[str, Any]:
        entry = {"base_datos": "memoria", "archivo": f"{directory or 'memoria'}/{label}.bak", "nombre": label,
                 "tamano_bytes": 0, "inicio": None, "fin": None, "verificado": True, "solo_copia": True}
        self.backups.append(entry)
        return entry

    def list_backups(self, limit: int) -> List[Dict[str, Any]]:
        return list(reversed(self.backups))[:limit]
