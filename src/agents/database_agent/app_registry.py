"""Registro de aplicaciones de Nexus en la base principal kinetix: aplicaciones, empresas, bases, migraciones y despliegues."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient

DATA_MODELS = ("por_empresa", "multiempresa")
DATABASE_STATES = ("pendiente", "desplegada", "error")
DEPLOYMENT_STATES = ("exitoso", "sin_cambios", "fallido")
MIGRATION_TYPES = ("base", "tabla", "sql")
ENGINE_CHANGE_STATES = ("esquema_pendiente", "esquema_desplegado", "esquema_con_errores", "copia_con_errores",
                        "datos_copiados", "completado", "revertido")
FINAL_CHANGE_STATES = frozenset({"completado", "revertido"})


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
    motor: str = "sqlserver"
    conexion: str = "kinetix"


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
    definicion: Optional[str] = None
    motor: Optional[str] = None
    equivalentes: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineChange:
    id_cambio: str
    id_aplicacion: str
    motor_origen: str
    conexion_origen: str
    motor_destino: str
    conexion_destino: str
    version_origen: int
    bases_origen: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    estado: str = "esquema_pendiente"
    detalle: Dict[str, Any] = field(default_factory=dict)
    solicitado_por: str = ""
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None

    @property
    def activo(self) -> bool:
        return self.estado not in FINAL_CHANGE_STATES


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
    def add_equivalent(self, id_aplicacion: str, numero: int, motor: str, script: str, checksum: str, actor: str,
                       now: datetime) -> bool:
        """False si la migración ya tiene equivalente para ese motor (los equivalentes son inmutables)."""

    @abstractmethod
    def start_engine_change(self, change: EngineChange) -> bool:
        """Atómico: registra el cambio, mueve la aplicación al motor/conexión destino y deja sus bases pendientes
        en versión 0. False si la aplicación ya tiene un cambio activo."""

    @abstractmethod
    def update_engine_change(self, id_cambio: str, estado: str, detalle: Dict[str, Any], fecha_fin: Optional[datetime]) -> None: ...

    @abstractmethod
    def revert_engine_change(self, change: EngineChange, now: datetime) -> bool:
        """Atómico: devuelve la aplicación al motor/conexión de origen con el estado y versión que tenían sus bases.
        False si el cambio ya no está activo."""

    @abstractmethod
    def engine_changes(self, id_aplicacion: str, limit: int) -> List[EngineChange]:
        """Del más reciente al más antiguo."""

    @abstractmethod
    def ping(self) -> None: ...


class InMemoryAppRegistry(AppRegistry):
    def __init__(self) -> None:
        self._apps: Dict[str, Application] = {}
        self._companies: Dict[str, List[AppCompany]] = {}
        self._databases: Dict[str, AppDatabase] = {}
        self._migrations: Dict[str, List[Migration]] = {}
        self._deployments: List[Deployment] = []
        self._changes: Dict[str, EngineChange] = {}
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
        return list(found) if with_script else [
            replace(m, script="", equivalentes={motor: "" for motor in m.equivalentes}) for m in found]

    def record_deployment(self, deployment) -> None:
        with self._lock:
            self._deployments.append(deployment)

    def deployments(self, id_aplicacion, limit):
        found = [d for d in self._deployments if d.id_aplicacion == id_aplicacion]
        return list(reversed(found))[:limit]

    def add_equivalent(self, id_aplicacion, numero, motor, script, checksum, actor, now) -> bool:
        with self._lock:
            current = self._migrations[id_aplicacion]
            index = next(i for i, m in enumerate(current) if m.numero == numero)
            if motor in current[index].equivalentes:
                return False
            current[index] = replace(current[index], equivalentes={**current[index].equivalentes, motor: script})
            return True

    def start_engine_change(self, change) -> bool:
        with self._lock:
            if any(c.activo for c in self._changes.values() if c.id_aplicacion == change.id_aplicacion):
                return False
            self._changes[change.id_cambio] = change
            app = self._apps[change.id_aplicacion]
            self._apps[app.id_aplicacion] = replace(app, motor=change.motor_destino, conexion=change.conexion_destino,
                                                    fecha_modificacion=change.fecha_inicio)
            for name, db in list(self._databases.items()):
                if db.id_aplicacion == change.id_aplicacion:
                    self._databases[name] = replace(db, estado="pendiente", version=0, ultimo_error=None)
            return True

    def update_engine_change(self, id_cambio, estado, detalle, fecha_fin) -> None:
        with self._lock:
            self._changes[id_cambio] = replace(self._changes[id_cambio], estado=estado, detalle=detalle, fecha_fin=fecha_fin)

    def revert_engine_change(self, change, now) -> bool:
        with self._lock:
            current = self._changes.get(change.id_cambio)
            if current is None or not current.activo:
                return False
            app = self._apps[change.id_aplicacion]
            self._apps[app.id_aplicacion] = replace(app, motor=change.motor_origen, conexion=change.conexion_origen,
                                                    fecha_modificacion=now)
            for name, db in list(self._databases.items()):
                if db.id_aplicacion == change.id_aplicacion:
                    origin = change.bases_origen.get(name, {})
                    self._databases[name] = replace(db, estado=origin.get("estado", "pendiente"),
                                                    version=origin.get("version", 0), ultimo_error=origin.get("ultimo_error"))
            self._changes[change.id_cambio] = replace(current, estado="revertido", fecha_fin=now)
            return True

    def engine_changes(self, id_aplicacion, limit):
        found = [c for c in self._changes.values() if c.id_aplicacion == id_aplicacion]
        return list(reversed(found))[:limit]


class SqlServerAppRegistry(AppRegistry):
    _APP_COLUMNS = ("id_aplicacion, nombre, modelo_datos, propietario, seguridad_por_fila, descripcion, id_solicitud, "
                    "estado, creado_por, fecha_creacion, fecha_modificacion, motor, conexion")
    _DB_COLUMNS = "nombre_base, id_aplicacion, id_empresa, estado, version, fecha_creacion, fecha_despliegue, ultimo_error"
    _MIGRATION_COLUMNS = ("id_aplicacion, nombre, tipo, {script}, checksum, numero, descripcion, creado_por, fecha_creacion, "
                          "definicion, motor")
    _CHANGE_COLUMNS = ("id_cambio, id_aplicacion, motor_origen, conexion_origen, motor_destino, conexion_destino, version_origen, "
                       "bases_origen, estado, detalle, solicitado_por, fecha_inicio, fecha_fin")
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
                           creado_por=row[8] or "", fecha_creacion=row[9], fecha_modificacion=row[10], motor=row[11],
                           conexion=row[12])

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
                f"INSERT INTO dbo.nexus_aplicaciones ({self._APP_COLUMNS}) SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? "
                "WHERE NOT EXISTS (SELECT 1 FROM dbo.nexus_aplicaciones WITH (UPDLOCK, HOLDLOCK) WHERE id_aplicacion = ?)",
                (app.id_aplicacion, app.nombre, app.modelo_datos, app.propietario, app.seguridad_por_fila, app.descripcion,
                 app.id_solicitud, app.estado, app.creado_por, app.fecha_creacion, app.fecha_modificacion, app.motor,
                 app.conexion, app.id_aplicacion),
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
            "creado_por, fecha_creacion, definicion, motor) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (migration.id_aplicacion, numero, migration.nombre, migration.tipo, migration.descripcion, migration.script,
             migration.checksum, migration.creado_por, migration.fecha_creacion, migration.definicion, migration.motor),
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
            rows = cur.fetchall()
            equivalents: Dict[int, Dict[str, str]] = {}
            script_column = "script" if with_script else "N''"
            cur.execute(f"SELECT numero, motor, {script_column} FROM dbo.nexus_migracion_equivalentes WHERE id_aplicacion = ?",
                        (id_aplicacion,))
            for numero, motor, script in cur.fetchall():
                equivalents.setdefault(numero, {})[motor] = script
        return [Migration(*r[:5], numero=r[5], descripcion=r[6], creado_por=r[7] or "", fecha_creacion=r[8],
                          definicion=r[9], motor=r[10], equivalentes=equivalents.get(r[5], {}))
                for r in rows]

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

    def add_equivalent(self, id_aplicacion, numero, motor, script, checksum, actor, now) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO dbo.nexus_migracion_equivalentes (id_aplicacion, numero, motor, script, checksum, creado_por, "
                "fecha_creacion) SELECT ?, ?, ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM dbo.nexus_migracion_equivalentes "
                "WITH (UPDLOCK, HOLDLOCK) WHERE id_aplicacion = ? AND numero = ? AND motor = ?)",
                (id_aplicacion, numero, motor, script, checksum, actor, now, id_aplicacion, numero, motor),
            )
            return cur.rowcount == 1

    def start_engine_change(self, change) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                f"INSERT INTO dbo.nexus_cambios_motor ({self._CHANGE_COLUMNS}) SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? "
                "WHERE NOT EXISTS (SELECT 1 FROM dbo.nexus_cambios_motor WITH (UPDLOCK, HOLDLOCK) WHERE id_aplicacion = ? "
                "AND estado NOT IN (N'completado', N'revertido'))",
                (change.id_cambio, change.id_aplicacion, change.motor_origen, change.conexion_origen, change.motor_destino,
                 change.conexion_destino, change.version_origen, dumps(change.bases_origen), change.estado,
                 dumps(change.detalle), change.solicitado_por, change.fecha_inicio, change.fecha_fin, change.id_aplicacion),
            )
            if cur.rowcount != 1:
                return False
            cur.execute("UPDATE dbo.nexus_aplicaciones SET motor = ?, conexion = ?, fecha_modificacion = ? WHERE id_aplicacion = ?",
                        (change.motor_destino, change.conexion_destino, change.fecha_inicio, change.id_aplicacion))
            cur.execute("UPDATE dbo.nexus_bases_datos SET estado = N'pendiente', version = 0, ultimo_error = NULL "
                        "WHERE id_aplicacion = ?", (change.id_aplicacion,))
            return True

    def update_engine_change(self, id_cambio, estado, detalle, fecha_fin) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute("UPDATE dbo.nexus_cambios_motor SET estado = ?, detalle = ?, fecha_fin = ? WHERE id_cambio = ?",
                        (estado, dumps(detalle), fecha_fin, id_cambio))

    def revert_engine_change(self, change, now) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute("UPDATE dbo.nexus_cambios_motor SET estado = N'revertido', fecha_fin = ? "
                        "WHERE id_cambio = ? AND estado NOT IN (N'completado', N'revertido')", (now, change.id_cambio))
            if cur.rowcount != 1:
                return False
            cur.execute("UPDATE dbo.nexus_aplicaciones SET motor = ?, conexion = ?, fecha_modificacion = ? WHERE id_aplicacion = ?",
                        (change.motor_origen, change.conexion_origen, now, change.id_aplicacion))
            cur.execute("UPDATE dbo.nexus_bases_datos SET estado = N'pendiente', version = 0, ultimo_error = NULL "
                        "WHERE id_aplicacion = ?", (change.id_aplicacion,))
            for name, origin in change.bases_origen.items():
                cur.execute("UPDATE dbo.nexus_bases_datos SET estado = ?, version = ?, ultimo_error = ? WHERE nombre_base = ?",
                            (origin.get("estado", "pendiente"), origin.get("version", 0), origin.get("ultimo_error"), name))
            return True

    def engine_changes(self, id_aplicacion, limit):
        with self._db.cursor() as cur:
            cur.execute(f"SELECT TOP (?) {self._CHANGE_COLUMNS} FROM dbo.nexus_cambios_motor WHERE id_aplicacion = ? "
                        "ORDER BY fecha_inicio DESC", (limit, id_aplicacion))
            return [EngineChange(id_cambio=r[0], id_aplicacion=r[1], motor_origen=r[2], conexion_origen=r[3], motor_destino=r[4],
                                 conexion_destino=r[5], version_origen=r[6], bases_origen=loads(r[7], {}), estado=r[8],
                                 detalle=loads(r[9], {}), solicitado_por=r[10] or "", fecha_inicio=r[11], fecha_fin=r[12])
                    for r in cur.fetchall()]
