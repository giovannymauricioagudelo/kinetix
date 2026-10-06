"""
Casos de uso del registro de aplicaciones de Nexus.

Cada aplicación generada elige su motor (SQL Server, PostgreSQL, Firebird o MongoDB) y tiene su propia base:
- por_empresa: una base independiente por empresa ({app}_{empresa}); las tablas no llevan columna de empresa.
- multiempresa: una sola base ({app}) con empresas; cada tabla lleva id_empresa con índice, FK y, si el motor
  lo admite y seguridad_por_fila, una política de seguridad por fila.
Las tablas se guardan como definición neutral y su script se genera para el motor de la aplicación, así el motor
se puede cambiar (p. ej. de MongoDB a SQL Server cuando la aplicación escala): se despliega el esquema en el
motor nuevo, se copian los datos tabla por tabla y las bases de origen quedan intactas hasta completar el cambio.
El SQL escrito a mano queda atado a su motor: para cambiar de motor necesita un script equivalente.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional, Union

from src.agents.common import iso, new_id, utcnow
from src.agents.database_agent.app_registry import (
    DATA_MODELS,
    AppCompany,
    AppDatabase,
    Application,
    AppRegistry,
    Deployment,
    EngineChange,
    Migration,
)
from src.agents.database_agent.app_templates import (
    BASE_MULTIEMPRESA,
    COMPANY_COLUMN,
    RLS_ENGINES,
    base_definition,
    canonical,
    definition_table,
    engine_warnings,
    render,
    table_definition,
    validate_script,
)
from src.agents.database_agent.database_agent import ColumnDefinition, ColumnType, TableDefinition
from src.agents.database_agent.datastores import copy_table
from src.agents.database_agent.dialects import MOTORES, get_dialect
from src.agents.database_agent.provisioner import ProvisionError, Provisioner, checksum
from src.agents.database_agent.servers import DEFAULT_SERVER, Server, ServerCatalog
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError

__all__ = ["NexusAppService", "BASE_MULTIEMPRESA", "validate_script", "database_name"]

APP_ID = re.compile(r"^[a-z][a-z0-9_]{1,29}$")
COMPANY_ID = re.compile(r"^[a-z0-9][a-z0-9_]{0,29}$")
MIGRATION_NAME = re.compile(r"^[a-z0-9][a-z0-9_]{0,99}$")
RESERVED_DATABASES = frozenset({"master", "model", "msdb", "tempdb", "kinetix", "distribution", "ssisdb",
                                "postgres", "template0", "template1", "admin", "local", "config"})
RESERVED_SCHEMAS = frozenset({"seguridad", "despliegue", "sys", "information_schema", "pg_catalog"})
COPY_BATCH = 1000


def database_name(app: str, company: Optional[str] = None) -> str:
    return f"{app}_{company}" if company else app


class NexusAppService:
    def __init__(self, registry: AppRegistry, servers: Union[ServerCatalog, Provisioner], clock: Callable = utcnow,
                 copy_batch: int = COPY_BATCH) -> None:
        if isinstance(servers, Provisioner):
            servers = ServerCatalog([Server(DEFAULT_SERVER, "sqlserver", servers)])
        self._registry = registry
        self._servers = servers
        self._clock = clock
        self._copy_batch = copy_batch

    def ping(self) -> None:
        self._registry.ping()

    def servers(self) -> List[Dict[str, str]]:
        return self._servers.views()

    # ================================================================ vistas

    @staticmethod
    def _rls(app: Application) -> bool:
        return app.modelo_datos == "multiempresa" and app.seguridad_por_fila and app.motor in RLS_ENGINES

    def _app_view(self, app: Application) -> Dict[str, Any]:
        return {
            "id_aplicacion": app.id_aplicacion,
            "nombre": app.nombre,
            "descripcion": app.descripcion,
            "modelo_datos": app.modelo_datos,
            "motor": app.motor,
            "conexion": app.conexion,
            "seguridad_por_fila": self._rls(app),
            "advertencias": engine_warnings(app.motor, app.modelo_datos == "multiempresa", app.seguridad_por_fila),
            "id_solicitud": app.id_solicitud,
            "estado": app.estado,
            "creado_por": app.creado_por,
            "fecha_creacion": iso(app.fecha_creacion),
        }

    @staticmethod
    def _database_view(db: AppDatabase, latest: int) -> Dict[str, Any]:
        return {
            "nombre_base": db.nombre_base,
            "id_empresa": db.id_empresa,
            "estado": db.estado,
            "version": db.version,
            "migraciones_pendientes": max(latest - db.version, 0),
            "fecha_despliegue": iso(db.fecha_despliegue),
            "ultimo_error": db.ultimo_error,
        }

    @staticmethod
    def _portable(m: Migration) -> bool:
        return m.definicion is not None or m.tipo == "base"

    def _migration_view(self, m: Migration, with_script: bool = False) -> Dict[str, Any]:
        view = {"numero": m.numero, "nombre": m.nombre, "tipo": m.tipo, "descripcion": m.descripcion,
                "checksum": m.checksum, "portable": self._portable(m), "motor": None if self._portable(m) else m.motor or "sqlserver",
                "equivalentes": sorted(m.equivalentes), "creado_por": m.creado_por, "fecha_creacion": iso(m.fecha_creacion)}
        if with_script:
            view["script"] = m.script
            if m.definicion:
                view["definicion"] = json.loads(m.definicion)
            if m.equivalentes:
                view["scripts_equivalentes"] = dict(m.equivalentes)
        return view

    @staticmethod
    def _deployment_view(d: Deployment) -> Dict[str, Any]:
        return {"id_despliegue": d.id_despliegue, "nombre_base": d.nombre_base, "id_empresa": d.id_empresa,
                "estado": d.estado, "migraciones_aplicadas": d.migraciones_aplicadas,
                "version_resultante": d.version_resultante, "detalle": d.detalle, "ejecutado_por": d.ejecutado_por,
                "fecha_inicio": iso(d.fecha_inicio), "fecha_fin": iso(d.fecha_fin)}

    @staticmethod
    def _change_view(c: EngineChange) -> Dict[str, Any]:
        return {"id_cambio": c.id_cambio, "estado": c.estado, "activo": c.activo,
                "origen": {"motor": c.motor_origen, "conexion": c.conexion_origen},
                "destino": {"motor": c.motor_destino, "conexion": c.conexion_destino},
                "version_origen": c.version_origen, "bases_origen": c.bases_origen, "detalle": c.detalle,
                "solicitado_por": c.solicitado_por, "fecha_inicio": iso(c.fecha_inicio), "fecha_fin": iso(c.fecha_fin)}

    def _get(self, id_aplicacion: str, owner: str) -> Application:
        app = self._registry.get_app(id_aplicacion, owner)
        if app is None:
            raise NotFoundError(f"Aplicación no encontrada: {id_aplicacion}")
        return app

    def _server(self, app: Application) -> Server:
        return self._servers.get(app.conexion)

    def _active_change(self, app: Application) -> Optional[EngineChange]:
        return next((c for c in self._registry.engine_changes(app.id_aplicacion, 20) if c.activo), None)

    def _ensure_no_change(self, app: Application) -> None:
        if self._active_change(app) is not None:
            raise ConflictError(f"{app.id_aplicacion} tiene un cambio de motor en curso: complétalo o reviértelo antes")

    def _ensure_free(self, name: str, server: Server) -> None:
        if name in RESERVED_DATABASES:
            raise InvalidInputError(f"El nombre de base {name!r} está reservado")
        if self._registry.database_registered(name):
            raise ConflictError(f"La base {name} ya está registrada en Nexus")
        if server.provisioner.database_exists(name):
            raise ConflictError(f"La base {name} ya existe en {server.nombre} y no la gestiona Nexus")

    # ================================================================ aplicaciones

    @staticmethod
    def _motor(value: Any) -> str:
        motor = str(value or "").strip().lower()
        if motor not in MOTORES:
            raise InvalidInputError(f"motor es obligatorio: {', '.join(MOTORES)}")
        return motor

    def register_app(self, actor: str, owner: str, data: Dict[str, Any]) -> Dict[str, Any]:
        app_id = str(data.get("id_aplicacion") or "").strip()
        if not APP_ID.match(app_id):
            raise InvalidInputError("id_aplicacion: minúscula inicial, luego minúsculas, números o '_' (2 a 30)")
        model = data.get("modelo_datos")
        if model not in DATA_MODELS:
            raise InvalidInputError(f"modelo_datos debe ser {' o '.join(DATA_MODELS)}")
        motor = self._motor(data.get("motor"))
        server = self._servers.resolve(motor, data.get("conexion") or None)
        name = str(data.get("nombre") or "").strip()
        if not 1 <= len(name) <= 100:
            raise InvalidInputError("nombre es obligatorio (máx. 100 caracteres)")
        companies = data.get("empresas") or []
        for company in companies:
            self._validate_company(company)
        if len({c["id_empresa"] for c in companies}) != len(companies):
            raise InvalidInputError("Hay empresas repetidas")
        if self._registry.get_app(app_id, owner) is not None:
            raise ConflictError(f"La aplicación {app_id} ya está registrada")
        if model == "por_empresa":
            for company in companies:
                self._ensure_free(database_name(app_id, company["id_empresa"]), server)
        now = self._clock()
        rls = bool(data.get("seguridad_por_fila", True))
        app = Application(
            id_aplicacion=app_id, nombre=name, modelo_datos=model, propietario=owner, seguridad_por_fila=rls,
            descripcion=data.get("descripcion"), id_solicitud=data.get("id_solicitud"), creado_por=actor,
            fecha_creacion=now, fecha_modificacion=now, motor=motor, conexion=server.nombre,
        )
        databases: List[AppDatabase] = []
        migrations: List[Migration] = []
        if model == "multiempresa":
            self._ensure_free(database_name(app_id), server)
            databases.append(AppDatabase(nombre_base=database_name(app_id), id_aplicacion=app_id, fecha_creacion=now))
            definition = canonical(base_definition(rls))
            migrations.append(Migration(id_aplicacion=app_id, nombre="base_multiempresa", tipo="base",
                                        script=render(base_definition(rls), motor), checksum=checksum(definition),
                                        descripcion="Catálogo de empresas y filtro de seguridad por fila",
                                        creado_por=actor, fecha_creacion=now, definicion=definition))
        if not self._registry.create_app(app, databases, migrations):
            raise ConflictError(f"La aplicación {app_id} o su base ya están registradas")
        for company in companies:
            self.add_company(actor, owner, app_id, company)
        return self.get_app(owner, app_id)

    def list_apps(self, owner: str) -> Dict[str, Any]:
        apps = self._registry.list_apps(owner)
        views = []
        for app in apps:
            latest = len(self._registry.migrations(app.id_aplicacion, with_script=False))
            dbs = self._registry.databases(app.id_aplicacion)
            views.append({**self._app_view(app), "total_bases": len(dbs),
                          "bases_desactualizadas": sum(1 for d in dbs if d.version < latest or d.estado != "desplegada")})
        return {"total": len(views), "aplicaciones": views}

    def get_app(self, owner: str, id_aplicacion: str) -> Dict[str, Any]:
        app = self._get(id_aplicacion, owner)
        migrations = self._registry.migrations(app.id_aplicacion, with_script=False)
        latest = max((m.numero for m in migrations), default=0)
        change = self._active_change(app)
        return {
            **self._app_view(app),
            "empresas": [{"id_empresa": c.id_empresa, "nombre": c.nombre, "estado": c.estado,
                          "nombre_base": database_name(app.id_aplicacion, c.id_empresa if app.modelo_datos == "por_empresa" else None),
                          "fecha_registro": iso(c.fecha_registro)} for c in self._registry.companies(app.id_aplicacion)],
            "bases_datos": [self._database_view(d, latest) for d in self._registry.databases(app.id_aplicacion)],
            "migraciones": [self._migration_view(m) for m in migrations],
            "version_actual": latest,
            "cambio_motor_activo": self._change_view(change) if change else None,
        }

    # ================================================================ empresas

    @staticmethod
    def _validate_company(data: Dict[str, Any]) -> None:
        if not COMPANY_ID.match(str(data.get("id_empresa") or "")):
            raise InvalidInputError("id_empresa: minúsculas, números o '_' (máx. 30)")
        if not 1 <= len(str(data.get("nombre") or "").strip()) <= 200:
            raise InvalidInputError("nombre de la empresa es obligatorio (máx. 200 caracteres)")

    def add_company(self, actor: str, owner: str, id_aplicacion: str, data: Dict[str, Any]) -> Dict[str, Any]:
        app = self._get(id_aplicacion, owner)
        self._validate_company(data)
        company_id = data["id_empresa"]
        now = self._clock()
        database = None
        if app.modelo_datos == "por_empresa":
            name = database_name(app.id_aplicacion, company_id)
            self._ensure_free(name, self._server(app))
            database = AppDatabase(nombre_base=name, id_aplicacion=app.id_aplicacion, id_empresa=company_id, fecha_creacion=now)
        company = AppCompany(id_aplicacion=app.id_aplicacion, id_empresa=company_id, nombre=str(data["nombre"]).strip(),
                             fecha_registro=now)
        if not self._registry.add_company(company, database):
            raise ConflictError(f"La empresa {company_id} ya está registrada en {app.id_aplicacion}")
        return {"id_empresa": company_id, "nombre": company.nombre,
                "nombre_base": database.nombre_base if database else database_name(app.id_aplicacion),
                "base_nueva": database is not None}

    # ================================================================ objetos y migraciones

    def _table_definition(self, app: Application, data: Dict[str, Any]) -> Dict[str, Any]:
        name, schema = str(data.get("nombre") or ""), str(data.get("esquema") or "dbo")
        if schema.lower() in RESERVED_SCHEMAS:
            raise InvalidInputError(f"El esquema {schema!r} está reservado por Nexus")
        try:
            columns = [c if isinstance(c, ColumnDefinition) else ColumnDefinition.model_validate(c)
                       for c in data.get("columnas") or []]
        except ValueError as e:
            raise InvalidInputError(str(e))
        if not columns:
            raise InvalidInputError("La tabla necesita al menos una columna")
        if not any(c.primary_key for c in columns):
            raise InvalidInputError("La tabla necesita una columna primary_key")
        names = [c.name.lower() for c in columns]
        if len(names) != len(set(names)):
            raise InvalidInputError("Hay columnas repetidas")
        multi = app.modelo_datos == "multiempresa"
        if multi and COMPANY_COLUMN in names:
            raise InvalidInputError(f"En multiempresa la columna {COMPANY_COLUMN} la agrega Nexus automáticamente")
        if multi:
            columns = [ColumnDefinition(name=COMPANY_COLUMN, type=ColumnType.VARCHAR, nullable=False), *columns]
        try:
            table = TableDefinition(name=name, schema=schema, columns=list(columns), company_column=False,
                                    warehouse_column=False, audit_columns=bool(data.get("columnas_auditoria", True)),
                                    description=data.get("descripcion"))
        except ValueError as e:
            raise InvalidInputError(str(e))
        return table_definition(table, multi, app.seguridad_por_fila)

    def table(self, actor: str, owner: str, id_aplicacion: str, data: Dict[str, Any], preview: bool = False) -> Dict[str, Any]:
        app = self._get(id_aplicacion, owner)
        definition = self._table_definition(app, data)
        try:
            ddl = render(definition, app.motor)
        except ValueError as e:
            raise InvalidInputError(str(e))
        compatible, incompatible = [], {}
        for motor in MOTORES:
            try:
                render(definition, motor)
                compatible.append(motor)
            except ValueError as e:
                incompatible[motor] = str(e)
        table = definition_table(definition)
        result: Dict[str, Any] = {"tabla": f"{table.schema}.{table.name}", "modelo_datos": app.modelo_datos,
                                  "motor": app.motor, "lenguaje_ddl": get_dialect(app.motor).lenguaje, "ddl": ddl,
                                  "motores_compatibles": compatible, "motores_incompatibles": incompatible}
        if preview:
            return {**result, "registrada": False}
        self._ensure_no_change(app)
        definition_json = canonical(definition)
        migration = self._add(app, Migration(
            id_aplicacion=app.id_aplicacion, nombre=f"tabla_{table.schema}_{table.name}".lower(), tipo="tabla", script=ddl,
            checksum=checksum(definition_json), descripcion=data.get("descripcion"), creado_por=actor,
            fecha_creacion=self._clock(), definicion=definition_json,
        ))
        return {**result, "registrada": True, "migracion": self._migration_view(migration)}

    def add_migration(self, actor: str, owner: str, id_aplicacion: str, data: Dict[str, Any]) -> Dict[str, Any]:
        app = self._get(id_aplicacion, owner)
        name = str(data.get("nombre") or "")
        if not MIGRATION_NAME.match(name):
            raise InvalidInputError("nombre de la migración: minúsculas, números o '_' (máx. 100)")
        script = validate_script(str(data.get("script") or ""), app.motor)
        self._ensure_no_change(app)
        migration = self._add(app, Migration(
            id_aplicacion=app.id_aplicacion, nombre=name, tipo="sql", script=script, checksum=checksum(script),
            descripcion=data.get("descripcion"), creado_por=actor, fecha_creacion=self._clock(), motor=app.motor,
        ))
        return {"migracion": self._migration_view(migration, True)}

    def _add(self, app: Application, migration: Migration) -> Migration:
        numero = self._registry.add_migration(migration)
        if numero is None:
            raise ConflictError(f"Ya existe la migración {migration.nombre!r} en {app.id_aplicacion}")
        return replace(migration, numero=numero)

    def _find_migration(self, app: Application, numero: int) -> Migration:
        for m in self._registry.migrations(app.id_aplicacion):
            if m.numero == numero:
                return m
        raise NotFoundError(f"Migración no encontrada: {numero}")

    def migration(self, owner: str, id_aplicacion: str, numero: int) -> Dict[str, Any]:
        return self._migration_view(self._find_migration(self._get(id_aplicacion, owner), numero), with_script=True)

    def add_equivalent(self, actor: str, owner: str, id_aplicacion: str, numero: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Script de una migración SQL manual para otro motor: sin él la aplicación no puede pasar a ese motor."""
        app = self._get(id_aplicacion, owner)
        migration = self._find_migration(app, numero)
        if self._portable(migration):
            raise InvalidInputError("Esta migración es portable: Nexus genera su script para cada motor")
        motor = self._motor(data.get("motor"))
        if motor == (migration.motor or "sqlserver"):
            raise InvalidInputError(f"La migración ya está escrita para {motor}")
        script = validate_script(str(data.get("script") or ""), motor)
        if not self._registry.add_equivalent(app.id_aplicacion, numero, motor, script, checksum(script), actor, self._clock()):
            raise ConflictError(f"La migración {numero} ya tiene equivalente para {motor} (los equivalentes son inmutables)")
        return {"migracion": self._migration_view(self._find_migration(app, numero), with_script=True)}

    # ================================================================ scripts por motor

    @staticmethod
    def _script_for(app: Application, m: Migration, motor: str) -> str:
        """ValueError si la migración no se puede llevar a ese motor."""
        if m.definicion:
            return render(json.loads(m.definicion), motor)
        if m.tipo == "base":
            return render(base_definition(app.seguridad_por_fila), motor)
        written_for = m.motor or "sqlserver"
        if motor == written_for:
            return m.script
        if motor in m.equivalentes:
            return m.equivalentes[motor]
        raise ValueError(f"Migración {m.numero} ({m.nombre}) es SQL manual de {written_for}: registra su equivalente para {motor}")

    def _deployable(self, app: Application, migrations: List[Migration], motor: str) -> List[Migration]:
        try:
            return [replace(m, script=self._script_for(app, m, motor)) for m in migrations]
        except ValueError as e:
            raise InvalidInputError(str(e))

    # ================================================================ despliegue

    def deploy(self, actor: str, owner: str, id_aplicacion: str, id_empresa: Optional[str] = None) -> Dict[str, Any]:
        app = self._get(id_aplicacion, owner)
        databases = self._registry.databases(app.id_aplicacion)
        if id_empresa:
            if app.modelo_datos == "multiempresa":
                raise InvalidInputError("En multiempresa todas las empresas comparten una base: despliega sin id_empresa")
            databases = [d for d in databases if d.id_empresa == id_empresa]
            if not databases:
                raise NotFoundError(f"La empresa {id_empresa} no tiene base en {app.id_aplicacion}")
        if not databases:
            raise InvalidInputError("La aplicación no tiene bases: registra al menos una empresa (modelo por_empresa)")
        migrations = self._registry.migrations(app.id_aplicacion)
        deployable = self._deployable(app, migrations, app.motor)
        companies = ([(c.id_empresa, c.nombre) for c in self._registry.companies(app.id_aplicacion)]
                     if app.modelo_datos == "multiempresa" else [])
        server = self._server(app)
        results = [self._deploy_one(app, server, db, deployable, companies, actor) for db in databases]
        failed = sum(1 for r in results if r["estado"] == "fallido")
        return {"id_aplicacion": app.id_aplicacion, "modelo_datos": app.modelo_datos, "motor": app.motor,
                "conexion": app.conexion, "version_objetivo": max((m.numero for m in migrations), default=0),
                "bases": len(results), "fallidas": failed, "despliegues": results}

    def _deploy_one(self, app: Application, server: Server, db: AppDatabase, migrations: List[Migration],
                    companies: List, actor: str) -> Dict[str, Any]:
        started = self._clock()
        created, error = False, None
        try:
            result = server.provisioner.deploy(db.nombre_base, migrations, companies, actor)
            created, applied, version = result.created, result.applied, result.version
            status = "exitoso" if applied or created else "sin_cambios"
            self._registry.update_database(db.nombre_base, "desplegada", version, None, self._clock())
        except ProvisionError as e:
            applied, error, status = e.applied, str(e)[:1000], "fallido"
            version = max([db.version, *applied])
            self._registry.update_database(db.nombre_base, "error", version, error, self._clock())
        deployment = Deployment(
            id_despliegue=new_id("dep"), id_aplicacion=app.id_aplicacion, nombre_base=db.nombre_base, estado=status,
            id_empresa=db.id_empresa, migraciones_aplicadas=list(applied), version_resultante=version, detalle=error,
            ejecutado_por=actor, fecha_inicio=started, fecha_fin=self._clock(),
        )
        self._registry.record_deployment(deployment)
        return {**self._deployment_view(deployment), "base_creada": created}

    def deployments(self, owner: str, id_aplicacion: str, limit: int) -> Dict[str, Any]:
        app = self._get(id_aplicacion, owner)
        found = self._registry.deployments(app.id_aplicacion, limit)
        return {"total": len(found), "despliegues": [self._deployment_view(d) for d in found]}

    # ================================================================ cambio de motor

    def engine_change_plan(self, owner: str, id_aplicacion: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Qué implica pasar la aplicación a otro motor/conexión y qué lo impide, sin tocar nada."""
        app = self._get(id_aplicacion, owner)
        motor = self._motor(data.get("motor"))
        target = self._servers.resolve(motor, data.get("conexion") or None)
        blockers: List[str] = []
        warnings: List[str] = []
        if motor == app.motor and target.nombre == app.conexion:
            blockers.append(f"La aplicación ya está en {motor} ({app.conexion})")
        if self._active_change(app) is not None:
            blockers.append("Ya hay un cambio de motor en curso: complétalo o reviértelo")
        for server in (self._server(app), target):
            if server.datos is None:
                blockers.append(f"La conexión {server.nombre} no permite copiar datos")
        migrations = self._registry.migrations(app.id_aplicacion)
        latest = max((m.numero for m in migrations), default=0)
        for m in migrations:
            try:
                self._script_for(app, m, motor)
            except ValueError as e:
                blockers.append(str(e))
        databases = self._registry.databases(app.id_aplicacion)
        previous = {c.conexion_destino for c in self._registry.engine_changes(app.id_aplicacion, 100) if c.estado == "revertido"}
        for db in databases:
            if db.version and (db.version < latest or db.estado != "desplegada"):
                blockers.append(f"La base {db.nombre_base} no está al día en {app.motor}: despliega antes de cambiar de motor")
            if target.nombre != app.conexion and target.provisioner.database_exists(db.nombre_base):
                if target.nombre in previous:
                    warnings.append(f"La base {db.nombre_base} quedó en {target.nombre} de un cambio revertido: "
                                    "las tablas que ya tengan filas no se vuelven a copiar (vacíalas antes)")
                else:
                    blockers.append(f"La base {db.nombre_base} ya existe en {target.nombre} y no la gestiona Nexus")
        tables = [definition_table(json.loads(m.definicion)) for m in migrations if m.tipo == "tabla" and m.definicion]
        manual = [m for m in migrations if not self._portable(m)]
        warnings.extend(engine_warnings(motor, app.modelo_datos == "multiempresa", app.seguridad_por_fila))
        if manual:
            warnings.append(f"{len(manual)} migración(es) SQL manual(es) se aplican con su equivalente, pero los datos "
                            "de las tablas que creen no se copian")
        if not any(db.version for db in databases):
            warnings.append("Las bases aún no se han desplegado: no hay datos que copiar")
        warnings.append("Detén las escrituras de la aplicación durante el cambio: la copia es una foto del momento")
        return {
            "id_aplicacion": app.id_aplicacion,
            "origen": {"motor": app.motor, "conexion": app.conexion},
            "destino": {"motor": motor, "conexion": target.nombre},
            "bases": [db.nombre_base for db in databases],
            "tablas_a_copiar": [f"{t.schema}.{t.name}" for t in tables],
            "version": latest,
            "viable": not blockers,
            "bloqueos": blockers,
            "advertencias": warnings,
        }

    def change_engine(self, actor: str, owner: str, id_aplicacion: str, data: Dict[str, Any],
                      preview: bool = False) -> Dict[str, Any]:
        """Mueve la aplicación al motor destino, despliega allí su esquema y copia los datos. Revertible hasta completar."""
        plan = self.engine_change_plan(owner, id_aplicacion, data)
        if preview:
            return {**plan, "vista_previa": True}
        if plan["bloqueos"]:
            raise ConflictError("No se puede cambiar de motor: " + "; ".join(plan["bloqueos"]))
        app = self._get(id_aplicacion, owner)
        now = self._clock()
        change = EngineChange(
            id_cambio=new_id("cmb"), id_aplicacion=app.id_aplicacion, motor_origen=app.motor, conexion_origen=app.conexion,
            motor_destino=plan["destino"]["motor"], conexion_destino=plan["destino"]["conexion"], version_origen=plan["version"],
            bases_origen={d.nombre_base: {"estado": d.estado, "version": d.version, "ultimo_error": d.ultimo_error}
                          for d in self._registry.databases(app.id_aplicacion)},
            solicitado_por=actor, fecha_inicio=now,
        )
        if not self._registry.start_engine_change(change):
            raise ConflictError("Ya hay un cambio de motor en curso: complétalo o reviértelo")
        result = self._run_change(actor, owner, change)
        return {**result, "advertencias": plan["advertencias"]}

    def _run_change(self, actor: str, owner: str, change: EngineChange) -> Dict[str, Any]:
        deployment = self.deploy(actor, owner, change.id_aplicacion)
        detail: Dict[str, Any] = {"despliegue": {"bases": deployment["bases"], "fallidas": deployment["fallidas"],
                                                 "version": deployment["version_objetivo"]}}
        if deployment["fallidas"]:
            self._registry.update_engine_change(change.id_cambio, "esquema_con_errores", detail, None)
            return {"cambio": self._change_view(self._reload(change)), "despliegue": deployment, "copia": [],
                    "siguiente_paso": "Corrige el error y reintenta con copiar-datos, o revierte el cambio"}
        self._registry.update_engine_change(change.id_cambio, "esquema_desplegado", detail, None)
        copies = self._copy(change)
        failed = [c for c in copies if c["estado"] == "incompleta"]
        detail["copia"] = copies
        self._registry.update_engine_change(change.id_cambio, "copia_con_errores" if failed else "datos_copiados", detail, None)
        return {"cambio": self._change_view(self._reload(change)), "despliegue": deployment, "copia": copies,
                "siguiente_paso": ("Revisa las tablas incompletas y reintenta con copiar-datos, o revierte el cambio" if failed
                                   else "Valida la aplicación en el motor nuevo y completa el cambio (o reviértelo)")}

    def _reload(self, change: EngineChange) -> EngineChange:
        return next(c for c in self._registry.engine_changes(change.id_aplicacion, 20) if c.id_cambio == change.id_cambio)

    def _copy(self, change: EngineChange) -> List[Dict[str, Any]]:
        source, target = self._servers.get(change.conexion_origen), self._servers.get(change.conexion_destino)
        if source.datos is None or target.datos is None:
            raise InvalidInputError(f"La conexión {source.nombre if source.datos is None else target.nombre} no permite copiar datos")
        tables = [(m.numero, definition_table(json.loads(m.definicion)))
                  for m in self._registry.migrations(change.id_aplicacion)
                  if m.tipo == "tabla" and m.definicion and m.numero <= change.version_origen]
        results = []
        for name, origin in sorted(change.bases_origen.items()):
            for numero, table in tables:
                if numero <= origin.get("version", 0):
                    results.append(copy_table(source.datos, target.datos, name, table, self._copy_batch))
        return results

    def _require_active(self, owner: str, id_aplicacion: str) -> EngineChange:
        change = self._active_change(self._get(id_aplicacion, owner))
        if change is None:
            raise NotFoundError(f"{id_aplicacion} no tiene un cambio de motor en curso")
        return change

    def copy_engine_data(self, actor: str, owner: str, id_aplicacion: str) -> Dict[str, Any]:
        """Reintenta el cambio en curso: despliega lo pendiente en el destino y copia las tablas que falten."""
        return self._run_change(actor, owner, self._require_active(owner, id_aplicacion))

    def complete_engine_change(self, actor: str, owner: str, id_aplicacion: str) -> Dict[str, Any]:
        change = self._require_active(owner, id_aplicacion)
        if change.estado != "datos_copiados":
            raise InvalidInputError(f"El cambio está en {change.estado}: solo se completa con los datos copiados")
        self._registry.update_engine_change(change.id_cambio, "completado", {**change.detalle, "completado_por": actor},
                                            self._clock())
        return {"cambio": self._change_view(self._reload(change)),
                "nota": f"Las bases de origen en {change.conexion_origen} quedan sin borrar: Nexus no elimina bases"}

    def revert_engine_change(self, actor: str, owner: str, id_aplicacion: str) -> Dict[str, Any]:
        change = self._require_active(owner, id_aplicacion)
        if not self._registry.revert_engine_change(change, self._clock()):
            raise ConflictError("El cambio ya no está activo")
        return {"cambio": self._change_view(self._reload(change)), "revertido_por": actor,
                "nota": f"La aplicación vuelve a {change.motor_origen} ({change.conexion_origen}); las bases creadas en "
                        f"{change.conexion_destino} quedan sin borrar"}

    def engine_changes(self, owner: str, id_aplicacion: str, limit: int) -> Dict[str, Any]:
        app = self._get(id_aplicacion, owner)
        found = self._registry.engine_changes(app.id_aplicacion, limit)
        return {"total": len(found), "cambios": [self._change_view(c) for c in found]}
