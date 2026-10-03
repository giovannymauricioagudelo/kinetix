"""
Argus (MonitoringAgent) — métricas, salud de agentes, recursos, alertas y reportes.
Todo requiere un token de Sentinel salvo /salud; /metricas acepta además ARGUS_SCRAPE_TOKEN para Prometheus.
"""

from __future__ import annotations

import asyncio
import hmac
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_client import CONTENT_TYPE_LATEST

from src.agents.agent_catalog import ALL_AGENTS, ARGUS, openapi_tag
from src.agents.monitoring_agent.alerts import ACTIVE, CRITICAL, RESOLVED, WARNING
from src.agents.monitoring_agent.middleware import PROBE_HEADER, PROBE_TOKEN
from src.agents.monitoring_agent.service import MonitoringService, get_monitoring_service
from src.agents.security_agent.dependencies import (
    get_security_service,
    require_permission,
    require_user,
    translate_errors,
)
from src.agents.security_agent.models import Principal, SecurityError
from src.agents.security_agent.service import SecurityService

PERM_VIEW = "monitoreo:ver"
PERM_ACKNOWLEDGE = "alertas:reconocer"

router = APIRouter(prefix="/api/v1/argus", tags=[openapi_tag(ARGUS)])
_bearer = HTTPBearer(auto_error=False)
_can_view = require_permission(PERM_VIEW)


def require_metrics_reader(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    security: SecurityService = Depends(get_security_service),
) -> None:
    scrape_token = os.getenv("ARGUS_SCRAPE_TOKEN")
    if scrape_token and credentials and hmac.compare_digest(credentials.credentials.encode(), scrape_token.encode()):
        return
    principal = require_user(credentials, security)
    with translate_errors():
        security.require(principal, PERM_VIEW)


def _codename_or_404(name: str) -> str:
    for profile in ALL_AGENTS:
        if profile.codename.lower() == name.lower():
            return profile.codename
    raise HTTPException(404, f"Agente no encontrado: {name}")


@router.get("/salud")
async def argus_health(request: Request, service: MonitoringService = Depends(get_monitoring_service)) -> Dict[str, Any]:
    if request.headers.get(PROBE_HEADER) != PROBE_TOKEN:
        await service.ensure_fresh(request.app)
    return {**service.overall_status(), "agente": ARGUS.codename, "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/info", dependencies=[Depends(_can_view)])
async def argus_info(service: MonitoringService = Depends(get_monitoring_service)) -> Dict[str, Any]:
    t = service.alerts.thresholds
    return {
        "id": "argus",
        "codename": ARGUS.codename,
        "legacy_id": ARGUS.legacy_id,
        "descripcion": ARGUS.tagline,
        "version": service.version,
        "endpoints": ARGUS.default_endpoints,
        "agentes_observados": [p.codename for p in ALL_AGENTS],
        "umbrales_alerta": {
            "latencia_ms": t.latency_ms,
            "tasa_error_5xx_porcentaje": t.error_rate_percent,
            "cpu_porcentaje": t.cpu_percent,
            "memoria_porcentaje": t.memory_percent,
            "disco_porcentaje": t.disk_percent,
            "ventana_minutos": t.window_minutes,
        },
        "sla_objetivo_porcentaje": service.sla_target,
    }


@router.get("/metricas", dependencies=[Depends(require_metrics_reader)])
async def prometheus_metrics(service: MonitoringService = Depends(get_monitoring_service)) -> Response:
    return Response(content=service.collector.render(), media_type=CONTENT_TYPE_LATEST)


@router.get("/metricas/json", dependencies=[Depends(_can_view)])
async def metrics_json(
    minutos: int = Query(60, ge=1, le=1440),
    service: MonitoringService = Depends(get_monitoring_service),
) -> Dict[str, Any]:
    return {"estado": "exito", **service.metrics_json(minutos)}


@router.get("/agentes", dependencies=[Depends(_can_view)])
async def agents(
    request: Request,
    minutos: int = Query(60, ge=1, le=1440),
    service: MonitoringService = Depends(get_monitoring_service),
) -> Dict[str, Any]:
    await service.refresh(request.app)
    return {"estado": "exito", **service.overall_status(), "agentes": service.agents_view(minutos)}


@router.get("/agentes/{nombre_agente}", dependencies=[Depends(_can_view)])
async def agent_detail(
    nombre_agente: str,
    request: Request,
    minutos: int = Query(60, ge=1, le=1440),
    service: MonitoringService = Depends(get_monitoring_service),
) -> Dict[str, Any]:
    codename = _codename_or_404(nombre_agente)
    await service.ensure_fresh(request.app)
    detail = service.agent_detail(codename, minutos)
    if detail is None:
        raise HTTPException(503, "Aún no hay sondas para este agente")
    return {"estado": "exito", **detail}


@router.get("/alertas", dependencies=[Depends(_can_view)])
async def alerts(
    request: Request,
    estado: Optional[str] = Query(ACTIVE, pattern=f"^({ACTIVE}|{RESOLVED}|todas)$"),
    severidad: Optional[str] = Query(None, pattern=f"^({CRITICAL}|{WARNING})$"),
    service: MonitoringService = Depends(get_monitoring_service),
) -> Dict[str, Any]:
    await service.ensure_fresh(request.app)
    items = service.alerts.list(None if estado == "todas" else estado, severidad)
    return {"estado": "exito", "total": len(items), "alertas": [a.to_dict() for a in items]}


@router.post("/alertas/{alerta_id}/reconocer")
async def acknowledge_alert(
    alerta_id: str,
    principal: Principal = Depends(require_permission(PERM_ACKNOWLEDGE)),
    service: MonitoringService = Depends(get_monitoring_service),
) -> Dict[str, Any]:
    try:
        alert = service.alerts.acknowledge(alerta_id, principal.nombre_usuario)
    except KeyError:
        raise HTTPException(404, f"Alerta no encontrada: {alerta_id}")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"estado": "exito", "alerta": alert.to_dict()}


@router.get("/sistema/recursos", dependencies=[Depends(_can_view)])
async def system_resources(service: MonitoringService = Depends(get_monitoring_service)) -> Dict[str, Any]:
    resources = await run_in_threadpool(service.resources)
    return {"estado": "exito", "timestamp": datetime.now(timezone.utc).isoformat(), **resources}


@router.get("/reportes/rendimiento", dependencies=[Depends(_can_view)])
async def performance_report(
    horas: int = Query(24, ge=1, le=24),
    service: MonitoringService = Depends(get_monitoring_service),
) -> Dict[str, Any]:
    return {"estado": "exito", **service.performance_report(horas)}


@router.get("/reportes/disponibilidad", dependencies=[Depends(_can_view)])
async def availability_report(service: MonitoringService = Depends(get_monitoring_service)) -> Dict[str, Any]:
    return {"estado": "exito", **service.availability_report()}


@router.websocket("/ws/metricas-vivo")
async def live_metrics(
    websocket: WebSocket,
    token: str = Query(...),
    intervalo: int = Query(5, ge=1, le=60),
) -> None:
    security = get_security_service()
    service = get_monitoring_service()
    try:
        principal = await run_in_threadpool(security.validate_access_token, token)
        await run_in_threadpool(security.require, principal, PERM_VIEW)
    except SecurityError:
        await websocket.close(code=1008)
        return
    except Exception:
        await websocket.close(code=1011)
        return
    await websocket.accept()
    disconnected = asyncio.create_task(_wait_for_disconnect(websocket))
    try:
        while not disconnected.done():
            if principal.expira <= datetime.now(timezone.utc).replace(tzinfo=None):
                await websocket.close(code=1008, reason="Token expirado")
                return
            await websocket.send_json(await run_in_threadpool(service.live_frame))
            await asyncio.wait({disconnected}, timeout=intervalo)
    except (WebSocketDisconnect, OSError, RuntimeError):
        return
    finally:
        disconnected.cancel()


async def _wait_for_disconnect(websocket: WebSocket) -> None:
    while (await websocket.receive())["type"] != "websocket.disconnect":
        pass
