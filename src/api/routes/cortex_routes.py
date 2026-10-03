"""
Cortex (OrchestratorAgent) — evalúa solicitudes, pregunta lo necesario y propone planes.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.agents.agent_catalog import ALL_AGENTS, CORTEX, openapi_tag
from src.agents.orchestrator_agent import OrchestratorAgent, RequestType

router = APIRouter(prefix="/api/v1/cortex", tags=[openapi_tag(CORTEX)])

_cortex = OrchestratorAgent()


class NewRequestBody(BaseModel):
    descripcion: str = Field(..., min_length=10, description="Qué se necesita, en lenguaje natural.")
    app_id: Optional[str] = Field(None, description="Aplicación existente (escalabilidad, mejora o corrección).")
    tipo_solicitud: Optional[RequestType] = Field(None, description="Opcional: si se omite, Cortex lo deduce o lo pregunta.")


class AnswersBody(BaseModel):
    respuestas: Dict[str, str] = Field(..., description="Mapa id_pregunta → respuesta. 'no aplica' es una respuesta válida.")


class ApprovalBody(BaseModel):
    aprobado_por: str = Field(..., min_length=1)


def _get_or_404(request_id: str):
    try:
        return _cortex.get(request_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Solicitud no encontrada: {request_id}")


@router.get("/info")
async def cortex_info() -> Dict[str, Any]:
    return {
        "id": "cortex",
        "codename": CORTEX.codename,
        "legacy_id": CORTEX.legacy_id,
        "descripcion": CORTEX.tagline,
        "version": _cortex.version,
        "tipos_solicitud": [t.value for t in RequestType],
        "agentes_coordinados": [p.codename for p in ALL_AGENTS if p is not CORTEX],
        "politica": "Pregunta según la complejidad y no delega nada sin aprobación humana.",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/requests", status_code=201)
async def create_request(body: NewRequestBody) -> Dict[str, Any]:
    try:
        request = _cortex.submit(body.descripcion, body.app_id, body.tipo_solicitud)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return request.to_dict()


@router.get("/requests")
async def list_requests() -> Dict[str, Any]:
    requests = _cortex.list_requests()
    return {
        "total": len(requests),
        "solicitudes": [
            {"id": r.id, "tipo_solicitud": r.request_type.value if r.request_type else None, "estado": r.status.value}
            for r in requests
        ],
    }


@router.get("/requests/{request_id}")
async def get_request(request_id: str) -> Dict[str, Any]:
    return _get_or_404(request_id).to_dict()


@router.post("/requests/{request_id}/answers")
async def answer_questions(request_id: str, body: AnswersBody) -> Dict[str, Any]:
    _get_or_404(request_id)
    try:
        return _cortex.answer(request_id, body.respuestas).to_dict()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/requests/{request_id}/approve")
async def approve_plan(request_id: str, body: ApprovalBody) -> Dict[str, Any]:
    _get_or_404(request_id)
    try:
        return _cortex.approve(request_id, body.aprobado_por).to_dict()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
