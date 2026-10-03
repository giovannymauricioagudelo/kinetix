"""Prism (QAAgent): conflictos de reglas, ejecución de pytest, compuerta de calidad y API protegida."""

import json
from datetime import timedelta

import pytest

from src.agents.business_rules_agent.agent import build_rule
from src.agents.common import utcnow
from src.agents.qa_agent import conflicts
from src.agents.qa_agent.dependencies import set_prism_service
from src.agents.qa_agent.repository import InMemoryTestRunRepository, TestRun
from src.agents.qa_agent.runner import PytestRunner, RunOutcome, TestRunner, parse_coverage, parse_junit
from src.agents.qa_agent.service import PrismService, count_tests
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import ConflictError, InvalidInputError
from src.api.routes import prism_routes
from tests.unit.agent_api import build_api, headers, init_repo


def rule(rule_id, conditions=(), actions=(), scope="global", priority=50, **extra):
    return build_rule({"rule_id": rule_id, "name": rule_id, "scope": scope, "priority": priority, "status": "active",
                       "conditions": list(conditions), "actions": list(actions), **extra})


def cond(field, operator, value, logical="AND"):
    return {"field": field, "operator": operator, "value": value, "logical_operator": logical}


def set_field(field, value):
    return {"type": "set_field", "details": {"field": field, "value": value}}


def pairs(result):
    return {(c["regla_a"], c["regla_b"], c["tipo"]) for c in result["conflictos"]}


def test_contradictory_assignments_only_when_conditions_overlap():
    result = conflicts.find_conflicts([
        rule("alto", [cond("monto", "gt", 100)], [set_field("descuento", 10)]),
        rule("muy_alto", [cond("monto", "gte", 500)], [set_field("descuento", 20)], priority=60),
        rule("bajo", [cond("monto", "lt", 50)], [set_field("descuento", 5)]),
        rule("borde", [cond("monto", "lte", 100)], [set_field("descuento", 7)]),
    ])
    assert pairs(result) == {("alto", "muy_alto", "asignacion_contradictoria"), ("bajo", "borde", "asignacion_contradictoria")}
    first = next(c for c in result["conflictos"] if c["regla_a"] == "alto")
    assert "muy_alto" in first["resolucion"]


def test_block_versus_allow_respects_sets_and_scopes():
    block = {"type": "block", "details": {"reason": "no"}}
    allow = {"type": "allow", "details": {}}
    result = conflicts.find_conflicts([
        rule("bloquea_a", [cond("tipo", "eq", "A")], [block]),
        rule("permite_b", [cond("tipo", "eq", "B")], [allow]),
        rule("permite_ac", [cond("tipo", "in", "A,C")], [allow]),
        rule("emp1", [], [block], scope="empresa", empresa_id=1),
        rule("emp2", [], [allow], scope="empresa", empresa_id=2),
        rule("linea_x", [cond("tipo", "eq", "Z")], [allow], scope="linea_negocio", business_line="x"),
    ])
    found = {(a, b) for a, b, _ in pairs(result)}
    assert {("bloquea_a", "permite_ac"), ("emp1", "linea_x"), ("bloquea_a", "emp2"), ("permite_b", "emp1")} <= found
    assert ("bloquea_a", "permite_b") not in found and ("emp1", "emp2") not in found


def test_duplicates_calculations_or_conditions_and_inactive_rules():
    calc = {"type": "calculate", "details": {"total": "monto * 2"}}
    inactive = rule("inactiva", [], [set_field("x", 2)])
    inactive.status = type(inactive.status)("inactive")
    result = conflicts.find_conflicts([
        rule("dup1", [cond("a", "eq", 1)], [set_field("x", 1)]),
        rule("dup2", [cond("a", "eq", 1)], [set_field("x", 1)]),
        rule("calc1", [cond("b", "gt", 1)], [calc]),
        rule("calc2", [cond("b", "lt", 0), cond("c", "eq", 1, "OR")], [calc]),
        inactive,
    ])
    found = pairs(result)
    assert ("dup1", "dup2", "reglas_duplicadas") in found
    assert ("calc1", "calc2", "calculo_sobrescrito") in found
    assert not any("inactiva" in p for p in found)
    assert result["reglas_activas"] == 4


def test_count_tests_and_report_parsers(tmp_path):
    assert count_tests("def test_a(): pass\nclass TestX:\n    def test_b(self): pass\n    def helper(self): pass\n") == 2
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuites><testsuite><testcase classname="t" name="ok"/><testcase classname="t" name="falla">'
        '<failure message="assert 1 == 2">detalle</failure></testcase><testcase classname="t" name="skip"><skipped/>'
        '</testcase><testcase classname="t" name="err"><error message="boom"/></testcase></testsuite></testsuites>',
        encoding="utf-8")
    parsed = parse_junit(junit)
    assert (parsed["total"], parsed["pasadas"], parsed["fallidas"], parsed["omitidas"], parsed["errores"]) == (4, 1, 1, 1, 1)
    assert parsed["fallos"][0]["prueba"] == "t::falla"
    cov = tmp_path / "cov.json"
    cov.write_text(json.dumps({"totals": {"percent_covered": 75.5}, "files": {
        "src\\a.py": {"summary": {"percent_covered": 50.0, "num_statements": 10, "missing_lines": 5}},
        "src/b.py": {"summary": {"percent_covered": 100.0, "num_statements": 4, "missing_lines": 0}},
        "src/vacio.py": {"summary": {"percent_covered": 100.0, "num_statements": 0, "missing_lines": 0}},
    }}), encoding="utf-8")
    coverage = parse_coverage(cov)
    assert coverage["cobertura"] == 75.5 and [f["archivo"] for f in coverage["archivos"]] == ["src/a.py", "src/b.py"]


def test_pytest_runner_runs_a_real_suite(tmp_path):
    init_repo(tmp_path / "repo")
    outcome = PytestRunner(str(tmp_path / "repo"), timeout_seconds=120).run(["tests"], None, True)
    assert outcome.estado == "aprobada" and outcome.total == 2 and outcome.pasadas == 2
    assert outcome.cobertura is not None
    missing = PytestRunner(str(tmp_path / "repo"), timeout_seconds=120).run(["tests"], "no_existe_nada", False)
    assert missing.estado == "error" and missing.mensaje == "no se recolectó ninguna prueba"


class FakeRunner(TestRunner):
    def __init__(self, outcome=None):
        self.outcome = outcome or RunOutcome("aprobada", total=3, pasadas=3, cobertura=91.0, duracion_s=1.5)
        self.calls = []

    def run(self, targets, keyword, coverage):
        self.calls.append((targets, keyword, coverage))
        return self.outcome

    def lint(self, paths):
        return {"total": 0, "por_codigo": {}, "problemas": [], "truncado": False}


@pytest.fixture
def prism(tmp_path):
    git = init_repo(tmp_path / "repo")
    security = {"criticos": 0, "puntuacion": 9.5, "hallazgos_criticos": []}
    runner = FakeRunner()
    service = PrismService(runner, InMemoryTestRunRepository(), git, rules_source=lambda empresa: [],
                           security_gate=lambda: security, min_coverage=80, submit=lambda job: job())
    return service, runner, security, tmp_path / "repo"


def test_full_run_with_coverage_opens_the_gate(prism):
    service, runner, security, _ = prism
    assert service.quality_gate()["aprobada"] is False
    run = service.start_run("ana")
    assert run["suite_completa"] and runner.calls == [(["tests"], None, True)]
    detail = service.get_run(run["id_ejecucion"])
    assert detail["estado"] == "aprobada" and detail["cobertura"] == 91.0
    gate = service.quality_gate()
    assert gate["aprobada"] and gate["id_ejecucion"] == run["id_ejecucion"]
    security["criticos"] = 1
    assert {c["nombre"]: c["aprobado"] for c in service.quality_gate()["comprobaciones"]}["seguridad"] is False


def test_gate_rejects_low_coverage_dirty_tree_and_partial_runs(prism):
    service, runner, _, path = prism
    runner.outcome = RunOutcome("aprobada", total=3, pasadas=3, cobertura=40.0)
    service.start_run("ana")
    assert {c["nombre"]: c["aprobado"] for c in service.quality_gate()["comprobaciones"]}["cobertura"] is False
    runner.outcome = RunOutcome("aprobada", total=3, pasadas=3, cobertura=95.0)
    (path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    service.start_run("ana")
    assert {c["nombre"]: c["aprobado"] for c in service.quality_gate()["comprobaciones"]}["arbol_limpio"] is False
    partial = service.start_run("ana", ["tests/test_app.py::test_uno"])
    assert partial["suite_completa"] is False
    assert service.quality_gate()["id_ejecucion"] != partial["id_ejecucion"]


@pytest.mark.parametrize("targets, keyword", [
    (["../fuera"], None), (["src/app.py"], None), (["-p", "evil"], None), (["tests/x.py::a b"], None),
    (["tests"], "--collect-only"), (["tests"], "x; rm"),
])
def test_run_targets_and_filters_are_validated(prism, targets, keyword):
    with pytest.raises(InvalidInputError):
        prism[0].start_run("ana", targets, keyword)


def test_only_one_run_at_a_time_and_recovery(tmp_path):
    git = init_repo(tmp_path / "repo")
    repo = InMemoryTestRunRepository()
    pending = []
    service = PrismService(FakeRunner(), repo, git, submit=pending.append)
    first = service.start_run("ana")
    with pytest.raises(ConflictError):
        service.start_run("ana")
    assert service.list_runs()["en_curso"] == first["id_ejecucion"]
    pending.pop()()
    assert service.active_run is None and service.get_run(first["id_ejecucion"])["estado"] == "aprobada"

    repo.create(TestRun("pe_viejo", ["tests"], None, True, True, "ejecutando", "abc", True, "ana", utcnow() - timedelta(hours=1)))
    assert service.recover() == 1 and repo.get("pe_viejo").estado == "error"


def test_runner_crash_is_recorded_as_error(prism):
    service, runner, _, _ = prism
    runner.run = lambda *a: (_ for _ in ()).throw(OSError("sin python"))
    run = service.start_run("ana")
    detail = service.get_run(run["id_ejecucion"])
    assert detail["estado"] == "error" and "OSError" in detail["mensaje"]
    assert service.active_run is None


def test_metrics_and_discovery(prism):
    service, runner, _, _ = prism
    service.start_run("ana")
    runner.outcome = RunOutcome("fallida", total=3, pasadas=2, fallidas=1, cobertura=85.0,
                                fallos=[{"prueba": "t::x", "tipo": "failure", "mensaje": "boom"}])
    service.start_run("ana")
    metrics = service.metrics()
    assert metrics["ejecuciones"] == 2 and metrics["tasa_aprobacion"] == 50.0
    assert metrics["pruebas_mas_fallidas"] == [{"prueba": "t::x", "fallos": 1}]
    assert service.discover()["total_pruebas"] == 2


@pytest.fixture
def api(prism):
    client, repo, _ = build_api([prism_routes.router], [("calidad", "ver"), ("calidad", "ejecutar")])
    set_prism_service(prism[0])
    yield client, repo
    set_prism_service(None)
    set_security_service(None)


def test_api_permissions_runs_and_gate(api):
    client, repo = api
    assert client.get("/api/v1/prism/salud").json()["agente"] == "Prism"
    assert client.get("/api/v1/prism/compuerta").status_code == 401
    assert client.post("/api/v1/prism/ejecuciones", json={}, headers=headers(client, "luis")).status_code == 403
    auth = headers(client)
    started = client.post("/api/v1/prism/ejecuciones", json={}, headers=auth)
    assert started.status_code == 202
    run_id = started.json()["id_ejecucion"]
    assert client.get(f"/api/v1/prism/ejecuciones/{run_id}", headers=auth).json()["estado"] == "aprobada"
    assert client.get("/api/v1/prism/compuerta", headers=auth).json()["aprobada"] is True
    assert client.get("/api/v1/prism/ejecuciones/no-existe", headers=auth).status_code == 404
    assert client.get("/api/v1/prism/reglas/conflictos", headers=auth).json()["total"] == 0
    _, entries = repo.list_audit("gio", None, None, None, None, None, 50, 0)
    assert "prism_ejecucion" in {e.accion for e in entries}
