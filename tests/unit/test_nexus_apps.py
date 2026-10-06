"""Nexus: registro de aplicaciones en kinetix, base por empresa o multiempresa, migraciones y despliegue."""

import pytest

from src.agents.database_agent.app_registry import InMemoryAppRegistry
from src.agents.database_agent.app_service import NexusAppService, validate_script
from src.agents.database_agent.dependencies import set_nexus_apps_service
from src.agents.database_agent.provisioner import InMemoryProvisioner, checksum, split_batches
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError
from src.api.routes import nexus_routes
from tests.unit.agent_api import build_api, headers

CLIENTES = {
    "nombre": "clientes",
    "columnas": [
        {"name": "id", "type": "bigint", "nullable": False, "primary_key": True},
        {"name": "nombre", "type": "varchar", "nullable": False},
        {"name": "datos", "type": "json"},
    ],
    "descripcion": "Clientes de la empresa",
}


@pytest.fixture
def provisioner():
    return InMemoryProvisioner(existing=("ajena",))


@pytest.fixture
def nexus(provisioner):
    return NexusAppService(InMemoryAppRegistry(), provisioner)


def test_per_company_model_creates_one_database_per_company(nexus, provisioner):
    app = nexus.register_app("ana", "gio", {"id_aplicacion": "talleres", "nombre": "Talleres", "motor": "sqlserver", "modelo_datos": "por_empresa",
                                            "empresas": [{"id_empresa": "acme", "nombre": "ACME"}]})
    assert [d["nombre_base"] for d in app["bases_datos"]] == ["talleres_acme"]
    assert app["migraciones"] == [] and app["seguridad_por_fila"] is False

    added = nexus.add_company("ana", "gio", "talleres", {"id_empresa": "beta", "nombre": "Beta"})
    assert added == {"id_empresa": "beta", "nombre": "Beta", "nombre_base": "talleres_beta", "base_nueva": True}
    with pytest.raises(ConflictError):
        nexus.add_company("ana", "gio", "talleres", {"id_empresa": "beta", "nombre": "Beta"})

    table = nexus.table("ana", "gio", "talleres", CLIENTES)
    assert "id_empresa" not in table["ddl"] and "SECURITY POLICY" not in table["ddl"]
    assert "PRIMARY KEY CLUSTERED" in table["ddl"] and table["migracion"]["numero"] == 1

    deployed = nexus.deploy("ana", "gio", "talleres")
    assert deployed["bases"] == 2 and deployed["fallidas"] == 0
    assert {d["nombre_base"]: d["migraciones_aplicadas"] for d in deployed["despliegues"]} == {
        "talleres_acme": [1], "talleres_beta": [1]}
    assert all(d["base_creada"] for d in deployed["despliegues"])
    assert set(provisioner.databases) == {"talleres_acme", "talleres_beta"}

    only_acme = nexus.deploy("ana", "gio", "talleres", "acme")
    assert [d["estado"] for d in only_acme["despliegues"]] == ["sin_cambios"]
    detail = nexus.get_app("gio", "talleres")
    assert all(d["estado"] == "desplegada" and d["version"] == 1 and d["migraciones_pendientes"] == 0
               for d in detail["bases_datos"])


def test_multi_company_model_shares_one_database_with_rls(nexus, provisioner):
    app = nexus.register_app("ana", "gio", {"id_aplicacion": "citas", "nombre": "Citas", "motor": "sqlserver", "modelo_datos": "multiempresa",
                                            "id_solicitud": "req-1234abcd",
                                            "empresas": [{"id_empresa": "acme", "nombre": "ACME"}]})
    assert [d["nombre_base"] for d in app["bases_datos"]] == ["citas"]
    assert app["migraciones"][0]["nombre"] == "base_multiempresa" and app["seguridad_por_fila"] is True
    assert app["empresas"][0]["nombre_base"] == "citas"
    assert nexus.add_company("ana", "gio", "citas", {"id_empresa": "beta", "nombre": "Beta"})["base_nueva"] is False

    ddl = nexus.table("ana", "gio", "citas", CLIENTES)["ddl"]
    assert "[id_empresa] NVARCHAR(255) NOT NULL" in ddl
    assert "FK_clientes_empresas" in ddl and "idx_clientes_id_empresa" in ddl
    assert "CREATE SECURITY POLICY seguridad.[politica_clientes]" in ddl
    with pytest.raises(InvalidInputError):
        nexus.table("ana", "gio", "citas", {**CLIENTES, "nombre": "otra",
                                             "columnas": [*CLIENTES["columnas"], {"name": "id_empresa", "type": "varchar"}]})
    with pytest.raises(InvalidInputError):
        nexus.deploy("ana", "gio", "citas", "acme")

    deployed = nexus.deploy("ana", "gio", "citas")
    assert deployed["despliegues"][0]["migraciones_aplicadas"] == [1, 2]
    assert provisioner.companies["citas"] == {"acme", "beta"}


def test_registration_rejects_invalid_or_taken_names(nexus):
    base = {"nombre": "X", "motor": "sqlserver", "modelo_datos": "multiempresa"}
    for bad in ("Mayus", "1app", "a", "con-guion"):
        with pytest.raises(InvalidInputError):
            nexus.register_app("ana", "gio", {**base, "id_aplicacion": bad})
    with pytest.raises(InvalidInputError):
        nexus.register_app("ana", "gio", {**base, "id_aplicacion": "kinetix"})
    with pytest.raises(InvalidInputError):
        nexus.register_app("ana", "gio", {**base, "id_aplicacion": "ok", "modelo_datos": "hibrido"})
    with pytest.raises(InvalidInputError, match="motor es obligatorio"):
        nexus.register_app("ana", "gio", {**base, "id_aplicacion": "ok", "motor": None})
    with pytest.raises(InvalidInputError, match="ninguna conexión postgresql"):
        nexus.register_app("ana", "gio", {**base, "id_aplicacion": "ok", "motor": "postgresql"})
    with pytest.raises(ConflictError):
        nexus.register_app("ana", "gio", {**base, "id_aplicacion": "ajena"})

    nexus.register_app("ana", "gio", {**base, "id_aplicacion": "unica"})
    with pytest.raises(ConflictError):
        nexus.register_app("ana", "gio", {**base, "id_aplicacion": "unica"})
    with pytest.raises(ConflictError):
        nexus.register_app("otro", "otra_empresa", {**base, "id_aplicacion": "unica"})
    with pytest.raises(NotFoundError):
        nexus.get_app("otra_empresa", "unica")


def test_per_company_database_that_already_exists_is_not_adopted():
    registry = InMemoryAppRegistry()
    nexus = NexusAppService(registry, InMemoryProvisioner(existing=("aje_na",)))
    with pytest.raises(ConflictError):
        nexus.register_app("ana", "gio", {"id_aplicacion": "aje", "nombre": "A", "motor": "sqlserver", "modelo_datos": "por_empresa",
                                          "empresas": [{"id_empresa": "na", "nombre": "N"}]})
    assert registry.list_apps("gio") == []

    nexus.register_app("ana", "gio", {"id_aplicacion": "aje", "nombre": "A", "motor": "sqlserver", "modelo_datos": "por_empresa"})
    with pytest.raises(ConflictError):
        nexus.add_company("ana", "gio", "aje", {"id_empresa": "na", "nombre": "N"})
    with pytest.raises(InvalidInputError):
        nexus.deploy("ana", "gio", "aje")


@pytest.mark.parametrize("script", [
    "USE master; CREATE TABLE x (id INT)",
    "CREATE DATABASE otra",
    "EXEC xp_cmdshell 'dir'",
    "EXEC('DROP TABLE x')",
    "DROP TABLE dbo.clientes",
    "TRUNCATE TABLE dbo.clientes",
    "DELETE FROM despliegue.migraciones",
    "ALTER SECURITY POLICY seguridad.politica_x WITH (STATE = OFF)",
    "BACKUP DATABASE x TO DISK = 'c:/x.bak'",
    "SELECT * FROM OPENROWSET('SQLNCLI', 'x', 'SELECT 1')",
])
def test_raw_migrations_reject_dangerous_sql(script):
    with pytest.raises(InvalidInputError):
        validate_script(script)


def test_raw_migrations_are_numbered_immutable_and_comments_are_ignored(nexus):
    nexus.register_app("ana", "gio", {"id_aplicacion": "crm", "nombre": "CRM", "motor": "sqlserver", "modelo_datos": "multiempresa"})
    script = "-- USE no aplica en comentarios\nALTER TABLE dbo.empresas ADD nit NVARCHAR(20) NULL;\nGO\nSELECT 1;"
    created = nexus.add_migration("ana", "gio", "crm", {"nombre": "agregar_nit", "script": script})["migracion"]
    assert created["numero"] == 2 and created["checksum"] == checksum(script)
    with pytest.raises(ConflictError):
        nexus.add_migration("ana", "gio", "crm", {"nombre": "agregar_nit", "script": "SELECT 2"})
    assert nexus.migration("gio", "crm", 2)["script"] == script
    assert split_batches(script) == ["-- USE no aplica en comentarios\nALTER TABLE dbo.empresas ADD nit NVARCHAR(20) NULL;",
                                     "SELECT 1;"]


def test_failed_migration_marks_database_and_is_logged():
    provisioner = InMemoryProvisioner(fail_marker="FALLA")
    nexus = NexusAppService(InMemoryAppRegistry(), provisioner)
    nexus.register_app("ana", "gio", {"id_aplicacion": "inv", "nombre": "Inv", "motor": "sqlserver", "modelo_datos": "multiempresa"})
    nexus.add_migration("ana", "gio", "inv", {"nombre": "rota", "script": "SELECT 'FALLA'"})
    result = nexus.deploy("ana", "gio", "inv")
    assert result["fallidas"] == 1
    failed = result["despliegues"][0]
    assert failed["estado"] == "fallido" and failed["migraciones_aplicadas"] == [1] and "rota" in failed["detalle"]
    db = nexus.get_app("gio", "inv")["bases_datos"][0]
    assert db["estado"] == "error" and db["version"] == 1 and db["migraciones_pendientes"] == 1
    assert nexus.deployments("gio", "inv", 10)["total"] == 1


# ============================================================================ API


@pytest.fixture
def api():
    client, repo, _ = build_api([nexus_routes.router], [("aplicaciones", "ver"), ("aplicaciones", "gestionar"),
                                                        ("aplicaciones", "desplegar")])
    set_nexus_apps_service(NexusAppService(InMemoryAppRegistry(), InMemoryProvisioner()))
    yield client, repo
    set_nexus_apps_service(None)
    set_security_service(None)


def test_api_registers_deploys_and_audits(api):
    client, repo = api
    url = "/api/v1/nexus/aplicaciones"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers(client, "luis")).status_code == 403

    auth = headers(client)
    created = client.post(url, json={"id_aplicacion": "vitalis", "nombre": "Vitalis", "motor": "sqlserver", "modelo_datos": "por_empresa",
                                     "empresas": [{"id_empresa": "clinica_a", "nombre": "Clínica A"}]}, headers=auth)
    assert created.status_code == 201
    assert created.json()["aplicacion"]["bases_datos"][0]["nombre_base"] == "vitalis_clinica_a"

    preview = client.post(f"{url}/vitalis/tablas?vista_previa=true", json=CLIENTES, headers=auth).json()
    assert preview["registrada"] is False and "CREATE TABLE" in preview["ddl"]
    assert client.post(f"{url}/vitalis/tablas", json=CLIENTES, headers=auth).status_code == 201
    assert client.post(f"{url}/vitalis/migraciones", json={"nombre": "x", "script": "DROP TABLE dbo.clientes"},
                       headers=auth).status_code == 400

    deployed = client.post(f"{url}/vitalis/desplegar", json={}, headers=auth)
    assert deployed.status_code == 200 and deployed.json()["fallidas"] == 0
    assert client.get(f"{url}/vitalis/despliegues", headers=auth).json()["total"] == 1
    assert client.get(f"{url}/otra", headers=auth).status_code == 404
    assert client.get(url, headers=auth).json()["aplicaciones"][0]["bases_desactualizadas"] == 0

    _, entries = repo.list_audit("gio", None, None, None, None, None, 50, 0)
    assert {"nexus_registrar_aplicacion", "nexus_definir_tabla", "nexus_desplegar_aplicacion"} <= {e.accion for e in entries}
