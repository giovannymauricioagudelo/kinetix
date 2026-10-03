"""Integración FastAPI de Sentinel: instancia compartida, dependencias de autenticación y mapeo de errores."""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Callable, Iterator, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.agents.security_agent.config import load_security_settings, load_sqlserver_settings
from src.agents.security_agent.models import (
    AuthenticationError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    Principal,
    RateLimitedError,
)
from src.agents.security_agent.repository import InMemorySecurityRepository
from src.agents.security_agent.service import SecurityService

logger = logging.getLogger(__name__)

_service: Optional[SecurityService] = None
_service_lock = threading.Lock()
_bearer = HTTPBearer(auto_error=False)


def build_default_service() -> SecurityService:
    backend = os.getenv("SENTINEL_REPOSITORY", "sqlserver").strip().lower()
    if backend == "memory":
        logger.warning("Sentinel usa repositorio en memoria: los datos se pierden al reiniciar.")
        repository = InMemorySecurityRepository()
    else:
        from src.agents.security_agent.sqlserver_repository import SqlServerSecurityRepository

        repository = SqlServerSecurityRepository(load_sqlserver_settings())
    return SecurityService(repository, load_security_settings())


def get_security_service() -> SecurityService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = build_default_service()
    return _service


def set_security_service(service: Optional[SecurityService]) -> None:
    global _service
    _service = service


@contextmanager
def translate_errors(unavailable: str = "Servicio de seguridad no disponible temporalmente") -> Iterator[None]:
    try:
        yield
    except HTTPException:
        raise
    except RateLimitedError as e:
        raise HTTPException(429, str(e), headers={"Retry-After": str(e.retry_after_seconds)})
    except AuthenticationError as e:
        raise HTTPException(401, str(e), headers={"WWW-Authenticate": "Bearer"})
    except PermissionDeniedError as e:
        raise HTTPException(403, str(e))
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ConflictError as e:
        raise HTTPException(409, str(e))
    except InvalidInputError as e:
        raise HTTPException(400, str(e))
    except Exception:
        logger.exception("Error interno: %s", unavailable)
        raise HTTPException(503, unavailable)


def require_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    service: SecurityService = Depends(get_security_service),
) -> Principal:
    if credentials is None:
        raise HTTPException(401, "Se requiere autenticación", headers={"WWW-Authenticate": "Bearer"})
    with translate_errors():
        return service.validate_access_token(credentials.credentials)


def require_permission(permiso: str) -> Callable[..., Principal]:
    def dependency(
        principal: Principal = Depends(require_user),
        service: SecurityService = Depends(get_security_service),
    ) -> Principal:
        with translate_errors():
            service.require(principal, permiso)
        return principal

    return dependency
