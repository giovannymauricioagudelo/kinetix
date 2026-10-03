"""Utilidades compartidas por los agentes con persistencia: identificadores, fechas UTC, JSON y variables de entorno."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generic, Optional, TypeVar

TRUE_VALUES = ("1", "true", "si", "sí", "yes")
T = TypeVar("T")


class Lazy(Generic[T]):
    """Instancia compartida creada al primer uso; los tests la reemplazan con set()."""

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._value: Optional[T] = None
        self._lock = threading.Lock()

    def get(self) -> T:
        if self._value is None:
            with self._lock:
                if self._value is None:
                    self._value = self._factory()
        return self._value

    def set(self, value: Optional[T]) -> None:
        self._value = value


def repo_path() -> str:
    """Repositorio git sobre el que trabajan Vector, Prism y Orbit (KINETIX_REPO_PATH o la raíz del proyecto)."""
    return os.getenv("KINETIX_REPO_PATH") or str(Path(__file__).resolve().parents[2])


def sqlserver_client(timeout_variable: str, default_timeout: int = 30):
    from src.agents.security_agent.config import load_sqlserver_settings
    from src.agents.sqlserver import SqlServerClient

    return SqlServerClient(load_sqlserver_settings(), env_int(timeout_variable, default_timeout))


def utcnow() -> datetime:
    """UTC sin zona: es lo que guardan las columnas DATETIME2 de la base kinetix."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.isoformat() if moment else None


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads(raw: Optional[str], default: Any = None) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in TRUE_VALUES


def use_memory(variable: str) -> bool:
    return os.getenv(variable, "sqlserver").strip().lower() == "memory"
