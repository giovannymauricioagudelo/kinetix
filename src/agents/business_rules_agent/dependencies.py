"""Instancia compartida de RulesService para la API (MATRIX_REPOSITORY=memory para desarrollo sin SQL Server)."""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from src.agents.business_rules_agent.repository import InMemoryRulesRepository
from src.agents.business_rules_agent.service import RulesService

logger = logging.getLogger(__name__)

_service: Optional[RulesService] = None
_lock = threading.Lock()


def build_default_service() -> RulesService:
    if os.getenv("MATRIX_REPOSITORY", "sqlserver").strip().lower() == "memory":
        logger.warning("Matrix usa repositorio en memoria: las reglas se pierden al reiniciar.")
        return RulesService(InMemoryRulesRepository())
    from src.agents.business_rules_agent.repository import SqlServerRulesRepository
    from src.agents.security_agent.config import load_sqlserver_settings
    from src.agents.sqlserver import SqlServerClient

    return RulesService(SqlServerRulesRepository(SqlServerClient(load_sqlserver_settings())))


def get_rules_service() -> RulesService:
    global _service
    if _service is None:
        with _lock:
            if _service is None:
                _service = build_default_service()
    return _service


def set_rules_service(service: Optional[RulesService]) -> None:
    global _service
    _service = service
