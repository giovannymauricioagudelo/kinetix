"""
Sentinel (SecurityAgent) — autenticación JWT + MFA TOTP, sesiones, RBAC y auditoría.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Deque, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.agents.agent_catalog import SENTINEL, openapi_tag
from src.agents.security_agent.dependencies import (
    get_security_service,
    require_user,
    translate_errors,
)
from src.agents.security_agent.models import Principal
from src.agents.security_agent.service import SecurityService

router = APIRouter(prefix="/api/v1/sentinel", tags=[openapi_tag(SENTINEL)])


class _IpRateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                retry_after = max(1, int(60 - (now - hits[0])))
                raise HTTPException(429, "Demasiadas solicitudes desde esta dirección.", headers={"Retry-After": str(retry_after)})
            hits.append(now)


_ip_limiter = _IpRateLimiter(int(os.getenv("SENTINEL_IP_LIMIT_PER_MINUTE", "30")))


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def public_rate_limit(request: Request) -> None:
    _ip_limiter.check(_client_ip(request) or "desconocida")


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"estado": "exito", **payload}


# ============================================================================ cuerpos


class LoginBody(BaseModel):
    nombre_usuario: str = Field(..., min_length=1, max_length=255)
    contrasena: str = Field(..., min_length=1, max_length=512)
    id_empresa: str = Field(..., min_length=1, max_length=50)


class MfaLoginBody(BaseModel):
    ficha_mfa: str = Field(..., min_length=1)
    codigo_mfa: str = Field(..., min_length=6, max_length=6)


class RefreshBody(BaseModel):
    token_refresco: str = Field(..., min_length=1)


class LogoutBody(BaseModel):
    token_refresco: Optional[str] = None
    todas_las_sesiones: bool = False


class MfaCodeBody(BaseModel):
    codigo: str = Field(..., min_length=6, max_length=6)


class DisableMfaBody(BaseModel):
    contrasena: str = Field(..., min_length=1, max_length=512)
    codigo_mfa: str = Field(..., min_length=6, max_length=6)


class AuthorizeBody(BaseModel):
    permiso: str = Field(..., min_length=3, description="Formato recurso:accion, p. ej. pedidos_venta:crear")


class AssignRoleBody(BaseModel):
    id_usuario: str = Field(..., min_length=1, max_length=50)
    id_rol: str = Field(..., min_length=1, max_length=50)


class GrantPermissionBody(BaseModel):
    id_rol: str = Field(..., min_length=1, max_length=50)
    id_permiso: str = Field(..., min_length=1, max_length=50)


# ============================================================================ salud e información


@router.get("/salud")
def sentinel_health(service: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors():
        service.ping()
    return {"estado": "ok", "agente": SENTINEL.codename, "timestamp": datetime.utcnow().isoformat()}


@router.get("/info")
def sentinel_info(
    _: Principal = Depends(require_user),
    service: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    settings = service.settings
    return {
        "id": "sentinel",
        "codename": SENTINEL.codename,
        "legacy_id": SENTINEL.legacy_id,
        "descripcion": SENTINEL.tagline,
        "version": service.version,
        "endpoints": SENTINEL.default_endpoints,
        "politicas": {
            "token_acceso_minutos": settings.access_minutes,
            "token_refresco_dias": settings.refresh_days,
            "intentos_antes_de_bloqueo": settings.max_failed_attempts,
            "bloqueo_minutos": settings.lockout_window_minutes,
            "mfa": "TOTP (RFC 6238), un solo uso por código",
        },
    }


# ============================================================================ autenticación y sesiones


@router.post("/autenticar", dependencies=[Depends(public_rate_limit)])
def authenticate(body: LoginBody, request: Request, service: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors():
        return _ok(service.authenticate(body.nombre_usuario, body.contrasena, body.id_empresa, _client_ip(request)))


@router.post("/autenticar-mfa", dependencies=[Depends(public_rate_limit)])
def authenticate_mfa(body: MfaLoginBody, request: Request, service: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors():
        return _ok(service.verify_mfa(body.ficha_mfa, body.codigo_mfa, _client_ip(request)))


@router.post("/refrescar", dependencies=[Depends(public_rate_limit)])
def refresh(body: RefreshBody, request: Request, service: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors():
        return _ok(service.refresh(body.token_refresco, _client_ip(request)))


@router.post("/cerrar-sesion")
def logout(
    request: Request,
    body: Optional[LogoutBody] = None,
    principal: Principal = Depends(require_user),
    service: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    body = body or LogoutBody()
    with translate_errors():
        return _ok(service.logout(principal, body.token_refresco, body.todas_las_sesiones, _client_ip(request)))


@router.get("/estado-limite")
def rate_limit_status(principal: Principal = Depends(require_user), service: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors():
        return _ok(service.rate_limit_status(principal))


# ============================================================================ MFA


@router.post("/configurar-mfa")
def setup_mfa(principal: Principal = Depends(require_user), service: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors():
        return _ok(service.setup_mfa(principal))


@router.post("/confirmar-mfa")
def confirm_mfa(body: MfaCodeBody, principal: Principal = Depends(require_user), service: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors():
        return _ok(service.confirm_mfa(principal, body.codigo))


@router.post("/deshabilitar-mfa")
def disable_mfa(
    body: DisableMfaBody,
    request: Request,
    principal: Principal = Depends(require_user),
    service: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors():
        return _ok(service.disable_mfa(principal, body.contrasena, body.codigo_mfa, _client_ip(request)))


# ============================================================================ autorización (RBAC)


@router.get("/permisos")
def my_permissions(principal: Principal = Depends(require_user), service: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors():
        return _ok(service.permissions(principal))


@router.post("/autorizar")
def authorize(
    body: AuthorizeBody,
    request: Request,
    principal: Principal = Depends(require_user),
    service: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors():
        allowed = service.authorize(principal, body.permiso, _client_ip(request))
    return _ok({"permiso": body.permiso, "permitido": allowed})


@router.post("/roles/asignar")
def assign_role(body: AssignRoleBody, principal: Principal = Depends(require_user), service: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors():
        return _ok(service.assign_role(principal, body.id_usuario, body.id_rol))


@router.post("/permisos/otorgar")
def grant_permission(body: GrantPermissionBody, principal: Principal = Depends(require_user), service: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors():
        return _ok(service.grant_permission(principal, body.id_rol, body.id_permiso))


# ============================================================================ cumplimiento


@router.get("/auditoria")
def audit_log(
    desde: Optional[datetime] = Query(None),
    hasta: Optional[datetime] = Query(None),
    accion: Optional[str] = Query(None, max_length=100),
    id_usuario: Optional[str] = Query(None, max_length=50),
    resultado: Optional[str] = Query(None, max_length=50),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_user),
    service: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors():
        return _ok(service.audit_log(principal, desde, hasta, accion, id_usuario, resultado, limit, offset))


@router.get("/reporte-cumplimiento")
def compliance_report(
    dias: int = Query(30, ge=1, le=365),
    principal: Principal = Depends(require_user),
    service: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors():
        return _ok(service.compliance_report(principal, dias))
