"""
Prism (QAAgent) — ejecuta la suite real de pytest con cobertura, lint con flake8, detecta conflictos entre reglas
de Matrix y expone la compuerta de calidad que Orbit exige antes de liberar. Todo requiere token de Sentinel salvo /salud.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from src.agents.agent_catalog import PRISM, openapi_tag
from src.agents.qa_agent.dependencies import get_prism_service
from src.agents.qa_agent.service import DEFAULT_TARGETS, LINT_ROOTS, TEST_ROOTS, VERSION, PrismService
from src.agents.security_agent.dependencies import get_security_service, require_permission, translate_errors
from src.agents.security_agent.models import Principal
from src.agents.security_agent.service import SecurityService
from src.api.routes._common import client_ip, health, ok

PERM_VIEW = "calidad:ver"
PERM_RUN = "calidad:ejecutar"
UNAVAILABLE = "Servicio de calidad no disponible temporalmente"
RUN_STATES = "^(en_cola|ejecutando|aprobada|fallida|error)$"

router = APIRouter(prefix="/api/v1/prism", tags=[openapi_tag(PRISM)])
_can_view = require_permission(PERM_VIEW)
_can_run = require_permission(PERM_RUN)


class RunBody(BaseModel):
    objetivos: List[str] = Field(default_factory=lambda: list(DEFAULT_TARGETS), max_length=20,
                                 description="Rutas bajo tests/ o identificadores ruta::prueba")
    filtro: Optional[str] = Field(None, max_length=200, description="Expresión -k de pytest")
    con_cobertura: bool = True


class LintBody(BaseModel):
    rutas: List[str] = Field(default_factory=lambda: ["src"], max_length=50)


@router.get("/salud")
def prism_health(service: PrismService = Depends(get_prism_service)) -> Dict[str, Any]:
    return health(PRISM.codename, service.ping, {"ejecucion_en_curso": service.active_run})


@router.get("/info", dependencies=[Depends(_can_view)])
def prism_info(service: PrismService = Depends(get_prism_service)) -> Dict[str, Any]:
    return {
        "id": "prism",
        "agente": PRISM.codename,
        "legacy_id": PRISM.legacy_id,
        "version": VERSION,
        "descripcion": PRISM.tagline,
        "herramientas": ["pytest", "pytest-cov", "flake8"],
        "rutas_pruebas": list(TEST_ROOTS),
        "rutas_lint": list(LINT_ROOTS),
        "cobertura_minima": service.min_coverage,
        "compuerta": ["pruebas", "cobertura", "arbol_limpio", "seguridad"],
        "permisos": {"ver": PERM_VIEW, "ejecutar": PERM_RUN},
    }


@router.get("/pruebas", dependencies=[Depends(_can_view)])
def discover_tests(service: PrismService = Depends(get_prism_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.discover())


@router.post("/ejecuciones", status_code=202)
def start_run(
    body: RunBody,
    request: Request,
    principal: Principal = Depends(_can_run),
    service: PrismService = Depends(get_prism_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        run = service.start_run(principal.nombre_usuario, body.objetivos, body.filtro, body.con_cobertura)
        security.record_audit(principal, "prism_ejecucion", f"ejecucion:{run['id_ejecucion']}",
                              f"{', '.join(run['objetivos'])} en {run['commit']}", ip=client_ip(request))
        return ok(run)


@router.get("/ejecuciones", dependencies=[Depends(_can_view)])
def list_runs(limite: int = Query(20, ge=1, le=200), estado: Optional[str] = Query(None, pattern=RUN_STATES),
              service: PrismService = Depends(get_prism_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.list_runs(limite, estado))


@router.get("/ejecuciones/{id_ejecucion}", dependencies=[Depends(_can_view)])
def get_run(id_ejecucion: str, service: PrismService = Depends(get_prism_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.get_run(id_ejecucion))


@router.post("/analisis-estatico", dependencies=[Depends(_can_view)])
def lint(body: LintBody, service: PrismService = Depends(get_prism_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.lint(body.rutas))


@router.get("/reglas/conflictos", dependencies=[Depends(_can_view)])
def rule_conflicts(id_empresa: Optional[int] = Query(None, description="Solo reglas globales, de línea y de esta empresa"),
                   service: PrismService = Depends(get_prism_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.rule_conflicts(id_empresa))


@router.get("/compuerta", dependencies=[Depends(_can_view)])
def quality_gate(referencia: str = Query("HEAD", max_length=200), service: PrismService = Depends(get_prism_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.quality_gate(referencia))


@router.get("/metricas", dependencies=[Depends(_can_view)])
def metrics(dias: int = Query(30, ge=1, le=365), service: PrismService = Depends(get_prism_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.metrics(dias))
