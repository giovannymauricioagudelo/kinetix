"""
Insight (ReportingAgent) — catálogo cerrado de reportes sobre Matrix, Sentinel, Argus, Prism, Orbit y Vector,
exportación CSV/JSON, reportes guardados por empresa y programaciones periódicas. Todo requiere token salvo /salud.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.agents.agent_catalog import INSIGHT, openapi_tag
from src.agents.reporting_agent.dependencies import get_insight_service
from src.agents.reporting_agent.exporters import FORMATS
from src.agents.reporting_agent.service import FREQUENCIES, VERSION, InsightService
from src.agents.security_agent.dependencies import get_security_service, require_permission, translate_errors
from src.agents.security_agent.models import Principal
from src.agents.security_agent.service import SecurityService
from src.api.routes._common import attachment, client_ip, health, ok

PERM_VIEW = "reportes:ver"
PERM_GENERATE = "reportes:generar"
PERM_SCHEDULE = "reportes:programar"
UNAVAILABLE = "Servicio de reportes no disponible temporalmente"
FORMAT_PATTERN = "^(json|csv)$"

router = APIRouter(prefix="/api/v1/insight", tags=[openapi_tag(INSIGHT)])
_can_view = require_permission(PERM_VIEW)
_can_generate = require_permission(PERM_GENERATE)
_can_schedule = require_permission(PERM_SCHEDULE)


class ReportBody(BaseModel):
    tipo: str = Field(..., max_length=50)
    parametros: Dict[str, Any] = Field(default_factory=dict)


class GenerateBody(ReportBody):
    guardar: bool = False
    nombre: Optional[str] = Field(None, max_length=200)


class ScheduleBody(ReportBody):
    nombre: str = Field(..., min_length=1, max_length=200)
    frecuencia: str = Field("diaria", pattern="^(diaria|semanal|mensual)$")
    hora_utc: int = Field(6, ge=0, le=23)
    activa: bool = True


class ScheduleUpdateBody(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=200)
    parametros: Optional[Dict[str, Any]] = None
    frecuencia: Optional[str] = Field(None, pattern="^(diaria|semanal|mensual)$")
    hora_utc: Optional[int] = Field(None, ge=0, le=23)
    activa: Optional[bool] = None


@router.get("/salud")
def insight_health(service: InsightService = Depends(get_insight_service)) -> Dict[str, Any]:
    return health(INSIGHT.codename, service.ping)


@router.get("/info", dependencies=[Depends(_can_view)])
def insight_info(service: InsightService = Depends(get_insight_service)) -> Dict[str, Any]:
    return {
        "id": "insight",
        "agente": INSIGHT.codename,
        "legacy_id": INSIGHT.legacy_id,
        "version": VERSION,
        "descripcion": INSIGHT.tagline,
        "reportes": [r["id"] for r in service.catalog()["reportes"]],
        "formatos": list(FORMATS),
        "frecuencias": list(FREQUENCIES),
        "max_filas": service.max_rows,
        "retencion_dias": service.retention_days,
        "permisos": {"ver": PERM_VIEW, "generar": PERM_GENERATE, "programar": PERM_SCHEDULE},
    }


@router.get("/catalogo", dependencies=[Depends(_can_view)])
def catalog(service: InsightService = Depends(get_insight_service)) -> Dict[str, Any]:
    return ok(service.catalog())


@router.get("/kpis", dependencies=[Depends(_can_view)])
def kpis(dias: int = Query(7, ge=1, le=90), service: InsightService = Depends(get_insight_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.kpis(dias))


@router.post("/reportes/generar")
def generate(
    body: GenerateBody,
    request: Request,
    principal: Principal = Depends(_can_generate),
    service: InsightService = Depends(get_insight_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        report = service.generate(principal, body.tipo, body.parametros, body.guardar, body.nombre)
        if body.guardar:
            security.record_audit(principal, "insight_reporte_guardar", f"reporte:{report['id_reporte']}",
                                  f"{body.tipo} ({report['total_filas']} filas)", ip=client_ip(request))
        return ok(report)


@router.post("/reportes/exportar")
def export(body: ReportBody, formato: str = Query("csv", pattern=FORMAT_PATTERN), principal: Principal = Depends(_can_generate),
           service: InsightService = Depends(get_insight_service)) -> Response:
    with translate_errors(UNAVAILABLE):
        return attachment(*service.export(principal, body.tipo, body.parametros, formato))


@router.get("/reportes")
def list_saved(tipo: Optional[str] = Query(None, max_length=50), limite: int = Query(50, ge=1, le=200),
               principal: Principal = Depends(_can_view), service: InsightService = Depends(get_insight_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.list_saved(principal.id_empresa, tipo, limite))


@router.get("/reportes/{id_reporte}")
def get_saved(id_reporte: str, principal: Principal = Depends(_can_view),
              service: InsightService = Depends(get_insight_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok({"reporte": service.get_saved(id_reporte, principal.id_empresa)})


@router.get("/reportes/{id_reporte}/exportar")
def export_saved(id_reporte: str, formato: str = Query("csv", pattern=FORMAT_PATTERN), principal: Principal = Depends(_can_view),
                 service: InsightService = Depends(get_insight_service)) -> Response:
    with translate_errors(UNAVAILABLE):
        return attachment(*service.export_saved(id_reporte, principal.id_empresa, formato))


@router.delete("/reportes/{id_reporte}")
def delete_saved(
    id_reporte: str,
    request: Request,
    principal: Principal = Depends(_can_generate),
    service: InsightService = Depends(get_insight_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.delete_saved(id_reporte, principal.id_empresa)
        security.record_audit(principal, "insight_reporte_eliminar", f"reporte:{id_reporte}", ip=client_ip(request))
        return ok(result)


@router.get("/programaciones")
def list_schedules(principal: Principal = Depends(_can_view), service: InsightService = Depends(get_insight_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.list_schedules(principal.id_empresa))


@router.post("/programaciones", status_code=201)
def create_schedule(
    body: ScheduleBody,
    request: Request,
    principal: Principal = Depends(_can_schedule),
    service: InsightService = Depends(get_insight_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.create_schedule(principal, body.model_dump())
        security.record_audit(principal, "insight_programacion_crear", f"programacion:{result['id_programacion']}",
                              f"{result['tipo']} {result['frecuencia']} {result['hora_utc']}:00 UTC", ip=client_ip(request))
        return ok(result)


@router.put("/programaciones/{id_programacion}")
def update_schedule(
    id_programacion: str,
    body: ScheduleUpdateBody,
    request: Request,
    principal: Principal = Depends(_can_schedule),
    service: InsightService = Depends(get_insight_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.update_schedule(id_programacion, principal.id_empresa, body.model_dump(exclude_unset=True))
        security.record_audit(principal, "insight_programacion_actualizar", f"programacion:{id_programacion}",
                              f"activa={result['activa']} {result['frecuencia']} {result['hora_utc']}:00 UTC", ip=client_ip(request))
        return ok(result)


@router.delete("/programaciones/{id_programacion}")
def delete_schedule(
    id_programacion: str,
    request: Request,
    principal: Principal = Depends(_can_schedule),
    service: InsightService = Depends(get_insight_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.delete_schedule(id_programacion, principal.id_empresa)
        security.record_audit(principal, "insight_programacion_eliminar", f"programacion:{id_programacion}", ip=client_ip(request))
        return ok(result)


@router.post("/programaciones/{id_programacion}/ejecutar")
def run_schedule(
    id_programacion: str,
    request: Request,
    principal: Principal = Depends(_can_schedule),
    service: InsightService = Depends(get_insight_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.run_schedule_now(id_programacion, principal.id_empresa)
        security.record_audit(principal, "insight_programacion_ejecutar", f"programacion:{id_programacion}",
                              f"estado={result['estado']}", ip=client_ip(request))
        return ok(result)
