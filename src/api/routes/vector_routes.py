"""
Vector (DevelopmentAgent) — análisis estático del repositorio, plantillas de módulos y escritura en git
(ramas de trabajo y commits sin checkout; master/main protegidas). Todo requiere un token de Sentinel salvo /salud.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from src.agents.agent_catalog import VECTOR, openapi_tag
from src.agents.development_agent import analyzer, scaffold
from src.agents.development_agent.dependencies import get_vector_service
from src.agents.development_agent.service import ANALYSIS_ROOTS, VERSION, WRITE_ROOTS, VectorService
from src.agents.git_tools import PROTECTED_BRANCHES
from src.agents.security_agent.dependencies import get_security_service, require_permission, translate_errors
from src.agents.security_agent.models import Principal
from src.agents.security_agent.service import SecurityService
from src.api.routes._common import client_ip, health, ok

PERM_VIEW = "codigo:ver"
PERM_WRITE = "codigo:escribir"
UNAVAILABLE = "Servicio de desarrollo no disponible temporalmente"

router = APIRouter(prefix="/api/v1/vector", tags=[openapi_tag(VECTOR)])
_can_view = require_permission(PERM_VIEW)
_can_write = require_permission(PERM_WRITE)


class AnalyzeBody(BaseModel):
    rutas: List[str] = Field(default_factory=lambda: ["src"], max_length=50)
    solo_versionados: bool = True


class SnippetBody(BaseModel):
    codigo: str = Field(..., min_length=1)
    nombre: str = Field("fragmento.py", max_length=100)


class BranchBody(BaseModel):
    nombre: str = Field(..., max_length=100, description="feature/, fix/, chore/ o vector/ + nombre")
    base: str = Field("HEAD", max_length=200)


class FieldBody(BaseModel):
    nombre: str = Field(..., max_length=41)
    tipo: str = Field("str", description="str, int, float o bool")
    requerido: bool = True


class ScaffoldBody(BaseModel):
    modulo: str = Field(..., max_length=41, description="snake_case, p. ej. inventario")
    entidad: Optional[str] = Field(None, max_length=41, description="CamelCase, p. ej. Producto")
    campos: List[FieldBody] = Field(..., min_length=1, max_length=30)

    def spec(self) -> Dict[str, Any]:
        return {"modulo": self.modulo, "entidad": self.entidad, "campos": [c.model_dump() for c in self.campos]}


class ApplyScaffoldBody(ScaffoldBody):
    rama: str = Field(..., max_length=100)
    base: str = Field("HEAD", max_length=200)
    mensaje: Optional[str] = Field(None, max_length=500)
    sobrescribir: bool = False


class CommitBody(BaseModel):
    rama: str = Field(..., max_length=100)
    base: str = Field("HEAD", max_length=200)
    mensaje: str = Field(..., min_length=3, max_length=500)
    archivos: Dict[str, str] = Field(..., description="ruta relativa → contenido completo")


@router.get("/salud")
def vector_health(service: VectorService = Depends(get_vector_service)) -> Dict[str, Any]:
    try:
        git = service.git_status()
    except Exception:
        git = None
    return health(VECTOR.codename, service.ping, {"git": "disponible" if git else "no disponible", **(git or {})})


@router.get("/info", dependencies=[Depends(_can_view)])
def vector_info(service: VectorService = Depends(get_vector_service)) -> Dict[str, Any]:
    return {
        "id": "vector",
        "agente": VECTOR.codename,
        "legacy_id": VECTOR.legacy_id,
        "version": VERSION,
        "descripcion": VECTOR.tagline,
        "repositorio": service.repo_path,
        "lenguajes_analizados": ["python"],
        "rutas_analizables": list(ANALYSIS_ROOTS),
        "rutas_escribibles": list(WRITE_ROOTS),
        "ramas_protegidas": sorted(PROTECTED_BRANCHES),
        "severidades": list(analyzer.SEVERITIES),
        "tipos_campo_plantilla": list(scaffold.FIELD_TYPES),
        "permisos": {"ver": PERM_VIEW, "escribir": PERM_WRITE},
    }


@router.post("/analisis")
def analyze_paths(body: AnalyzeBody, principal: Principal = Depends(_can_view),
                  service: VectorService = Depends(get_vector_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.analyze_paths(principal.nombre_usuario, body.rutas, body.solo_versionados))


@router.post("/analisis/codigo")
def analyze_snippet(body: SnippetBody, principal: Principal = Depends(_can_view),
                    service: VectorService = Depends(get_vector_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.analyze_code(principal.nombre_usuario, body.codigo, body.nombre))


@router.get("/analisis", dependencies=[Depends(_can_view)])
def analysis_history(limite: int = Query(20, ge=1, le=200), service: VectorService = Depends(get_vector_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.history(limite))


@router.get("/ramas", dependencies=[Depends(_can_view)])
def list_branches(service: VectorService = Depends(get_vector_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.branches())


@router.post("/ramas", status_code=201)
def create_branch(
    body: BranchBody,
    request: Request,
    principal: Principal = Depends(_can_write),
    service: VectorService = Depends(get_vector_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.create_branch(body.nombre, body.base)
        security.record_audit(principal, "vector_rama_crear", f"rama:{result['rama']}", f"desde {result['commit']}", ip=client_ip(request))
        return ok(result)


@router.get("/commits", dependencies=[Depends(_can_view)])
def list_commits(rama: str = Query("HEAD", max_length=200), limite: int = Query(20, ge=1, le=500),
                 service: VectorService = Depends(get_vector_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.commits(rama, limite))


@router.get("/diff", dependencies=[Depends(_can_view)])
def diff(base: str = Query(..., max_length=200), destino: str = Query("HEAD", max_length=200),
         service: VectorService = Depends(get_vector_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.diff(base, destino))


@router.post("/plantillas/vista-previa", dependencies=[Depends(_can_view)])
def preview_scaffold(body: ScaffoldBody, base: str = Query("HEAD", max_length=200),
                     service: VectorService = Depends(get_vector_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.scaffold_preview(body.spec(), base))


@router.post("/plantillas/aplicar", status_code=201)
def apply_scaffold(
    body: ApplyScaffoldBody,
    request: Request,
    principal: Principal = Depends(_can_write),
    service: VectorService = Depends(get_vector_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.scaffold_apply(principal.nombre_usuario, body.spec(), body.rama, body.base, body.mensaje, body.sobrescribir)
        security.record_audit(principal, "vector_plantilla_aplicar", f"rama:{result['rama']}",
                              f"commit {result['commit']}: {', '.join(result['archivos'])}", ip=client_ip(request))
        return ok(result)


@router.post("/commits", status_code=201)
def commit_files(
    body: CommitBody,
    request: Request,
    principal: Principal = Depends(_can_write),
    service: VectorService = Depends(get_vector_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.commit_files(principal.nombre_usuario, body.rama, body.archivos, body.mensaje, body.base)
        security.record_audit(principal, "vector_commit", f"rama:{result['rama']}",
                              f"commit {result['commit']}: {', '.join(result['archivos'])}", ip=client_ip(request))
        return ok(result)
