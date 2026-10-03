"""Instancia compartida de VectorService (VECTOR_REPOSITORY=memory para no guardar el historial en SQL Server)."""

from __future__ import annotations

import logging
from typing import Optional

from src.agents.common import Lazy, env_int, repo_path, sqlserver_client, use_memory
from src.agents.development_agent.repository import InMemoryAnalysisRepository
from src.agents.development_agent.service import VectorService
from src.agents.git_tools import GitRepository

logger = logging.getLogger(__name__)


def build_default_service() -> VectorService:
    git = GitRepository(repo_path(), timeout_seconds=env_int("KINETIX_GIT_TIMEOUT_SECONDS", 60))
    if use_memory("VECTOR_REPOSITORY"):
        logger.warning("Vector guarda el historial de análisis en memoria.")
        return VectorService(git, InMemoryAnalysisRepository())
    from src.agents.development_agent.repository import SqlServerAnalysisRepository

    return VectorService(git, SqlServerAnalysisRepository(sqlserver_client("VECTOR_QUERY_TIMEOUT_SECONDS")))


_service: Lazy[VectorService] = Lazy(build_default_service)


def get_vector_service() -> VectorService:
    return _service.get()


def set_vector_service(service: Optional[VectorService]) -> None:
    _service.set(service)
