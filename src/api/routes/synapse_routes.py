"""
Synapse (APIsAgent) — pasarela de integraciones con APIs externas por empresa: credenciales cifradas,
importación de OpenAPI, llamadas con protección SSRF, límite de tasa, circuit breaker y reintentos,
pruebas de conexión, bitácora y métricas. Todo requiere token de Sentinel salvo /salud.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from src.agents.agent_catalog import SYNAPSE, openapi_tag
from src.agents.apis_agent.dependencies import get_synapse_service
from src.agents.apis_agent.service import AUTH_TYPES, METHODS, VERSION, SynapseService
from src.agents.security_agent.dependencies import get_security_service, require_permission, translate_errors
from src.agents.security_agent.models import Principal
from src.agents.security_agent.service import SecurityService
from src.api.routes._common import client_ip, health, ok

PERM_VIEW = "integraciones:ver"
PERM_MANAGE = "integraciones:gestionar"
PERM_INVOKE = "integraciones:invocar"
UNAVAILABLE = "Servicio de integraciones no disponible temporalmente"

router = APIRouter(prefix="/api/v1/synapse", tags=[openapi_tag(SYNAPSE)])
_can_view = require_permission(PERM_VIEW)
_can_manage = require_permission(PERM_MANAGE)
_can_invoke = require_permission(PERM_INVOKE)


class IntegrationBody(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=60)
    url_base: str = Field(..., max_length=500)
    descripcion: str = Field("", max_length=500)
    tipo_auth: str = Field("none", description="none, bearer, api_key o basic")
    auth: Optional[Dict[str, str]] = Field(None, description="api_key: {'ubicacion': 'header'|'query', 'nombre': 'X-API-Key'}")
    credenciales: Optional[Dict[str, str]] = Field(None, description="bearer: token · api_key: valor · basic: usuario, contrasena")
    encabezados: Optional[Dict[str, str]] = None
    timeout_s: float = Field(15, ge=1, le=60)
    reintentos: int = Field(2, ge=0, le=3)
    limite_por_minuto: int = Field(60, ge=1, le=600)
    estado: str = "activa"


class IntegrationUpdateBody(BaseModel):
    version: Optional[int] = Field(None, ge=1, description="Versión leída; evita sobrescribir cambios ajenos")
    nombre: Optional[str] = Field(None, min_length=2, max_length=60)
    url_base: Optional[str] = Field(None, max_length=500)
    descripcion: Optional[str] = Field(None, max_length=500)
    tipo_auth: Optional[str] = None
    auth: Optional[Dict[str, str]] = None
    credenciales: Optional[Dict[str, str]] = None
    encabezados: Optional[Dict[str, str]] = None
    timeout_s: Optional[float] = Field(None, ge=1, le=60)
    reintentos: Optional[int] = Field(None, ge=0, le=3)
    limite_por_minuto: Optional[int] = Field(None, ge=1, le=600)
    estado: Optional[str] = None


class SpecBody(BaseModel):
    especificacion: Optional[Dict[str, Any]] = None
    contenido: Optional[str] = Field(None, max_length=2_000_000)
    url: Optional[str] = Field(None, max_length=500)


class CallBody(BaseModel):
    id_operacion: Optional[str] = Field(None, max_length=100)
    metodo: Optional[str] = Field(None, max_length=10)
    ruta: Optional[str] = Field(None, max_length=2000)
    parametros: Dict[str, Any] = Field(default_factory=dict)
    consulta: Dict[str, Any] = Field(default_factory=dict)
    encabezados: Dict[str, str] = Field(default_factory=dict)
    cuerpo: Optional[Any] = None
    clave_idempotencia: Optional[str] = Field(None, max_length=100)


class TestBody(BaseModel):
    ruta: str = Field("/", max_length=2000)
    metodo: str = "GET"


@router.get("/salud")
def synapse_health(service: SynapseService = Depends(get_synapse_service)) -> Dict[str, Any]:
    return health(SYNAPSE.codename, service.ping, {"cifrado": "configurado" if service.encryption_configured else "sin llave"})


@router.get("/info", dependencies=[Depends(_can_view)])
def synapse_info(service: SynapseService = Depends(get_synapse_service)) -> Dict[str, Any]:
    return {
        "id": "synapse",
        "agente": SYNAPSE.codename,
        "legacy_id": SYNAPSE.legacy_id,
        "version": VERSION,
        "descripcion": SYNAPSE.tagline,
        "tipos_auth": list(AUTH_TYPES),
        "metodos": list(METHODS),
        "esquemas_permitidos": service.allowed_schemes,
        "cifrado_credenciales": service.encryption_configured,
        "max_integraciones": service.max_integrations,
        "permisos": {"ver": PERM_VIEW, "gestionar": PERM_MANAGE, "invocar": PERM_INVOKE},
    }


@router.get("/integraciones")
def list_integrations(principal: Principal = Depends(_can_view),
                      service: SynapseService = Depends(get_synapse_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.list_integrations(principal.id_empresa))


@router.post("/integraciones", status_code=201)
def create_integration(
    body: IntegrationBody,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: SynapseService = Depends(get_synapse_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.create_integration(principal.nombre_usuario, principal.id_empresa, body.model_dump())
        security.record_audit(principal, "synapse_integracion_crear", f"integracion:{result['id_integracion']}",
                              f"{result['nombre']} {result['url_base']} ({result['tipo_auth']})", ip=client_ip(request))
        return ok({"integracion": result})


@router.get("/integraciones/{id_integracion}")
def get_integration(id_integracion: str, principal: Principal = Depends(_can_view),
                    service: SynapseService = Depends(get_synapse_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok({"integracion": service.get_integration(id_integracion, principal.id_empresa)})


@router.put("/integraciones/{id_integracion}")
def update_integration(
    id_integracion: str,
    body: IntegrationUpdateBody,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: SynapseService = Depends(get_synapse_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        data = body.model_dump(exclude_unset=True)
        result = service.update_integration(id_integracion, principal.id_empresa, data)
        changed = ", ".join(sorted(k for k in data if k != "version"))
        security.record_audit(principal, "synapse_integracion_actualizar", f"integracion:{id_integracion}",
                              f"versión {result['version']}: {changed or 'sin cambios'}", ip=client_ip(request))
        return ok({"integracion": result})


@router.delete("/integraciones/{id_integracion}")
def delete_integration(
    id_integracion: str,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: SynapseService = Depends(get_synapse_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.delete_integration(id_integracion, principal.id_empresa)
        security.record_audit(principal, "synapse_integracion_eliminar", f"integracion:{id_integracion}", ip=client_ip(request))
        return ok(result)


@router.post("/integraciones/{id_integracion}/especificacion")
def import_spec(
    id_integracion: str,
    body: SpecBody,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: SynapseService = Depends(get_synapse_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.import_spec(principal.nombre_usuario, id_integracion, principal.id_empresa, body.model_dump())
        security.record_audit(principal, "synapse_especificacion_importar", f"integracion:{id_integracion}",
                              f"{result['formato']} {result['titulo']} ({result['operaciones']} operaciones)", ip=client_ip(request))
        return ok(result)


@router.get("/integraciones/{id_integracion}/operaciones")
def list_operations(id_integracion: str, filtro: Optional[str] = Query(None, max_length=100), principal: Principal = Depends(_can_view),
                    service: SynapseService = Depends(get_synapse_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.operations(id_integracion, principal.id_empresa, filtro))


@router.post("/integraciones/{id_integracion}/llamar")
def call_integration(id_integracion: str, body: CallBody, principal: Principal = Depends(_can_invoke),
                     service: SynapseService = Depends(get_synapse_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.call(principal.nombre_usuario, id_integracion, principal.id_empresa, body.model_dump()))


@router.post("/integraciones/{id_integracion}/probar")
def test_integration(id_integracion: str, body: TestBody = TestBody(), principal: Principal = Depends(_can_invoke),
                     service: SynapseService = Depends(get_synapse_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.test_connection(principal.nombre_usuario, id_integracion, principal.id_empresa, body.ruta, body.metodo))


@router.get("/llamadas")
def list_calls(id_integracion: Optional[str] = Query(None, max_length=40), limite: int = Query(50, ge=1, le=500),
               principal: Principal = Depends(_can_view), service: SynapseService = Depends(get_synapse_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.list_calls(principal.id_empresa, id_integracion, limite))


@router.get("/metricas")
def metrics(horas: int = Query(24, ge=1, le=168), principal: Principal = Depends(_can_view),
            service: SynapseService = Depends(get_synapse_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.metrics(principal.id_empresa, horas))
