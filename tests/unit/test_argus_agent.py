"""Unit tests for Argus (MonitoringAgent)."""

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.agents.monitoring_agent import MonitoringService, install_argus, set_monitoring_service
from src.agents.monitoring_agent.alerts import AlertManager, AlertThresholds
from src.agents.monitoring_agent.collector import agent_for_route
from src.agents.monitoring_agent.health import AgentHealth
from src.agents.security_agent import SecurityService
from src.agents.security_agent.config import SecuritySettings
from src.agents.security_agent.dependencies import set_security_service
from src.api.routes import argus_routes, sentinel_routes
from tests.unit.test_sentinel_agent import PASSWORDS, seeded_repository


def build_app() -> FastAPI:
    app = FastAPI()
    nexus = APIRouter(prefix="/api/v1/nexus")

    @nexus.get("/info")
    async def nexus_info():
        return {"id": "nexus"}

    @nexus.get("/items/{item_id}")
    async def nexus_item(item_id: int):
        return {"id": item_id}

    @nexus.get("/boom")
    async def nexus_boom():
        raise HTTPException(503, "fallo simulado")

    matrix = APIRouter(prefix="/api/v1/matrix")

    @matrix.get("/info")
    async def matrix_info():
        raise HTTPException(500, "caído")

    app.include_router(nexus)
    app.include_router(matrix)
    app.include_router(sentinel_routes.router)
    app.include_router(argus_routes.router)
    return app


@pytest.fixture
def monitoring(monkeypatch):
    monkeypatch.setenv("ARGUS_PROBE_INTERVAL_SECONDS", "0")
    monkeypatch.delenv("ARGUS_SCRAPE_TOKEN", raising=False)
    security = SecurityService(seeded_repository(), SecuritySettings(secret_key="argus-test-secret-" + "x" * 32))
    set_security_service(security)
    sentinel_routes._ip_limiter._hits.clear()
    service = MonitoringService()
    app = build_app()
    install_argus(app, service)
    yield TestClient(app), service
    set_security_service(None)
    set_monitoring_service(None)


def token(client, user="ana"):
    response = client.post(
        "/api/v1/sentinel/autenticar",
        json={"nombre_usuario": user, "contrasena": PASSWORDS[user], "id_empresa": "gio"},
    )
    return response.json()["token_acceso"]


def auth(client, user="ana"):
    return {"Authorization": f"Bearer {token(client, user)}"}


def test_route_to_agent_mapping():
    assert agent_for_route("/api/v1/nexus/info") == "Nexus"
    assert agent_for_route("/api/v1/database/tables") == "Nexus"
    assert agent_for_route("/api/v1/argus/salud") == "Argus"
    assert agent_for_route("/health") == "Plataforma"


def test_middleware_records_real_requests_by_route_template(monitoring):
    client, service = monitoring
    client.get("/api/v1/nexus/items/7")
    client.get("/api/v1/nexus/items/8")
    client.get("/no-existe")
    samples = service.collector.samples_since(60)
    routes = [(s.agent, s.route, s.status) for s in samples]
    assert routes.count(("Nexus", "/api/v1/nexus/items/{item_id}", 200)) == 2
    assert ("Plataforma", "sin_ruta", 404) in routes


def test_salud_is_public_and_reflects_real_probes(monitoring):
    client, _ = monitoring
    body = client.get("/api/v1/argus/salud").json()
    assert body["estado"] == "critico"
    assert body["agentes_desplegados"] == 4
    assert body["agentes_activos"] == 3


def test_monitoring_endpoints_require_sentinel_permission(monitoring):
    client, _ = monitoring
    assert client.get("/api/v1/argus/agentes").status_code == 401
    assert client.get("/api/v1/argus/agentes", headers=auth(client, "luis")).status_code == 403
    assert client.get("/api/v1/argus/agentes", headers=auth(client)).status_code == 200


def test_agents_view_distinguishes_up_down_and_not_deployed(monitoring):
    client, _ = monitoring
    agents = {a["agente"]: a for a in client.get("/api/v1/argus/agentes", headers=auth(client)).json()["agentes"]}
    assert agents["Nexus"]["estado"] == "activo"
    assert agents["Sentinel"]["estado"] == "activo"
    assert agents["Argus"]["estado"] == "activo"
    assert agents["Matrix"]["estado"] == "caido"
    assert agents["Aurora"]["estado"] == "no_desplegado"
    assert len(agents) == 12


def test_agent_detail_lists_endpoints(monitoring):
    client, _ = monitoring
    client.get("/api/v1/nexus/items/1")
    detail = client.get("/api/v1/argus/agentes/nexus", headers=auth(client)).json()
    assert detail["agente"] == "Nexus"
    assert any(e["endpoint"] == "GET /api/v1/nexus/items/{item_id}" for e in detail["endpoints"])
    assert client.get("/api/v1/argus/agentes/desconocido", headers=auth(client)).status_code == 404


def test_prometheus_metrics_and_scrape_token(monitoring, monkeypatch):
    client, _ = monitoring
    client.get("/api/v1/nexus/items/1")
    assert client.get("/api/v1/argus/metricas").status_code == 401
    text = client.get("/api/v1/argus/metricas", headers=auth(client)).text
    assert 'kinetix_http_requests_total{agent="Nexus"' in text

    monkeypatch.setenv("ARGUS_SCRAPE_TOKEN", "token-de-raspado")
    scraped = client.get("/api/v1/argus/metricas", headers={"Authorization": "Bearer token-de-raspado"})
    assert scraped.status_code == 200


def test_error_rate_and_down_agent_raise_alerts_that_can_be_acknowledged(monitoring):
    client, _ = monitoring
    for _ in range(25):
        client.get("/api/v1/nexus/boom")
    headers = auth(client)
    alerts = client.get("/api/v1/argus/alertas", headers=headers).json()["alertas"]
    kinds = {(a["tipo"], a["agente"]) for a in alerts}
    assert ("tasa_error_alta", "Nexus") in kinds
    assert ("agente_caido", "Matrix") in kinds

    alert_id = alerts[0]["id"]
    acknowledged = client.post(f"/api/v1/argus/alertas/{alert_id}/reconocer", headers=headers).json()
    assert acknowledged["alerta"]["reconocida_por"] == "ana"
    assert client.post("/api/v1/argus/alertas/no-existe/reconocer", headers=headers).status_code == 404
    assert client.post(f"/api/v1/argus/alertas/{alert_id}/reconocer", headers=auth(client, "luis")).status_code == 403


def test_alerts_resolve_when_condition_clears():
    manager = AlertManager(AlertThresholds())
    down = AgentHealth("Matrix", "BusinessRulesAgent", "caido", 3.0, 500, 0.0)
    up = AgentHealth("Matrix", "BusinessRulesAgent", "activo", 3.0, 200, 0.0)
    assert [a.tipo for a in manager.evaluate({}, [down])] == ["agente_caido"]
    assert manager.evaluate({}, [down])[0].id == manager.active()[0].id
    assert manager.evaluate({}, [up]) == []
    assert manager.list("resuelta")[0].tipo == "agente_caido"


def test_reports_use_observed_data(monitoring):
    client, _ = monitoring
    client.get("/api/v1/nexus/items/1")
    headers = auth(client)
    client.get("/api/v1/argus/agentes", headers=headers)

    performance = client.get("/api/v1/argus/reportes/rendimiento", headers=headers).json()
    assert performance["por_agente"]["Nexus"]["total"] >= 1

    availability = client.get("/api/v1/argus/reportes/disponibilidad", headers=headers).json()
    assert availability["por_agente"]["Nexus"]["disponibilidad_porcentaje"] == 100.0
    assert availability["por_agente"]["Matrix"]["disponibilidad_porcentaje"] == 0.0
    assert "Matrix" in availability["sla"]["incumplen"]
    assert "Aurora" in availability["agentes_no_desplegados"]


def test_system_resources_are_real(monitoring):
    client, _ = monitoring
    resources = client.get("/api/v1/argus/sistema/recursos", headers=auth(client)).json()
    assert resources["cpu"]["nucleos_logicos"] > 0
    assert resources["memoria"]["total_gb"] > 0
    assert 0 <= resources["disco"]["uso_porcentaje"] <= 100


def test_live_websocket_requires_valid_token(monitoring):
    client, _ = monitoring
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/argus/ws/metricas-vivo?token=invalido") as ws:
            ws.receive_json()
    with client.websocket_connect(f"/api/v1/argus/ws/metricas-vivo?token={token(client)}&intervalo=1") as ws:
        frame = ws.receive_json()
    assert {"peticiones_por_segundo", "cpu_porcentaje", "estado"} <= set(frame)
