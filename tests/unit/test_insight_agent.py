"""Insight (ReportingAgent): catálogo, exportación segura, reportes por empresa, programaciones, KPIs y API protegida."""

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from src.agents.reporting_agent import exporters
from src.agents.reporting_agent.dependencies import default_sources, set_insight_service
from src.agents.reporting_agent.reports import Sources
from src.agents.reporting_agent.repository import InMemoryInsightRepository
from src.agents.reporting_agent.service import InsightService, add_month, first_run, next_after
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import InvalidInputError, NotFoundError, Principal
from src.api.routes import insight_routes
from tests.unit.agent_api import build_api, headers

START = datetime(2026, 10, 3, 12, 0, 0)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now


@dataclass
class Evaluation:
    id_regla: str
    id_empresa: int
    decision: str
    condiciones_cumplidas: bool
    tiempo_ejecucion_ms: float
    fecha: datetime


class FakeRules:
    def evaluation_records(self, id_regla, dias, limite):
        records = [
            Evaluation("br_1", 1, "aplicada", True, 2.0, START - timedelta(days=1)),
            Evaluation("br_1", 1, "bloqueada", True, 4.0, START - timedelta(days=1)),
            Evaluation("br_2", 2, "sin_cambios", False, 6.0, START),
        ]
        return [r for r in records if id_regla in (None, r.id_regla)]

    def analytics(self, dias):
        return {"reglas_activas": 2, "evaluaciones": 3, "bloqueos": 1, "reglas_activas_sin_uso": ["br_3"], "por_regla": []}


class FakeSecurity:
    def __init__(self):
        self.allowed = True

    def authorize(self, principal, permission):
        return self.allowed

    def audit_counts(self, actor, dias):
        return [("autenticar", "exito", 5), ("autenticar", "fallo_credenciales", 2), ("cerrar_sesion", "exito", 1)]


class FakeOrbit:
    def list_deployments(self, entorno, estado, limit):
        items = [
            {"id_despliegue": "od_2", "fecha_inicio": "2026-10-03T10:00:00", "entorno": "produccion", "tipo": "reversion",
             "estado": "exitoso", "commit": "b" * 40, "tag": "release/produccion/20261003-100000", "tag_publicado": True,
             "iniciado_por": "=HYPERLINK(\"http://x\")"},
            {"id_despliegue": "od_1", "fecha_inicio": "2026-10-02T10:00:00", "entorno": "staging", "tipo": "despliegue",
             "estado": "rechazado", "commit": "a" * 40, "tag": None, "tag_publicado": False, "iniciado_por": "ana"},
            {"id_despliegue": "od_0", "fecha_inicio": "2026-01-01T10:00:00", "entorno": "staging", "tipo": "despliegue",
             "estado": "exitoso", "commit": "c" * 40, "tag": "release/staging/20260101-100000", "tag_publicado": False,
             "iniciado_por": "ana"},
        ]
        return {"despliegues": [d for d in items if entorno in (None, d["entorno"])]}


def broken():
    raise RuntimeError("Argus caído")


def make_service(security=None, clock=None):
    clock = clock or Clock()
    security = security or FakeSecurity()
    sources = Sources(rules=FakeRules, security=lambda: security, monitoring=broken, prism=broken, orbit=FakeOrbit,
                      vector=broken, now=clock)
    return InsightService(InMemoryInsightRepository(), sources, clock=clock, max_rows=2), security, clock


def principal(empresa="gio", user="ana"):
    return Principal(id=f"u_{user}", nombre_usuario=user, id_empresa=empresa, jti="t", expira=START + timedelta(hours=1))


def test_schedule_arithmetic():
    assert first_run(6, START) == datetime(2026, 10, 4, 6)
    assert first_run(18, START) == datetime(2026, 10, 3, 18)
    assert add_month(datetime(2026, 1, 31, 6)) == datetime(2026, 2, 28, 6)
    assert add_month(datetime(2026, 12, 15)) == datetime(2027, 1, 15)
    assert next_after(datetime(2026, 9, 30, 6), "diaria", START) == datetime(2026, 10, 4, 6)
    assert next_after(datetime(2026, 10, 1, 6), "semanal", START) == datetime(2026, 10, 8, 6)


def test_catalog_validates_parameters():
    service, _, _ = make_service()
    ids = {r["id"] for r in service.catalog()["reportes"]}
    assert {"evaluaciones_reglas", "auditoria_seguridad", "despliegues", "analisis_codigo"} <= ids
    with pytest.raises(NotFoundError):
        service.generate(principal(), "sql_libre")
    with pytest.raises(InvalidInputError, match="no admitidos"):
        service.generate(principal(), "despliegues", {"consulta": "DROP TABLE"})
    with pytest.raises(InvalidInputError, match="entre 1 y 365"):
        service.generate(principal(), "despliegues", {"dias": 0})
    with pytest.raises(InvalidInputError, match="uno de"):
        service.generate(principal(), "despliegues", {"entorno": "qa"})


def test_reports_group_and_truncate():
    service, _, _ = make_service()
    by_rule = service.generate(principal(), "evaluaciones_reglas", {"agrupacion": "regla"})
    assert by_rule["filas"][0] == {"regla": "br_1", "evaluaciones": 2, "cumplidas": 2, "bloqueadas": 1,
                                   "tasa_cumplimiento": 100.0, "tiempo_promedio_ms": 3.0}
    assert by_rule["resumen"]["bloqueadas"] == 1
    security = service.generate(principal(), "auditoria_seguridad")
    assert security["filas"][0] == {"accion": "autenticar", "total": 7, "exitosas": 5, "fallidas": 2}
    assert security["resumen"]["tasa_fallo"] == 25.0
    deployments = service.generate(principal(), "despliegues", {"dias": 30})
    assert deployments["total_filas"] == 2 and not deployments["filas_truncadas"]
    assert deployments["resumen"]["reversiones"] == 1
    everything = service.generate(principal(), "despliegues", {"dias": 365})
    assert everything["total_filas"] == 3 and everything["filas_truncadas"] and len(everything["filas"]) == 2


def test_csv_export_neutralizes_formulas():
    service, _, _ = make_service()
    content, filename, media = service.export(principal(), "despliegues", {"dias": 30}, "csv")
    assert filename.startswith("insight_despliegues_") and filename.endswith(".csv") and media == "text/csv"
    assert content.startswith("\ufeff")
    rows = list(csv.DictReader(io.StringIO(content.lstrip("\ufeff"))))
    assert rows[0]["iniciado_por"].startswith("'=HYPERLINK")
    assert rows[1]["tag"] == "" and rows[0]["tag_publicado"] == "True"
    assert exporters.to_csv(["n"], [{"n": "-3.5"}, {"n": "-1+1"}]).splitlines()[1:] == ["-3.5", "'-1+1"]
    with pytest.raises(InvalidInputError):
        service.export(principal(), "despliegues", {}, "xlsx")


def test_saved_reports_are_scoped_by_company_and_purged():
    service, _, clock = make_service()
    saved = service.generate(principal(), "despliegues", guardar=True, nombre="Cierre semanal")
    report_id = saved["id_reporte"]
    assert service.list_saved("gio")["total"] == 1 and service.list_saved("otra")["total"] == 0
    assert service.get_saved(report_id, "gio")["resultado"]["tipo"] == "despliegues"
    with pytest.raises(NotFoundError):
        service.get_saved(report_id, "otra")
    content, filename, _ = service.export_saved(report_id, "gio", "json")
    assert '"tipo": "despliegues"' in content and filename.endswith(".json")
    with pytest.raises(InvalidInputError):
        service.generate(principal(), "despliegues", guardar=True, nombre="<script>")
    clock.now += timedelta(days=91)
    assert service.purge() == 1 and service.list_saved("gio")["total"] == 0


def test_due_schedules_run_once_and_stop_when_permission_is_revoked():
    service, security, clock = make_service()
    created = service.create_schedule(principal(), {"tipo": "despliegues", "nombre": "Diario", "hora_utc": 13,
                                                    "parametros": {"entorno": "staging"}})
    assert created["proxima_ejecucion"] == "2026-10-03T13:00:00"
    with pytest.raises(InvalidInputError):
        service.create_schedule(principal(), {"tipo": "despliegues", "nombre": "x", "frecuencia": "horaria"})
    assert service.run_due() == []
    clock.now = datetime(2026, 10, 3, 13, 5)
    results = service.run_due()
    assert [r["estado"] for r in results] == ["exito"]
    assert service.run_due() == []
    saved = service.list_saved("gio")["reportes"][0]
    assert saved["origen"] == "programado" and saved["id_programacion"] == created["id_programacion"]
    schedule = service.list_schedules("gio")["programaciones"][0]
    assert schedule["proxima_ejecucion"] == "2026-10-04T13:00:00" and schedule["ultimo_estado"] == "exito"

    security.allowed = False
    failed = service.run_schedule_now(created["id_programacion"], "gio")
    assert failed["estado"] == "error" and "reportes:programar" in failed["error"]
    assert service.list_schedules("gio")["programaciones"][0]["ultimo_error"] == failed["error"]

    paused = service.update_schedule(created["id_programacion"], "gio", {"activa": False})
    clock.now = datetime(2026, 10, 5, 0, 0)
    assert paused["activa"] is False and service.run_due() == []
    resumed = service.update_schedule(created["id_programacion"], "gio", {"activa": True, "frecuencia": "mensual"})
    assert resumed["proxima_ejecucion"] == "2026-10-05T13:00:00"
    with pytest.raises(NotFoundError):
        service.delete_schedule(created["id_programacion"], "otra")
    assert service.delete_schedule(created["id_programacion"], "gio")["eliminada"]


def test_kpis_degrade_per_section():
    service, _, _ = make_service()
    kpis = service.kpis(7)
    assert kpis["reglas"] == {"disponible": True, "reglas_activas": 2, "evaluaciones": 3, "bloqueos": 1, "activas_sin_uso": 1}
    assert kpis["despliegues"]["despliegues"] == 2 and kpis["despliegues"]["rechazados"] == 1
    assert kpis["despliegues"]["version_actual"] == {"staging": "release/staging/20260101-100000",
                                                     "produccion": "release/produccion/20261003-100000"}
    for section in ("api", "calidad", "codigo"):
        assert kpis[section] == {"disponible": False, "motivo": "RuntimeError"}


@pytest.fixture
def api():
    client, repo, security = build_api([insight_routes.router],
                                       [("reportes", "ver"), ("reportes", "generar"), ("reportes", "programar")])
    sources = default_sources()
    sources.rules, sources.orbit, sources.security = FakeRules, FakeOrbit, lambda: security
    set_insight_service(InsightService(InMemoryInsightRepository(), sources))
    yield client, repo
    set_insight_service(None)
    set_security_service(None)


def test_api_permissions_exports_and_audit(api):
    client, repo = api
    assert client.get("/api/v1/insight/salud").json()["estado"] == "activo"
    assert client.get("/api/v1/insight/catalogo").status_code == 401
    assert client.get("/api/v1/insight/catalogo", headers=headers(client, "luis")).status_code == 403
    auth = headers(client)
    assert client.get("/api/v1/insight/catalogo", headers=auth).json()["total"] == 9

    audit = client.post("/api/v1/insight/reportes/generar", json={"tipo": "auditoria_seguridad", "guardar": True,
                                                                  "nombre": "Auditoría"}, headers=auth)
    assert audit.status_code == 200 and audit.json()["resumen"]["eventos"] >= 1
    report_id = audit.json()["id_reporte"]
    exported = client.get(f"/api/v1/insight/reportes/{report_id}/exportar?formato=csv", headers=auth)
    assert exported.headers["content-type"].startswith("text/csv")
    assert "attachment" in exported.headers["content-disposition"]
    assert client.post("/api/v1/insight/reportes/generar", json={"tipo": "despliegues", "parametros": {"x": 1}},
                       headers=auth).status_code == 400

    schedule = client.post("/api/v1/insight/programaciones", json={"tipo": "despliegues", "nombre": "Semanal",
                                                                   "frecuencia": "semanal"}, headers=auth)
    assert schedule.status_code == 201
    schedule_id = schedule.json()["id_programacion"]
    assert client.post(f"/api/v1/insight/programaciones/{schedule_id}/ejecutar", headers=auth).json()["estado"] == "exito"
    assert client.delete(f"/api/v1/insight/reportes/{report_id}", headers=auth).json()["eliminado"]
    assert client.delete(f"/api/v1/insight/reportes/{report_id}", headers=auth).status_code == 404

    _, entries = repo.list_audit("gio", None, None, None, None, None, 50, 0)
    assert {"insight_reporte_guardar", "insight_programacion_crear", "insight_programacion_ejecutar",
            "insight_reporte_eliminar"} <= {e.accion for e in entries}
