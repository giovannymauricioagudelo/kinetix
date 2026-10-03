"""Instancia compartida de InsightService y su planificador (INSIGHT_REPOSITORY=memory para no usar SQL Server)."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from src.agents.common import Lazy, env_int, sqlserver_client, use_memory, utcnow
from src.agents.reporting_agent.reports import Sources
from src.agents.reporting_agent.repository import InMemoryInsightRepository, InsightRepository
from src.agents.reporting_agent.service import InsightService

logger = logging.getLogger(__name__)


def _rules():
    from src.agents.business_rules_agent.dependencies import get_rules_service

    return get_rules_service()


def _security():
    from src.agents.security_agent.dependencies import get_security_service

    return get_security_service()


def _monitoring():
    from src.agents.monitoring_agent.service import get_monitoring_service

    return get_monitoring_service()


def _prism():
    from src.agents.qa_agent.dependencies import get_prism_service

    return get_prism_service()


def _orbit():
    from src.agents.git_deployment_agent.dependencies import get_orbit_service

    return get_orbit_service()


def _vector():
    from src.agents.development_agent.dependencies import get_vector_service

    return get_vector_service()


def default_sources() -> Sources:
    return Sources(rules=_rules, security=_security, monitoring=_monitoring, prism=_prism, orbit=_orbit, vector=_vector, now=utcnow)


def build_default_service() -> InsightService:
    repository: InsightRepository
    if use_memory("INSIGHT_REPOSITORY"):
        logger.warning("Insight guarda reportes y programaciones en memoria.")
        repository = InMemoryInsightRepository()
    else:
        from src.agents.reporting_agent.repository import SqlServerInsightRepository

        repository = SqlServerInsightRepository(sqlserver_client("INSIGHT_QUERY_TIMEOUT_SECONDS"))
    return InsightService(repository, default_sources(), max_rows=env_int("INSIGHT_MAX_FILAS", 5000),
                          retention_days=env_int("INSIGHT_RETENCION_DIAS", 90))


_service: Lazy[InsightService] = Lazy(build_default_service)


def get_insight_service() -> InsightService:
    return _service.get()


def set_insight_service(service: Optional[InsightService]) -> None:
    _service.set(service)


async def _scheduler_loop(interval: int) -> None:
    cycles = 0
    while True:
        await asyncio.sleep(interval)
        try:
            service = get_insight_service()
            await run_in_threadpool(service.run_due)
            cycles += 1
            if cycles % max(1, 3600 // interval) == 0:
                await run_in_threadpool(service.purge)
        except Exception as e:
            logger.warning("Insight: ciclo del planificador falló (%s)", type(e).__name__)


def install_insight_scheduler(app: FastAPI) -> None:
    """Ejecuta las programaciones vencidas cada INSIGHT_SCHEDULER_INTERVAL_SECONDS (0 = apagado)."""
    interval = env_int("INSIGHT_SCHEDULER_INTERVAL_SECONDS", 60)
    if interval <= 0:
        return

    @app.on_event("startup")
    async def _start_insight() -> None:
        app.state.insight_task = asyncio.create_task(_scheduler_loop(interval))

    @app.on_event("shutdown")
    async def _stop_insight() -> None:
        task = getattr(app.state, "insight_task", None)
        if task:
            task.cancel()
