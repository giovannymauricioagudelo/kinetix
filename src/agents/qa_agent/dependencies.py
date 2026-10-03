"""Instancia compartida de PrismService (PRISM_REPOSITORY=memory para no guardar las ejecuciones en SQL Server)."""

from __future__ import annotations

import logging
from typing import Optional

from src.agents.common import Lazy, env_float, env_int, repo_path, sqlserver_client, use_memory
from src.agents.git_tools import GitRepository
from src.agents.qa_agent.repository import InMemoryTestRunRepository, TestRunRepository
from src.agents.qa_agent.runner import PytestRunner
from src.agents.qa_agent.service import PrismService

logger = logging.getLogger(__name__)


def _active_rules(id_empresa: Optional[int]):
    from src.agents.business_rules_agent.dependencies import get_rules_service

    return get_rules_service().active_rules(id_empresa)


def _security_gate():
    from src.agents.development_agent.dependencies import get_vector_service

    return get_vector_service().security_gate()


def build_default_service() -> PrismService:
    root = repo_path()
    repository: TestRunRepository
    if use_memory("PRISM_REPOSITORY"):
        logger.warning("Prism guarda las ejecuciones en memoria.")
        repository = InMemoryTestRunRepository()
    else:
        from src.agents.qa_agent.repository import SqlServerTestRunRepository

        repository = SqlServerTestRunRepository(sqlserver_client("PRISM_QUERY_TIMEOUT_SECONDS"))
    service = PrismService(
        PytestRunner(root, timeout_seconds=env_int("PRISM_TIMEOUT_SECONDS", 900)),
        repository,
        GitRepository(root, timeout_seconds=env_int("KINETIX_GIT_TIMEOUT_SECONDS", 60)),
        rules_source=_active_rules,
        security_gate=_security_gate,
        min_coverage=env_float("PRISM_COBERTURA_MINIMA", 80.0),
    )
    try:
        service.recover()
    except Exception as e:
        logger.warning("Prism no pudo revisar ejecuciones interrumpidas: %s", type(e).__name__)
    return service


_service: Lazy[PrismService] = Lazy(build_default_service)


def get_prism_service() -> PrismService:
    return _service.get()


def set_prism_service(service: Optional[PrismService]) -> None:
    _service.set(service)
