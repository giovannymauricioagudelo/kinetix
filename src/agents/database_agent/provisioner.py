"""Aprovisionador de Nexus: crea la base independiente de cada aplicación y le aplica las migraciones registradas."""

from __future__ import annotations

import hashlib
import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Set, Tuple

from src.agents.database_agent.app_registry import Migration
from src.agents.database_agent.database_agent import quote_identifier

DATABASE_NAME = re.compile(r"^[a-z][a-z0-9_]{1,99}$")
_GO = re.compile(r"^\s*GO\s*;?\s*$", re.IGNORECASE | re.MULTILINE)
LOCK_RESOURCE = "nexus_despliegue"


def checksum(script: str) -> str:
    normalized = script.lstrip("\ufeff").replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def split_batches(script: str) -> List[str]:
    return [batch.strip() for batch in _GO.split(script) if batch.strip()]


class ProvisionError(Exception):
    def __init__(self, message: str, applied: Optional[List[int]] = None) -> None:
        super().__init__(message)
        self.applied = applied or []


@dataclass
class DeployResult:
    created: bool
    applied: List[int] = field(default_factory=list)
    version: int = 0


class Provisioner(ABC):
    @abstractmethod
    def database_exists(self, name: str) -> bool: ...

    @abstractmethod
    def deploy(self, database: str, migrations: Sequence[Migration], companies: Sequence[Tuple[str, str]],
               actor: str) -> DeployResult:
        """Crea la base si falta, aplica en orden las migraciones pendientes y sincroniza dbo.empresas (multiempresa).
        Lanza ProvisionError si una migración falla o si el checksum de una ya aplicada cambió."""


def _verify_applied(database: str, migrations: Sequence[Migration], applied: Dict[int, str]) -> None:
    for migration in migrations:
        recorded = applied.get(migration.numero)
        if recorded is not None and recorded != migration.checksum:
            raise ProvisionError(
                f"La migración {migration.numero} ({migration.nombre}) cambió después de aplicarse en {database}"
            )


class InMemoryProvisioner(Provisioner):
    """Doble para pruebas: falla las migraciones cuyo script contiene fail_marker."""

    def __init__(self, existing: Sequence[str] = (), fail_marker: Optional[str] = None) -> None:
        self.foreign: Set[str] = set(existing)
        self.databases: Dict[str, Dict[int, str]] = {}
        self.companies: Dict[str, Set[str]] = {}
        self.scripts: Dict[str, List[str]] = {}
        self._fail_marker = fail_marker
        self._lock = threading.Lock()

    def database_exists(self, name: str) -> bool:
        return name in self.foreign or name in self.databases

    def deploy(self, database, migrations, companies, actor) -> DeployResult:
        with self._lock:
            created = database not in self.databases
            applied = self.databases.setdefault(database, {})
            self.scripts.setdefault(database, [])
            _verify_applied(database, migrations, applied)
            done: List[int] = []
            for migration in sorted(migrations, key=lambda m: m.numero):
                if migration.numero in applied:
                    continue
                if self._fail_marker and self._fail_marker in migration.script:
                    raise ProvisionError(f"Migración {migration.numero} ({migration.nombre}): error simulado", done)
                applied[migration.numero] = migration.checksum
                self.scripts[database].append(migration.script)
                done.append(migration.numero)
            self.companies.setdefault(database, set()).update(c for c, _ in companies)
            return DeployResult(created, done, max(applied, default=0))


class SqlServerProvisioner(Provisioner):
    """Una conexión por base durante todo el despliegue: el bloqueo sp_getapplock es de sesión."""

    _HISTORY = (
        "IF SCHEMA_ID(N'despliegue') IS NULL EXEC(N'CREATE SCHEMA despliegue');\n"
        "IF OBJECT_ID(N'despliegue.migraciones', N'U') IS NULL\n"
        "    CREATE TABLE despliegue.migraciones (\n"
        "        numero INT NOT NULL CONSTRAINT PK_despliegue_migraciones PRIMARY KEY CLUSTERED,\n"
        "        nombre NVARCHAR(100) NOT NULL,\n"
        "        checksum CHAR(64) NOT NULL,\n"
        "        aplicada_por NVARCHAR(100) NOT NULL,\n"
        "        aplicada_en DATETIME2 NOT NULL CONSTRAINT DF_despliegue_migraciones_fecha DEFAULT SYSUTCDATETIME()\n"
        "    );"
    )

    def __init__(self, settings, query_timeout: int = 120, lock_timeout_ms: int = 30000) -> None:
        self._settings = settings
        self._timeout = query_timeout
        self._lock_timeout_ms = lock_timeout_ms

    def _connect(self, database: str, autocommit: bool):
        import pyodbc

        conn = pyodbc.connect(replace(self._settings, database=database).connection_string(), autocommit=autocommit)
        conn.timeout = self._timeout
        return conn

    def database_exists(self, name: str) -> bool:
        conn = self._connect("master", autocommit=True)
        try:
            return conn.cursor().execute("SELECT DB_ID(?)", (name,)).fetchone()[0] is not None
        finally:
            conn.close()

    def _create_if_missing(self, database: str) -> bool:
        if not DATABASE_NAME.match(database):
            raise ProvisionError(f"Nombre de base inválido: {database!r}")
        conn = self._connect("master", autocommit=True)
        try:
            cur = conn.cursor()
            if cur.execute("SELECT DB_ID(?)", (database,)).fetchone()[0] is not None:
                return False
            cur.execute(f"CREATE DATABASE {quote_identifier(database)}")
            return True
        finally:
            conn.close()

    def deploy(self, database, migrations, companies, actor) -> DeployResult:
        import pyodbc

        from src.agents.sqlserver import server_message

        try:
            created = self._create_if_missing(database)
            conn = self._connect(database, autocommit=False)
        except pyodbc.Error as e:
            raise ProvisionError(f"No se pudo crear o abrir {database}: {server_message(e)}")
        done: List[int] = []
        try:
            cur = conn.cursor()
            cur.execute(self._HISTORY)
            conn.commit()
            cur.execute(
                "SET NOCOUNT ON; DECLARE @r INT; EXEC @r = sp_getapplock @Resource = ?, @LockMode = N'Exclusive', "
                "@LockOwner = N'Session', @LockTimeout = ?; SELECT @r;",
                (LOCK_RESOURCE, self._lock_timeout_ms),
            )
            if cur.fetchone()[0] < 0:
                raise ProvisionError(f"Otro despliegue está en curso sobre {database}")
            applied = {row[0]: row[1] for row in cur.execute("SELECT numero, checksum FROM despliegue.migraciones").fetchall()}
            _verify_applied(database, migrations, applied)
            for migration in sorted(migrations, key=lambda m: m.numero):
                if migration.numero in applied:
                    continue
                try:
                    for batch in split_batches(migration.script):
                        cur.execute(batch)
                    cur.execute("INSERT INTO despliegue.migraciones (numero, nombre, checksum, aplicada_por) VALUES (?, ?, ?, ?)",
                                (migration.numero, migration.nombre, migration.checksum, actor))
                    conn.commit()
                except pyodbc.Error as e:
                    conn.rollback()
                    raise ProvisionError(f"Migración {migration.numero} ({migration.nombre}): {server_message(e)}", done)
                applied[migration.numero] = migration.checksum
                done.append(migration.numero)
            for id_empresa, nombre in companies:
                cur.execute("INSERT INTO dbo.empresas (id_empresa, nombre) SELECT ?, ? "
                            "WHERE NOT EXISTS (SELECT 1 FROM dbo.empresas WHERE id_empresa = ?)", (id_empresa, nombre, id_empresa))
            conn.commit()
            return DeployResult(created, done, max(applied, default=0))
        except pyodbc.Error as e:
            conn.rollback()
            raise ProvisionError(f"Error desplegando {database}: {server_message(e)}", done)
        finally:
            conn.close()
