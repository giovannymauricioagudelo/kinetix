"""Instancia compartida de OrbitService (ORBIT_REPOSITORY=memory para no guardar los despliegues en SQL Server)."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from src.agents.common import Lazy, env_int, repo_path, sqlserver_client, use_memory
from src.agents.git_deployment_agent.repository import DeploymentRepository, InMemoryDeploymentRepository
from src.agents.git_deployment_agent.service import OrbitService
from src.agents.git_tools import GitRepository
from src.agents.github_client import github_from_env

logger = logging.getLogger(__name__)


def _prism_gate(commit: str) -> Dict[str, Any]:
    from src.agents.qa_agent.dependencies import get_prism_service

    return get_prism_service().quality_gate(commit)


def build_default_service() -> OrbitService:
    git = GitRepository(repo_path(), timeout_seconds=env_int("KINETIX_GIT_TIMEOUT_SECONDS", 60))
    repository: DeploymentRepository
    if use_memory("ORBIT_REPOSITORY"):
        logger.warning("Orbit guarda el historial de despliegues en memoria.")
        repository = InMemoryDeploymentRepository()
    else:
        from src.agents.git_deployment_agent.repository import SqlServerDeploymentRepository

        repository = SqlServerDeploymentRepository(sqlserver_client("ORBIT_QUERY_TIMEOUT_SECONDS"))
    try:
        remote = git.remote_url("origin")
    except Exception:
        remote = None
    return OrbitService(
        git, repository, _prism_gate, github=github_from_env(remote),
        workflow=os.getenv("ORBIT_GITHUB_WORKFLOW"), release_branch=os.getenv("ORBIT_RELEASE_BRANCH", "master"),
    )


_service: Lazy[OrbitService] = Lazy(build_default_service)


def get_orbit_service() -> OrbitService:
    return _service.get()


def set_orbit_service(service: Optional[OrbitService]) -> None:
    _service.set(service)
