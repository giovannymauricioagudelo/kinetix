"""
Genesis (CustomAIAgent) — agentes de IA personalizados por empresa, generación de código/SQL/documentos revisada
por Vector y commiteable en una rama, cascada de modelos Anthropic/OpenAI y presupuesto mensual de tokens.
Todo requiere token de Sentinel salvo /salud.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.agents.agent_catalog import GENESIS, openapi_tag
from src.agents.custom_ai_agent.cascade import LEVELS, TIERS
from src.agents.custom_ai_agent.dependencies import get_genesis_service
from src.agents.custom_ai_agent.service import LANGUAGES, VERSION, GenerationFailed, GenesisService
from src.agents.security_agent.dependencies import get_security_service, require_permission, translate_errors
from src.agents.security_agent.models import Principal
from src.agents.security_agent.service import SecurityService
from src.api.routes._common import client_ip, health, ok

PERM_VIEW = "ia:ver"
PERM_MANAGE = "ia:gestionar"
PERM_INVOKE = "ia:invocar"
PERM_COMMIT = "codigo:escribir"
UNAVAILABLE = "Servicio de IA no disponible temporalmente"

router = APIRouter(prefix="/api/v1/genesis", tags=[openapi_tag(GENESIS)])
_can_view = require_permission(PERM_VIEW)
_can_manage = require_permission(PERM_MANAGE)
_can_invoke = require_permission(PERM_INVOKE)


@contextmanager
def genesis_errors() -> Iterator[None]:
    with translate_errors(UNAVAILABLE):
        try:
            yield
        except GenerationFailed as e:
            raise HTTPException(502, str(e)) from None


class AgentBody(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=60)
    prompt_sistema: str = Field(..., min_length=10, max_length=10_000)
    descripcion: str = Field("", max_length=500)
    proveedor: str = Field("auto", description="auto, anthropic u openai")
    nivel: str = Field("auto", description="auto, economico o premium")
    temperatura: Optional[float] = Field(None, ge=0, le=1)
    max_tokens: int = Field(1024, ge=64, le=8192)


class AgentUpdateBody(BaseModel):
    version: Optional[int] = Field(None, ge=1)
    nombre: Optional[str] = Field(None, min_length=2, max_length=60)
    prompt_sistema: Optional[str] = Field(None, min_length=10, max_length=10_000)
    descripcion: Optional[str] = Field(None, max_length=500)
    proveedor: Optional[str] = None
    nivel: Optional[str] = None
    temperatura: Optional[float] = Field(None, ge=0, le=1)
    max_tokens: Optional[int] = Field(None, ge=64, le=8192)
    estado: Optional[str] = None


class InvokeBody(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=20_000)
    contexto: Optional[str] = Field(None, max_length=20_000)


class GenerateBody(BaseModel):
    tipo: str = Field("codigo", description="codigo, sql o documento")
    lenguaje: Optional[str] = Field(None, description="python, typescript, javascript, sql o markdown")
    descripcion: str = Field(..., min_length=10, max_length=20_000)
    ruta_sugerida: Optional[str] = Field(None, max_length=200)
    nivel: str = "auto"
    proveedor: str = "auto"
    max_tokens: int = Field(4096, ge=256, le=8192)


class CommitBody(BaseModel):
    rama: str = Field(..., max_length=100, description="feature/, fix/, chore/ o vector/ (nunca master/main)")
    ruta: Optional[str] = Field(None, max_length=200)
    mensaje: Optional[str] = Field(None, min_length=3, max_length=500)
    base: str = Field("HEAD", max_length=200)


class BudgetBody(BaseModel):
    tokens_mensuales: int = Field(..., ge=1_000, le=1_000_000_000)


@router.get("/salud")
def genesis_health(service: GenesisService = Depends(get_genesis_service)) -> Dict[str, Any]:
    return health(GENESIS.codename, service.ping, {"proveedores": service.providers_status()})


@router.get("/info", dependencies=[Depends(_can_view)])
def genesis_info(service: GenesisService = Depends(get_genesis_service)) -> Dict[str, Any]:
    return {
        "id": "genesis",
        "agente": GENESIS.codename,
        "legacy_id": GENESIS.legacy_id,
        "version": VERSION,
        "descripcion": GENESIS.tagline,
        "proveedores": service.providers_status(),
        "modelos": service.catalog.describe(),
        "proveedor_preferido": service.catalog.preferred[0],
        "niveles": list(LEVELS),
        "niveles_modelo": list(TIERS),
        "tipos_generacion": {k: list(v) for k, v in LANGUAGES.items()},
        "presupuesto_por_defecto": service.default_budget,
        "guarda_contenido": service.store_content,
        "permisos": {"ver": PERM_VIEW, "gestionar": PERM_MANAGE, "invocar": PERM_INVOKE, "commit": PERM_COMMIT},
    }


@router.get("/agentes")
def list_agents(incluir_archivados: bool = Query(False), principal: Principal = Depends(_can_view),
                service: GenesisService = Depends(get_genesis_service)) -> Dict[str, Any]:
    with genesis_errors():
        return ok(service.list_agents(principal.id_empresa, incluir_archivados))


@router.post("/agentes", status_code=201)
def create_agent(
    body: AgentBody,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: GenesisService = Depends(get_genesis_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with genesis_errors():
        result = service.create_agent(principal.nombre_usuario, principal.id_empresa, body.model_dump())
        security.record_audit(principal, "genesis_agente_crear", f"agente_ia:{result['id_agente']}",
                              f"{result['nombre']} ({result['proveedor']}/{result['nivel']})", ip=client_ip(request))
        return ok({"agente": result})


@router.get("/agentes/{id_agente}")
def get_agent(id_agente: str, principal: Principal = Depends(_can_view),
              service: GenesisService = Depends(get_genesis_service)) -> Dict[str, Any]:
    with genesis_errors():
        return ok({"agente": service.get_agent(id_agente, principal.id_empresa)})


@router.put("/agentes/{id_agente}")
def update_agent(
    id_agente: str,
    body: AgentUpdateBody,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: GenesisService = Depends(get_genesis_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with genesis_errors():
        data = body.model_dump(exclude_unset=True)
        result = service.update_agent(id_agente, principal.id_empresa, data)
        security.record_audit(principal, "genesis_agente_actualizar", f"agente_ia:{id_agente}",
                              f"versión {result['version']}: {', '.join(sorted(k for k in data if k != 'version')) or 'sin cambios'}",
                              ip=client_ip(request))
        return ok({"agente": result})


@router.delete("/agentes/{id_agente}")
def archive_agent(
    id_agente: str,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: GenesisService = Depends(get_genesis_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with genesis_errors():
        result = service.archive_agent(id_agente, principal.id_empresa)
        security.record_audit(principal, "genesis_agente_archivar", f"agente_ia:{id_agente}", ip=client_ip(request))
        return ok({"agente": result})


@router.post("/agentes/{id_agente}/invocar")
def invoke_agent(id_agente: str, body: InvokeBody, principal: Principal = Depends(_can_invoke),
                 service: GenesisService = Depends(get_genesis_service)) -> Dict[str, Any]:
    with genesis_errors():
        return ok(service.invoke_agent(principal.nombre_usuario, principal.id_empresa, id_agente, body.prompt, body.contexto))


@router.get("/invocaciones")
def list_invocations(id_agente: Optional[str] = Query(None, max_length=40), limite: int = Query(50, ge=1, le=200),
                     con_contenido: bool = Query(False), principal: Principal = Depends(_can_view),
                     service: GenesisService = Depends(get_genesis_service)) -> Dict[str, Any]:
    with genesis_errors():
        return ok(service.list_invocations(principal.id_empresa, id_agente, limite, con_contenido))


@router.post("/generaciones", status_code=201)
def generate(body: GenerateBody, principal: Principal = Depends(_can_invoke),
             service: GenesisService = Depends(get_genesis_service)) -> Dict[str, Any]:
    with genesis_errors():
        return ok(service.generate(principal.nombre_usuario, principal.id_empresa, body.model_dump()))


@router.get("/generaciones")
def list_generations(limite: int = Query(50, ge=1, le=200), principal: Principal = Depends(_can_view),
                     service: GenesisService = Depends(get_genesis_service)) -> Dict[str, Any]:
    with genesis_errors():
        return ok(service.list_generations(principal.id_empresa, limite))


@router.get("/generaciones/{id_generacion}")
def get_generation(id_generacion: str, principal: Principal = Depends(_can_view),
                   service: GenesisService = Depends(get_genesis_service)) -> Dict[str, Any]:
    with genesis_errors():
        return ok({"generacion": service.get_generation(id_generacion, principal.id_empresa)})


@router.post("/generaciones/{id_generacion}/commit")
def commit_generation(
    id_generacion: str,
    body: CommitBody,
    request: Request,
    principal: Principal = Depends(_can_invoke),
    service: GenesisService = Depends(get_genesis_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with genesis_errors():
        security.require(principal, PERM_COMMIT, client_ip(request))
        result = service.commit_generation(principal.nombre_usuario, principal.id_empresa, id_generacion, body.rama, body.ruta,
                                           body.mensaje, body.base)
        security.record_audit(principal, "genesis_generacion_commit", f"generacion:{id_generacion}",
                              f"{result['ruta']} en {result['rama']} ({result['commit'][:12]})", ip=client_ip(request))
        return ok(result)


@router.get("/uso")
def usage(principal: Principal = Depends(_can_view), service: GenesisService = Depends(get_genesis_service)) -> Dict[str, Any]:
    with genesis_errors():
        return ok(service.usage(principal.id_empresa))


@router.put("/presupuesto")
def set_budget(
    body: BudgetBody,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: GenesisService = Depends(get_genesis_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with genesis_errors():
        result = service.set_budget(principal.nombre_usuario, principal.id_empresa, body.tokens_mensuales)
        security.record_audit(principal, "genesis_presupuesto_actualizar", f"empresa:{principal.id_empresa}",
                              f"{body.tokens_mensuales} tokens/mes", ip=client_ip(request))
        return ok(result)
