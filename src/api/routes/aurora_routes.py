"""
Aurora (InterfaceDesignAgent) — sistemas de diseño por empresa: tokens versionados, componentes,
accesibilidad WCAG 2.1, exportación (CSS, SCSS, Tailwind, DTCG, Android), layouts y pantallas HTML.
Todo requiere un token de Sentinel salvo /salud.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from src.agents.agent_catalog import AURORA, openapi_tag
from src.agents.interface_design_agent import design, exporters
from src.agents.interface_design_agent.dependencies import get_aurora_service
from src.agents.interface_design_agent.service import VERSION, AuroraService
from src.agents.security_agent.dependencies import get_security_service, require_permission, translate_errors
from src.agents.security_agent.models import Principal
from src.agents.security_agent.service import SecurityService
from src.api.routes._common import attachment, client_ip, health, ok

PERM_VIEW = "diseno:ver"
PERM_MANAGE = "diseno:gestionar"
UNAVAILABLE = "Servicio de diseño no disponible temporalmente"

router = APIRouter(prefix="/api/v1/aurora", tags=[openapi_tag(AURORA)])
_can_view = require_permission(PERM_VIEW)
_can_manage = require_permission(PERM_MANAGE)


class SystemBody(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    paleta_base: str = Field("kinetix", description="kinetix, material, apple o personalizada")
    color_primario: Optional[str] = Field(None, max_length=7)
    color_secundario: Optional[str] = Field(None, max_length=7)
    color_neutro: Optional[str] = Field(None, max_length=7)
    nivel_wcag: str = "AA"
    tipografia: Optional[str] = Field(None, max_length=200)
    tamano_base_px: int = Field(16, ge=10, le=32)
    escala_tipografica: float = Field(1.25, ge=1.05, le=2.0)
    espaciado_base_px: int = Field(4, ge=2, le=16)


class TokensBody(BaseModel):
    version: int = Field(..., ge=1, description="Versión leída; evita sobrescribir cambios ajenos")
    tokens: Dict[str, Any] = Field(..., description="Cambios parciales, p. ej. {'themes': {'light': {'primary': '#1D4ED8'}}}")
    nivel_wcag: Optional[str] = None


class ComponentBody(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=60)
    tipo: str
    variantes: List[str] = Field(default_factory=lambda: ["default"], max_length=20)
    estados: List[str] = Field(default_factory=lambda: ["default"], max_length=20)
    propiedades: Dict[str, Any] = Field(default_factory=dict)


class AccessibilityBody(BaseModel):
    nivel_wcag: Optional[str] = None
    aplicar_correcciones: bool = False


class LayoutBody(BaseModel):
    tipo: str = "grid"
    columnas_movil: int = 1
    columnas_tablet: int = 6
    columnas_escritorio: int = 12
    espaciado: str = "md"
    ancho_maximo_px: int = 1280
    clase: str = "kx-layout"


class ScreenBody(BaseModel):
    tipo: str = Field(..., description="login, dashboard, list o form")
    nombre_app: str = Field(..., min_length=1, max_length=80)
    idioma: str = "es"


class ContrastBody(BaseModel):
    color_texto: str = Field(..., max_length=7)
    color_fondo: str = Field(..., max_length=7)


@router.get("/salud")
def aurora_health(service: AuroraService = Depends(get_aurora_service)) -> Dict[str, Any]:
    return health(AURORA.codename, service.ping)


@router.get("/info", dependencies=[Depends(_can_view)])
def aurora_info() -> Dict[str, Any]:
    return {
        "id": "aurora",
        "agente": AURORA.codename,
        "legacy_id": AURORA.legacy_id,
        "version": VERSION,
        "descripcion": AURORA.tagline,
        "paletas_base": [*design.PRESETS, "personalizada"],
        "niveles_wcag": list(design.WCAG_LEVELS),
        "tipos_componente": list(design.COMPONENT_TYPES),
        "formatos_exportacion": list(exporters.EXPORT_FORMATS),
        "layouts": list(exporters.LAYOUT_TYPES),
        "pantallas": list(exporters.SCREEN_TYPES),
        "puntos_de_quiebre": design.BREAKPOINTS,
        "permisos": {"ver": PERM_VIEW, "gestionar": PERM_MANAGE},
    }


@router.post("/contraste", dependencies=[Depends(_can_view)])
def check_contrast(body: ContrastBody, service: AuroraService = Depends(get_aurora_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.contrast(body.color_texto, body.color_fondo))


@router.get("/sistemas")
def list_systems(principal: Principal = Depends(_can_view), service: AuroraService = Depends(get_aurora_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.list_systems(principal.id_empresa))


@router.post("/sistemas", status_code=201)
def create_system(
    body: SystemBody,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: AuroraService = Depends(get_aurora_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.create_system(principal.nombre_usuario, principal.id_empresa, body.model_dump())
        security.record_audit(principal, "aurora_sistema_crear", f"sistema_diseno:{result['id_sistema']}",
                              f"{result['nombre']} ({result['nivel_wcag']})", ip=client_ip(request))
        return ok({"sistema": result})


@router.get("/sistemas/{id_sistema}")
def get_system(id_sistema: str, principal: Principal = Depends(_can_view),
               service: AuroraService = Depends(get_aurora_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok({"sistema": service.get_system(id_sistema, principal.id_empresa)})


@router.put("/sistemas/{id_sistema}/tokens")
def update_tokens(
    id_sistema: str,
    body: TokensBody,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: AuroraService = Depends(get_aurora_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.update_tokens(id_sistema, principal.id_empresa, body.tokens, body.version, body.nivel_wcag)
        security.record_audit(principal, "aurora_tokens_actualizar", f"sistema_diseno:{id_sistema}",
                              f"versión {result['version']}", ip=client_ip(request))
        return ok({"sistema": result})


@router.put("/sistemas/{id_sistema}/componentes")
def save_component(
    id_sistema: str,
    body: ComponentBody,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: AuroraService = Depends(get_aurora_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.upsert_component(id_sistema, principal.id_empresa, body.model_dump())
        security.record_audit(principal, "aurora_componente_guardar", f"sistema_diseno:{id_sistema}",
                              result["componente"]["nombre"], ip=client_ip(request))
        return ok(result)


@router.delete("/sistemas/{id_sistema}/componentes/{nombre}")
def delete_component(
    id_sistema: str,
    nombre: str,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: AuroraService = Depends(get_aurora_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.delete_component(id_sistema, principal.id_empresa, nombre)
        security.record_audit(principal, "aurora_componente_eliminar", f"sistema_diseno:{id_sistema}", nombre, ip=client_ip(request))
        return ok(result)


@router.post("/sistemas/{id_sistema}/accesibilidad")
def validate_accessibility(
    id_sistema: str,
    body: AccessibilityBody,
    request: Request,
    principal: Principal = Depends(_can_view),
    service: AuroraService = Depends(get_aurora_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        if body.aplicar_correcciones:
            security.require(principal, PERM_MANAGE, client_ip(request))
        result = service.accessibility(id_sistema, principal.id_empresa, body.nivel_wcag, body.aplicar_correcciones)
        if result["correcciones_aplicadas"]:
            security.record_audit(principal, "aurora_accesibilidad_corregir", f"sistema_diseno:{id_sistema}",
                                  f"versión {result['version_nueva']}", ip=client_ip(request))
        return ok(result)


@router.get("/sistemas/{id_sistema}/exportar")
def export_tokens(
    id_sistema: str,
    formato: str = Query("css", description="css, scss, tailwind, json o android"),
    descargar: bool = Query(False),
    principal: Principal = Depends(_can_view),
    service: AuroraService = Depends(get_aurora_service),
):
    with translate_errors(UNAVAILABLE):
        result = service.export(id_sistema, principal.id_empresa, formato)
    if descargar:
        return attachment(result["contenido"], result["archivo"], result["tipo_contenido"])
    return ok(result)


@router.post("/sistemas/{id_sistema}/layout")
def responsive_layout(id_sistema: str, body: LayoutBody, principal: Principal = Depends(_can_view),
                      service: AuroraService = Depends(get_aurora_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.layout(id_sistema, principal.id_empresa, body.model_dump()))


@router.post("/sistemas/{id_sistema}/pantallas")
def generate_screen(
    id_sistema: str,
    body: ScreenBody,
    descargar: bool = Query(False),
    principal: Principal = Depends(_can_view),
    service: AuroraService = Depends(get_aurora_service),
):
    with translate_errors(UNAVAILABLE):
        result = service.screen(id_sistema, principal.id_empresa, body.tipo, body.nombre_app, body.idioma)
    if descargar:
        return attachment(result["html"], f"{result['pantalla']}.html", exporters.MEDIA_TYPES["html"])
    return ok(result)
