"""Aprovisionadores de Nexus para PostgreSQL, Firebird y MongoDB (el de SQL Server vive en provisioner.py).

Igual que en SQL Server: crean la base de la aplicación si falta, llevan el historial de migraciones con su
checksum dentro de la propia base, aplican en orden las pendientes y sincronizan la tabla de empresas.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from src.agents.database_agent.dialects import FirebirdDialect, firebird_statements
from src.agents.database_agent.engines import FirebirdSettings, MongoSettings, PostgresSettings
from src.agents.database_agent.provisioner import (
    DATABASE_NAME,
    LOCK_RESOURCE,
    DeployResult,
    ProvisionError,
    Provisioner,
    _verify_applied,
)


def _check_name(database: str) -> None:
    if not DATABASE_NAME.match(database):
        raise ProvisionError(f"Nombre de base inválido: {database!r}")


def firebird_database_settings(settings: FirebirdSettings, database: str) -> FirebirdSettings:
    """Las bases de las aplicaciones van en la misma carpeta del servidor que la base de la conexión: {carpeta}/{base}.fdb."""
    _check_name(database)
    path = settings.database.replace("\\", "/")
    if "/" not in path:
        raise ProvisionError("La conexión Firebird debe usar una ruta (no un alias) para ubicar las bases de las aplicaciones")
    return replace(settings, database=f"{path.rsplit('/', 1)[0]}/{database}.fdb")


# ============================================================================ PostgreSQL


class PostgresProvisioner(Provisioner):
    """La conexión apunta a una base de mantenimiento (p. ej. postgres) desde la que se crean las demás."""

    _HISTORY = (
        "CREATE SCHEMA IF NOT EXISTS despliegue;\n"
        "CREATE TABLE IF NOT EXISTS despliegue.migraciones (\n"
        "    numero INTEGER NOT NULL PRIMARY KEY,\n"
        "    nombre VARCHAR(100) NOT NULL,\n"
        "    checksum CHAR(64) NOT NULL,\n"
        "    aplicada_por VARCHAR(100) NOT NULL,\n"
        "    aplicada_en TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')\n"
        ");"
    )

    def __init__(self, settings: PostgresSettings, query_timeout: int = 120) -> None:
        self._settings = settings
        self._timeout = query_timeout

    def _connect(self, database: str, autocommit: bool):
        import psycopg2

        s = self._settings
        kwargs = {"host": s.host, "port": s.port, "dbname": database, "user": s.user, "password": s.password,
                  "connect_timeout": 30, "application_name": "kinetix-nexus",
                  "options": f"-c statement_timeout={self._timeout * 1000}"}
        if s.sslmode:
            kwargs["sslmode"] = s.sslmode
        conn = psycopg2.connect(**kwargs)
        conn.autocommit = autocommit
        return conn

    def database_exists(self, name: str) -> bool:
        conn = self._connect(self._settings.database, autocommit=True)
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            return cur.fetchone() is not None
        finally:
            conn.close()

    def _create_if_missing(self, database: str) -> bool:
        _check_name(database)
        if self.database_exists(database):
            return False
        conn = self._connect(self._settings.database, autocommit=True)
        try:
            conn.cursor().execute(f'CREATE DATABASE "{database}"')
            return True
        finally:
            conn.close()

    def deploy(self, database, migrations, companies, actor) -> DeployResult:
        import psycopg2

        from src.agents.database_agent.postgres_catalog import _message

        try:
            created = self._create_if_missing(database)
            conn = self._connect(database, autocommit=False)
        except psycopg2.Error as e:
            raise ProvisionError(f"No se pudo crear o abrir {database}: {_message(e)}")
        done: List[int] = []
        try:
            cur = conn.cursor()
            cur.execute(self._HISTORY)
            conn.commit()
            cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (LOCK_RESOURCE,))
            if not cur.fetchone()[0]:
                raise ProvisionError(f"Otro despliegue está en curso sobre {database}")
            cur.execute("SELECT numero, checksum FROM despliegue.migraciones")
            applied = {row[0]: row[1] for row in cur.fetchall()}
            conn.commit()
            _verify_applied(database, migrations, applied)
            for migration in sorted(migrations, key=lambda m: m.numero):
                if migration.numero in applied:
                    continue
                try:
                    cur.execute(migration.script)
                    cur.execute("INSERT INTO despliegue.migraciones (numero, nombre, checksum, aplicada_por) VALUES (%s, %s, %s, %s)",
                                (migration.numero, migration.nombre, migration.checksum, actor))
                    conn.commit()
                except psycopg2.Error as e:
                    conn.rollback()
                    raise ProvisionError(f"Migración {migration.numero} ({migration.nombre}): {_message(e)}", done)
                applied[migration.numero] = migration.checksum
                done.append(migration.numero)
            for id_empresa, nombre in companies:
                cur.execute('INSERT INTO "public"."empresas" ("id_empresa", "nombre") VALUES (%s, %s) '
                            'ON CONFLICT ("id_empresa") DO NOTHING', (id_empresa, nombre))
            conn.commit()
            return DeployResult(created, done, max(applied, default=0))
        except psycopg2.Error as e:
            conn.rollback()
            raise ProvisionError(f"Error desplegando {database}: {_message(e)}", done)
        finally:
            conn.close()


# ============================================================================ Firebird


class FirebirdProvisioner(Provisioner):
    """Firebird no tiene bloqueos de aplicación: los despliegues se serializan por base dentro de este proceso."""

    _locks: Dict[str, threading.Lock] = {}
    _locks_guard = threading.Lock()

    def __init__(self, settings: FirebirdSettings) -> None:
        self._settings = settings

    def _connect(self, settings: FirebirdSettings):
        from firebird.driver import connect

        return connect(settings.dsn, user=settings.user, password=settings.password, charset=settings.charset)

    def database_exists(self, name: str) -> bool:
        from firebird.driver import DatabaseError

        try:
            self._connect(firebird_database_settings(self._settings, name)).close()
            return True
        except DatabaseError:
            return False

    def _lock(self, database: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(database, threading.Lock())

    def deploy(self, database, migrations, companies, actor) -> DeployResult:
        from firebird.driver import DatabaseError, create_database

        from src.agents.database_agent.firebird_catalog import _message

        target = firebird_database_settings(self._settings, database)
        lock = self._lock(database)
        if not lock.acquire(timeout=30):
            raise ProvisionError(f"Otro despliegue está en curso sobre {database}")
        done: List[int] = []
        try:
            created = not self.database_exists(database)
            try:
                conn = (create_database(target.dsn, user=target.user, password=target.password, charset=target.charset)
                        if created else self._connect(target))
            except DatabaseError as e:
                raise ProvisionError(f"No se pudo crear o abrir {database}: {_message(e)}")
            try:
                history = FirebirdDialect().if_missing(
                    "RDB$RELATIONS", "RDB$RELATION_NAME", "DESPLIEGUE_MIGRACIONES",
                    'CREATE TABLE "DESPLIEGUE_MIGRACIONES" ("NUMERO" INTEGER NOT NULL PRIMARY KEY, '
                    '"NOMBRE" VARCHAR(100) NOT NULL, "CHECKSUM" CHAR(64) NOT NULL, "APLICADA_POR" VARCHAR(100) NOT NULL, '
                    '"APLICADA_EN" TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)',
                )
                self._run(conn, history)
                cur = conn.cursor()
                cur.execute('SELECT "NUMERO", TRIM("CHECKSUM") FROM "DESPLIEGUE_MIGRACIONES"')
                applied = {row[0]: row[1] for row in cur.fetchall()}
                conn.commit()
                _verify_applied(database, migrations, applied)
                for migration in sorted(migrations, key=lambda m: m.numero):
                    if migration.numero in applied:
                        continue
                    try:
                        self._run(conn, migration.script)
                        conn.cursor().execute(
                            'INSERT INTO "DESPLIEGUE_MIGRACIONES" ("NUMERO", "NOMBRE", "CHECKSUM", "APLICADA_POR") VALUES (?, ?, ?, ?)',
                            (migration.numero, migration.nombre, migration.checksum, actor))
                        conn.commit()
                    except DatabaseError as e:
                        conn.rollback()
                        raise ProvisionError(f"Migración {migration.numero} ({migration.nombre}): {_message(e)}", done)
                    applied[migration.numero] = migration.checksum
                    done.append(migration.numero)
                for id_empresa, nombre in companies:
                    conn.cursor().execute(
                        'MERGE INTO "EMPRESAS" e USING (SELECT CAST(? AS VARCHAR(255)) AS ID, CAST(? AS VARCHAR(255)) AS N '
                        'FROM RDB$DATABASE) s ON e."ID_EMPRESA" = s.ID '
                        'WHEN NOT MATCHED THEN INSERT ("ID_EMPRESA", "NOMBRE") VALUES (s.ID, s.N)', (id_empresa, nombre))
                conn.commit()
                return DeployResult(created, done, max(applied, default=0))
            except DatabaseError as e:
                conn.rollback()
                raise ProvisionError(f"Error desplegando {database}: {_message(e)}", done)
            finally:
                conn.close()
        finally:
            lock.release()

    @staticmethod
    def _run(conn, script: str) -> None:
        cur = conn.cursor()
        for statement in firebird_statements(script):
            if statement.upper() == "COMMIT":
                conn.commit()
                cur = conn.cursor()
            else:
                cur.execute(statement)
        conn.commit()


# ============================================================================ MongoDB


class MongoProvisioner(Provisioner):
    """Las bases se crean al escribir; el historial va en _nexus_migraciones y el bloqueo en _nexus_bloqueo."""

    HISTORY, LOCK = "_nexus_migraciones", "_nexus_bloqueo"

    def __init__(self, settings: MongoSettings, lock_seconds: int = 300, client=None) -> None:
        self._settings = settings
        self._lock_seconds = lock_seconds
        self._client_instance = client

    @property
    def _client(self):
        if self._client_instance is None:
            from pymongo import MongoClient

            self._client_instance = MongoClient(self._settings.uri, appname="kinetix-nexus", serverSelectionTimeoutMS=30000)
        return self._client_instance

    def database_exists(self, name: str) -> bool:
        return name in self._client.list_database_names()

    def _acquire(self, db, database: str) -> None:
        from pymongo.errors import DuplicateKeyError

        now = datetime.now(timezone.utc)
        for _ in range(2):
            try:
                db[self.LOCK].insert_one({"_id": LOCK_RESOURCE, "hasta": now + timedelta(seconds=self._lock_seconds)})
                return
            except DuplicateKeyError:
                db[self.LOCK].delete_one({"_id": LOCK_RESOURCE, "hasta": {"$lt": now}})
        raise ProvisionError(f"Otro despliegue está en curso sobre {database}")

    def deploy(self, database, migrations, companies, actor) -> DeployResult:
        from pymongo.errors import OperationFailure, PyMongoError

        from src.agents.database_agent.mongo_catalog import NAMESPACE_EXISTS, parse_commands

        _check_name(database)
        done: List[int] = []
        try:
            created = not self.database_exists(database)
            db = self._client[database]
            self._acquire(db, database)
        except PyMongoError as e:
            raise ProvisionError(f"No se pudo abrir {database}: {e}")
        try:
            applied = {d["_id"]: d["checksum"] for d in db[self.HISTORY].find({}, {"checksum": 1})}
            _verify_applied(database, migrations, applied)
            for migration in sorted(migrations, key=lambda m: m.numero):
                if migration.numero in applied:
                    continue
                try:
                    for command in parse_commands(migration.script):
                        try:
                            db.command(command)
                        except OperationFailure as e:
                            if next(iter(command)) != "create" or e.code != NAMESPACE_EXISTS:
                                raise
                    db[self.HISTORY].insert_one({"_id": migration.numero, "nombre": migration.nombre, "checksum": migration.checksum,
                                                 "aplicada_por": actor, "aplicada_en": datetime.now(timezone.utc)})
                except (PyMongoError, ValueError) as e:
                    raise ProvisionError(f"Migración {migration.numero} ({migration.nombre}): {str(e)[:500]}", done)
                applied[migration.numero] = migration.checksum
                done.append(migration.numero)
            for id_empresa, nombre in companies:
                db["empresas"].update_one({"id_empresa": id_empresa}, {"$setOnInsert": {
                    "id_empresa": id_empresa, "nombre": nombre, "estado": "activa", "fecha_creacion": datetime.now(timezone.utc)}},
                    upsert=True)
            return DeployResult(created, done, max(applied, default=0))
        except PyMongoError as e:
            raise ProvisionError(f"Error desplegando {database}: {str(e)[:500]}", done)
        finally:
            db[self.LOCK].delete_one({"_id": LOCK_RESOURCE})


def build_provisioner(spec, query_timeout: int = 120, lock_timeout_ms: int = 30000) -> Provisioner:
    if spec.motor == "sqlserver":
        from src.agents.database_agent.provisioner import SqlServerProvisioner

        return SqlServerProvisioner(spec.settings, query_timeout, lock_timeout_ms)
    if spec.motor == "postgresql":
        return PostgresProvisioner(spec.settings, query_timeout)
    if spec.motor == "firebird":
        return FirebirdProvisioner(spec.settings)
    return MongoProvisioner(spec.settings, max(60, query_timeout))
