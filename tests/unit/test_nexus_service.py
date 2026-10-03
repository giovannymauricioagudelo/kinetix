"""Unit tests for Nexus (DatabaseAgent) on SQL Server: T-SQL DDL, NexusService and API routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agents.database_agent.catalog import InMemoryCatalog, ProcedureParameter, json_value
from src.agents.database_agent.database_agent import ColumnDefinition, ColumnType, SchemaManager, TableDefinition
from src.agents.database_agent.dependencies import set_nexus_service
from src.agents.database_agent.service import NexusService, split_name
from src.agents.security_agent import SecurityService
from src.agents.security_agent.config import SecuritySettings
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError
from src.api.routes import nexus_routes, sentinel_routes
from tests.unit.test_sentinel_agent import PASSWORDS, seeded_repository


def table(name="clientes", **column_overrides):
    columns = [
        ColumnDefinition(name="cliente_id", type=ColumnType.BIGINT, primary_key=True),
        ColumnDefinition(name="empresa_id", type=ColumnType.INT, nullable=False),
        ColumnDefinition(name="bodega_id", type=ColumnType.INT, nullable=False),
        ColumnDefinition(name="nombre", type=ColumnType.VARCHAR, nullable=False, default="O'Brien"),
        ColumnDefinition(name="activo", type=ColumnType.BOOLEAN, default="true"),
        ColumnDefinition(name="datos", type=ColumnType.JSON),
    ]
    return TableDefinition(name=name, columns=columns, description="Clientes | multisector", **column_overrides)


def catalog():
    cat = InMemoryCatalog()
    cat.add_table("dbo", "reglas_negocio", ["id_regla", "nombre"], rows=11)
    cat.add_procedure("dbo", "sp_listar_reglas_por_alcance", [
        ProcedureParameter("@nivel_alcance", "varchar", 20, False, False),
        ProcedureParameter("@id_empresa", "int", 4, False, False),
    ], "CREATE PROCEDURE sp_listar_reglas_por_alcance ...")
    cat.add_procedure("dbo", "sp_con_salida", [ProcedureParameter("@total", "int", 4, True, False)])
    return cat


# ============================================================================ DDL T-SQL


def test_ddl_is_idempotent_sql_server():
    ddl = SchemaManager().create_table(table())
    assert "IF OBJECT_ID(N'dbo.clientes', N'U') IS NULL" in ddl
    assert "CREATE TABLE [dbo].[clientes]" in ddl
    assert "[cliente_id] BIGINT NOT NULL CONSTRAINT [PK_clientes] PRIMARY KEY CLUSTERED" in ddl
    assert "DEFAULT N'O''Brien'" in ddl
    assert "[activo] BIT NULL CONSTRAINT [DF_clientes_activo] DEFAULT 1" in ddl
    assert "CHECK (ISJSON([datos]) = 1)" in ddl
    assert "CREATE INDEX [idx_clientes_empresa_id]" in ddl
    assert "sp_addextendedproperty" in ddl
    assert "IF NOT EXISTS" in ddl and "CREATE TABLE IF NOT EXISTS" not in ddl


@pytest.mark.parametrize("definition, message", [
    (TableDefinition(name="x; DROP TABLE usuarios", columns=table().columns), "Invalid identifier"),
    (TableDefinition(name="t", columns=[*table().columns, ColumnDefinition(name="a-b", type=ColumnType.INT)]), "Invalid identifier"),
    (TableDefinition(name="t", columns=[*table().columns, ColumnDefinition(name="n", type=ColumnType.INT, default="0; DROP TABLE x")]), "numérico"),
    (TableDefinition(name="t", columns=[*table().columns, ColumnDefinition(name="j", type=ColumnType.TEXT, unique=True)]), "UNIQUE"),
    (TableDefinition(name="t", columns=[*table().columns, ColumnDefinition(name="created_at", type=ColumnType.DATETIME)]), "reserved"),
])
def test_schema_validation_rejects_unsafe_definitions(definition, message):
    valid, error = SchemaManager().validate_schema(definition)
    assert not valid and message in error


# ============================================================================ servicio


@pytest.fixture
def nexus():
    return NexusService(catalog(), backup_dir="D:\\respaldos", max_rows=100)


def test_split_name():
    assert split_name("sp_x") == ("dbo", "sp_x")
    assert split_name("ventas.sp_x") == ("ventas", "sp_x")
    for bad in ("a.b.c", "sp x", "dbo.[sp]", "sp;--"):
        with pytest.raises(InvalidInputError):
            split_name(bad)


def test_schema_queries(nexus):
    assert nexus.tables()["tablas"][0]["filas"] == 11
    assert nexus.table("reglas_negocio")["tabla"] == "reglas_negocio"
    with pytest.raises(NotFoundError):
        nexus.table("dbo.no_existe")
    assert nexus.procedure("sp_listar_reglas_por_alcance")["parametros"][0]["nombre"] == "@nivel_alcance"


def test_execute_procedure_only_passes_declared_parameters(nexus):
    result = nexus.execute_procedure("sp_listar_reglas_por_alcance", {"NIVEL_ALCANCE": "global", "@id_empresa": 1}, max_filas=5000)
    assert result["parametros"] == ["@nivel_alcance", "@id_empresa"]
    assert result["max_filas"] == 100
    assert result["conjuntos_resultado"][0]["filas"] == [["global", 1]]

    with pytest.raises(InvalidInputError, match="no tiene el parámetro"):
        nexus.execute_procedure("sp_listar_reglas_por_alcance", {"nivel_alcance; DROP TABLE x --": "global"})
    with pytest.raises(InvalidInputError, match="texto, número"):
        nexus.execute_procedure("sp_listar_reglas_por_alcance", {"nivel_alcance": ["global"]})
    with pytest.raises(InvalidInputError, match="salida"):
        nexus.execute_procedure("sp_con_salida", {"total": 1})
    with pytest.raises(NotFoundError):
        nexus.execute_procedure("sp_executesql", {})


def test_create_table_applies_ddl_once(nexus):
    created = nexus.create_table(table())
    assert created["creada"] and created["tabla"] == "dbo.clientes"
    with pytest.raises(ConflictError):
        nexus.create_table(table())
    with pytest.raises(InvalidInputError):
        nexus.create_table(TableDefinition(name="mala tabla", columns=table().columns))


def test_backups(nexus):
    assert nexus.backup("pre_migracion")["archivo"] == "D:\\respaldos/pre_migracion.bak"
    assert nexus.backups()["total"] == 1
    with pytest.raises(InvalidInputError):
        nexus.backup("../../etc")


def test_json_value_conversions():
    from datetime import datetime
    from decimal import Decimal

    assert json_value(Decimal("12.50")) == 12.5
    assert json_value(datetime(2026, 10, 3, 14, 0)) == "2026-10-03T14:00:00"
    assert json_value(b"\x00\x01") == "AAE="


# ============================================================================ API


@pytest.fixture
def api():
    repo = seeded_repository()
    for perm_id, recurso, accion in (
        ("p_ev", "esquema", "ver"), ("p_em", "esquema", "modificar"),
        ("p_pe", "procedimientos", "ejecutar"), ("p_rs", "respaldos", "gestionar"),
    ):
        repo.add_permission(perm_id, recurso, accion)
        repo.grant_permission("rol_admin", perm_id)
    set_security_service(SecurityService(repo, SecuritySettings(secret_key="nexus-test-secret-" + "x" * 32)))
    set_nexus_service(NexusService(catalog(), max_rows=100))
    sentinel_routes._ip_limiter._hits.clear()
    app = FastAPI()
    app.include_router(sentinel_routes.router)
    app.include_router(nexus_routes.router)
    yield TestClient(app), repo
    set_security_service(None)
    set_nexus_service(None)


def headers(client, user="ana"):
    session = client.post("/api/v1/sentinel/autenticar",
                          json={"nombre_usuario": user, "contrasena": PASSWORDS[user], "id_empresa": "gio"}).json()
    return {"Authorization": f"Bearer {session['token_acceso']}"}


def test_api_permissions(api):
    client, _ = api
    assert client.get("/api/v1/nexus/salud").json()["estado"] == "activo"
    assert client.get("/api/v1/nexus/esquema/tablas").status_code == 401
    luis = headers(client, "luis")
    assert client.get("/api/v1/nexus/esquema/tablas", headers=luis).status_code == 403
    assert client.post("/api/v1/nexus/procedimientos/sp_listar_reglas_por_alcance/ejecutar", json={}, headers=luis).status_code == 403


def test_api_operations_are_audited(api):
    client, repo = api
    auth = headers(client)
    assert client.get("/api/v1/nexus/esquema/tablas", headers=auth).json()["total"] == 1
    assert client.get("/api/v1/nexus/esquema/tablas/dbo.reglas_negocio", headers=auth).status_code == 200
    assert client.get("/api/v1/nexus/esquema/tablas/dbo.otra", headers=auth).status_code == 404

    executed = client.post(
        "/api/v1/nexus/procedimientos/dbo.sp_listar_reglas_por_alcance/ejecutar",
        json={"parametros": {"nivel_alcance": "global"}},
        headers=auth,
    )
    assert executed.status_code == 200
    bad = client.post("/api/v1/nexus/procedimientos/sp_listar_reglas_por_alcance/ejecutar",
                      json={"parametros": {"x": 1}}, headers=auth)
    assert bad.status_code == 400

    ddl = client.post("/api/v1/nexus/esquema/ddl", json=table().model_dump(), headers=auth).json()
    assert "PRIMARY KEY CLUSTERED" in ddl["ddl"]
    assert client.post("/api/v1/nexus/esquema/tablas", json=table().model_dump(), headers=auth).status_code == 201
    assert client.post("/api/v1/nexus/respaldos", json={"etiqueta": "manual"}, headers=auth).status_code == 201

    _, entries = repo.list_audit("gio", None, None, None, None, None, 50, 0)
    acciones = {e.accion for e in entries}
    assert {"nexus_ejecutar_procedimiento", "nexus_crear_tabla", "nexus_respaldo"} <= acciones
    executed_entry = next(e for e in entries if e.accion == "nexus_ejecutar_procedimiento")
    assert "global" not in executed_entry.detalles
