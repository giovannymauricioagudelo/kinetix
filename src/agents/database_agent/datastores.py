"""Lectura y escritura de filas por motor para copiar los datos de una aplicación al cambiar de motor.

La copia es por tabla y por lotes. Una tabla solo se copia si en el destino está vacía, y en los motores con
transacciones se confirma de una vez al final, así un fallo deja el destino vacío y se puede reintentar.
Las bases de origen no se tocan: el cambio se puede revertir.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from src.agents.database_agent.database_agent import ColumnType, TableDefinition
from src.agents.database_agent.dialects import PostgresDialect

AUDIT_COLUMNS: Tuple[Tuple[str, ColumnType], ...] = (
    ("created_at", ColumnType.DATETIME), ("updated_at", ColumnType.DATETIME), ("created_by", ColumnType.VARCHAR),
)
Row = Dict[str, Any]


def table_columns(table: TableDefinition) -> List[Tuple[str, ColumnType]]:
    columns = [(c.name, c.type) for c in table.columns]
    if table.audit_columns:
        columns.extend(AUDIT_COLUMNS)
    return columns


def _quoted(names: Iterable[str], upper: bool = False) -> str:
    return ", ".join(f'"{n.upper() if upper else n}"' for n in names)


def _primary_key(table: TableDefinition) -> str:
    return next((c.name for c in table.columns if c.primary_key), table.columns[0].name)


def to_target(value: Any, column_type: ColumnType, motor: str) -> Any:
    """Normaliza un valor leído de cualquier motor al tipo que espera el driver del motor destino."""
    if value is None:
        return None
    if hasattr(value, "read") and callable(value.read):
        value = value.read()
    kind = type(value).__name__
    if kind == "ObjectId":
        value = str(value)
    elif kind == "Decimal128":
        value = value.to_decimal()
    if column_type == ColumnType.JSON:
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        parsed = json.loads(value) if isinstance(value, str) else value
        if motor == "mongodb":
            return parsed
        if motor == "postgresql":
            from psycopg2.extras import Json

            return Json(parsed)
        return json.dumps(parsed, ensure_ascii=False)
    if column_type == ColumnType.DATETIME and isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    if column_type == ColumnType.DECIMAL:
        value = Decimal(str(value)) if not isinstance(value, Decimal) else value
        if motor == "mongodb":
            from bson.decimal128 import Decimal128

            return Decimal128(value)
        return value
    if column_type == ColumnType.BOOLEAN:
        return bool(value)
    if column_type in (ColumnType.INT, ColumnType.BIGINT):
        return int(value)
    if column_type in (ColumnType.VARCHAR, ColumnType.TEXT) and not isinstance(value, str):
        return value.decode("utf-8") if isinstance(value, (bytes, bytearray)) else str(value)
    return value


class DataStore(ABC):
    motor: str

    @abstractmethod
    def count(self, database: str, table: TableDefinition) -> Optional[int]:
        """Filas de la tabla; None si la tabla no existe en esa base."""

    @abstractmethod
    def read(self, database: str, table: TableDefinition, batch_size: int) -> Iterator[List[Row]]: ...

    @abstractmethod
    def write(self, database: str, table: TableDefinition, batches: Iterable[List[Row]]) -> int:
        """Inserta todos los lotes; si falla no deja filas a medias (o las borra donde no hay transacciones)."""


def copy_table(source: DataStore, target: DataStore, database: str, table: TableDefinition,
               batch_size: int = 1000) -> Dict[str, Any]:
    result: Dict[str, Any] = {"tabla": f"{table.schema}.{table.name}", "nombre_base": database, "filas": 0}
    try:
        total = source.count(database, table)
        if total is None:
            return {**result, "estado": "sin_origen", "detalle": "La tabla no existe en la base de origen"}
        existing = target.count(database, table)
        if existing is None:
            return {**result, "estado": "incompleta", "detalle": "La tabla no existe en el destino: despliega el esquema"}
        if existing == total and total > 0:
            return {**result, "estado": "ya_copiada", "filas": total}
        if existing:
            return {**result, "estado": "incompleta", "filas": existing,
                    "detalle": f"El destino ya tiene {existing} de {total} filas: vacía la tabla destino y reintenta"}
        columns = table_columns(table)
        converted = ([{name: to_target(row.get(name), kind, target.motor) for name, kind in columns} for row in batch]
                     for batch in source.read(database, table, batch_size))
        written = target.write(database, table, converted)
        copied = target.count(database, table)
    except Exception as e:  # noqa: BLE001 - cada driver tiene su jerarquía de errores; se reporta por tabla
        return {**result, "estado": "incompleta", "detalle": f"{type(e).__name__}: {str(e)[:500]}"}
    if copied != total:
        return {**result, "estado": "incompleta", "filas": copied or 0,
                "detalle": f"Se escribieron {written} filas pero el destino tiene {copied} de {total}"}
    return {**result, "estado": "copiada", "filas": total}


# ============================================================================ memoria


class InMemoryDataStore(DataStore):
    """Doble para pruebas; con create_on_write toda tabla existe vacía hasta el primer write (como tras desplegar)."""

    def __init__(self, motor: str = "sqlserver", create_on_write: bool = False, fail_tables: Iterable[str] = ()) -> None:
        self.motor = motor
        self.tables: Dict[Tuple[str, str], List[Row]] = {}
        self._create_on_write = create_on_write
        self._fail = {t.lower() for t in fail_tables}

    @staticmethod
    def _key(database: str, table: TableDefinition) -> Tuple[str, str]:
        return database, table.name.lower()

    def create(self, database: str, table: TableDefinition, rows: Iterable[Row] = ()) -> None:
        self.tables[self._key(database, table)] = [dict(r) for r in rows]

    def count(self, database, table):
        rows = self.tables.get(self._key(database, table))
        if rows is None:
            return 0 if self._create_on_write else None
        return len(rows)

    def read(self, database, table, batch_size):
        rows = self.tables.get(self._key(database, table), [])
        for start in range(0, len(rows), batch_size):
            yield [dict(r) for r in rows[start:start + batch_size]]

    def write(self, database, table, batches):
        key = self._key(database, table)
        if key not in self.tables:
            if not self._create_on_write:
                raise RuntimeError(f"La tabla {table.name} no existe en {database}")
            self.tables[key] = []
        pending = [row for batch in batches for row in batch]
        if table.name.lower() in self._fail:
            raise RuntimeError(f"error simulado escribiendo {table.name}")
        self.tables[key].extend(pending)
        return len(pending)


# ============================================================================ SQL Server


class SqlServerDataStore(DataStore):
    motor = "sqlserver"

    def __init__(self, settings, timeout: int = 300) -> None:
        self._settings = settings
        self._timeout = timeout

    def _connect(self, database: str):
        import pyodbc

        conn = pyodbc.connect(replace(self._settings, database=database).connection_string(), autocommit=False)
        conn.timeout = self._timeout
        return conn

    @staticmethod
    def _target(table: TableDefinition) -> str:
        return f"[{table.schema}].[{table.name}]"

    def count(self, database, table):
        conn = self._connect(database)
        try:
            cur = conn.cursor()
            if cur.execute("SELECT OBJECT_ID(?, N'U')", (f"{table.schema}.{table.name}",)).fetchone()[0] is None:
                return None
            return cur.execute(f"SELECT COUNT_BIG(*) FROM {self._target(table)}").fetchone()[0]
        finally:
            conn.close()

    def read(self, database, table, batch_size):
        names = [name for name, _ in table_columns(table)]
        conn = self._connect(database)
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT {', '.join(f'[{n}]' for n in names)} FROM {self._target(table)} ORDER BY [{_primary_key(table)}]")
            while rows := cur.fetchmany(batch_size):
                yield [dict(zip(names, row)) for row in rows]
        finally:
            conn.close()

    def write(self, database, table, batches):
        names = [name for name, _ in table_columns(table)]
        sql = (f"INSERT INTO {self._target(table)} ({', '.join(f'[{n}]' for n in names)}) "
               f"VALUES ({', '.join('?' for _ in names)})")
        conn = self._connect(database)
        total = 0
        try:
            cur = conn.cursor()
            cur.fast_executemany = True
            for batch in batches:
                if batch:
                    cur.executemany(sql, [tuple(row[n] for n in names) for row in batch])
                    total += len(batch)
            conn.commit()
            return total
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ============================================================================ PostgreSQL


class PostgresDataStore(DataStore):
    motor = "postgresql"

    def __init__(self, settings, timeout: int = 300) -> None:
        self._settings = settings
        self._timeout = timeout

    def _connect(self, database: str):
        import psycopg2

        s = self._settings
        kwargs = {"host": s.host, "port": s.port, "dbname": database, "user": s.user, "password": s.password,
                  "connect_timeout": 30, "application_name": "kinetix-nexus",
                  "options": f"-c statement_timeout={self._timeout * 1000} -c row_security=off"}
        if s.sslmode:
            kwargs["sslmode"] = s.sslmode
        return psycopg2.connect(**kwargs)

    @staticmethod
    def _target(table: TableDefinition) -> str:
        return f'"{PostgresDialect().resolve_schema(table.schema)}"."{table.name}"'

    def count(self, database, table):
        conn = self._connect(database)
        try:
            cur = conn.cursor()
            cur.execute("SELECT to_regclass(%s)", (self._target(table),))
            if cur.fetchone()[0] is None:
                return None
            cur.execute(f"SELECT COUNT(*) FROM {self._target(table)}")
            return cur.fetchone()[0]
        finally:
            conn.close()

    def read(self, database, table, batch_size):
        names = [name for name, _ in table_columns(table)]
        conn = self._connect(database)
        try:
            cur = conn.cursor(name="nexus_copia")
            cur.itersize = batch_size
            cur.execute(f'SELECT {_quoted(names)} FROM {self._target(table)} ORDER BY "{_primary_key(table)}"')
            while rows := cur.fetchmany(batch_size):
                yield [dict(zip(names, row)) for row in rows]
        finally:
            conn.close()

    def write(self, database, table, batches):
        from psycopg2.extras import execute_values

        names = [name for name, _ in table_columns(table)]
        sql = f"INSERT INTO {self._target(table)} ({_quoted(names)}) VALUES %s"
        conn = self._connect(database)
        total = 0
        try:
            cur = conn.cursor()
            for batch in batches:
                if batch:
                    execute_values(cur, sql, [tuple(row[n] for n in names) for row in batch], page_size=len(batch))
                    total += len(batch)
            conn.commit()
            return total
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ============================================================================ Firebird


class FirebirdDataStore(DataStore):
    motor = "firebird"

    def __init__(self, settings) -> None:
        self._settings = settings

    def _connect(self, database: str):
        from firebird.driver import connect

        from src.agents.database_agent.engine_provisioners import firebird_database_settings

        s = firebird_database_settings(self._settings, database)
        return connect(s.dsn, user=s.user, password=s.password, charset=s.charset)

    def count(self, database, table):
        conn = self._connect(database)
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ?", (table.name.upper(),))
            if cur.fetchone() is None:
                return None
            cur.execute(f'SELECT COUNT(*) FROM "{table.name.upper()}"')
            return cur.fetchone()[0]
        finally:
            conn.close()

    def read(self, database, table, batch_size):
        names = [name for name, _ in table_columns(table)]
        conn = self._connect(database)
        try:
            cur = conn.cursor()
            cur.execute(f'SELECT {_quoted(names, upper=True)} FROM "{table.name.upper()}" '
                        f'ORDER BY "{_primary_key(table).upper()}"')
            while rows := cur.fetchmany(batch_size):
                yield [dict(zip(names, row)) for row in rows]
        finally:
            conn.close()

    def write(self, database, table, batches):
        names = [name for name, _ in table_columns(table)]
        sql = (f'INSERT INTO "{table.name.upper()}" ({_quoted(names, upper=True)}) '
               f"VALUES ({', '.join('?' for _ in names)})")
        conn = self._connect(database)
        total = 0
        try:
            cur = conn.cursor()
            for batch in batches:
                if batch:
                    cur.executemany(sql, [tuple(row[n] for n in names) for row in batch])
                    total += len(batch)
            conn.commit()
            return total
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ============================================================================ MongoDB


class MongoDataStore(DataStore):
    """Sin transacciones: si una escritura falla se borra lo insertado (la colección estaba vacía al empezar)."""

    motor = "mongodb"

    def __init__(self, settings, client=None) -> None:
        self._settings = settings
        self._client_instance = client

    @property
    def _client(self):
        if self._client_instance is None:
            from pymongo import MongoClient

            self._client_instance = MongoClient(self._settings.uri, appname="kinetix-nexus", serverSelectionTimeoutMS=30000)
        return self._client_instance

    def count(self, database, table):
        db = self._client[database]
        if table.name not in db.list_collection_names():
            return None
        return db[table.name].count_documents({})

    def read(self, database, table, batch_size):
        projection = {"_id": 0, **{name: 1 for name, _ in table_columns(table)}}
        cursor = self._client[database][table.name].find({}, projection).sort(_primary_key(table), 1).batch_size(batch_size)
        batch: List[Row] = []
        for document in cursor:
            batch.append(document)
            if len(batch) == batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def write(self, database, table, batches):
        collection = self._client[database][table.name]
        total = 0
        try:
            for batch in batches:
                if batch:
                    collection.insert_many([{k: v for k, v in row.items() if v is not None} for row in batch], ordered=True)
                    total += len(batch)
            return total
        except Exception:
            collection.delete_many({})
            raise


def build_datastore(spec, timeout: int = 300) -> DataStore:
    if spec.motor == "sqlserver":
        return SqlServerDataStore(spec.settings, timeout)
    if spec.motor == "postgresql":
        return PostgresDataStore(spec.settings, timeout)
    if spec.motor == "firebird":
        return FirebirdDataStore(spec.settings)
    return MongoDataStore(spec.settings)
