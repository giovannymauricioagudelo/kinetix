"""Orbit (GitDeploymentAgent): compuerta, tags anotados, promoción, reversión, GitHub Actions y API protegida."""

import json
from datetime import datetime, timedelta

import httpx
import pytest

from src.agents.git_deployment_agent.dependencies import set_orbit_service
from src.agents.git_deployment_agent.repository import InMemoryDeploymentRepository
from src.agents.git_deployment_agent.service import DeploymentRejected, OrbitService
from src.agents.github_client import GitHubClient, repository_from_remote
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import ConflictError, InvalidInputError
from src.api.routes import orbit_routes
from tests.unit.agent_api import build_api, commit_file, git, headers, init_repo


class StepClock:
    def __init__(self):
        self.now = datetime(2026, 10, 3, 12, 0, 0)

    def __call__(self):
        self.now += timedelta(seconds=1)
        return self.now


def gate(approved=True):
    def check(commit):
        return {"commit": commit, "aprobada": approved,
                "comprobaciones": [{"nombre": "cobertura", "aprobado": approved}]}
    return check


class FakeGitHub:
    def __init__(self):
        self.requests = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/dispatches"):
            return httpx.Response(204)
        if request.url.path.endswith("/actions/runs"):
            return httpx.Response(200, json={"workflow_runs": [{"id": 1, "name": "CI", "status": "completed",
                                                                "conclusion": "success", "head_sha": "a" * 40}]})
        if "/check-runs" in request.url.path:
            return httpx.Response(200, json={"check_runs": [{"name": "tests", "status": "completed", "conclusion": "success"}]})
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"state": "success", "statuses": [{"state": "success"}]})
        return httpx.Response(404, json={"message": "Not Found"})

    def client(self):
        return GitHubClient("token-de-prueba", "kinetix/studio", transport=httpx.MockTransport(self.handler))


@pytest.fixture
def orbit(tmp_path):
    path = tmp_path / "repo"
    repo = init_repo(path)
    github = FakeGitHub()
    service = OrbitService(repo, InMemoryDeploymentRepository(), gate(), github=github.client(), workflow="deploy.yml",
                           clock=StepClock())
    return service, path, github


def test_repository_from_remote():
    assert repository_from_remote("https://github.com/giovanny/kinetix.git") == "giovanny/kinetix"
    assert repository_from_remote("git@github.com:giovanny/kinetix.git") == "giovanny/kinetix"
    assert repository_from_remote("https://gitlab.com/x/y.git") is None


def test_deploy_creates_annotated_tag_and_promotion_requires_staging(orbit):
    service, path, _ = orbit
    head = git(path, "rev-parse", "HEAD")
    with pytest.raises(DeploymentRejected, match="staging"):
        service.deploy("ana", "produccion")
    staging = service.deploy("ana", "staging", notas="primera versión")
    assert staging["estado"] == "exitoso" and staging["commit"] == head
    assert staging["tag"].startswith("release/staging/2026")
    assert git(path, "cat-file", "-t", staging["tag"]) == "tag"
    assert git(path, "rev-parse", f"{staging['tag']}^{{commit}}") == head
    message = git(path, "tag", "-l", "--format=%(contents)", staging["tag"])
    assert "primera versión" in message and "por ana" in message
    production = service.deploy("ana", "produccion")
    assert production["estado"] == "exitoso" and production["tag"].startswith("release/produccion/")
    assert service.list_deployments(estado="rechazado")["total"] == 1
    assert service.releases("staging")["total"] == 1


def test_gate_and_release_branch_are_enforced(orbit, tmp_path):
    service, path, _ = orbit
    rejected = OrbitService(service._git, InMemoryDeploymentRepository(), gate(False), clock=StepClock())
    with pytest.raises(DeploymentRejected, match="compuerta de Prism no aprobada \\(cobertura\\)") as error:
        rejected.deploy("ana", "staging")
    assert error.value.deployment["estado"] == "rechazado"
    git(path, "checkout", "-q", "-b", "feature/x")
    commit_file(path, "src/otro.py", "y = 2\n", "fuera de master")
    with pytest.raises(DeploymentRejected, match="no está integrado en master"):
        service.deploy("ana", "staging", "feature/x")
    with pytest.raises(InvalidInputError):
        service.deploy("ana", "qa")


def test_publish_tag_and_dispatch_workflow(orbit):
    service, path, github = orbit
    with pytest.raises(InvalidInputError):
        service.deploy("ana", "staging", lanzar_workflow=True)
    result = service.deploy("ana", "staging", publicar_tag=True, lanzar_workflow=True)
    assert result["tag_publicado"] and result["workflow"]["disparado"]
    assert result["tag"] in git(path, "ls-remote", "--tags", "origin")
    dispatch = next(r for r in github.requests if r.url.path.endswith("/dispatches"))
    assert json.loads(dispatch.content)["ref"] == result["tag"]

    without_github = OrbitService(service._git, InMemoryDeploymentRepository(), gate(), clock=StepClock())
    with pytest.raises(ConflictError, match="GitHub Actions no está configurado"):
        without_github.deploy("ana", "staging", publicar_tag=True, lanzar_workflow=True)


def test_failed_push_marks_deployment_failed_and_removes_local_tag(orbit):
    service, path, _ = orbit
    git(path, "remote", "set-url", "origin", str(path.parent / "no-existe.git"))
    result = service.deploy("ana", "staging", publicar_tag=True)
    assert result["estado"] == "fallido" and result["tag"] is None
    assert git(path, "tag", "-l", "release/*") == ""
    assert any(step["paso"] == "limpieza" for step in result["bitacora"])


def test_rollback_retags_the_previous_successful_commit(orbit):
    service, path, _ = orbit
    with pytest.raises(ConflictError):
        service.rollback("ana", "staging", "no hay nada")
    first = service.deploy("ana", "staging")
    second_commit = commit_file(path, "src/app.py", "def suma(a, b):\n    return b + a\n", "cambio")
    second = service.deploy("ana", "staging")
    assert second["commit"] == second_commit
    with pytest.raises(InvalidInputError):
        service.rollback("ana", "staging", "x")
    reverted = service.rollback("ana", "staging", "regresión en pagos")
    assert reverted["tipo"] == "reversion" and reverted["commit"] == first["commit"]
    assert reverted["id_origen"] == first["id_despliegue"] and reverted["compuerta"]["omitida"]
    assert service.current("staging").commit_git == first["commit"]
    with pytest.raises(ConflictError, match="ya es el desplegado"):
        service.rollback("ana", "staging", "otra vez", first["id_despliegue"])


def test_verify_detects_missing_tags_and_reads_github_checks(orbit):
    service, path, _ = orbit
    deployed = service.deploy("ana", "staging")
    report = service.verify("staging")
    assert report["consistente"] and report["entornos"][0]["github"]["aprobado"]
    git(path, "tag", "-d", deployed["tag"])
    assert service.verify()["consistente"] is False
    assert service.workflow_runs()["ejecuciones"][0]["conclusion"] == "success"


@pytest.fixture
def api(orbit):
    client, repo, _ = build_api([orbit_routes.router], [("despliegues", "ver"), ("despliegues", "ejecutar")])
    set_orbit_service(orbit[0])
    yield client, repo
    set_orbit_service(None)
    set_security_service(None)


def test_api_permissions_rejections_and_audit(api):
    client, repo = api
    assert client.get("/api/v1/orbit/salud").json()["github"] == "configurado"
    assert client.get("/api/v1/orbit/despliegues").status_code == 401
    assert client.post("/api/v1/orbit/despliegues", json={"entorno": "staging"}, headers=headers(client, "luis")).status_code == 403
    auth = headers(client)
    rejected = client.post("/api/v1/orbit/despliegues", json={"entorno": "produccion"}, headers=auth)
    assert rejected.status_code == 409 and rejected.json()["detail"]["despliegue"]["estado"] == "rechazado"
    created = client.post("/api/v1/orbit/despliegues", json={"entorno": "staging"}, headers=auth)
    assert created.status_code == 201
    deployment_id = created.json()["id_despliegue"]
    assert client.get(f"/api/v1/orbit/despliegues/{deployment_id}", headers=auth).json()["estado"] == "exitoso"
    assert client.get("/api/v1/orbit/despliegues/verificacion", headers=auth).json()["consistente"] is True
    assert client.get("/api/v1/orbit/github/estado/HEAD", headers=auth).json()["aprobado"] is True
    _, entries = repo.list_audit("gio", None, None, None, None, None, 50, 0)
    assert {"orbit_despliegue", "orbit_despliegue_rechazado"} <= {e.accion for e in entries}
