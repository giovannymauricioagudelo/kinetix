"""Registro de aplicaciones de Nexus en la base principal kinetix: aplicaciones, empresas, bases, migraciones y despliegues."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient

DATA_MODELS = ("por_empresa", "multiempresa")
DATABASE_STATES = ("pendiente", "desplegada", "error")
DEPLOYMENT_STATES = ("exitoso", "sin_cambios", "fallido")
MIGRATION_TYPES = ("base", "tabla", "sql")


@dataclass(frozen=True)
class Application:
    id_aplicacion: str
    nombre: str
    modelo_datos: str
    propietario: str
    seguridad_por_fila: bool = True
    descripcion: Optional[str] = None
    id_solicitud: Optional[str] = None
    estado: str = "activa"
    creado_por: str = ""
    fecha_creacion: Optional[datetime] = None
    fecha_modificacion: Optional[datetime] = None


@dataclass(frozen=True)
class AppCompany:
    id_aplicacion: str
    id_empresa: str
    nombre: str
    estado: str = "activa"
    fecha_registro: Optional[datetime] = None


@dataclass(frozen=True)
class AppDatabase:
    nombre_base: str
    id_aplicacion: str
    id_empresa: Optional[str] = None
    estado: str = "pendiente"
    version: int = 0
    fecha_creacion: Optional[datetime] = None
    fecha_despliegue: Optional[datetime] = None
    ultimo_error: Optional[str] = None


@dataclass(frozen=True)
class Migration:
    id_aplicacion: str
    nombre: str
    tipo: str
    script: str
    checksum: str
    numero: int = 0
    descripcion: Optional[str] = None
    creado_por: str = ""
    fecha_creacion: Optional[datetime] = None


@dataclass(frozen=True)
class Deployment:
    id_despliegue: str
    id_aplicacion: str
    nombre_base: str
    estado: str
    id_empresa: Optional[str] = None
    migraciones_aplicadas: List[int] = field(default_factory=list)
    version_resultante: int = 0
    detalle: Optional[str] = None
    ejecutado_por: str = ""
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None


class AppRegistry(ABC):
    @abstractmethod
    def create_app(self, app: Application, databases: Sequence[AppDatabase], migrations: Sequence[Migration]) -> bool:
        """Atómico. False si el id de la aplicación o alguna base ya está registrada."""

    @abstractmethod
    def get_app(self, id_aplicacion: str, propietario: str) -> Optional[Application]: ...

    @abstractmethod
    def list_apps(self, propietario: str) -> List[Application]: ...

    @abstractmethod
    def database_registered(self, nombre_base: str) -> bool: ...

    @abstractmethod
    def add_company(self, company: AppCompany, database: Optional[AppDatabase]) -> bool:
        """Atómico. False si la empresa ya está en la aplicación o la base ya está registrada."""

    @abstractmethod
    def companies(self, id_aplicacion: str) -> List[AppCompany]: ...

    @abstractmethod
    def databases(self, id_aplicacion: str) -> List[AppDatabase]: ...

    @abstractmethod
    def update_database(self, nombre_base: str, estado: str, version: Optional[int], error: Optional[str],
                        now: datetime) -> None: ...

    @abstractmethod
    def add_migration(self, migration: Migration) -> Optional[int]:
        """Asigna el siguiente número; None si ya existe una migración con ese nombre en la aplicación."""

    @abstractmethod
    def migrations(self, id_aplicacion: str, with_script: bool = True) -> List[Migration]: ...

    @abstractmethod
    def record_deployment(self, deployment: Deployment) -> None: ...

    @abstractmethod
    def deployments(self, id_aplicacion: str, limit: int) -> List[Deployment]: ...

    @abstractmethod
    def ping(self) -> None: ...


class InMemoryAppRegistry(AppRegistry):
    def __init__(self) -> None:
        self._apps: Dict[str, Application] = {}
        self._companies: Dict[str, List[AppCompany]] = {}
        self._databases: Dict[str, AppDatabase] = {}
        self._migrations: Dict[str, List[Migration]] = {}
        self._deployments: List[Deployment] = []
        self._lock = threading.Lock()

    def ping(self) -> None:
        return None

    def create_app(self, app, databases, migrations) -> bool:
        with self._lock:
            if app.id_aplicacion in self._apps or any(d.nombre_base in self._databases for d in databases):
                return False
            self._apps[app.id_aplicacion] = app
            self._companies[app.id_aplicacion] = []
            self._databases.update({d.nombre_base: d for d in databases})
            self._migrations[app.id_aplicacion] = [replace(m, numero=i) for i, m in enumerate(migrations, start=1)]
            return True

    def get_app(self, id_aplicacion, propietario):
        app = self._apps.get(id_aplicacion)
        return app if app and app.propietario == propietario else None

    def list_apps(self, propietario):
        return sorted((a for a in self._apps.values() if a.propietario == propietario), key=lambda a: a.id_aplicacion)

    def database_registered(self, nombre_base):
        return nombre_base in self._databases

    def add_company(self, company, database) -> bool:
        with self._lock:
            current = self._companies[company.id_aplicacion]
            if any(c.id_empresa == company.id_empresa for c in current):
                return False
            if database is not None:
                if database.nombre_base in self._databases:
                    return False
                self._databases[database.nombre_base] = database
            current.append(company)
            return True

    def companies(self, id_aplicacion):
        return sorted(self._companies.get(id_aplicacion, []), key=lambda c: c.id_empresa)

    def databases(self, id_aplicacion):
        return sorted((d for d in self._databases.values() if d.id_aplicacion == id_aplicacion), key=lambda d: d.nombre_base)

    def update_database(self, nombre_base, estado, version, error, now) -> None:
        with self._lock:
            current = self._databases[nombre_base]
            self._databases[nombre_base] = replace(
                current, estado=estado, version=current.version if version is None else version,
                ultimo_error=error, fecha_despliegue=now if estado == "desplegada" else current.fecha_despliegue,
            )

    def add_migration(self, migration) -> Optional[int]:
        with self._lock:
            current = self._migrations[migration.id_aplicacion]
            if any(m.nombre == migration.nombre for m in current):
                return None
            numero = len(current) + 1
            current.append(replace(migration, numero=numero))
            return numero

    def migrations(self, id_aplicacion, with_script=True):
        found = self._migrations.get(id_aplicacion, [])
        return list(found) if with_script else [replace(m, script="") for m in found]

    def record_deployment(self, deployment) -> None:
        with self._lock:
            self._deployments.append(deployment)

    def deployments(self, id_aplicacion, limit):
        found = [d for d in self._deployments if d.id_aplicacion == id_aplicacion]
        return list(reversed(found))[:limit]


class SqlServerAppRegistry(AppRegistry):
    _APP_COLUMNS = ("id_aplicacion, nombre, modelo_datos, propietario, seguridad_por_fila, descripcion, id_solicitud, "
                    "estado, creado_por, fecha_creacion, fecha_modificacion")
    _DB_COLUMNS = "nombre_base, id_aplicacion, id_empresa, estado, version, fecha_creacion, fecha_despliegue, ultimo_error"
    _MIGRATION_COLUMNS = "id_aplicacion, nombre, tipo, {script}, checksum, numero, descripcion, creado_por, fecha_creacion"
    _DEPLOYMENT_COLUMNS = ("id_despliegue, id_aplicacion, nombre_base, estado, id_empresa, migraciones_aplicadas, "
                           "version_resultante, detalle, ejecutado_por, fecha_inicio, fecha_fin")

    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def ping(self) -> None:
        self._db.ping()

    @staticmethod
    def _app(row) -> Application:
        return Application(id_aplicacion=row[0], nombre=row[1], modelo_datos=row[2], propietario=row[3],
                           seguridad_por_fila=bool(row[4]), descripcion=row[5], id_solicitud=row[6], estado=row[7],
                           creado_por=row[8] or "", fecha_creacion=row[9], fecha_modificacion=row[10])

    @staticmethod
    def _database(row) -> AppDatabase:
        return AppDatabase(nombre_base=row[0], id_aplicacion=row[1], id_empresa=row[2], estado=row[3], version=row[4],
                           fecha_creacion=row[5], fecha_despliegue=row[6], ultimo_error=row[7])

    @staticmethod
    def _insert_database(cur, database: AppDatabase) -> bool:
        cur.execute(
            f"INSERT INTO dbo.nexus_bases_datos ({SqlServerAppRegistry._DB_COLUMNS}) SELECT ?, ?, ?, ?, ?, ?, ?, ? "
            "WHERE NOT EXISTS (SELECT 1 FROM dbo.nexus_bases_datos WITH (UPDLOCK, HOLDLOCK) WHERE nombre_base = ?)",
            (database.nombre_base, database.id_aplicacion, database.id_empresa, database.estado, database.version,
             database.fecha_creacion, database.fecha_despliegue, database.ultimo_error, database.nombre_base),
        )
        return cur.rowcount == 1

    def create_app(self, app, databases, migrations) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                f"INSERT INTO dbo.nexus_aplicaciones ({self._APP_COLUMNS}) SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? "
                "WHERE NOT EXISTS (SELECT 1 FROM dbo.nexus_aplicaciones WITH (UPDLOCK, HOLDLOCK) WHERE id_aplicacion = ?)",
                (app.id_aplicacion, app.nombre, app.modelo_datos, app.propietario, app.seguridad_por_fila, app.descripcion,
                 app.id_solicitud, app.estado, app.creado_por, app.fecha_creacion, app.fecha_modificacion, app.id_aplicacion),
            )
            if cur.rowcount != 1:
                return False
            for database in databases:
                if not self._insert_database(cur, database):
                    cur.connection.rollback()
                    return False
            for numero, migration in enumerate(migrations, start=1):
                self._insert_migration(cur, migration, numero)
            return True

    def get_app(self, id_aplicacion, propietario):
        with self._db.cursor() as cur:
            cur.execute(f"SELECT {self._APP_COLUMNS} FROM dbo.nexus_aplicaciones WHERE id_aplicacion = ? AND propietario = ?",
                        (id_aplicacion, propietario))
            row = cur.fetchone()
        return self._app(row) if row else None

    def list_apps(self, propietario):
        with self._db.cursor() as cur:
            cur.execute(f"SELECT {self._APP_COLUMNS} FROM dbo.nexus_aplicaciones WHERE propietario = ? ORDER BY id_aplicacion",
                        (propietario,))
            return [self._app(r) for r in cur.fetchall()]

    def database_registered(self, nombre_base):
        with self._db.cursor() as cur:
            cur.execute("SELECT 1 FROM dbo.nexus_bases_datos WHERE nombre_base = ?", (nombre_base,))
            return cur.fetchone() is not None

    def add_company(self, company, database) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO dbo.nexus_aplicacion_empresas (id_aplicacion, id_empresa, nombre, estado, fecha_registro) "
                "SELECT ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM dbo.nexus_aplicacion_empresas WITH (UPDLOCK, HOLDLOCK) "
                "WHERE id_aplicacion = ? AND id_empresa = ?)",
                (company.id_aplicacion, company.id_empresa, company.nombre, company.estado, company.fecha_registro,
                 company.id_aplicacion, company.id_empresa),
            )
            if cur.rowcount != 1:
                return False
            if database is not None and not self._insert_database(cur, database):
                cur.connection.rollback()
                return False
            return True

    def companies(self, id_aplicacion):
        with self._db.cursor() as cur:
            cur.execute("SELECT id_aplicacion, id_empresa, nombre, estado, fecha_registro FROM dbo.nexus_aplicacion_empresas "
                        "WHERE id_aplicacion = ? ORDER BY id_empresa", (id_aplicacion,))
            return [AppCompany(*r) for r in cur.fetchall()]

    def databases(self, id_aplicacion):
        with self._db.cursor() as cur:
            cur.execute(f"SELECT {self._DB_COLUMNS} FROM dbo.nexus_bases_datos WHERE id_aplicacion = ? ORDER BY nombre_base",
                        (id_aplicacion,))
            return [self._database(r) for r in cur.fetchall()]

    def update_database(self, nombre_base, estado, version, error, now) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.nexus_bases_datos SET estado = ?, version = COALESCE(?, version), ultimo_error = ?, "
                "fecha_despliegue = CASE WHEN ? = 'desplegada' THEN ? ELSE fecha_despliegue END WHERE nombre_base = ?",
                (estado, version, error, estado, now, nombre_base),
            )

    @staticmethod
    def _insert_migration(cur, migration: Migration, numero: int) -> None:
        cur.execute(
            "INSERT INTO dbo.nexus_migraciones (id_aplicacion, numero, nombre, tipo, descripcion, script, checksum, "
            "creado_por, fecha_creacion) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (migration.id_aplicacion, numero, migration.nombre, migration.tipo, migration.descripcion, migration.script,
             migration.checksum, migration.creado_por, migration.fecha_creacion),
        )

    def add_migration(self, migration) -> Optional[int]:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "SELECT ISNULL(MAX(numero), 0) + 1, SUM(CASE WHEN nombre = ? THEN 1 ELSE 0 END) "
                "FROM dbo.nexus_migraciones WITH (UPDLOCK, HOLDLOCK) WHERE id_aplicacion = ?",
                (migration.nombre, migration.id_aplicacion),
            )
            numero, duplicated = cur.fetchone()
            if duplicated:
                return None
            self._insert_migration(cur, migration, numero)
            return numero

    def migrations(self, id_aplicacion, with_script=True):
        columns = self._MIGRATION_COLUMNS.format(script="script" if with_script else "N''")
        with self._db.cursor() as cur:
            cur.execute(f"SELECT {columns} FROM dbo.nexus_migraciones WHERE id_aplicacion = ? ORDER BY numero", (id_aplicacion,))
            return [Migration(*r[:5], numero=r[5], descripcion=r[6], creado_por=r[7] or "", fecha_creacion=r[8])
                    for r in cur.fetchall()]

    def record_deployment(self, deployment) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                f"INSERT INTO dbo.nexus_despliegues ({self._DEPLOYMENT_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (deployment.id_despliegue, deployment.id_aplicacion, deployment.nombre_base, deployment.estado,
                 deployment.id_empresa, dumps(deployment.migraciones_aplicadas), deployment.version_resultante,
                 deployment.detalle, deployment.ejecutado_por, deployment.fecha_inicio, deployment.fecha_fin),
            )

    def deployments(self, id_aplicacion, limit):
        with self._db.cursor() as cur:
            cur.execute(
                f"SELECT TOP (?) {self._DEPLOYMENT_COLUMNS} FROM dbo.nexus_despliegues WHERE id_aplicacion = ? "
                "ORDER BY fecha_inicio DESC",
                (limit, id_aplicacion),
            )
            return [Deployment(id_despliegue=r[0], id_aplicacion=r[1], nombre_base=r[2], estado=r[3], id_empresa=r[4],
                               migraciones_aplicadas=loads(r[5], []), version_resultante=r[6] or 0, detalle=r[7],
                               ejecutado_por=r[8] or "", fecha_inicio=r[9], fecha_fin=r[10])
                    for r in cur.fetchall()]
