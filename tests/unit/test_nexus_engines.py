"""Unit tests for Nexus multi-engine support: dialects (PostgreSQL, Firebird, MongoDB), connection URLs,
engine capabilities, the connection registry, file backups and the ?conexion= / ?motor= API."""

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agents.base_agent import AgentStatus
from src.agents.database_agent import dependencies
from src.agents.database_agent.catalog import InMemoryCatalog, ProcedureParameter
from src.agents.database_agent.database_agent import (
    ColumnDefinition,
    ColumnType,
    DatabaseAgent,
    DatabaseAgentInput,
    SchemaManager,
    TableDefinition,
)
from src.agents.database_agent.dialects import (
    FirebirdDialect,
    MongoDialect,
    PostgresDialect,
    firebird_statements,
    get_dialect,
)
from src.agents.database_agent.engines import FirebirdSettings, MongoSettings, PostgresSettings, parse_connection_url
from src.agents.database_agent.file_backups import backup_target, list_backup_files, run_tool
from src.agents.database_agent.firebird_catalog import FirebirdCatalog, field_type
from src.agents.database_agent.mongo_catalog import MongoCatalog, columns_from_validator, parse_commands
from src.agents.database_agent.postgres_catalog import PostgresCatalog
from src.agents.database_agent.service import NexusService
from src.agents.security_agent import SecurityService
from src.agents.security_agent.config import SecuritySettings, SqlServerSettings
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError
from src.api.routes import nexus_routes, sentinel_routes
from tests.unit.test_sentinel_agent import PASSWORDS, seeded_repository


def clientes(schema="dbo", description="Clientes | multisector", alta="GETUTCDATE()"):
    return TableDefinition(name="clientes", schema=schema, description=description, columns=[
        ColumnDefinition(name="cliente_id", type=ColumnType.BIGINT, primary_key=True),
        ColumnDefinition(name="empresa_id", type=ColumnType.INT, nullable=False),
        ColumnDefinition(name="bodega_id", type=ColumnType.INT, nullable=False),
        ColumnDefinition(name="nombre", type=ColumnType.VARCHAR, nullable=False, default="O'Brien"),
        ColumnDefinition(name="nit", type=ColumnType.VARCHAR, unique=True),
        ColumnDefinition(name="activo", type=ColumnType.BOOLEAN, default="true"),
        ColumnDefinition(name="alta", type=ColumnType.DATETIME, default=alta),
        ColumnDefinition(name="datos", type=ColumnType.JSON),
    ])


# ============================================================================ dialectos


def test_postgres_ddl_is_idempotent_and_maps_dbo_to_public():
    ddl = PostgresDialect().create_table(clientes())
    assert 'CREATE TABLE IF NOT EXISTS "public"."clientes" (' in ddl
    assert "CREATE SCHEMA" not in ddl
    assert '"cliente_id" BIGINT NOT NULL CONSTRAINT "pk_clientes" PRIMARY KEY' in ddl
    assert "\"nombre\" VARCHAR(255) NOT NULL DEFAULT 'O''Brien'" in ddl
    assert '"activo" BOOLEAN NULL DEFAULT TRUE' in ddl
    assert "\"alta\" TIMESTAMP NULL DEFAULT (NOW() AT TIME ZONE 'utc')" in ddl
    assert '"datos" JSONB NULL' in ddl
    assert '"nit" VARCHAR(255) NULL CONSTRAINT "uq_clientes_nit" UNIQUE' in ddl
    assert 'CREATE INDEX IF NOT EXISTS "idx_clientes_empresa_id" ON "public"."clientes" ("empresa_id");' in ddl
    assert "COMMENT ON TABLE \"public\".\"clientes\" IS 'Clientes | multisector';" in ddl
    assert "--| Tabla public.clientes: Clientes / multisector |" in ddl


def test_postgres_ddl_creates_custom_schema():
    ddl = PostgresDialect().create_table(clientes(schema="ventas"))
    assert 'CREATE SCHEMA IF NOT EXISTS "ventas";' in ddl
    assert 'CREATE TABLE IF NOT EXISTS "ventas"."clientes"' in ddl


def test_firebird_ddl_is_an_isql_script_with_guarded_statements():
    ddl = FirebirdDialect().create_table(clientes(alta="CURRENT_TIMESTAMP"))
    assert ddl.splitlines()[1] == "SET TERM ^ ;" and ddl.endswith("SET TERM ; ^")
    assert "WHERE RDB$RELATION_NAME = 'CLIENTES'" in ddl
    assert "\"NOMBRE\" VARCHAR(255) CHARACTER SET UTF8 DEFAULT ''O''''Brien'' NOT NULL" in ddl
    assert '"CLIENTE_ID" BIGINT NOT NULL CONSTRAINT "PK_CLIENTES" PRIMARY KEY' in ddl
    assert '"DATOS" BLOB SUB_TYPE TEXT CHARACTER SET UTF8' in ddl
    assert '"ACTIVO" BOOLEAN DEFAULT TRUE' in ddl

    statements = firebird_statements(ddl)
    assert [s.split()[0] for s in statements] == ["EXECUTE", "COMMIT", "EXECUTE", "COMMIT", "EXECUTE", "COMMIT", "COMMENT", "COMMIT"]
    assert "IDX_CLIENTES_BODEGA_ID" in statements[4]
    assert statements[6] == "COMMENT ON TABLE \"CLIENTES\" IS 'Clientes / multisector'"


@pytest.mark.parametrize("default, message", [("GETUTCDATE()", "CURRENT_TIMESTAMP"), ("NEWID()", "no admite")])
def test_firebird_rejects_defaults_it_cannot_store(default, message):
    definition = clientes(alta="CURRENT_TIMESTAMP")
    definition.columns.append(ColumnDefinition(name="extra", type=ColumnType.VARCHAR, default=default))
    valid, error = SchemaManager(FirebirdDialect()).validate_schema(definition)
    assert not valid and message in error


def test_mongo_ddl_is_a_list_of_allowed_commands():
    commands = json.loads(MongoDialect().create_table(clientes()))
    create, indexes = commands
    schema = create["validator"]["$jsonSchema"]
    assert create["create"] == "clientes" and create["validationLevel"] == "strict"
    assert schema["properties"]["cliente_id"] == {"bsonType": ["long", "int"]}
    assert schema["properties"]["nombre"] == {"bsonType": "string", "maxLength": 255, "description": "default: O'Brien"}
    assert schema["properties"]["datos"]["bsonType"] == ["object", "array", "null"]
    assert {"cliente_id", "empresa_id", "bodega_id", "nombre", "created_at", "updated_at"} == set(schema["required"])
    by_name = {i["name"]: i for i in indexes["indexes"]}
    assert by_name["pk_clientes"]["unique"] is True and "partialFilterExpression" not in by_name["pk_clientes"]
    assert by_name["uq_clientes_nit"]["partialFilterExpression"] == {"nit": {"$type": "string"}}
    assert set(by_name) == {"pk_clientes", "uq_clientes_nit", "idx_clientes_empresa_id", "idx_clientes_bodega_id"}
    assert parse_commands(json.dumps(commands)) == commands


def test_get_dialect():
    assert get_dialect(None).motor == "sqlserver"
    assert get_dialect(" PostgreSQL ").motor == "postgresql"
    with pytest.raises(ValueError, match="no soportado"):
        get_dialect("oracle")


def test_legacy_agent_generates_ddl_for_requested_engine():
    output = DatabaseAgent()
    result = pytest.importorskip("asyncio").run(output.execute(DatabaseAgentInput(
        request_id="r1", action="create_table", table_definition=clientes(), motor="postgresql")))
    assert result.status == AgentStatus.SUCCESS
    assert result.result["motor"] == "postgresql" and "JSONB" in result.result["ddl_script"]


# ============================================================================ URLs de conexión


def test_parse_postgres_url_decodes_credentials_and_hides_them():
    spec = parse_connection_url("ventas_pg", "postgresql://app:cl%40ve@db.local:6543/ventas?sslmode=require")
    assert spec.motor == "postgresql"
    assert spec.settings == PostgresSettings("db.local", 6543, "ventas", "app", "cl@ve", "require")
    assert spec.public_view() == {"nombre": "ventas_pg", "motor": "postgresql", "host": "db.local", "base_datos": "ventas"}
    assert "cl@ve" not in repr(spec) and "cl@ve" not in repr(spec.settings)


@pytest.mark.parametrize("url, dsn", [
    ("firebird://SYSDBA:mk@srv:3050/C:/datos/erp.fdb", "srv/3050:C:/datos/erp.fdb"),
    ("firebird://SYSDBA:mk@srv//var/db/erp.fdb", "srv:/var/db/erp.fdb"),
    ("firebird://SYSDBA:mk@srv/erp", "srv:erp"),
    ("firebird:///C:/local/erp.fdb", "C:/local/erp.fdb"),
])
def test_parse_firebird_url(url, dsn):
    spec = parse_connection_url("legado", url)
    assert spec.motor == "firebird" and spec.settings.dsn == dsn


def test_parse_mongo_and_sqlserver_urls():
    mongo = parse_connection_url("docs", "mongodb://u:p@h1:27017,h2:27017/documentos?replicaSet=rs0")
    assert mongo.motor == "mongodb" and mongo.settings.database == "documentos" and mongo.host == "h1:27017,h2:27017"
    assert parse_connection_url("atlas", "mongodb+srv://u:p@cluster.example.net/app").motor == "mongodb"
    sql = parse_connection_url("sucursal", "mssql://sa:x@srv:1433/sucursal?driver=ODBC+Driver+17+for+SQL+Server")
    assert sql.settings == SqlServerSettings("ODBC Driver 17 for SQL Server", "srv,1433", "sucursal", "sa", "x")


@pytest.mark.parametrize("name, url, message", [
    ("x", "postgresql://h/db", "Nombre de conexión inválido"),
    ("legado", "oracle://h/db", "no soportado"),
    ("ventas", "postgresql://u:p@h:5432", "/base"),
    ("docs", "mongodb://h:27017", "debe indicar la base"),
    ("legado", "firebird://u:p@h", "ruta o el alias"),
])
def test_parse_connection_url_errors(name, url, message):
    with pytest.raises(ValueError, match=message):
        parse_connection_url(name, url)


# ============================================================================ servicio por motor


def test_mongo_connection_has_no_procedures_but_has_ddl():
    nexus = NexusService(InMemoryCatalog("mongodb"))
    assert nexus.info()["capacidades"] == ["respaldos"] and nexus.info()["lenguaje_ddl"] == "json"
    for call in (nexus.procedures, lambda: nexus.procedure("sp_x"), lambda: nexus.execute_procedure("sp_x", {})):
        with pytest.raises(InvalidInputError, match="MongoDB no admite procedimientos"):
            call()
    created = nexus.create_table(clientes())
    assert created["tabla"] == "clientes" and created["motor"] == "mongodb"
    assert nexus.table("clientes")["tabla"] == "clientes"
    with pytest.raises(ConflictError):
        nexus.create_table(clientes())


def test_firebird_connection_ignores_schema_and_case():
    nexus = NexusService(InMemoryCatalog("firebird"))
    with pytest.raises(InvalidInputError, match="CURRENT_TIMESTAMP"):
        nexus.create_table(clientes())
    created = nexus.create_table(clientes(alta="CURRENT_TIMESTAMP"))
    assert created["tabla"] == "CLIENTES" and "SET TERM" in created["ddl"]
    assert nexus.table("clientes")["tabla"] == "CLIENTES"
    assert nexus.table("cualquier_esquema.clientes")["tabla"] == "CLIENTES"
    with pytest.raises(ConflictError):
        nexus.create_table(clientes(alta="CURRENT_TIMESTAMP"))


def test_postgres_connection_resolves_default_schema_and_generates_for_other_engines():
    catalog = InMemoryCatalog("postgresql")
    catalog.add_procedure("public", "fn_total", [ProcedureParameter("@id_empresa", "integer", None, False, False)])
    nexus = NexusService(catalog)
    assert nexus.create_table(clientes())["tabla"] == "public.clientes"
    assert nexus.table("clientes")["esquema"] == "public"
    assert nexus.procedure("fn_total")["esquema"] == "public"
    assert nexus.execute_procedure("fn_total", {"id_empresa": 3})["procedimiento"] == "public.fn_total"

    other = nexus.generate_ddl(clientes(alta="NULL"), motor="firebird")
    assert other["motor"] == "firebird" and other["tabla"] == "CLIENTES"
    assert len(catalog.applied_scripts) == 1
    with pytest.raises(InvalidInputError, match="no soportado"):
        nexus.generate_ddl(clientes(), motor="db2")


# ============================================================================ catálogos sin servidor


def test_firebird_positional_parameters():
    inputs = [ProcedureParameter("@A", "integer", None, False, False),
              ProcedureParameter("@B", "varchar", 20, False, True),
              ProcedureParameter("@C", "integer", None, False, True)]
    assert FirebirdCatalog.positional_values(inputs, {"@a": 1}) == [1]
    assert FirebirdCatalog.positional_values(inputs, {"@A": 1, "@B": "x", "@C": 2}) == [1, "x", 2]
    with pytest.raises(InvalidInputError, match="Falta el parámetro @B"):
        FirebirdCatalog.positional_values(inputs, {"@A": 1, "@C": 2})
    with pytest.raises(InvalidInputError, match="Falta el parámetro @A"):
        FirebirdCatalog.positional_values(inputs, {})
    assert field_type(16, 2) == "decimal" and field_type(261, 1) == "blob sub_type text" and field_type(37, 0) == "varchar"


class FakeMongoDatabase:
    def __init__(self):
        self.commands, self.existing = [], set()

    def command(self, command):
        from pymongo.errors import OperationFailure

        name = next(iter(command))
        if name == "create" and command["create"] in self.existing:
            raise OperationFailure("Collection already exists", code=48)
        if name == "createIndexes" and command["createIndexes"] == "rota":
            raise OperationFailure("bad index", code=67, details={"errmsg": "Index key pattern invalid"})
        self.commands.append(name)
        if name == "create":
            self.existing.add(command["create"])


def test_mongo_apply_ddl_is_idempotent_and_only_runs_allowed_commands():
    db = FakeMongoDatabase()
    catalog = MongoCatalog(MongoSettings("mongodb://h/app", "app"), database=db)
    ddl = MongoDialect().create_table(clientes())
    catalog.apply_ddl(ddl)
    catalog.apply_ddl(ddl)
    assert db.commands == ["create", "createIndexes", "createIndexes"]
    for script, message in (('[{"dropDatabase": 1}]', "no permitido"), ("DROP TABLE x", "lista JSON"), ("[]", "no vacía")):
        with pytest.raises(InvalidInputError, match=message):
            catalog.apply_ddl(script)
    with pytest.raises(InvalidInputError, match="Index key pattern invalid"):
        catalog.apply_ddl('[{"createIndexes": "rota", "indexes": []}]')


def test_mongo_columns_from_validator():
    columns = columns_from_validator({"$jsonSchema": {"required": ["a"], "properties": {
        "a": {"bsonType": "string", "maxLength": 10}, "b": {"bsonType": ["int", "null"]}}}})
    assert [(c["nombre"], c["tipo"], c["nulable"], c["longitud"]) for c in columns] == [("a", "string", False, 10), ("b", "int", True, None)]
    assert columns_from_validator(None) == []


# ============================================================================ respaldos por archivo


def test_backup_target_and_listing(tmp_path):
    with pytest.raises(InvalidInputError, match="NEXUS_BACKUP_DIR"):
        backup_target(None, "ventas", "manual", ".dump")
    with pytest.raises(InvalidInputError, match="no existe"):
        backup_target(str(tmp_path / "falta"), "ventas", "manual", ".dump")
    path = backup_target(str(tmp_path), "C:/datos/Legado ERP.fdb", "manual", ".fbk")
    assert path.parent == tmp_path and path.name.startswith("Legado_ERP_") and path.name.endswith("_manual.fbk")
    path.write_bytes(b"x" * 10)
    (tmp_path / "otra_20260101_000000_manual.fbk").write_bytes(b"y")
    listed = list_backup_files(str(tmp_path), "C:/datos/Legado ERP.fdb", ".fbk", 10)
    assert [b["archivo"] for b in listed] == [str(path)] and listed[0]["tamano_bytes"] == 10
    assert list_backup_files(None, "x", ".fbk", 10) == []


def test_run_tool_reports_failures():
    assert run_tool([sys.executable, "-c", "print('ok')"], None, 30).strip() == "ok"
    with pytest.raises(InvalidInputError, match="falló: boom"):
        run_tool([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"], None, 30)


def test_postgres_backup_passes_password_by_environment(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, env, timeout):
        calls.append((list(args), env))
        if "--format=custom" in args:
            Path(next(a for a in args if a.startswith("--file="))[7:]).write_bytes(b"PGDMP")
        return ""

    monkeypatch.setattr("src.agents.database_agent.postgres_catalog.run_tool", fake_run)
    monkeypatch.setattr("src.agents.database_agent.postgres_catalog.tool_path", lambda tool: tool)
    catalog = PostgresCatalog(PostgresSettings("db", 5432, "ventas", "app", "s3cr3t", "require"))
    entry = catalog.backup(str(tmp_path), "manual")
    assert entry["verificado"] and entry["tamano_bytes"] == 5
    (dump_args, dump_env), (restore_args, _) = calls
    assert dump_env["PGPASSWORD"] == "s3cr3t" and dump_env["PGSSLMODE"] == "require"
    assert not any("s3cr3t" in a for a in dump_args + restore_args)
    assert restore_args[:2] == ["pg_restore", "--list"]
    assert catalog.list_backups(str(tmp_path), 5)[0]["archivo"] == entry["archivo"]


def test_firebird_backup_uses_isc_environment(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, env, timeout):
        calls.append((list(args), env))
        Path(args[-1]).write_bytes(b"gbak")
        return ""

    monkeypatch.setattr("src.agents.database_agent.firebird_catalog.run_tool", fake_run)
    monkeypatch.setattr("src.agents.database_agent.firebird_catalog.tool_path", lambda tool: tool)
    catalog = FirebirdCatalog(FirebirdSettings("srv", 3050, "C:/datos/erp.fdb", "SYSDBA", "masterkey"))
    entry = catalog.backup(str(tmp_path), "pre_cambio")
    args, env = calls[0]
    assert args[:4] == ["gbak", "-b", "-g", "srv/3050:C:/datos/erp.fdb"]
    assert env == {"ISC_USER": "SYSDBA", "ISC_PASSWORD": "masterkey"} and "masterkey" not in args
    assert entry["verificado"] is False and entry["archivo"].endswith("_pre_cambio.fbk")


# ============================================================================ registro de conexiones


@pytest.fixture
def clean_connections(monkeypatch):
    import os

    for key in [k for k in os.environ if k.upper().startswith("NEXUS_CONEXION_")]:
        monkeypatch.delenv(key)
    dependencies.reset_nexus_connections()
    yield monkeypatch
    dependencies.reset_nexus_connections()


def test_connections_from_environment(clean_connections):
    clean_connections.setenv("NEXUS_CONEXION_VENTAS_PG", "postgresql://app:x@db/ventas")
    clean_connections.setenv("NEXUS_CONEXION_LEGADO", "firebird://SYSDBA:x@srv/erp")
    clean_connections.setenv("NEXUS_CONEXION_ROTA", "oracle://h/db")
    clean_connections.setenv("NEXUS_CONEXION_KINETIX", "postgresql://h/kinetix")
    dependencies.set_nexus_service(NexusService(InMemoryCatalog()))

    assert dependencies.connection_names() == ["kinetix", "legado", "ventas_pg"]
    invalid = dependencies.invalid_connections()
    assert set(invalid) == {"rota", "kinetix"} and "no soportado" in invalid["rota"]
    service = dependencies.get_nexus_service("VENTAS_PG")
    assert service.motor == "postgresql" and dependencies.get_nexus_service("ventas_pg") is service
    assert dependencies.connection_view("legado") == {"nombre": "legado", "motor": "firebird", "host": "srv",
                                                      "base_datos": "erp", "por_defecto": False}
    with pytest.raises(NotFoundError, match="mal configurada"):
        dependencies.get_nexus_service("rota")
    with pytest.raises(NotFoundError, match="no encontrada"):
        dependencies.get_nexus_service("otra")


# ============================================================================ API


@pytest.fixture
def api(clean_connections):
    repo = seeded_repository()
    for perm_id, recurso, accion in (
        ("p_ev", "esquema", "ver"), ("p_em", "esquema", "modificar"),
        ("p_pe", "procedimientos", "ejecutar"), ("p_rs", "respaldos", "gestionar"),
    ):
        repo.add_permission(perm_id, recurso, accion)
        repo.grant_permission("rol_admin", perm_id)
    set_security_service(SecurityService(repo, SecuritySettings(secret_key="nexus-test-secret-" + "x" * 32)))
    docs = InMemoryCatalog("mongodb")
    docs.add_table(None, "pedidos", ["_id", "total"], rows=7)
    dependencies.set_nexus_service(NexusService(InMemoryCatalog(), max_rows=100))
    dependencies.set_nexus_service(NexusService(docs, max_rows=100), "docs")
    sentinel_routes._ip_limiter._hits.clear()
    app = FastAPI()
    app.include_router(sentinel_routes.router)
    app.include_router(nexus_routes.router)
    yield TestClient(app), repo
    set_security_service(None)


def auth_headers(client):
    session = client.post("/api/v1/sentinel/autenticar",
                          json={"nombre_usuario": "ana", "contrasena": PASSWORDS["ana"], "id_empresa": "gio"}).json()
    return {"Authorization": f"Bearer {session['token_acceso']}"}


def test_api_connections_and_engine_selection(api):
    client, repo = api
    auth = auth_headers(client)
    assert client.get("/api/v1/nexus/conexiones").status_code == 401

    listed = client.get("/api/v1/nexus/conexiones", headers=auth).json()
    by_name = {c["nombre"]: c for c in listed["conexiones"]}
    assert by_name["kinetix"]["por_defecto"] and by_name["docs"]["motor"] == "mongodb"
    assert by_name["docs"]["estado"] == "conectada" and by_name["docs"]["capacidades"] == ["respaldos"]

    tables = client.get("/api/v1/nexus/esquema/tablas?conexion=docs", headers=auth).json()
    assert tables["motor"] == "mongodb" and tables["tablas"][0]["filas"] == 7
    assert client.get("/api/v1/nexus/esquema/tablas?conexion=nada", headers=auth).status_code == 404
    assert client.get("/api/v1/nexus/procedimientos?conexion=docs", headers=auth).status_code == 400
    assert client.get("/api/v1/nexus/info?conexion=docs", headers=auth).json()["motor"] == "MongoDB"

    ddl = client.post("/api/v1/nexus/esquema/ddl?motor=postgresql", json=clientes().model_dump(), headers=auth).json()
    assert ddl["motor"] == "postgresql" and "JSONB" in ddl["ddl"]
    assert client.post("/api/v1/nexus/esquema/ddl?motor=db2", json=clientes().model_dump(), headers=auth).status_code == 400

    created = client.post("/api/v1/nexus/esquema/tablas?conexion=docs", json=clientes().model_dump(), headers=auth)
    assert created.status_code == 201 and created.json()["motor"] == "mongodb"
    _, entries = repo.list_audit("gio", None, None, None, None, None, 50, 0)
    entry = next(e for e in entries if e.accion == "nexus_crear_tabla")
    assert entry.recurso == "tabla:docs/clientes" and entry.detalles.startswith("mongodb hash")


def test_api_health_ignores_connection_parameter(api):
    client, _ = api
    assert client.get("/api/v1/nexus/salud?conexion=nada").json()["estado"] == "activo"
