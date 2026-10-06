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
    assert {"modelo_datos", "cumplimiento", "plazo_presupuesto"} <= set(pending)
    assert request.status == RequestStatus.NEEDS_CLARIFICATION


@pytest.mark.parametrize("answer, model", [
    ("Una base por empresa", "por_empresa"),
    ("multiempresa con datos separados", "multiempresa"),
    ("una sola base compartida", "multiempresa"),
    ("no aplica", "por_empresa"),
])
def test_new_app_data_model_drives_nexus_task(cortex, answer, model):
    request = cortex.submit("Crear una aplicación nueva de citas con pantallas web")
    assert "modelo_datos" in _pending_ids(request)
    request = cortex.answer(request.id, {"modelo_datos": answer})
    request = _answer_all(cortex, request)
    assert request.data_model == model and request.to_dict()["modelo_datos"] == model
    nexus = next(t for t in request.plan if t.agent.codename == "Nexus")
    assert ("{app}_{empresa}" if model == "por_empresa" else "id_empresa") in nexus.accion


def test_unclear_data_model_is_asked_again(cortex):
    request = cortex.submit("Crear una aplicación nueva de citas con pantallas web")
    request = cortex.answer(request.id, {"modelo_datos": "lo que sea"})
    assert "modelo_datos" in _pending_ids(request) and request.data_model is None


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


# ============================================================================ sprints


def _medium_app(cortex, app_name="Talleres SICITA"):
    request = cortex.submit("Crear una aplicación nueva de citas con reportes y pantallas web")
    assert request.complexity == Complexity.MEDIUM and "id_aplicacion" in _pending_ids(request)
    request = cortex.answer(request.id, {"id_aplicacion": app_name, "motor_base_datos": "PostgreSQL"})
    return _answer_all(cortex, request)


def test_low_complexity_keeps_single_plan(cortex):
    request = _answer_all(cortex, cortex.submit("El login no funciona", app_id="sicita"))
    assert request.sprints == [] and request.to_dict()["ejecucion_por_sprints"] is False
    assert "id_aplicacion" not in request.answers


def test_medium_new_app_is_split_into_logical_sprints_identified_by_app(cortex):
    request = _medium_app(cortex)
    sprints = request.to_dict()["sprints"]
    assert [s["clave"] for s in sprints] == ["fundaciones", "interfaz", "reportes", "salida"]
    assert [s["etiqueta"] for s in sprints] == [f"Sprint {n} de 4" for n in range(1, 5)]
    assert sprints[0]["id"] == "talleres_sicita-sprint-01" and sprints[1]["depende_de"] == "talleres_sicita-sprint-01"
    assert all(s["estado"] == "planificado" for s in sprints)
    foundations = {t["agente"]: t for t in sprints[0]["tareas"]}
    assert "PostgreSQL" in foundations["Nexus"]["accion"] and foundations["Prism"]["depende_de"] == ["s01_vector"]
    assert request.to_dict()["progreso_sprints"] == {"aplicacion": "talleres_sicita", "total": 4, "completados": 0,
                                                     "actual": None, "siguiente": "Sprint 1 de 4"}


def test_unclear_app_id_is_asked_again_and_no_aplica_gets_generated_id(cortex):
    request = cortex.submit("Crear una aplicación nueva de citas con reportes y pantallas web")
    request = cortex.answer(request.id, {"id_aplicacion": "???"})
    assert "id_aplicacion" in _pending_ids(request)
    request = _answer_all(cortex, request)
    assert request.aplicacion == f"app_{request.id.removeprefix('req-')}"
    assert request.sprints[0].id.startswith("app_")


def test_humans_decide_when_each_sprint_starts(cortex):
    request = _medium_app(cortex)
    with pytest.raises(ValueError, match="Aprueba el plan"):
        cortex.start_sprint(request.id, 1, "giovanny")
    request = cortex.approve(request.id, "giovanny")
    assert all(s.status.value == "pendiente" for s in request.sprints)
    assert all(t.status.value == "por_sprint" for t in request.plan)
    assert all(t.status.value == "espera_sprint" for s in request.sprints for t in s.tareas)
    assert "inicia el Sprint 1 de 4" in request.to_dict()["siguiente_paso"]

    with pytest.raises(ValueError, match="Completa primero el Sprint 1 de 4"):
        cortex.start_sprint(request.id, 2, "giovanny")
    request = cortex.start_sprint(request.id, 1, "giovanny")
    assert all(t.status.value == "lista_para_delegar" for t in request.sprints[0].tareas)
    with pytest.raises(ValueError, match="solo se inicia un sprint pendiente"):
        cortex.start_sprint(request.id, 1, "giovanny")
    with pytest.raises(ValueError, match="solo se completa un sprint en curso"):
        cortex.complete_sprint(request.id, 2, "giovanny")

    request = cortex.complete_sprint(request.id, 1, "giovanny", "Base creada en PostgreSQL")
    assert request.sprints[0].notas == "Base creada en PostgreSQL"
    assert request.sprints[1].status.value == "pendiente" and request.current_sprint() is None
    assert "inicia el Sprint 2 de 4 (talleres_sicita-sprint-02)" in request.to_dict()["siguiente_paso"]

    for numero in (2, 3, 4):
        cortex.start_sprint(request.id, numero, "giovanny")
        request = cortex.complete_sprint(request.id, numero, "giovanny")
    assert request.status == RequestStatus.COMPLETED
    with pytest.raises(ValueError):
        cortex.answer(request.id, {"objetivo": "otro"})
    with pytest.raises(KeyError):
        cortex.start_sprint(request.id, 5, "giovanny")


def test_high_complexity_adds_compliance_performance_and_pilot(cortex):
    request = cortex.submit(
        "Crear una aplicación nueva multiempresa para talleres con integración al ERP, reglas de impuestos, "
        "dashboards de KPIs y app web y móvil para millones de usuarios, cumpliendo normativa DIAN"
    )
    assert request.complexity == Complexity.HIGH
    request = _answer_all(cortex, cortex.answer(request.id, {"id_aplicacion": "talleres"}))
    assert [s.clave for s in request.sprints] == ["fundaciones", "reglas", "integraciones", "interfaz", "reportes",
                                                  "cumplimiento", "rendimiento", "piloto", "salida"]
    assert request.sprints[-1].etiqueta == "Sprint 9 de 9"


def test_scale_with_engine_change_gets_its_own_sprint_and_app_view(cortex):
    request = cortex.submit("Necesitamos escalar el módulo de citas, está lento y con alta concurrencia de usuarios",
                            app_id="sicita")
    request = _answer_all(cortex, cortex.answer(request.id, {"cambio_motor": "de Mongo a PostgreSQL"}))
    assert request.complexity in (Complexity.MEDIUM, Complexity.HIGH)
    assert [s.clave for s in request.sprints] == ["diagnostico", "cambio_motor", "optimizacion", "salida"]
    assert request.sprints[1].nombre == "Cambio de motor a PostgreSQL" and request.sprints[0].id == "sicita-sprint-01"
    other = _answer_all(cortex, cortex.submit("La búsqueda de clientes no funciona", app_id="crm"))
    assert [s.id for _, s in cortex.sprints_for_app("SICITA")] == [f"sicita-sprint-0{n}" for n in range(1, 5)]
    assert cortex.sprints_for_app("crm") == [] and other.sprints == []


def test_api_sprint_flow():
    from src.api.routes.cortex_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    body = client.post("/api/v1/cortex/requests", json={
        "descripcion": "Crear una aplicación nueva de inventario con reportes y pantallas web"}).json()
    request_id = body["id"]
    while body["preguntas_pendientes"]:
        answers = {q["id"]: ("inventario" if q["id"] == "id_aplicacion" else "no aplica") for q in body["preguntas_pendientes"]}
        body = client.post(f"/api/v1/cortex/requests/{request_id}/answers", json={"respuestas": answers}).json()
    assert body["ejecucion_por_sprints"] and body["sprints"][0]["id"] == "inventario-sprint-01"
    client.post(f"/api/v1/cortex/requests/{request_id}/approve", json={"aprobado_por": "giovanny"})

    url = f"/api/v1/cortex/requests/{request_id}/sprints"
    assert client.post(f"{url}/2/iniciar", json={"iniciado_por": "giovanny"}).status_code == 409
    assert client.post(f"{url}/9/iniciar", json={"iniciado_por": "giovanny"}).status_code == 404
    started = client.post(f"{url}/1/iniciar", json={"iniciado_por": "giovanny"}).json()
    assert started["progreso_sprints"]["actual"] == "Sprint 1 de 4"
    done = client.post(f"{url}/1/completar", json={"completado_por": "giovanny", "notas": "ok"}).json()
    assert done["sprints"][0]["estado"] == "completado" and done["sprints"][1]["estado"] == "pendiente"

    view = client.get("/api/v1/cortex/apps/inventario/sprints").json()
    assert view["completados"] == 1 and view["siguiente_disponible"] == "inventario-sprint-02"
    assert view["sprints"][0]["id_solicitud"] == request_id
    listed = client.get("/api/v1/cortex/requests").json()["solicitudes"]
    assert any(s["aplicacion"] == "inventario" and s["progreso_sprints"]["completados"] == 1 for s in listed)


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
