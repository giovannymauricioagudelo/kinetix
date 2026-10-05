"""
Nexus (DatabaseAgent) — esquema, procedimientos almacenados, DDL y respaldos sobre SQL Server kinetix,
y registro de aplicaciones: cada aplicación tiene su propia base (una por empresa o una multiempresa)
registrada en kinetix, con migraciones numeradas que se despliegan a cada base.
Todo requiere un token de Sentinel salvo /salud.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from src.agents.agent_catalog import NEXUS, openapi_tag
from src.agents.database_agent.app_registry import DATA_MODELS
from src.agents.database_agent.app_service import NexusAppService
from src.agents.database_agent.database_agent import ColumnDefinition, TableDefinition
from src.agents.database_agent.dependencies import get_nexus_apps_service, get_nexus_service
from src.agents.database_agent.service import VERSION, NexusService
from src.agents.security_agent.dependencies import get_security_service, require_permission, translate_errors
from src.agents.security_agent.models import Principal
from src.agents.security_agent.service import SecurityService

PERM_VIEW_SCHEMA = "esquema:ver"
PERM_MODIFY_SCHEMA = "esquema:modificar"
PERM_EXECUTE = "procedimientos:ejecutar"
PERM_BACKUPS = "respaldos:gestionar"
PERM_VIEW_APPS = "aplicaciones:ver"
PERM_MANAGE_APPS = "aplicaciones:gestionar"
PERM_DEPLOY_APPS = "aplicaciones:desplegar"
UNAVAILABLE = "Servicio de base de datos no disponible temporalmente"

router = APIRouter(prefix="/api/v1/nexus", tags=[openapi_tag(NEXUS)])
_can_view = require_permission(PERM_VIEW_SCHEMA)
_can_modify = require_permission(PERM_MODIFY_SCHEMA)
_can_execute = require_permission(PERM_EXECUTE)
_can_backup = require_permission(PERM_BACKUPS)
_can_view_apps = require_permission(PERM_VIEW_APPS)
_can_manage_apps = require_permission(PERM_MANAGE_APPS)
_can_deploy_apps = require_permission(PERM_DEPLOY_APPS)


class ExecuteBody(BaseModel):
    parametros: Dict[str, Any] = Field(default_factory=dict)
    max_filas: Optional[int] = Field(None, ge=1)


class BackupBody(BaseModel):
    etiqueta: str = Field("manual", min_length=1, max_length=50)


class CompanyBody(BaseModel):
    id_empresa: str = Field(..., min_length=1, max_length=30, description="Minúsculas, números o '_'")
    nombre: str = Field(..., min_length=1, max_length=200)


class ApplicationBody(BaseModel):
    id_aplicacion: str = Field(..., min_length=2, max_length=30, description="Nombra la base: {app} o {app}_{empresa}")
    nombre: str = Field(..., min_length=1, max_length=100)
    modelo_datos: str = Field(..., description=" o ".join(DATA_MODELS))
    descripcion: Optional[str] = Field(None, max_length=500)
    id_solicitud: Optional[str] = Field(None, max_length=50, description="Solicitud de Cortex que originó la aplicación")
    seguridad_por_fila: bool = Field(True, description="Solo multiempresa: política RLS por SESSION_CONTEXT('id_empresa')")
    empresas: List[CompanyBody] = Field(default_factory=list, max_length=200)


class AppTableBody(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    esquema: str = Field("dbo", min_length=1, max_length=100)
    columnas: List[ColumnDefinition] = Field(..., min_length=1, max_length=200)
    descripcion: Optional[str] = Field(None, max_length=500)
    columnas_auditoria: bool = True


class MigrationBody(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    script: str = Field(..., min_length=1)
    descripcion: Optional[str] = Field(None, max_length=500)


class DeployBody(BaseModel):
    id_empresa: Optional[str] = Field(None, max_length=30, description="Solo por_empresa: despliega únicamente esa base")


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
            "ver_aplicaciones": PERM_VIEW_APPS,
            "gestionar_aplicaciones": PERM_MANAGE_APPS,
            "desplegar_aplicaciones": PERM_DEPLOY_APPS,
        },
        "modelos_datos": {
            "por_empresa": "Una base independiente por empresa: {app}_{empresa}",
            "multiempresa": "Una base compartida {app} con id_empresa, FK a dbo.empresas y seguridad por fila",
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


# ============================================================================ aplicaciones


@router.get("/aplicaciones")
def list_applications(principal: Principal = Depends(_can_view_apps),
                      apps: NexusAppService = Depends(get_nexus_apps_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(apps.list_apps(principal.id_empresa))


@router.post("/aplicaciones", status_code=201)
def register_application(
    body: ApplicationBody,
    request: Request,
    principal: Principal = Depends(_can_manage_apps),
    apps: NexusAppService = Depends(get_nexus_apps_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = apps.register_app(principal.nombre_usuario, principal.id_empresa, body.model_dump())
        security.record_audit(principal, "nexus_registrar_aplicacion", f"aplicacion:{result['id_aplicacion']}",
                              f"modelo {result['modelo_datos']}, {len(result['bases_datos'])} base(s)", ip=_ip(request))
        return _ok({"aplicacion": result})


@router.get("/aplicaciones/{id_aplicacion}")
def application_detail(id_aplicacion: str, principal: Principal = Depends(_can_view_apps),
                       apps: NexusAppService = Depends(get_nexus_apps_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok({"aplicacion": apps.get_app(principal.id_empresa, id_aplicacion)})


@router.post("/aplicaciones/{id_aplicacion}/empresas", status_code=201)
def add_application_company(
    id_aplicacion: str,
    body: CompanyBody,
    request: Request,
    principal: Principal = Depends(_can_manage_apps),
    apps: NexusAppService = Depends(get_nexus_apps_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = apps.add_company(principal.nombre_usuario, principal.id_empresa, id_aplicacion, body.model_dump())
        security.record_audit(principal, "nexus_agregar_empresa", f"aplicacion:{id_aplicacion}",
                              f"empresa {result['id_empresa']} en {result['nombre_base']}", ip=_ip(request))
        return _ok({"empresa": result})


@router.post("/aplicaciones/{id_aplicacion}/tablas", status_code=201)
def define_application_table(
    id_aplicacion: str,
    body: AppTableBody,
    request: Request,
    vista_previa: bool = Query(False, description="Solo genera el DDL según el modelo de datos, sin registrarlo"),
    principal: Principal = Depends(_can_manage_apps),
    apps: NexusAppService = Depends(get_nexus_apps_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = apps.table(principal.nombre_usuario, principal.id_empresa, id_aplicacion, body.model_dump(), vista_previa)
        if result["registrada"]:
            security.record_audit(principal, "nexus_definir_tabla", f"aplicacion:{id_aplicacion}",
                                  f"{result['tabla']} (migración {result['migracion']['numero']})", ip=_ip(request))
        return _ok(result)


@router.post("/aplicaciones/{id_aplicacion}/migraciones", status_code=201)
def add_application_migration(
    id_aplicacion: str,
    body: MigrationBody,
    request: Request,
    principal: Principal = Depends(_can_manage_apps),
    apps: NexusAppService = Depends(get_nexus_apps_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = apps.add_migration(principal.nombre_usuario, principal.id_empresa, id_aplicacion, body.model_dump())
        migration = result["migracion"]
        security.record_audit(principal, "nexus_agregar_migracion", f"aplicacion:{id_aplicacion}",
                              f"{migration['numero']} {migration['nombre']} sha256 {migration['checksum']}", ip=_ip(request))
        return _ok(result)


@router.get("/aplicaciones/{id_aplicacion}/migraciones/{numero}")
def application_migration(id_aplicacion: str, numero: int, principal: Principal = Depends(_can_view_apps),
                          apps: NexusAppService = Depends(get_nexus_apps_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok({"migracion": apps.migration(principal.id_empresa, id_aplicacion, numero)})


@router.post("/aplicaciones/{id_aplicacion}/desplegar")
def deploy_application(
    id_aplicacion: str,
    body: DeployBody,
    request: Request,
    principal: Principal = Depends(_can_deploy_apps),
    apps: NexusAppService = Depends(get_nexus_apps_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = apps.deploy(principal.nombre_usuario, principal.id_empresa, id_aplicacion, body.id_empresa)
        summary = ", ".join(f"{d['nombre_base']}={d['estado']}" for d in result["despliegues"])
        security.record_audit(principal, "nexus_desplegar_aplicacion", f"aplicacion:{id_aplicacion}",
                              f"v{result['version_objetivo']}: {summary}"[:1000], ip=_ip(request))
        return _ok(result)


@router.get("/aplicaciones/{id_aplicacion}/despliegues")
def application_deployments(id_aplicacion: str, limite: int = Query(20, ge=1, le=200),
                            principal: Principal = Depends(_can_view_apps),
                            apps: NexusAppService = Depends(get_nexus_apps_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(apps.deployments(principal.id_empresa, id_aplicacion, limite))
