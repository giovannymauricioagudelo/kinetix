"""
Nexus (DatabaseAgent) — esquema, procedimientos almacenados, DDL y respaldos sobre varias conexiones:
kinetix (SQL Server, por defecto) y las declaradas en NEXUS_CONEXION_<NOMBRE> (SQL Server, PostgreSQL,
Firebird o MongoDB), elegidas con ?conexion=. También el registro de aplicaciones: cada aplicación elige
su motor y tiene su propia base (una por empresa o una multiempresa) registrada en kinetix, con migraciones
numeradas que se despliegan a cada base. El motor se puede cambiar después (esquema + copia de datos),
de forma revertible hasta completar el cambio.
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
from src.agents.database_agent.dependencies import (
    DEFAULT_CONNECTION,
    connection_names,
    connection_view,
    get_nexus_apps_service,
    get_nexus_service,
    invalid_connections,
)
from src.agents.database_agent.dialects import MOTORES
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
    motor: str = Field(..., description=" | ".join(MOTORES) + " (se puede cambiar después con cambio-motor)")
    conexion: Optional[str] = Field(None, max_length=40, description="Servidor de GET /aplicaciones/servidores; "
                                    "vacío = kinetix en SQL Server o la única conexión del motor")
    descripcion: Optional[str] = Field(None, max_length=500)
    id_solicitud: Optional[str] = Field(None, max_length=50, description="Solicitud de Cortex que originó la aplicación")
    seguridad_por_fila: bool = Field(True, description="Solo multiempresa en SQL Server o PostgreSQL: política de seguridad por fila")
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


class EquivalentBody(BaseModel):
    motor: str = Field(..., description=" | ".join(MOTORES))
    script: str = Field(..., min_length=1, description="Mismo efecto que la migración original, escrito para ese motor")


class EngineChangeBody(BaseModel):
    motor: str = Field(..., description=" | ".join(MOTORES))
    conexion: Optional[str] = Field(None, max_length=40, description="Vacío = conexión por defecto del motor")


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"estado": "exito", **payload}


def _connection(conexion: Optional[str] = Query(None, max_length=40, description="Conexión de GET /conexiones; vacío = kinetix")) -> str:
    return (conexion or DEFAULT_CONNECTION).strip().lower()


def _service(conexion: str = Depends(_connection)) -> NexusService:
    with translate_errors(UNAVAILABLE):
        return get_nexus_service(conexion)


def _resource(kind: str, name: str, conexion: str) -> str:
    return f"{kind}:{name}" if conexion == DEFAULT_CONNECTION else f"{kind}:{conexion}/{name}"


@router.get("/salud")
def nexus_health() -> Dict[str, Any]:
    try:
        get_nexus_service().ping()
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
def nexus_info(service: NexusService = Depends(_service)) -> Dict[str, Any]:
    return {
        "id": "nexus",
        "agente": NEXUS.codename,
        "legacy_id": NEXUS.legacy_id,
        "version": VERSION,
        "descripcion": NEXUS.tagline,
        "motor": service.info()["nombre_motor"],
        "conexion": service.info(),
        "motores_soportados": list(MOTORES),
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


@router.get("/conexiones", dependencies=[Depends(_can_view)])
def list_connections() -> Dict[str, Any]:
    connections = []
    for name in connection_names():
        with translate_errors(UNAVAILABLE):
            view = connection_view(name)
            service = get_nexus_service(name)
        try:
            service.ping()
            status = "conectada"
        except Exception:
            status = "no disponible"
        connections.append({**view, **service.info(), "estado": status})
    invalid = [{"nombre": name, "estado": "configuracion_invalida", "error": error}
               for name, error in sorted(invalid_connections().items())]
    return _ok({"total": len(connections), "conexiones": connections, "invalidas": invalid})


@router.get("/esquema/tablas", dependencies=[Depends(_can_view)])
def list_tables(service: NexusService = Depends(_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.tables())


@router.get("/esquema/tablas/{nombre}", dependencies=[Depends(_can_view)])
def describe_table(nombre: str, service: NexusService = Depends(_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok({"tabla": service.table(nombre)})


@router.post("/esquema/ddl", dependencies=[Depends(_can_view)])
def generate_ddl(
    definition: TableDefinition,
    motor: Optional[str] = Query(None, description=f"Genera para otro motor sin conectarse: {', '.join(MOTORES)}"),
    service: NexusService = Depends(_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.generate_ddl(definition, motor))


@router.post("/esquema/tablas", status_code=201)
def create_table(
    definition: TableDefinition,
    request: Request,
    conexion: str = Depends(_connection),
    principal: Principal = Depends(_can_modify),
    service: NexusService = Depends(_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.create_table(definition)
        security.record_audit(principal, "nexus_crear_tabla", _resource("tabla", result["tabla"], conexion),
                              f"{result['motor']} hash {result['hash_esquema']}", ip=_ip(request))
        return _ok(result)


@router.get("/procedimientos", dependencies=[Depends(_can_view)])
def list_procedures(service: NexusService = Depends(_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.procedures())


@router.get("/procedimientos/{nombre}", dependencies=[Depends(_can_view)])
def procedure_detail(nombre: str, service: NexusService = Depends(_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok({"procedimiento": service.procedure(nombre)})


@router.post("/procedimientos/{nombre}/ejecutar")
def execute_procedure(
    nombre: str,
    body: ExecuteBody,
    request: Request,
    conexion: str = Depends(_connection),
    principal: Principal = Depends(_can_execute),
    service: NexusService = Depends(_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.execute_procedure(nombre, body.parametros, body.max_filas)
        security.record_audit(principal, "nexus_ejecutar_procedimiento",
                              _resource("procedimiento", result["procedimiento"], conexion),
                              json.dumps({"parametros": result["parametros"]}, ensure_ascii=False), ip=_ip(request))
        return _ok(result)


@router.get("/respaldos", dependencies=[Depends(_can_backup)])
def list_backups(limite: int = Query(20, ge=1, le=200), service: NexusService = Depends(_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(service.backups(limite))


@router.post("/respaldos", status_code=201)
def create_backup(
    body: BackupBody,
    request: Request,
    conexion: str = Depends(_connection),
    principal: Principal = Depends(_can_backup),
    service: NexusService = Depends(_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.backup(body.etiqueta)
        security.record_audit(principal, "nexus_respaldo", _resource("respaldo", result["nombre"], conexion),
                              result["archivo"], ip=_ip(request))
        return _ok({"respaldo": result})


# ============================================================================ aplicaciones


@router.get("/aplicaciones")
def list_applications(principal: Principal = Depends(_can_view_apps),
                      apps: NexusAppService = Depends(get_nexus_apps_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(apps.list_apps(principal.id_empresa))


@router.get("/aplicaciones/servidores", dependencies=[Depends(_can_view_apps)])
def application_servers(apps: NexusAppService = Depends(get_nexus_apps_service)) -> Dict[str, Any]:
    """Conexiones donde se pueden crear bases de aplicaciones, con su motor."""
    with translate_errors(UNAVAILABLE):
        servers = apps.servers()
        return _ok({"total": len(servers), "servidores": servers, "motores_soportados": list(MOTORES)})


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
                              f"modelo {result['modelo_datos']}, motor {result['motor']} ({result['conexion']}), "
                              f"{len(result['bases_datos'])} base(s)", ip=_ip(request))
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


@router.post("/aplicaciones/{id_aplicacion}/migraciones/{numero}/equivalentes", status_code=201)
def add_migration_equivalent(
    id_aplicacion: str,
    numero: int,
    body: EquivalentBody,
    request: Request,
    principal: Principal = Depends(_can_manage_apps),
    apps: NexusAppService = Depends(get_nexus_apps_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    """Script equivalente de una migración SQL manual para otro motor (requisito para cambiar a ese motor)."""
    with translate_errors(UNAVAILABLE):
        result = apps.add_equivalent(principal.nombre_usuario, principal.id_empresa, id_aplicacion, numero, body.model_dump())
        security.record_audit(principal, "nexus_agregar_equivalente", f"aplicacion:{id_aplicacion}",
                              f"migración {numero} para {body.motor}", ip=_ip(request))
        return _ok(result)


@router.post("/aplicaciones/{id_aplicacion}/cambio-motor")
def change_application_engine(
    id_aplicacion: str,
    body: EngineChangeBody,
    request: Request,
    vista_previa: bool = Query(False, description="Solo muestra bloqueos y advertencias, sin cambiar nada"),
    principal: Principal = Depends(_can_deploy_apps),
    apps: NexusAppService = Depends(get_nexus_apps_service),
    security: SecurityService = Depends(get_security_service),
) -> Dict[str, Any]:
    """Pasa la aplicación a otro motor: despliega el esquema allí y copia los datos tabla por tabla.
    Las bases de origen no se tocan: el cambio se puede revertir hasta completarlo."""
    with translate_errors(UNAVAILABLE):
        result = apps.change_engine(principal.nombre_usuario, principal.id_empresa, id_aplicacion, body.model_dump(),
                                    vista_previa)
        if not vista_previa:
            change = result["cambio"]
            security.record_audit(principal, "nexus_cambiar_motor", f"aplicacion:{id_aplicacion}",
                                  f"{change['origen']['motor']}/{change['origen']['conexion']} -> "
                                  f"{change['destino']['motor']}/{change['destino']['conexion']}: {change['estado']}",
                                  ip=_ip(request))
        return _ok(result)


def _engine_change_action(action: str, audit: str):
    def endpoint(
        id_aplicacion: str,
        request: Request,
        principal: Principal = Depends(_can_deploy_apps),
        apps: NexusAppService = Depends(get_nexus_apps_service),
        security: SecurityService = Depends(get_security_service),
    ) -> Dict[str, Any]:
        with translate_errors(UNAVAILABLE):
            result = getattr(apps, action)(principal.nombre_usuario, principal.id_empresa, id_aplicacion)
            change = result["cambio"]
            security.record_audit(principal, audit, f"aplicacion:{id_aplicacion}",
                                  f"{change['id_cambio']}: {change['estado']}", ip=_ip(request))
            return _ok(result)
    return endpoint


router.add_api_route("/aplicaciones/{id_aplicacion}/cambio-motor/copiar-datos",
                     _engine_change_action("copy_engine_data", "nexus_copiar_datos_motor"), methods=["POST"],
                     summary="Reintenta el cambio de motor en curso: despliega lo pendiente y copia las tablas que falten")
router.add_api_route("/aplicaciones/{id_aplicacion}/cambio-motor/completar",
                     _engine_change_action("complete_engine_change", "nexus_completar_cambio_motor"), methods=["POST"],
                     summary="Cierra el cambio de motor con los datos copiados (ya no se puede revertir)")
router.add_api_route("/aplicaciones/{id_aplicacion}/cambio-motor/revertir",
                     _engine_change_action("revert_engine_change", "nexus_revertir_cambio_motor"), methods=["POST"],
                     summary="Devuelve la aplicación al motor de origen, con sus bases como estaban")


@router.get("/aplicaciones/{id_aplicacion}/cambio-motor")
def application_engine_changes(id_aplicacion: str, limite: int = Query(20, ge=1, le=200),
                               principal: Principal = Depends(_can_view_apps),
                               apps: NexusAppService = Depends(get_nexus_apps_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return _ok(apps.engine_changes(principal.id_empresa, id_aplicacion, limite))
