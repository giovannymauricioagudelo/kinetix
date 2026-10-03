"""Instancia compartida de NexusService para la API (NEXUS_CATALOG=memory para desarrollo sin SQL Server)."""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from src.agents.database_agent.catalog import InMemoryCatalog
from src.agents.database_agent.service import NexusService

logger = logging.getLogger(__name__)

_service: Optional[NexusService] = None
_lock = threading.Lock()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def build_default_service() -> NexusService:
    backup_dir = os.getenv("NEXUS_BACKUP_DIR") or None
    max_rows = _int_env("NEXUS_MAX_ROWS", 1000)
    if os.getenv("NEXUS_CATALOG", "sqlserver").strip().lower() == "memory":
        logger.warning("Nexus usa un catálogo en memoria: no hay conexión a SQL Server.")
        return NexusService(InMemoryCatalog(), backup_dir, max_rows)
    from src.agents.database_agent.catalog import SqlServerCatalog
    from src.agents.security_agent.config import load_sqlserver_settings
    from src.agents.sqlserver import SqlServerClient

    client = SqlServerClient(load_sqlserver_settings(), _int_env("NEXUS_QUERY_TIMEOUT_SECONDS", 30))
    catalog = SqlServerCatalog(client, _int_env("NEXUS_BACKUP_TIMEOUT_SECONDS", 600))
    return NexusService(catalog, backup_dir, max_rows)


def get_nexus_service() -> NexusService:
    global _service
    if _service is None:
        with _lock:
            if _service is None:
                _service = build_default_service()
    return _service


def set_nexus_service(service: Optional[NexusService]) -> None:
    global _service
    _service = service
