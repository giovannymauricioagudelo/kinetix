"""
Orbit (GitDeploymentAgent) — releases como tags anotados tras la compuerta de Prism, promoción staging → producción,
reversión a un despliegue anterior y consulta/disparo de GitHub Actions. Todo requiere token de Sentinel salvo /salud.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.agents.agent_catalog import ORBIT, openapi_tag
from src.agents.git_deployment_agent.dependencies import get_orbit_service
from src.agents.git_deployment_agent.service import ENVIRONMENTS, PREVIOUS_STAGE, TAG_PREFIX, VERSION, DeploymentRejected, OrbitService
from src.agents.github_client import GitHubError, GitHubNotConfigured
from src.agents.security_agent.dependencies import get_security_service, require_permission, translate_errors
from src.agents.security_agent.models import Principal
from src.agents.security_agent.service import SecurityService
from src.api.routes._common import client_ip, health, ok

PERM_VIEW = "despliegues:ver"
PERM_DEPLOY = "despliegues:ejecutar"
UNAVAILABLE = "Servicio de despliegues no disponible temporalmente"
ENV_PATTERN = "^(staging|produccion)$"
STATE_PATTERN = "^(exitoso|fallido|rechazado)$"

router = APIRouter(prefix="/api/v1/orbit", tags=[openapi_tag(ORBIT)])
_can_view = require_permission(PERM_VIEW)
_can_deploy = require_permission(PERM_DEPLOY)


class DeployBody(BaseModel):
    entorno: str = Field(..., pattern=ENV_PATTERN)
    referencia: str = Field("HEAD", max_length=200, description="Commit, rama o tag a liberar")
    publicar_tag: bool = Field(False, description="Hace push del tag a origin")
    lanzar_workflow: bool = Field(False, description="Dispara ORBIT_GITHUB_WORKFLOW sobre el tag publicado")
    notas: Optional[str] = Field(None, max_length=500)


class RollbackBody(BaseModel):
    entorno: str = Field(..., pattern=ENV_PATTERN)
    motivo: str = Field(..., min_length=5, max_length=500)
    id_despliegue: Optional[str] = Field(None, max_length=50, description="Despliegue exitoso al que volver (por defecto el anterior)")
    publicar_tag: bool = False
    lanzar_workflow: bool = False


@contextmanager
def github_errors() -> Iterator[None]:
    try:
        yield
    except GitHubNotConfigured as e:
        raise HTTPException(503, str(e))
    except GitHubError as e:
        raise HTTPException(404 if e.status_code == 404 else 502, str(e))


@router.get("/salud")
def orbit_health(service: OrbitService = Depends(get_orbit_service)) -> Dict[str, Any]:
    return health(ORBIT.codename, service.ping, {"github": "configurado" if service.github_configured else "no configurado"})


@router.get("/info", dependencies=[Depends(_can_view)])
def orbit_info(service: OrbitService = Depends(get_orbit_service)) -> Dict[str, Any]:
    return {
        "id": "orbit",
        "agente": ORBIT.codename,
        "legacy_id": ORBIT.legacy_id,
        "version": VERSION,
        "descripcion": ORBIT.tagline,
        "entornos": list(ENVIRONMENTS),
        "promocion": {env: f"requiere despliegue exitoso previo en {prev}" for env, prev in PREVIOUS_STAGE.items()},
        "formato_tag": f"{TAG_PREFIX}/<entorno>/<AAAAMMDD-HHMMSS> (UTC)",
        "rama_release": service.release_branch,
        "github": {"configurado": service.github_configured, "workflow": service.workflow},
        "permisos": {"ver": PERM_VIEW, "ejecutar": PERM_DEPLOY},
    }


@router.get("/repositorio", dependencies=[Depends(_can_view)])
def repository(service: OrbitService = Depends(get_orbit_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.repository_info())


@router.get("/releases", dependencies=[Depends(_can_view)])
def releases(entorno: Optional[str] = Query(None, pattern=ENV_PATTERN), limite: int = Query(50, ge=1, le=500),
             service: OrbitService = Depends(get_orbit_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.releases(entorno, limite))


def _audited_release(action: str, run, principal: Principal, request: Request, security: SecurityService) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        try:
            result = run()
        except DeploymentRejected as e:
            d = e.deployment
            security.record_audit(principal, f"{action}_rechazado", f"despliegue:{d['id_despliegue']}",
                                  f"{d['entorno']} {d['commit']}: {e}", ip=client_ip(request))
            raise HTTPException(409, {"mensaje": str(e), "despliegue": d})
        security.record_audit(principal, action, f"despliegue:{result['id_despliegue']}",
                              f"{result['entorno']} {result['commit']} tag={result['tag']} estado={result['estado']}",
                              ip=client_ip(request))
        return ok(result)


@router.post("/despliegues", status_code=201)
def deploy(
    body: DeployBody,
    request: Request,
    principal: Principal = Depends(_can_deploy),
    service: OrbitService = Depends(get_orbit_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    return _audited_release(
        "orbit_despliegue",
        lambda: service.deploy(principal.nombre_usuario, body.entorno, body.referencia, body.publicar_tag,
                               body.lanzar_workflow, body.notas),
        principal, request, security,
    )


@router.post("/despliegues/reversion", status_code=201)
def rollback(
    body: RollbackBody,
    request: Request,
    principal: Principal = Depends(_can_deploy),
    service: OrbitService = Depends(get_orbit_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    return _audited_release(
        "orbit_reversion",
        lambda: service.rollback(principal.nombre_usuario, body.entorno, body.motivo, body.id_despliegue,
                                 body.publicar_tag, body.lanzar_workflow),
        principal, request, security,
    )


@router.get("/despliegues/verificacion", dependencies=[Depends(_can_view)])
def verify(entorno: Optional[str] = Query(None, pattern=ENV_PATTERN), service: OrbitService = Depends(get_orbit_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.verify(entorno))


@router.get("/despliegues", dependencies=[Depends(_can_view)])
def list_deployments(entorno: Optional[str] = Query(None, pattern=ENV_PATTERN), estado: Optional[str] = Query(None, pattern=STATE_PATTERN),
                     limite: int = Query(20, ge=1, le=200), service: OrbitService = Depends(get_orbit_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.list_deployments(entorno, estado, limite))


@router.get("/despliegues/{id_despliegue}", dependencies=[Depends(_can_view)])
def get_deployment(id_despliegue: str, service: OrbitService = Depends(get_orbit_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.get_deployment(id_despliegue))


@router.get("/github/workflows", dependencies=[Depends(_can_view)])
def workflow_runs(limite: int = Query(20, ge=1, le=100), rama: Optional[str] = Query(None, max_length=200),
                  workflow: Optional[str] = Query(None, max_length=100), service: OrbitService = Depends(get_orbit_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE), github_errors():
        return ok(service.workflow_runs(limite, rama, workflow))


@router.get("/github/estado/{referencia:path}", dependencies=[Depends(_can_view)])
def commit_status(referencia: str, service: OrbitService = Depends(get_orbit_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE), github_errors():
        return ok(service.commit_status(referencia))
