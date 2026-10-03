"""
Nexus (DatabaseAgent) — esquema, procedimientos almacenados, DDL y respaldos sobre SQL Server kinetix.
Todo requiere un token de Sentinel salvo /salud.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from src.agents.agent_catalog import NEXUS, openapi_tag
from src.agents.database_agent.database_agent import TableDefinition
from src.agents.database_agent.dependencies import get_nexus_service
from src.agents.database_agent.service import VERSION, NexusService
from src.agents.security_agent.dependencies import get_security_service, require_permission, translate_errors
from src.agents.security_agent.models import Principal
from src.agents.security_agent.service import SecurityService

PERM_VIEW_SCHEMA = "esquema:ver"
PERM_MODIFY_SCHEMA = "esquema:modificar"
PERM_EXECUTE = "procedimientos:ejecutar"
PERM_BACKUPS = "respaldos:gestionar"
UNAVAILABLE = "Servicio de base de datos no disponible temporalmente"

router = APIRouter(prefix="/api/v1/nexus", tags=[openapi_tag(NEXUS)])
_can_view = require_permission(PERM_VIEW_SCHEMA)
_can_modify = require_permission(PERM_MODIFY_SCHEMA)
_can_execute = require_permission(PERM_EXECUTE)
_can_backup = require_permission(PERM_BACKUPS)


class ExecuteBody(BaseModel):
    parametros: Dict[str, Any] = Field(default_factory=dict)
    max_filas: Optional[int] = Field(None, ge=1)


class BackupBody(BaseModel):
    etiqueta: str = Field("manual", min_length=1, max_length=50)


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"estado": "exito", **payload}


@router.get("/salud")
def nexus_health(service: NexusService = Depends(get_nexus_service)) -> Dict[str, Any]:
    try:
        service.ping()
        database = "conectada"
    except Exception:
        database = "no disponible"
    return {
        "agente": NEXUS.codename,
        "estado": "activo" if database == "conectada" else "degradado",
        "base_datos": database,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/info", dependencies=[Depends(_can_view)])
def nexus_info(service: NexusService = Depends(get_nexus_service)) -> Dict[str, Any]:
    return {
        "id": "nexus",
        "agente": NEXUS.codename,
        "legacy_id": NEXUS.legacy_id,
        "version": VERSION,
        "descripcion": NEXUS.tagline,
        "motor": "SQL Server",
        "max_filas_por_conjunto": service.max_rows,
        "permisos": {
            "ver_esquema": PERM_VIEW_SCHEMA,
            "modificar_esquema": PERM_MODIFY_SCHEMA,
            "ejecutar_procedimientos": PERM_EXECUTE,
            "respaldos": PERM_BACKUPS,
        },
    }


@router.get("/esquema/tablas", dependencies=[Depends(_can_view)])
def list_tables(service: NexusService = Depends(get_nexus_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.tables())


@router.get("/esquema/tablas/{nombre}", dependencies=[Depends(_can_view)])
def describe_table(nombre: str, service: NexusService = Depends(get_nexus_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok({"tabla": service.table(nombre)})


@router.post("/esquema/ddl", dependencies=[Depends(_can_view)])
def generate_ddl(definition: TableDefinition, service: NexusService = Depends(get_nexus_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.generate_ddl(definition))


@router.post("/esquema/tablas", status_code=201)
def create_table(
    definition: TableDefinition,
    request: Request,
    principal: Principal = Depends(_can_modify),
    service: NexusService = Depends(get_nexus_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.create_table(definition)
        security.record_audit(principal, "nexus_crear_tabla", f"tabla:{result['tabla']}",
                              f"hash {result['hash_esquema']}", ip=_ip(request))
        return _ok(result)


@router.get("/procedimientos", dependencies=[Depends(_can_view)])
def list_procedures(service: NexusService = Depends(get_nexus_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.procedures())


@router.get("/procedimientos/{nombre}", dependencies=[Depends(_can_view)])
def procedure_detail(nombre: str, service: NexusService = Depends(get_nexus_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok({"procedimiento": service.procedure(nombre)})


@router.post("/procedimientos/{nombre}/ejecutar")
def execute_procedure(
    nombre: str,
    body: ExecuteBody,
    request: Request,
    principal: Principal = Depends(_can_execute),
    service: NexusService = Depends(get_nexus_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.execute_procedure(nombre, body.parametros, body.max_filas)
        security.record_audit(principal, "nexus_ejecutar_procedimiento", f"procedimiento:{result['procedimiento']}",
                              json.dumps({"parametros": result["parametros"]}, ensure_ascii=False), ip=_ip(request))
        return _ok(result)


@router.get("/respaldos", dependencies=[Depends(_can_backup)])
def list_backups(limite: int = Query(20, ge=1, le=200), service: NexusService = Depends(get_nexus_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.backups(limite))


@router.post("/respaldos", status_code=201)
def create_backup(
    body: BackupBody,
    request: Request,
    principal: Principal = Depends(_can_backup),
    service: NexusService = Depends(get_nexus_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.backup(body.etiqueta)
        security.record_audit(principal, "nexus_respaldo", f"respaldo:{result['nombre']}", result["archivo"], ip=_ip(request))
        return _ok({"respaldo": result})
