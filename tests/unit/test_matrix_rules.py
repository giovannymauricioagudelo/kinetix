"""Unit tests for Matrix (BusinessRulesAgent): engine fixes, RulesService and API routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agents.business_rules_agent import formula
from src.agents.business_rules_agent.agent import ActionType, Condition, OperatorType, RuleAction, RuleEngine, build_rule
from src.agents.business_rules_agent.dependencies import set_rules_service
from src.agents.business_rules_agent.repository import InMemoryRulesRepository, _decode_details, _encode_details
from src.agents.business_rules_agent.service import RulesService
from src.agents.security_agent import SecurityService
from src.agents.security_agent.config import SecuritySettings
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError
from src.api.routes import matrix_routes, sentinel_routes
from tests.unit.test_sentinel_agent import PASSWORDS, seeded_repository


def rule_body(rule_id="RULE_DEUDA", **overrides):
    body = {
        "id_regla": rule_id,
        "nombre": "Bloquear si deuda",
        "nivel_alcance": "global",
        "prioridad": 100,
        "condiciones": [{"campo": "deuda_pendiente", "operador": "gt", "valor": "5000"}],
        "acciones": [{"tipo": "block", "detalles": {"mensaje": "Deuda superior al límite"}, "critica": True}],
    }
    body.update(overrides)
    return body


# ============================================================================ motor


def test_condition_accepts_falsy_values_and_db_strings():
    assert Condition("saldo", OperatorType.EQ, 0).evaluate({"saldo": 0}) is True
    assert Condition("activo", OperatorType.EQ, False).evaluate({"activo": False}) is True
    assert Condition("deuda", OperatorType.GT, "5000").evaluate({"deuda": 7000}) is True
    assert Condition("id_empresa", OperatorType.EQ, "2").evaluate({"id_empresa": 2}) is True
    assert Condition("deuda", OperatorType.GT, "5000").evaluate({}) is False
    assert Condition("estado", OperatorType.IN, '["activo", "pendiente"]').evaluate({"estado": "pendiente"}) is True
    assert Condition("estado", OperatorType.NOT_IN, "activo,pendiente").evaluate({"estado": "retirado"}) is True
    assert Condition("monto", OperatorType.GT, 10).evaluate({"monto": "texto"}) is False


def test_or_conditions_are_combined_left_to_right():
    conditions = [
        Condition("edad", OperatorType.LT, 18),
        Condition("pensionado", OperatorType.EQ, True, "OR"),
    ]
    assert RuleEngine.conditions_met(conditions, {"edad": 70, "pensionado": True}) is True
    assert RuleEngine.conditions_met(conditions, {"edad": 30, "pensionado": False}) is False


def test_formula_is_sandboxed():
    assert formula.evaluate("max(ventas_mes * 0.015, 10)", {"ventas_mes": "2000"}) == 30.0
    for malicious in ("__import__('os').system('dir')", "monto.__class__", "[x for x in ()]", "monto if 1 else 2", "2 ** 100"):
        with pytest.raises(formula.FormulaError):
            formula.evaluate(malicious, {"monto": 1})
    with pytest.raises(formula.FormulaError):
        formula.evaluate("monto / 0", {"monto": 1})


def test_actions_accept_the_database_detail_formats():
    rule = build_rule({
        "rule_id": "r", "name": "r",
        "actions": [
            {"type": "calculate", "details": {"comision": "ventas_mes * 0.015", "bono": "comision * 2"}},
            {"type": "set_field", "details": {"fondo_obligatorio": "moderado", "porcentaje": 10}},
            {"type": "notify", "details": {"mensaje": "Auditoría requerida"}},
        ],
    })
    result = RuleEngine().evaluate_rule(rule, {"ventas_mes": 2000})
    assert result.calculated_values == {"comision": 30.0, "bono": 60.0, "fondo_obligatorio": "moderado", "porcentaje": 10}
    assert result.actions_executed[2]["message"] == "Auditoría requerida"
    assert result.decision.value == "permitida"


def test_block_action_sets_blocked_decision():
    result = RuleEngine().evaluate_rule(
        build_rule({"rule_id": "r", "name": "r", "actions": [{"type": "block", "details": {"mensaje": "No"}}]}), {}
    )
    assert result.decision.value == "bloqueada"
    assert result.actions_executed[0]["reason"] == "No"


def test_detail_encoding_round_trip():
    assert _encode_details({"mensaje": "Texto plano"}) == "Texto plano"
    assert _decode_details("Texto plano") == {"mensaje": "Texto plano"}
    assert _decode_details('{"comision": "x * 2"}') == {"comision": "x * 2"}


def test_failed_formula_is_reported_not_raised():
    engine = RuleEngine()
    rule = build_rule({"rule_id": "r", "name": "r", "actions": [{"type": "calculate", "details": {"x": "falta * 2"}}]})
    result = engine.evaluate_rule(rule, {})
    assert result.calculated_values == {}
    assert "Variable desconocida" in result.errors[0]
    assert engine._execute_action(RuleAction(ActionType.LOG, {"mensaje": "hola"}), {}, result)["message"] == "hola"


# ============================================================================ servicio


@pytest.fixture
def rules():
    return RulesService(InMemoryRulesRepository())


def test_create_get_update_archive(rules):
    created = rules.create_rule(rule_body(), "ana")
    assert created["estado"] == "activa" and created["modificada_por"] == "ana"
    with pytest.raises(ConflictError):
        rules.create_rule(rule_body(), "ana")

    updated = rules.update_rule("RULE_DEUDA", rule_body(nombre="Bloqueo por deuda", prioridad=90), "luis")
    assert updated["nombre"] == "Bloqueo por deuda" and updated["prioridad"] == 90

    assert rules.archive_rule("RULE_DEUDA", "ana")["estado"] == "archivada"
    assert rules.list_rules(estado="activa")["total"] == 0
    with pytest.raises(ConflictError):
        rules.evaluate_rule("RULE_DEUDA", {"deuda_pendiente": 9000}, "ana")
    with pytest.raises(NotFoundError):
        rules.get_rule("NO_EXISTE")


@pytest.mark.parametrize("overrides, message", [
    ({"id_regla": "regla con espacios"}, "id_regla"),
    ({"nivel_alcance": "planeta"}, "nivel_alcance"),
    ({"nivel_alcance": "empresa"}, "id_empresa"),
    ({"nivel_alcance": "linea_negocio"}, "linea_negocio"),
    ({"acciones": [{"tipo": "calculate", "detalles": {"x": "__import__('os')"}}]}, "Fórmula"),
    ({"condiciones": [{"campo": "x", "operador": "parecido", "valor": 1}]}, "inválida"),
])
def test_invalid_rules_are_rejected(rules, overrides, message):
    with pytest.raises(InvalidInputError, match=message):
        rules.create_rule(rule_body(**overrides), "ana")


def test_evaluate_records_audit(rules):
    rules.create_rule(rule_body(), "ana")
    outcome = rules.evaluate_rule("RULE_DEUDA", {"deuda_pendiente": 9000}, "ana", id_empresa=1)
    assert outcome["condiciones_cumplidas"] is True and outcome["decision"] == "bloqueada"
    audit = rules.audit("RULE_DEUDA")
    assert audit["total"] == 1
    assert audit["registros"][0]["decision"] == "bloqueada"
    assert audit["registros"][0]["evaluada_por"] == "ana"
    assert audit["registros"][0]["id_empresa"] == 1


def test_evaluate_applicable_follows_hierarchy_and_priority(rules):
    rules.create_rule(rule_body(), "ana")
    rules.create_rule(rule_body(
        "RULE_COMISION", nombre="Comisión retail", nivel_alcance="linea_negocio", linea_negocio="retail", prioridad=80,
        condiciones=[{"campo": "ventas_mes", "operador": "gt", "valor": "1000"}],
        acciones=[{"tipo": "calculate", "detalles": {"comision": "ventas_mes * 0.015"}}],
    ), "ana")
    rules.create_rule(rule_body(
        "RULE_EMPRESA_2", nombre="Contribución", nivel_alcance="empresa", id_empresa=2, prioridad=70,
        condiciones=[], acciones=[{"tipo": "notify", "detalles": "Contribución adicional"}],
    ), "ana")

    allowed = rules.evaluate_applicable({"ventas_mes": 2000, "deuda_pendiente": 0}, "ana", id_empresa=1, linea_negocio="retail")
    assert allowed["decision"] == "permitida"
    assert allowed["reglas_evaluadas"] == 2
    assert allowed["reglas_cumplidas"] == ["RULE_COMISION"]
    assert allowed["valores_calculados"] == {"comision": 30.0}

    blocked = rules.evaluate_applicable({"deuda_pendiente": 6000}, "ana", id_empresa=2)
    assert blocked["decision"] == "bloqueada"
    assert [d["id_regla"] for d in blocked["detalle"]] == ["RULE_DEUDA", "RULE_EMPRESA_2"]
    assert blocked["notificaciones"][0]["id_regla"] == "RULE_EMPRESA_2"

    assert rules.evaluate_applicable({}, "ana")["decision"] == "no_aplica"


def test_try_rule_scenarios_do_not_write_audit(rules):
    rules.create_rule(rule_body(), "ana")
    report = rules.test_rule("RULE_DEUDA", [
        {"contexto": {"deuda_pendiente": 9000}, "esperado": "bloqueada"},
        {"contexto": {"deuda_pendiente": 10}, "esperado": True},
        {"contexto": {"deuda_pendiente": 10}},
    ])
    assert (report["total"], report["verificados"], report["aprobados"]) == (3, 2, 1)
    assert rules.audit()["total"] == 0


def test_analytics(rules):
    rules.create_rule(rule_body(), "ana")
    rules.create_rule(rule_body("RULE_SIN_USO"), "ana")
    rules.evaluate_rule("RULE_DEUDA", {"deuda_pendiente": 9000}, "ana")
    rules.evaluate_rule("RULE_DEUDA", {"deuda_pendiente": 1}, "ana")
    stats = rules.analytics()
    assert stats["evaluaciones"] == 2 and stats["bloqueos"] == 1
    assert stats["reglas_activas_sin_uso"] == ["RULE_SIN_USO"]
    assert stats["por_regla"][0]["tasa_cumplimiento_porcentaje"] == 50.0


# ============================================================================ API


@pytest.fixture
def api():
    repo = seeded_repository()
    for perm_id, accion in (("p_rv", "ver"), ("p_rg", "gestionar"), ("p_re", "evaluar")):
        repo.add_permission(perm_id, "reglas", accion)
        repo.grant_permission("rol_admin", perm_id)
    security = SecurityService(repo, SecuritySettings(secret_key="matrix-test-secret-" + "x" * 32))
    set_security_service(security)
    set_rules_service(RulesService(InMemoryRulesRepository()))
    sentinel_routes._ip_limiter._hits.clear()
    app = FastAPI()
    app.include_router(sentinel_routes.router)
    app.include_router(matrix_routes.router)
    yield TestClient(app), repo
    set_security_service(None)
    set_rules_service(None)


def headers(client, user="ana"):
    session = client.post("/api/v1/sentinel/autenticar",
                          json={"nombre_usuario": user, "contrasena": PASSWORDS[user], "id_empresa": "gio"}).json()
    return {"Authorization": f"Bearer {session['token_acceso']}"}


def test_api_requires_sentinel_permissions(api):
    client, _ = api
    assert client.get("/api/v1/matrix/salud").json()["base_datos"] == "conectada"
    assert client.get("/api/v1/matrix/reglas").status_code == 401
    assert client.get("/api/v1/matrix/reglas", headers=headers(client, "luis")).status_code == 403


def test_api_rule_lifecycle_and_audit(api):
    client, repo = api
    auth = headers(client)
    created = client.post("/api/v1/matrix/reglas", json=rule_body(), headers=auth)
    assert created.status_code == 201
    assert client.post("/api/v1/matrix/reglas", json=rule_body(), headers=auth).status_code == 409

    plain = rule_body("RULE_TEXTO", acciones=[{"tipo": "notify", "detalles": "Mensaje plano"}])
    assert client.post("/api/v1/matrix/reglas", json=plain, headers=auth).json()["regla"]["acciones"][0]["detalles"] == {"mensaje": "Mensaje plano"}

    evaluated = client.post("/api/v1/matrix/reglas/RULE_DEUDA/evaluar", json={"contexto": {"deuda_pendiente": 8000}}, headers=auth).json()
    assert evaluated["decision"] == "bloqueada"
    overall = client.post("/api/v1/matrix/evaluar", json={"contexto": {"deuda_pendiente": 8000}}, headers=auth).json()
    assert overall["decision"] == "bloqueada" and overall["bloqueos"][0]["id_regla"] == "RULE_DEUDA"

    assert client.get("/api/v1/matrix/auditoria?id_regla=RULE_DEUDA", headers=auth).json()["total"] == 2
    assert client.get("/api/v1/matrix/analitica", headers=auth).json()["evaluaciones"] == 3
    assert client.delete("/api/v1/matrix/reglas/RULE_DEUDA", headers=auth).json()["estado"] == "archivada"
    assert client.get("/api/v1/matrix/reglas/NO_EXISTE", headers=auth).status_code == 404

    total, entries = repo.list_audit("gio", None, None, None, None, None, 50, 0)
    acciones = {e.accion for e in entries}
    assert {"matrix_regla_crear", "matrix_regla_archivar"} <= acciones


def test_api_validation_errors_are_400(api):
    client, _ = api
    bad = rule_body(acciones=[{"tipo": "calculate", "detalles": {"x": "open('archivo')"}}])
    response = client.post("/api/v1/matrix/reglas", json=bad, headers=headers(client))
    assert response.status_code == 400
    assert "Fórmula" in response.json()["detail"]
