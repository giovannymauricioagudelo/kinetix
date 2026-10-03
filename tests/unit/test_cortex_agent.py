"""Unit tests for Cortex (OrchestratorAgent)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agents.orchestrator_agent import (
    Complexity,
    OrchestratorAgent,
    RequestStatus,
    RequestType,
)


@pytest.fixture
def cortex():
    return OrchestratorAgent()


def _pending_ids(request):
    return [q.id for q in request.pending_questions]


def _answer_all(cortex, request, value="no aplica"):
    while request.pending_questions:
        request = cortex.answer(request.id, {q.id: value for q in request.pending_questions})
    return request


def test_uses_cortex_codename(cortex):
    assert cortex.name == "Cortex"


def test_ambiguous_request_asks_for_type_first(cortex):
    request = cortex.submit("Necesito revisar el módulo de facturación")
    assert request.request_type is None
    assert _pending_ids(request) == ["tipo_solicitud"]
    assert request.plan == []


def test_type_answer_resolves_request_type(cortex):
    request = cortex.submit("Necesito revisar el módulo de facturación")
    request = cortex.answer(request.id, {"tipo_solicitud": "Es una corrección"})
    assert request.request_type == RequestType.BUGFIX
    assert "app_id" in _pending_ids(request)


def test_unclear_type_answer_is_asked_again(cortex):
    request = cortex.submit("Necesito revisar el módulo de facturación")
    request = cortex.answer(request.id, {"tipo_solicitud": "no estoy seguro"})
    assert _pending_ids(request) == ["tipo_solicitud"]


def test_simple_bugfix_is_low_and_asks_only_base_questions(cortex):
    request = cortex.submit("El login no funciona después del último cambio", app_id="sicita")
    assert request.request_type == RequestType.BUGFIX
    assert request.complexity == Complexity.LOW
    assert set(_pending_ids(request)) == {"pasos_reproducir", "esperado_vs_actual", "severidad"}


def test_complex_new_app_is_high_and_asks_more_questions(cortex):
    request = cortex.submit(
        "Crear una aplicación nueva multiempresa para talleres con integración al ERP, "
        "reglas de impuestos, dashboards de KPIs y app web y móvil, cumpliendo normativa DIAN"
    )
    assert request.request_type == RequestType.NEW_APP
    assert request.complexity == Complexity.HIGH
    pending = _pending_ids(request)
    assert {"multiempresa", "cumplimiento", "plazo_presupuesto"} <= set(pending)
    assert request.status == RequestStatus.NEEDS_CLARIFICATION


def test_no_plan_until_questions_answered(cortex):
    request = cortex.submit("El login no funciona", app_id="sicita")
    assert request.plan == []
    request = _answer_all(cortex, request)
    assert request.status == RequestStatus.PLAN_PROPOSED
    assert request.plan


def test_new_app_plan_delegates_with_dependencies(cortex):
    request = cortex.submit("Crear una aplicación nueva de citas con reportes y pantallas web")
    request = _answer_all(cortex, request)
    tasks = {t.agent.codename: t for t in request.plan}
    assert {"Nexus", "Insight", "Aurora", "Vector", "Prism", "Orbit"} <= set(tasks)
    assert "nexus_01" in tasks["Insight"].depends_on
    assert tasks["Prism"].depends_on == ["vector_01"]
    assert tasks["Orbit"].depends_on == ["prism_01"]
    assert "Cortex" not in tasks


def test_new_app_always_includes_sentinel_and_argus(cortex):
    request = _answer_all(cortex, cortex.submit("Crear una aplicación nueva de citas con pantallas web"))
    tasks = {t.agent.codename: t for t in request.plan}
    assert "nexus_01" in tasks["Sentinel"].depends_on
    assert "sentinel_01" in tasks["Vector"].depends_on
    assert tasks["Argus"].depends_on == ["orbit_01"]
    assert [t.agent.codename for t in request.plan][-1] == "Argus"


def test_scale_request_includes_argus_but_not_sentinel(cortex):
    request = _answer_all(cortex, cortex.submit("Necesitamos escalar el módulo de citas, está lento", app_id="sicita"))
    agents = [t.agent.codename for t in request.plan]
    assert "Argus" in agents and "Sentinel" not in agents


def test_bugfix_plan_is_minimal(cortex):
    request = cortex.submit("La búsqueda de clientes no funciona", app_id="crm")
    request = _answer_all(cortex, request)
    assert [t.agent.codename for t in request.plan] == ["Vector", "Prism", "Orbit"]


def test_login_bug_involves_sentinel(cortex):
    request = _answer_all(cortex, cortex.submit("El login no funciona", app_id="sicita"))
    assert [t.agent.codename for t in request.plan] == ["Sentinel", "Vector", "Prism", "Orbit"]
    assert "sentinel_01" in request.plan[1].depends_on


def test_answers_do_not_change_resolved_type(cortex):
    request = cortex.submit("Quiero mejorar la búsqueda de clientes", app_id="crm")
    assert request.request_type == RequestType.ENHANCEMENT
    request = cortex.answer(request.id, {"criterios_aceptacion": "que no haya errores al buscar"})
    assert request.request_type == RequestType.ENHANCEMENT


def test_plan_requires_human_approval(cortex):
    request = cortex.submit("El login no funciona", app_id="sicita")
    with pytest.raises(ValueError):
        cortex.approve(request.id, "giovanny")
    request = _answer_all(cortex, request)
    assert all(t.status.value == "pendiente_aprobacion" for t in request.plan)
    request = cortex.approve(request.id, "giovanny")
    assert request.status == RequestStatus.APPROVED
    assert request.approved_by == "giovanny"
    assert all(t.status.value == "lista_para_delegar" for t in request.plan)


def test_approved_request_rejects_new_answers(cortex):
    request = _answer_all(cortex, cortex.submit("El login no funciona", app_id="sicita"))
    cortex.approve(request.id, "giovanny")
    with pytest.raises(ValueError):
        cortex.answer(request.id, {"severidad": "alta"})


def test_api_flow():
    from src.api.routes.cortex_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    created = client.post(
        "/api/v1/cortex/requests",
        json={"descripcion": "El login no funciona en producción", "app_id": "sicita"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["estado"] == "requiere_aclaraciones"

    request_id = body["id"]
    while body["preguntas_pendientes"]:
        answers = {q["id"]: "no aplica" for q in body["preguntas_pendientes"]}
        body = client.post(f"/api/v1/cortex/requests/{request_id}/answers", json={"respuestas": answers}).json()
    assert body["estado"] == "plan_propuesto"

    approved = client.post(f"/api/v1/cortex/requests/{request_id}/approve", json={"aprobado_por": "giovanny"})
    assert approved.status_code == 200
    assert approved.json()["estado"] == "aprobado"

    assert client.get("/api/v1/cortex/requests/req-inexistente").status_code == 404
