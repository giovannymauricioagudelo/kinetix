"""Utilidades de pruebas para los agentes protegidos por Sentinel: API en memoria y repositorios git temporales."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable, Tuple

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from src.agents.git_tools import GitRepository
from src.agents.security_agent import SecurityService
from src.agents.security_agent.config import SecuritySettings
from src.agents.security_agent.dependencies import set_security_service
from src.api.routes import sentinel_routes
from tests.unit.test_sentinel_agent import PASSWORDS, seeded_repository


def build_api(routers: Iterable[APIRouter], permissions: Iterable[Tuple[str, str]]):
    """ana (rol_admin) recibe los permisos indicados; luis no tiene ninguno."""
    repo = seeded_repository()
    for recurso, accion in permissions:
        perm_id = f"p_{recurso}_{accion}"
        repo.add_permission(perm_id, recurso, accion)
        repo.grant_permission("rol_admin", perm_id)
    security = SecurityService(repo, SecuritySettings(secret_key="agents-test-secret-" + "x" * 32))
    set_security_service(security)
    sentinel_routes._ip_limiter._hits.clear()
    app = FastAPI()
    app.include_router(sentinel_routes.router)
    for router in routers:
        app.include_router(router)
    return TestClient(app), repo, security


def headers(client: TestClient, user: str = "ana") -> dict:
    session = client.post("/api/v1/sentinel/autenticar",
                          json={"nombre_usuario": user, "contrasena": PASSWORDS[user], "id_empresa": "gio"}).json()
    return {"Authorization": f"Bearer {session['token_acceso']}"}


def git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout.strip()


def init_repo(path: Path) -> GitRepository:
    """Repositorio con un commit inicial en master y un remoto bare 'origin'."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "symbolic-ref", "HEAD", "refs/heads/master")
    git(path, "config", "user.name", "Kinetix Test")
    git(path, "config", "user.email", "test@kinetix.local")
    git(path, "config", "commit.gpgsign", "false")
    git(path, "config", "tag.gpgsign", "false")
    (path / "src").mkdir()
    (path / "tests").mkdir()
    (path / "src" / "app.py").write_text('def suma(a, b):\n    """Suma."""\n    return a + b\n', encoding="utf-8")
    (path / "tests" / "test_app.py").write_text("def test_uno():\n    assert True\n\n\nclass TestDos:\n    def test_dos(self):\n"
                                                "        assert True\n", encoding="utf-8")
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "inicial")
    remote = path.parent / f"{path.name}-origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True, capture_output=True)
    git(path, "remote", "add", "origin", str(remote))
    return GitRepository(str(path))


def commit_file(path: Path, relative: str, content: str, message: str) -> str:
    target = path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git(path, "add", relative)
    git(path, "commit", "-q", "-m", message)
    return git(path, "rev-parse", "HEAD")
