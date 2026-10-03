"""Instancia compartida de AuroraService (AURORA_REPOSITORY=memory para desarrollo sin SQL Server)."""

from __future__ import annotations

import logging
from typing import Optional

from src.agents.common import Lazy, sqlserver_client, use_memory
from src.agents.interface_design_agent.repository import InMemoryDesignRepository
from src.agents.interface_design_agent.service import AuroraService

logger = logging.getLogger(__name__)


def build_default_service() -> AuroraService:
    if use_memory("AURORA_REPOSITORY"):
        logger.warning("Aurora usa un repositorio en memoria: los sistemas de diseño se pierden al reiniciar.")
        return AuroraService(InMemoryDesignRepository())
    from src.agents.interface_design_agent.repository import SqlServerDesignRepository

    return AuroraService(SqlServerDesignRepository(sqlserver_client("AURORA_QUERY_TIMEOUT_SECONDS")))


_service: Lazy[AuroraService] = Lazy(build_default_service)


def get_aurora_service() -> AuroraService:
    return _service.get()


def set_aurora_service(service: Optional[AuroraService]) -> None:
    _service.set(service)
