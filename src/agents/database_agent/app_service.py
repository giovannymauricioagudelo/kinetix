"""
Casos de uso del registro de aplicaciones de Nexus.

Cada aplicación generada tiene su propia base de datos, registrada en kinetix:
- por_empresa: una base independiente por empresa ({app}_{empresa}); las tablas no llevan columna de empresa.
- multiempresa: una sola base ({app}) con dbo.empresas; cada tabla lleva id_empresa con FK, índice y,
  si seguridad_por_fila, una política RLS que filtra por SESSION_CONTEXT('id_empresa').
Las tablas y scripts se registran como migraciones numeradas e inmutables y se despliegan a cada base.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.agents.common import iso, new_id, utcnow
from src.agents.database_agent.app_registry import (
    DATA_MODELS,
    AppCompany,
    AppDatabase,
    Application,
    AppRegistry,
    Deployment,
    Migration,
)
from src.agents.database_agent.database_agent import (
    ColumnDefinition,
    ColumnType,
    SchemaManager,
    TableDefinition,
    quote_identifier,
    sql_string,
)
from src.agents.database_agent.provisioner import ProvisionError, Provisioner, checksum
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError

APP_ID = re.compile(r"^[a-z][a-z0-9_]{1,29}$")
COMPANY_ID = re.compile(r"^[a-z0-9][a-z0-9_]{0,29}$")
MIGRATION_NAME = re.compile(r"^[a-z0-9][a-z0-9_]{0,99}$")
RESERVED_DATABASES = frozenset({"master", "model", "msdb", "tempdb", "kinetix", "distribution", "ssisdb"})
RESERVED_SCHEMAS = frozenset({"seguridad", "despliegue", "sys", "information_schema"})
COMPANY_COLUMN = "id_empresa"
MAX_SCRIPT_CHARS = 200_000
FORBIDDEN_SQL = (
    (r"\bUSE\s+\[?\w", "USE (la base la elige Nexus)"),
    (r"\b(CREATE|ALTER|DROP)\s+DATABASE\b", "CREATE/ALTER/DROP DATABASE"),
    (r"\b(CREATE|ALTER|DROP)\s+LOGIN\b", "CREATE/ALTER/DROP LOGIN"),
    (r"\b(ALTER|CONTROL)\s+SERVER\b|\bSERVER\s+ROLE\b", "permisos de servidor"),
    (r"\bxp_\w+|\bsp_configure\b|\bRECONFIGURE\b|\bSHUTDOWN\b", "procedimientos de sistema"),
    (r"\bOPEN(ROWSET|DATASOURCE|QUERY)\b", "acceso a datos externos"),
    (r"\b(BACKUP|RESTORE)\b", "BACKUP/RESTORE (usa los respaldos de Nexus)"),
    (r"\bEXEC(UTE)?\s*\(|\bsp_executesql\b|\bEXECUTE\s+AS\b|\bIMPERSONATE\b", "SQL dinámico o suplantación"),
    (r"\bDROP\s+(TABLE|SCHEMA|SECURITY\s+POLICY)\b|\bTRUNCATE\b", "borrado de objetos (las migraciones solo agregan)"),
    (r"\bdespliegue\s*\.|\bseguridad\s*\.", "objetos internos de Nexus (despliegue, seguridad)"),
)
_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)

BASE_MULTIEMPRESA = """--| Base multiempresa: catálogo de empresas y función de filtro para seguridad por fila |
IF OBJECT_ID(N'dbo.empresas', N'U') IS NULL
    CREATE TABLE dbo.empresas (
        id_empresa NVARCHAR(255) NOT NULL CONSTRAINT PK_empresas PRIMARY KEY CLUSTERED,
        nombre NVARCHAR(200) NOT NULL,
        estado NVARCHAR(20) NOT NULL CONSTRAINT DF_empresas_estado DEFAULT N'activa',
        fecha_creacion DATETIME2 NOT NULL CONSTRAINT DF_empresas_fecha DEFAULT SYSUTCDATETIME()
    );
GO
IF SCHEMA_ID(N'seguridad') IS NULL EXEC(N'CREATE SCHEMA seguridad');
GO
IF OBJECT_ID(N'seguridad.fn_filtro_empresa', N'IF') IS NULL
    EXEC(N'CREATE FUNCTION seguridad.fn_filtro_empresa(@id_empresa NVARCHAR(255))
RETURNS TABLE WITH SCHEMABINDING AS
RETURN SELECT 1 AS permitido
WHERE @id_empresa = CAST(SESSION_CONTEXT(N''id_empresa'') AS NVARCHAR(255)) OR IS_ROLEMEMBER(N''db_owner'') = 1');
"""


def database_name(app: str, company: Optional[str] = None) -> str:
    return f"{app}_{company}" if company else app


def validate_script(script: str) -> str:
    if not script or not script.strip():
        raise InvalidInputError("El script está vacío")
    if len(script) > MAX_SCRIPT_CHARS:
        raise InvalidInputError(f"El script supera {MAX_SCRIPT_CHARS} caracteres")
    code = _COMMENTS.sub(" ", script)
    for pattern, label in FORBIDDEN_SQL:
        if re.search(pattern, code, re.IGNORECASE):
            raise InvalidInputError(f"El script contiene una instrucción no permitida: {label}")
    return script.replace("\r\n", "\n").lstrip("\ufeff")


def table_ddl(app: Application, name: str, schema: str, columns: Sequence[ColumnDefinition],
              description: Optional[str], audit_columns: bool) -> str:
    if schema.lower() in RESERVED_SCHEMAS:
        raise InvalidInputError(f"El esquema {schema!r} está reservado por Nexus")
    if not any(c.primary_key for c in columns):
        raise InvalidInputError("La tabla necesita una columna primary_key (PK CLUSTERED)")
    names = [c.name.lower() for c in columns]
    if len(names) != len(set(names)):
        raise InvalidInputError("Hay columnas repetidas")
    multi = app.modelo_datos == "multiempresa"
    if multi and COMPANY_COLUMN in names:
        raise InvalidInputError(f"En multiempresa la columna {COMPANY_COLUMN} la agrega Nexus automáticamente")
    if multi:
        columns = [ColumnDefinition(name=COMPANY_COLUMN, type=ColumnType.VARCHAR, nullable=False), *columns]
    try:
        definition = TableDefinition(name=name, schema=schema, columns=list(columns), company_column=False,
                                     warehouse_column=False, audit_columns=audit_columns, description=description)
        quoted_schema, quoted_table = quote_identifier(schema), quote_identifier(name)
        ddl = SchemaManager().create_table(definition)
    except ValueError as e:
        raise InvalidInputError(str(e))
    parts = []
    if schema != "dbo":
        parts.append(f"IF SCHEMA_ID({sql_string(schema)}) IS NULL EXEC(N'CREATE SCHEMA {quoted_schema}');")
    parts.append(ddl)
    if multi:
        object_name = sql_string(f"{schema}.{name}")
        index, fk, policy = f"idx_{name}_{COMPANY_COLUMN}", f"FK_{name}_empresas", f"politica_{name}"
        parts.append(
            f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = {sql_string(index)} AND object_id = OBJECT_ID({object_name}))\n"
            f"    CREATE INDEX [{index}] ON {quoted_schema}.{quoted_table} ([{COMPANY_COLUMN}]);\n"
            f"IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = {sql_string(fk)})\n"
            f"    ALTER TABLE {quoted_schema}.{quoted_table} ADD CONSTRAINT [{fk}] FOREIGN KEY ([{COMPANY_COLUMN}]) "
            "REFERENCES dbo.empresas (id_empresa);"
        )
        if app.seguridad_por_fila:
            target = f"{quoted_schema}.{quoted_table}"
            predicate = f"seguridad.fn_filtro_empresa({COMPANY_COLUMN})"
            statement = (f"CREATE SECURITY POLICY seguridad.[{policy}] ADD FILTER PREDICATE {predicate} ON {target}, "
                         f"ADD BLOCK PREDICATE {predicate} ON {target} AFTER INSERT, "
                         f"ADD BLOCK PREDICATE {predicate} ON {target} AFTER UPDATE WITH (STATE = ON);")
            parts.append(
                f"IF NOT EXISTS (SELECT 1 FROM sys.security_policies WHERE name = {sql_string(policy)})\n"
                f"    EXEC({sql_string(statement)});"
            )
    return "\nGO\n".join(parts) + "\n"


class NexusAppService:
    def __init__(self, registry: AppRegistry, provisioner: Provisioner, clock: Callable = utcnow) -> None:
        self._registry = registry
        self._provisioner = provisioner
        self._clock = clock

    def ping(self) -> None:
        self._registry.ping()

    # ================================================================ vistas

    @staticmethod
    def _app_view(app: Application) -> Dict[str, Any]:
        return {
            "id_aplicacion": app.id_aplicacion,
            "nombre": app.nombre,
            "descripcion": app.descripcion,
            "modelo_datos": app.modelo_datos,
            "seguridad_por_fila": app.seguridad_por_fila if app.modelo_datos == "multiempresa" else False,
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
    def _migration_view(m: Migration, with_script: bool = False) -> Dict[str, Any]:
        view = {"numero": m.numero, "nombre": m.nombre, "tipo": m.tipo, "descripcion": m.descripcion,
                "checksum": m.checksum, "creado_por": m.creado_por, "fecha_creacion": iso(m.fecha_creacion)}
        if with_script:
            view["script"] = m.script
        return view

    @staticmethod
    def _deployment_view(d: Deployment) -> Dict[str, Any]:
        return {"id_despliegue": d.id_despliegue, "nombre_base": d.nombre_base, "id_empresa": d.id_empresa,
                "estado": d.estado, "migraciones_aplicadas": d.migraciones_aplicadas,
                "version_resultante": d.version_resultante, "detalle": d.detalle, "ejecutado_por": d.ejecutado_por,
                "fecha_inicio": iso(d.fecha_inicio), "fecha_fin": iso(d.fecha_fin)}

    def _get(self, id_aplicacion: str, owner: str) -> Application:
        app = self._registry.get_app(id_aplicacion, owner)
        if app is None:
            raise NotFoundError(f"Aplicación no encontrada: {id_aplicacion}")
        return app

    def _ensure_free(self, name: str) -> None:
        if name in RESERVED_DATABASES:
            raise InvalidInputError(f"El nombre de base {name!r} está reservado")
        if self._registry.database_registered(name):
            raise ConflictError(f"La base {name} ya está registrada en Nexus")
        if self._provisioner.database_exists(name):
            raise ConflictError(f"La base {name} ya existe en el servidor y no la gestiona Nexus")

    # ================================================================ aplicaciones

    def register_app(self, actor: str, owner: str, data: Dict[str, Any]) -> Dict[str, Any]:
        app_id = str(data.get("id_aplicacion") or "").strip()
        if not APP_ID.match(app_id):
            raise InvalidInputError("id_aplicacion: minúscula inicial, luego minúsculas, números o '_' (2 a 30)")
        model = data.get("modelo_datos")
        if model not in DATA_MODELS:
            raise InvalidInputError(f"modelo_datos debe ser {' o '.join(DATA_MODELS)}")
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
                self._ensure_free(database_name(app_id, company["id_empresa"]))
        now = self._clock()
        app = Application(
            id_aplicacion=app_id, nombre=name, modelo_datos=model, propietario=owner,
            seguridad_por_fila=bool(data.get("seguridad_por_fila", True)), descripcion=data.get("descripcion"),
            id_solicitud=data.get("id_solicitud"), creado_por=actor, fecha_creacion=now, fecha_modificacion=now,
        )
        databases: List[AppDatabase] = []
        migrations: List[Migration] = []
        if model == "multiempresa":
            self._ensure_free(database_name(app_id))
            databases.append(AppDatabase(nombre_base=database_name(app_id), id_aplicacion=app_id, fecha_creacion=now))
            migrations.append(Migration(id_aplicacion=app_id, nombre="base_multiempresa", tipo="base",
                                        script=BASE_MULTIEMPRESA, checksum=checksum(BASE_MULTIEMPRESA),
                                        descripcion="Catálogo de empresas y filtro de seguridad por fila",
                                        creado_por=actor, fecha_creacion=now))
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
        return {
            **self._app_view(app),
            "empresas": [{"id_empresa": c.id_empresa, "nombre": c.nombre, "estado": c.estado,
                          "nombre_base": database_name(app.id_aplicacion, c.id_empresa if app.modelo_datos == "por_empresa" else None),
                          "fecha_registro": iso(c.fecha_registro)} for c in self._registry.companies(app.id_aplicacion)],
            "bases_datos": [self._database_view(d, latest) for d in self._registry.databases(app.id_aplicacion)],
            "migraciones": [self._migration_view(m) for m in migrations],
            "version_actual": latest,
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
            self._ensure_free(name)
            database = AppDatabase(nombre_base=name, id_aplicacion=app.id_aplicacion, id_empresa=company_id, fecha_creacion=now)
        company = AppCompany(id_aplicacion=app.id_aplicacion, id_empresa=company_id, nombre=str(data["nombre"]).strip(),
                             fecha_registro=now)
        if not self._registry.add_company(company, database):
            raise ConflictError(f"La empresa {company_id} ya está registrada en {app.id_aplicacion}")
        return {"id_empresa": company_id, "nombre": company.nombre,
                "nombre_base": database.nombre_base if database else database_name(app.id_aplicacion),
                "base_nueva": database is not None}

    # ================================================================ objetos y migraciones

    def table(self, actor: str, owner: str, id_aplicacion: str, data: Dict[str, Any], preview: bool = False) -> Dict[str, Any]:
        app = self._get(id_aplicacion, owner)
        name, schema = str(data.get("nombre") or ""), str(data.get("esquema") or "dbo")
        try:
            columns = [c if isinstance(c, ColumnDefinition) else ColumnDefinition.model_validate(c)
                       for c in data.get("columnas") or []]
        except ValueError as e:
            raise InvalidInputError(str(e))
        if not columns:
            raise InvalidInputError("La tabla necesita al menos una columna")
        ddl = table_ddl(app, name, schema, columns, data.get("descripcion"), bool(data.get("columnas_auditoria", True)))
        result: Dict[str, Any] = {"tabla": f"{schema}.{name}", "modelo_datos": app.modelo_datos, "ddl": ddl}
        if preview:
            return {**result, "registrada": False}
        migration = self._add(app, f"tabla_{schema}_{name}".lower(), "tabla", ddl, data.get("descripcion"), actor)
        return {**result, "registrada": True, "migracion": self._migration_view(migration)}

    def add_migration(self, actor: str, owner: str, id_aplicacion: str, data: Dict[str, Any]) -> Dict[str, Any]:
        app = self._get(id_aplicacion, owner)
        name = str(data.get("nombre") or "")
        if not MIGRATION_NAME.match(name):
            raise InvalidInputError("nombre de la migración: minúsculas, números o '_' (máx. 100)")
        script = validate_script(str(data.get("script") or ""))
        return {"migracion": self._migration_view(self._add(app, name, "sql", script, data.get("descripcion"), actor), True)}

    def _add(self, app: Application, name: str, kind: str, script: str, description: Optional[str], actor: str) -> Migration:
        migration = Migration(id_aplicacion=app.id_aplicacion, nombre=name, tipo=kind, script=script,
                              checksum=checksum(script), descripcion=description, creado_por=actor,
                              fecha_creacion=self._clock())
        numero = self._registry.add_migration(migration)
        if numero is None:
            raise ConflictError(f"Ya existe la migración {name!r} en {app.id_aplicacion}")
        return replace(migration, numero=numero)

    def migration(self, owner: str, id_aplicacion: str, numero: int) -> Dict[str, Any]:
        app = self._get(id_aplicacion, owner)
        for m in self._registry.migrations(app.id_aplicacion):
            if m.numero == numero:
                return self._migration_view(m, with_script=True)
        raise NotFoundError(f"Migración no encontrada: {numero}")

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
        companies = ([(c.id_empresa, c.nombre) for c in self._registry.companies(app.id_aplicacion)]
                     if app.modelo_datos == "multiempresa" else [])
        results = [self._deploy_one(app, db, migrations, companies, actor) for db in databases]
        failed = sum(1 for r in results if r["estado"] == "fallido")
        return {"id_aplicacion": app.id_aplicacion, "modelo_datos": app.modelo_datos,
                "version_objetivo": max((m.numero for m in migrations), default=0),
                "bases": len(results), "fallidas": failed, "despliegues": results}

    def _deploy_one(self, app: Application, db: AppDatabase, migrations: List[Migration],
                    companies: List, actor: str) -> Dict[str, Any]:
        started = self._clock()
        created, error = False, None
        try:
            result = self._provisioner.deploy(db.nombre_base, migrations, companies, actor)
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
