"""Nexus: motor por aplicación, migraciones portables, equivalentes y cambio de motor con copia de datos."""

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from bson import ObjectId
from bson.decimal128 import Decimal128

from src.agents.database_agent.app_registry import InMemoryAppRegistry
from src.agents.database_agent.app_service import NexusAppService
from src.agents.database_agent.app_templates import base_definition, render, table_definition, validate_script
from src.agents.database_agent.database_agent import ColumnType, TableDefinition
from src.agents.database_agent.datastores import InMemoryDataStore, copy_table, to_target
from src.agents.database_agent.dependencies import set_nexus_apps_service
from src.agents.database_agent.engine_provisioners import firebird_database_settings
from src.agents.database_agent.engines import FirebirdSettings
from src.agents.database_agent.provisioner import InMemoryProvisioner, ProvisionError
from src.agents.database_agent.servers import Server, ServerCatalog
from src.agents.orchestrator_agent import OrchestratorAgent
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError
from src.api.routes import nexus_routes
from tests.unit.agent_api import build_api, headers

PEDIDOS = {
    "nombre": "pedidos",
    "columnas": [
        {"name": "id", "type": "varchar", "nullable": False, "primary_key": True},
        {"name": "total", "type": "decimal", "nullable": False},
        {"name": "detalle", "type": "json"},
    ],
    "columnas_auditoria": False,
    "descripcion": "Pedidos",
}


def _server(nombre, motor, existing=()):
    return Server(nombre, motor, InMemoryProvisioner(existing=existing), InMemoryDataStore(motor, create_on_write=True))


@pytest.fixture
def servers():
    return {"kinetix": _server("kinetix", "sqlserver"), "docs": _server("docs", "mongodb"),
            "pg": _server("pg", "postgresql"), "fb": _server("fb", "firebird")}


@pytest.fixture
def nexus(servers):
    return NexusAppService(InMemoryAppRegistry(), ServerCatalog(servers.values()), copy_batch=2)


def _table(nexus, app="tienda"):
    nexus.table("ana", "gio", app, PEDIDOS)
    return TableDefinition.model_validate({"name": "pedidos", "columns": PEDIDOS["columnas"], "company_column": False,
                                           "warehouse_column": False, "audit_columns": False})


def _mongo_app(nexus, servers, rows=3):
    nexus.register_app("ana", "gio", {"id_aplicacion": "tienda", "nombre": "Tienda", "modelo_datos": "por_empresa",
                                      "motor": "mongodb", "empresas": [{"id_empresa": "acme", "nombre": "ACME"}]})
    table = _table(nexus)
    nexus.deploy("ana", "gio", "tienda")
    servers["docs"].datos.create("tienda_acme", table, [
        {"id": str(i), "total": Decimal128(f"{i}.50"), "detalle": {"items": i}, "_id": ObjectId()} for i in range(rows)])
    return table


# ============================================================================ plantillas por motor


def _clientes(multi=True, rls=True):
    table = TableDefinition(name="clientes", company_column=False, warehouse_column=False, columns=[
        {"name": "id_empresa", "type": "varchar", "nullable": False},
        {"name": "id", "type": "bigint", "nullable": False, "primary_key": True},
        {"name": "nombre", "type": "varchar", "nullable": False}])
    return table_definition(table, multi, rls)


def test_multi_company_table_renders_tenant_controls_per_engine():
    sqlserver = render(_clientes(), "sqlserver")
    assert "FK_clientes_empresas" in sqlserver and "CREATE SECURITY POLICY seguridad.[politica_clientes]" in sqlserver
    postgres = render(_clientes(), "postgresql")
    assert 'ENABLE ROW LEVEL SECURITY' in postgres and "current_setting('app.id_empresa', true)" in postgres
    assert '"fk_clientes_empresas"' in postgres and "DO $nexus$" in postgres
    firebird = render(_clientes(), "firebird")
    assert '"FK_CLIENTES_EMPRESAS"' in firebird and "ROW LEVEL" not in firebird and "POLICY" not in firebird
    mongo = json.loads(render(_clientes(), "mongodb"))
    assert mongo[-1] == {"createIndexes": "clientes", "indexes": [{"key": {"id_empresa": 1}, "name": "idx_clientes_id_empresa"}]}
    assert "POLICY" not in render(_clientes(rls=False), "postgresql")


def test_base_multiempresa_exists_for_every_engine():
    assert "seguridad.fn_filtro_empresa" in render(base_definition(True), "sqlserver")
    assert '"public"."empresas"' in render(base_definition(True), "postgresql")
    assert 'CREATE TABLE "EMPRESAS"' in render(base_definition(True), "firebird")
    assert json.loads(render(base_definition(True), "mongodb"))[0]["create"] == "empresas"


@pytest.mark.parametrize("motor, script", [
    ("postgresql", "COPY pedidos TO PROGRAM 'rm -rf /'"),
    ("postgresql", "SELECT pg_read_file('/etc/passwd')"),
    ("postgresql", "ALTER TABLE pedidos DISABLE ROW LEVEL SECURITY"),
    ("postgresql", "DROP POLICY politica_pedidos ON pedidos"),
    ("postgresql", "CREATE EXTENSION dblink"),
    ("firebird", "CREATE TABLE ext EXTERNAL FILE 'c:/x.txt' (id INTEGER)"),
    ("firebird", "DECLARE EXTERNAL FUNCTION f ENTRY_POINT 'x' MODULE_NAME 'y'"),
    ("mongodb", '[{"drop": "pedidos"}]'),
    ("mongodb", '[{"create": "_nexus_migraciones"}]'),
    ("mongodb", '[{"create": "system.js"}]'),
])
def test_manual_scripts_are_validated_per_engine(motor, script):
    with pytest.raises(InvalidInputError):
        validate_script(script, motor)


def test_valid_manual_scripts_pass_per_engine():
    assert validate_script("ALTER TABLE pedidos ADD COLUMN nota TEXT;", "postgresql")
    assert validate_script('[{"collMod": "pedidos", "validationLevel": "moderate"}]', "mongodb")


# ============================================================================ registro con motor


def test_app_chooses_engine_and_default_connection(nexus, servers):
    app = nexus.register_app("ana", "gio", {"id_aplicacion": "crm", "nombre": "CRM", "modelo_datos": "multiempresa",
                                            "motor": "postgresql"})
    assert (app["motor"], app["conexion"], app["seguridad_por_fila"]) == ("postgresql", "pg", True)
    assert app["migraciones"][0]["portable"] is True
    nexus.deploy("ana", "gio", "crm")
    assert '"public"."empresas"' in servers["pg"].provisioner.scripts["crm"][0]

    mongo = nexus.register_app("ana", "gio", {"id_aplicacion": "logs", "nombre": "Logs", "modelo_datos": "multiempresa",
                                              "motor": "mongodb"})
    assert mongo["seguridad_por_fila"] is False and len(mongo["advertencias"]) == 2
    with pytest.raises(InvalidInputError, match="es mongodb"):
        nexus.register_app("ana", "gio", {"id_aplicacion": "x1", "nombre": "X", "modelo_datos": "por_empresa",
                                          "motor": "sqlserver", "conexion": "docs"})
    with pytest.raises(NotFoundError):
        nexus.register_app("ana", "gio", {"id_aplicacion": "x2", "nombre": "X", "modelo_datos": "por_empresa",
                                          "motor": "sqlserver", "conexion": "nada"})


def test_table_reports_engines_it_can_move_to(nexus):
    nexus.register_app("ana", "gio", {"id_aplicacion": "crm", "nombre": "CRM", "modelo_datos": "por_empresa",
                                      "motor": "sqlserver"})
    result = nexus.table("ana", "gio", "crm", {**PEDIDOS, "columnas": [
        *PEDIDOS["columnas"], {"name": "alta", "type": "datetime", "default": "GETUTCDATE()"}]})
    assert result["motores_compatibles"] == ["sqlserver", "postgresql", "mongodb"]
    assert "CURRENT_TIMESTAMP" in result["motores_incompatibles"]["firebird"]
    nexus.register_app("ana", "gio", {"id_aplicacion": "fbapp", "nombre": "F", "modelo_datos": "por_empresa",
                                      "motor": "firebird"})
    with pytest.raises(InvalidInputError, match="CURRENT_TIMESTAMP"):
        nexus.table("ana", "gio", "fbapp", {**PEDIDOS, "columnas": [
            *PEDIDOS["columnas"], {"name": "alta", "type": "datetime", "default": "GETUTCDATE()"}]})


# ============================================================================ copia de datos


def test_values_are_normalized_for_the_target_engine():
    assert to_target(ObjectId("64b7f0c2a1b2c3d4e5f60718"), ColumnType.VARCHAR, "sqlserver") == "64b7f0c2a1b2c3d4e5f60718"
    assert to_target(Decimal128("10.25"), ColumnType.DECIMAL, "postgresql") == Decimal("10.25")
    assert to_target(Decimal("1.5"), ColumnType.DECIMAL, "mongodb") == Decimal128("1.5")
    assert to_target({"a": 1}, ColumnType.JSON, "sqlserver") == '{"a": 1}'
    assert to_target('{"a": 1}', ColumnType.JSON, "mongodb") == {"a": 1}
    aware = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
    assert to_target(aware, ColumnType.DATETIME, "firebird") == datetime(2026, 10, 5, 12, 0)
    assert to_target(1, ColumnType.BOOLEAN, "mongodb") is True


def test_copy_table_only_fills_empty_targets():
    table = TableDefinition(name="t", company_column=False, warehouse_column=False, audit_columns=False,
                            columns=[{"name": "id", "type": "int", "nullable": False, "primary_key": True}])
    source, target = InMemoryDataStore("mongodb"), InMemoryDataStore("sqlserver")
    assert copy_table(source, target, "db", table)["estado"] == "sin_origen"
    source.create("db", table, [{"id": 1}, {"id": 2}, {"id": 3}])
    assert "despliega el esquema" in copy_table(source, target, "db", table)["detalle"]
    target.create("db", table, [{"id": 1}])
    partial = copy_table(source, target, "db", table)
    assert partial["estado"] == "incompleta" and "1 de 3" in partial["detalle"]
    target.create("db", table)
    assert copy_table(source, target, "db", table, batch_size=2) == {
        "tabla": "dbo.t", "nombre_base": "db", "filas": 3, "estado": "copiada"}
    assert copy_table(source, target, "db", table)["estado"] == "ya_copiada"
    failing = InMemoryDataStore("postgresql", create_on_write=True, fail_tables=["t"])
    assert "error simulado" in copy_table(source, failing, "db", table)["detalle"]


def test_firebird_app_databases_live_next_to_the_connection_database():
    settings = FirebirdSettings("fb", 3050, "/data/kinetix.fdb", "SYSDBA", "x")
    assert firebird_database_settings(settings, "tienda_acme").database == "/data/tienda_acme.fdb"
    with pytest.raises(ProvisionError):
        firebird_database_settings(FirebirdSettings("fb", 3050, "alias", "SYSDBA", "x"), "tienda")


# ============================================================================ cambio de motor


def test_mongo_app_moves_to_sqlserver_with_its_data_and_completes(nexus, servers):
    _mongo_app(nexus, servers)
    plan = nexus.change_engine("ana", "gio", "tienda", {"motor": "sqlserver"}, preview=True)
    assert plan["viable"] and plan["destino"] == {"motor": "sqlserver", "conexion": "kinetix"}
    assert plan["tablas_a_copiar"] == ["dbo.pedidos"]

    result = nexus.change_engine("ana", "gio", "tienda", {"motor": "sqlserver"})
    assert result["cambio"]["estado"] == "datos_copiados" and result["copia"][0]["filas"] == 3
    copied = servers["kinetix"].datos.tables[("tienda_acme", "pedidos")]
    assert copied[0] == {"id": "0", "total": Decimal("0.50"), "detalle": '{"items": 0}'}
    assert "CREATE TABLE [dbo].[pedidos]" in servers["kinetix"].provisioner.scripts["tienda_acme"][0]
    app = nexus.get_app("gio", "tienda")
    assert (app["motor"], app["conexion"]) == ("sqlserver", "kinetix")
    assert app["bases_datos"][0]["version"] == 1 and app["cambio_motor_activo"]["estado"] == "datos_copiados"

    with pytest.raises(ConflictError, match="cambio de motor en curso"):
        nexus.table("ana", "gio", "tienda", {**PEDIDOS, "nombre": "otra"})
    assert nexus.copy_engine_data("ana", "gio", "tienda")["copia"][0]["estado"] == "ya_copiada"
    done = nexus.complete_engine_change("ana", "gio", "tienda")
    assert done["cambio"]["estado"] == "completado" and "sin borrar" in done["nota"]
    assert len(servers["docs"].datos.tables[("tienda_acme", "pedidos")]) == 3
    with pytest.raises(NotFoundError):
        nexus.revert_engine_change("ana", "gio", "tienda")
    assert nexus.engine_changes("gio", "tienda", 10)["total"] == 1
    assert nexus.table("ana", "gio", "tienda", {**PEDIDOS, "nombre": "otra"})["registrada"]


def test_revert_restores_the_original_engine_and_databases(nexus, servers):
    _mongo_app(nexus, servers)
    nexus.change_engine("ana", "gio", "tienda", {"motor": "postgresql"})
    assert len(servers["pg"].datos.tables[("tienda_acme", "pedidos")]) == 3
    reverted = nexus.revert_engine_change("ana", "gio", "tienda")
    assert reverted["cambio"]["estado"] == "revertido" and "quedan sin borrar" in reverted["nota"]
    app = nexus.get_app("gio", "tienda")
    assert (app["motor"], app["conexion"], app["cambio_motor_activo"]) == ("mongodb", "docs", None)
    assert app["bases_datos"][0]["estado"] == "desplegada" and app["bases_datos"][0]["version"] == 1

    again = nexus.change_engine("ana", "gio", "tienda", {"motor": "postgresql"}, preview=True)
    assert again["viable"] and any("cambio revertido" in w for w in again["advertencias"])


def test_schema_failure_keeps_change_open_until_reverted(nexus, servers):
    _mongo_app(nexus, servers)
    servers["pg"].provisioner._fail_marker = "pedidos"
    result = nexus.change_engine("ana", "gio", "tienda", {"motor": "postgresql"})
    assert result["cambio"]["estado"] == "esquema_con_errores" and result["copia"] == []
    with pytest.raises(InvalidInputError):
        nexus.complete_engine_change("ana", "gio", "tienda")
    servers["pg"].provisioner._fail_marker = None
    assert nexus.copy_engine_data("ana", "gio", "tienda")["cambio"]["estado"] == "datos_copiados"


def test_manual_sql_needs_an_equivalent_before_changing_engine(nexus, servers):
    _mongo_app(nexus, servers)
    nexus.add_migration("ana", "gio", "tienda", {"nombre": "validador", "script": json.dumps(
        [{"collMod": "pedidos", "validationLevel": "moderate"}])})
    nexus.deploy("ana", "gio", "tienda")
    plan = nexus.change_engine("ana", "gio", "tienda", {"motor": "sqlserver"}, preview=True)
    assert not plan["viable"] and "registra su equivalente para sqlserver" in plan["bloqueos"][0]
    with pytest.raises(ConflictError):
        nexus.change_engine("ana", "gio", "tienda", {"motor": "sqlserver"})

    with pytest.raises(InvalidInputError, match="portable"):
        nexus.add_equivalent("ana", "gio", "tienda", 1, {"motor": "sqlserver", "script": "SELECT 1"})
    with pytest.raises(InvalidInputError, match="ya está escrita"):
        nexus.add_equivalent("ana", "gio", "tienda", 2, {"motor": "mongodb", "script": "[]"})
    with pytest.raises(InvalidInputError):
        nexus.add_equivalent("ana", "gio", "tienda", 2, {"motor": "sqlserver", "script": "DROP TABLE dbo.pedidos"})
    added = nexus.add_equivalent("ana", "gio", "tienda", 2, {"motor": "sqlserver", "script": "SELECT 1;"})["migracion"]
    assert added["equivalentes"] == ["sqlserver"] and added["scripts_equivalentes"]["sqlserver"] == "SELECT 1;"
    with pytest.raises(ConflictError, match="inmutables"):
        nexus.add_equivalent("ana", "gio", "tienda", 2, {"motor": "sqlserver", "script": "SELECT 2;"})

    assert nexus.get_app("gio", "tienda")["migraciones"][1]["equivalentes"] == ["sqlserver"]

    result = nexus.change_engine("ana", "gio", "tienda", {"motor": "sqlserver"})
    assert result["cambio"]["estado"] == "datos_copiados"
    assert servers["kinetix"].provisioner.scripts["tienda_acme"][-1] == "SELECT 1;"


def test_plan_blocks_stale_databases_and_foreign_targets(servers):
    servers["pg"] = _server("pg", "postgresql", existing=("tienda_acme",))
    nexus = NexusAppService(InMemoryAppRegistry(), ServerCatalog(servers.values()))
    _mongo_app(nexus, servers)
    nexus.table("ana", "gio", "tienda", {**PEDIDOS, "nombre": "facturas"})
    plan = nexus.change_engine("ana", "gio", "tienda", {"motor": "postgresql"}, preview=True)
    assert any("no está al día" in b for b in plan["bloqueos"])
    assert any("ya existe en pg" in b for b in plan["bloqueos"])
    assert "ya está en mongodb" in nexus.engine_change_plan("gio", "tienda", {"motor": "mongodb"})["bloqueos"][0]


# ============================================================================ API


@pytest.fixture
def api(servers):
    client, repo, _ = build_api([nexus_routes.router], [("aplicaciones", "ver"), ("aplicaciones", "gestionar"),
                                                        ("aplicaciones", "desplegar")])
    set_nexus_apps_service(NexusAppService(InMemoryAppRegistry(), ServerCatalog(servers.values())))
    yield client, repo
    set_nexus_apps_service(None)
    set_security_service(None)


def test_api_engine_change_flow(api, servers):
    client, repo = api
    url, auth = "/api/v1/nexus/aplicaciones", headers(client)
    listed = client.get(f"{url}/servidores", headers=auth).json()
    assert {"nombre": "docs", "motor": "mongodb"} in listed["servidores"] and "firebird" in listed["motores_soportados"]
    body = {"id_aplicacion": "tienda", "nombre": "Tienda", "modelo_datos": "por_empresa",
            "empresas": [{"id_empresa": "acme", "nombre": "ACME"}]}
    assert client.post(url, json=body, headers=auth).status_code == 422
    created = client.post(url, json={**body, "motor": "mongodb"}, headers=auth)
    assert created.status_code == 201 and created.json()["aplicacion"]["conexion"] == "docs"
    table = client.post(f"{url}/tienda/tablas", json=PEDIDOS, headers=auth).json()
    assert table["lenguaje_ddl"] == "json" and table["motor"] == "mongodb"
    client.post(f"{url}/tienda/desplegar", json={}, headers=auth)

    preview = client.post(f"{url}/tienda/cambio-motor?vista_previa=true", json={"motor": "sqlserver"}, headers=auth).json()
    assert preview["vista_previa"] and preview["viable"]
    changed = client.post(f"{url}/tienda/cambio-motor", json={"motor": "sqlserver"}, headers=auth)
    assert changed.status_code == 200 and changed.json()["cambio"]["estado"] == "datos_copiados"
    assert client.post(f"{url}/tienda/cambio-motor", json={"motor": "postgresql"}, headers=auth).status_code == 409
    reverted = client.post(f"{url}/tienda/cambio-motor/revertir", headers=auth)
    assert reverted.status_code == 200 and reverted.json()["cambio"]["estado"] == "revertido"
    assert client.post(f"{url}/tienda/cambio-motor/completar", headers=auth).status_code == 404
    assert client.get(f"{url}/tienda/cambio-motor", headers=auth).json()["total"] == 1

    _, entries = repo.list_audit("gio", None, None, None, None, None, 50, 0)
    assert {"nexus_cambiar_motor", "nexus_revertir_cambio_motor"} <= {e.accion for e in entries}


# ============================================================================ Cortex


def _answer_all(cortex, request, value="no aplica"):
    while request.pending_questions:
        request = cortex.answer(request.id, {q.id: value for q in request.pending_questions})
    return request


@pytest.mark.parametrize("answer, engine", [
    ("PostgreSQL", "postgresql"), ("MongoDB, es documental", "mongodb"), ("Firebird", "firebird"),
    ("SQL Server", "sqlserver"), ("no aplica", "sqlserver"), ("recomienda tú", "sqlserver"),
])
def test_cortex_asks_engine_for_new_apps(answer, engine):
    cortex = OrchestratorAgent()
    request = cortex.submit("Crear una aplicación nueva de citas con pantallas web")
    assert "motor_base_datos" in [q.id for q in request.pending_questions]
    request = _answer_all(cortex, cortex.answer(request.id, {"motor_base_datos": answer}))
    assert request.db_engine == engine and request.to_dict()["motor_base_datos"] == engine
    nexus = next(t for t in request.plan if t.agent.codename == "Nexus")
    assert {"sqlserver": "SQL Server", "postgresql": "PostgreSQL", "firebird": "Firebird",
            "mongodb": "MongoDB"}[engine] in nexus.accion and "portable" in nexus.accion


def test_cortex_recommends_mongo_for_flexible_documents_and_reasks_unclear():
    cortex = OrchestratorAgent()
    request = cortex.submit("Crear una aplicación nueva para guardar documentos de sensores IoT con pantallas web")
    request = cortex.answer(request.id, {"motor_base_datos": "lo que sea"})
    assert "motor_base_datos" in [q.id for q in request.pending_questions]
    request = _answer_all(cortex, request)
    assert request.db_engine == "mongodb" and request.db_engine_reason.startswith("Recomendado por Cortex")


def test_cortex_scale_request_can_plan_an_engine_change():
    cortex = OrchestratorAgent()
    request = cortex.submit("Necesitamos escalar el módulo de citas, está lento", app_id="sicita")
    assert "cambio_motor" in [q.id for q in request.pending_questions]
    request = _answer_all(cortex, cortex.answer(request.id, {"cambio_motor": "Sí, pasar de Mongo a SQL Server"}))
    assert request.engine_change == "sqlserver" and request.to_dict()["cambio_motor"] == "sqlserver"
    nexus = next(t for t in request.plan if t.agent.codename == "Nexus")
    assert nexus.accion.startswith("Cambiar el motor de la aplicación a SQL Server")

    unchanged = _answer_all(cortex, cortex.submit("Necesitamos escalar el módulo de citas, está lento", app_id="sicita"))
    assert unchanged.engine_change is None
    assert next(t for t in unchanged.plan if t.agent.codename == "Nexus").accion.startswith("Analizar consultas lentas")
