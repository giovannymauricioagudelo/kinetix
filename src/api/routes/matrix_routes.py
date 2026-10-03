"""
Matrix (BusinessRulesAgent) — reglas de negocio sobre SQL Server kinetix.
Todo requiere un token de Sentinel salvo /salud.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from src.agents.agent_catalog import MATRIX, openapi_tag
from src.agents.business_rules_agent.dependencies import get_rules_service
from src.agents.business_rules_agent.service import VERSION, RulesService
from src.agents.security_agent.dependencies import get_security_service, require_permission, translate_errors
from src.agents.security_agent.models import Principal
from src.agents.security_agent.service import SecurityService

PERM_VIEW = "reglas:ver"
PERM_MANAGE = "reglas:gestionar"
PERM_EVALUATE = "reglas:evaluar"
UNAVAILABLE = "Servicio de reglas no disponible temporalmente"

router = APIRouter(prefix="/api/v1/matrix", tags=[openapi_tag(MATRIX)])
_can_view = require_permission(PERM_VIEW)
_can_manage = require_permission(PERM_MANAGE)
_can_evaluate = require_permission(PERM_EVALUATE)


class ConditionBody(BaseModel):
    campo: str = Field(..., min_length=1, max_length=200)
    operador: str = Field("eq", max_length=20)
    valor: Any = None
    operador_logico: str = Field("AND", max_length=5)


class ActionBody(BaseModel):
    tipo: str = Field(..., max_length=50)
    detalles: Union[Dict[str, Any], str, None] = None
    critica: bool = False

    def as_dict(self) -> Dict[str, Any]:
        detalles = {"mensaje": self.detalles} if isinstance(self.detalles, str) else (self.detalles or {})
        return {"tipo": self.tipo, "detalles": detalles, "critica": self.critica}


class RuleBody(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=255)
    descripcion: Optional[str] = Field(None, max_length=4000)
    nivel_alcance: str = "global"
    linea_negocio: Optional[str] = Field(None, max_length=50)
    id_empresa: Optional[int] = None
    estado: str = "activa"
    prioridad: int = Field(50, ge=0, le=1000)
    condiciones: List[ConditionBody] = Field(default_factory=list, max_length=50)
    acciones: List[ActionBody] = Field(..., min_length=1, max_length=50)

    def as_dict(self) -> Dict[str, Any]:
        data = self.model_dump(exclude={"condiciones", "acciones"})
        data["condiciones"] = [c.model_dump() for c in self.condiciones]
        data["acciones"] = [a.as_dict() for a in self.acciones]
        return data


class NewRuleBody(RuleBody):
    id_regla: str = Field(..., min_length=1, max_length=100)

    def as_dict(self) -> Dict[str, Any]:
        return {**super().as_dict(), "id_regla": self.id_regla}


class EvaluateBody(BaseModel):
    contexto: Dict[str, Any] = Field(default_factory=dict)
    id_empresa: Optional[int] = None
    linea_negocio: Optional[str] = Field(None, max_length=50)


class ScenarioBody(EvaluateBody):
    esperado: Union[bool, str, None] = None


class ScenariosBody(BaseModel):
    escenarios: List[ScenarioBody] = Field(..., min_length=1, max_length=50)


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"estado": "exito", **payload}


@router.get("/salud")
def matrix_health(service: RulesService = Depends(get_rules_service)) -> Dict[str, Any]:
    try:
        service.ping()
        database = "conectada"
    except Exception:
        database = "no disponible"
    return {
        "agente": MATRIX.codename,
        "estado": "activo" if database == "conectada" else "degradado",
        "base_datos": database,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/info", dependencies=[Depends(_can_view)])
def matrix_info() -> Dict[str, Any]:
    return {
        "id": "matrix",
        "agente": MATRIX.codename,
        "legacy_id": MATRIX.legacy_id,
        "version": VERSION,
        "descripcion": MATRIX.tagline,
        "alcances": ["global", "linea_negocio", "empresa"],
        "operadores": ["eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "contains", "regex"],
        "acciones": ["calculate", "set_field", "notify", "block", "allow", "log"],
        "permisos": {"ver": PERM_VIEW, "gestionar": PERM_MANAGE, "evaluar": PERM_EVALUATE},
    }


@router.get("/reglas", dependencies=[Depends(_can_view)])
def list_rules(
    nivel_alcance: Optional[str] = None,
    id_empresa: Optional[int] = None,
    linea_negocio: Optional[str] = None,
    estado: Optional[str] = None,
    service: RulesService = Depends(get_rules_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.list_rules(nivel_alcance, id_empresa, linea_negocio, estado))


@router.get("/reglas/{id_regla}", dependencies=[Depends(_can_view)])
def get_rule(id_regla: str, service: RulesService = Depends(get_rules_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok({"regla": service.get_rule(id_regla)})


@router.post("/reglas", status_code=201)
def create_rule(
    body: NewRuleBody,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: RulesService = Depends(get_rules_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        rule = service.create_rule(body.as_dict(), principal.nombre_usuario)
        security.record_audit(principal, "matrix_regla_crear", f"regla:{rule['id_regla']}", rule["nombre"], ip=_ip(request))
        return _ok({"regla": rule})


@router.put("/reglas/{id_regla}")
def update_rule(
    id_regla: str,
    body: RuleBody,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: RulesService = Depends(get_rules_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        rule = service.update_rule(id_regla, body.as_dict(), principal.nombre_usuario)
        security.record_audit(principal, "matrix_regla_actualizar", f"regla:{id_regla}", rule["nombre"], ip=_ip(request))
        return _ok({"regla": rule})


@router.delete("/reglas/{id_regla}")
def archive_rule(
    id_regla: str,
    request: Request,
    principal: Principal = Depends(_can_manage),
    service: RulesService = Depends(get_rules_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.archive_rule(id_regla, principal.nombre_usuario)
        security.record_audit(principal, "matrix_regla_archivar", f"regla:{id_regla}", ip=_ip(request))
        return _ok(result)


@router.post("/reglas/{id_regla}/evaluar")
def evaluate_rule(
    id_regla: str,
    body: EvaluateBody,
    principal: Principal = Depends(_can_evaluate),
    service: RulesService = Depends(get_rules_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.evaluate_rule(id_regla, body.contexto, principal.nombre_usuario, body.id_empresa, body.linea_negocio))


@router.post("/evaluar")
def evaluate_applicable(
    body: EvaluateBody,
    principal: Principal = Depends(_can_evaluate),
    service: RulesService = Depends(get_rules_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.evaluate_applicable(body.contexto, principal.nombre_usuario, body.id_empresa, body.linea_negocio))


@router.post("/reglas/{id_regla}/probar", dependencies=[Depends(_can_evaluate)])
def try_rule(id_regla: str, body: ScenariosBody, service: RulesService = Depends(get_rules_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.test_rule(id_regla, [s.model_dump() for s in body.escenarios]))


@router.get("/auditoria", dependencies=[Depends(_can_view)])
def audit(
    id_regla: Optional[str] = None,
    dias: int = Query(30, ge=1, le=365),
    limite: int = Query(100, ge=1, le=500),
    service: RulesService = Depends(get_rules_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.audit(id_regla, dias, limite))


@router.get("/analitica", dependencies=[Depends(_can_view)])
def analytics(dias: int = Query(30, ge=1, le=365), service: RulesService = Depends(get_rules_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.analytics(dias))
