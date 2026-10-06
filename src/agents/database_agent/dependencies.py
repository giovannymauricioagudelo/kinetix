"""Instancias compartidas de NexusService (una por conexión) y NexusAppService.

La conexión por defecto es kinetix (SQL Server; NEXUS_CATALOG=memory para desarrollo sin SQL Server).
Las adicionales se declaran con NEXUS_CONEXION_<NOMBRE>=<url> (ver engines.py) y se crean al primer uso.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from src.agents.database_agent.app_registry import InMemoryAppRegistry
from src.agents.database_agent.app_service import NexusAppService
from src.agents.database_agent.catalog import InMemoryCatalog
from src.agents.database_agent.datastores import InMemoryDataStore
from src.agents.database_agent.dialects import MOTORES
from src.agents.database_agent.engines import ConnectionSpec, build_catalog, connection_urls, parse_connection_url
from src.agents.database_agent.provisioner import InMemoryProvisioner
from src.agents.database_agent.servers import Server, ServerCatalog
from src.agents.database_agent.service import NexusService
from src.agents.security_agent.models import NotFoundError

logger = logging.getLogger(__name__)

DEFAULT_CONNECTION = "kinetix"

_services: Dict[str, NexusService] = {}
_specs: Optional[Dict[str, ConnectionSpec]] = None
_invalid: Dict[str, str] = {}
_lock = threading.Lock()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _memory_mode() -> bool:
    return os.getenv("NEXUS_CATALOG", "sqlserver").strip().lower() == "memory"


def build_default_service() -> NexusService:
    backup_dir = os.getenv("NEXUS_BACKUP_DIR") or None
    max_rows = _int_env("NEXUS_MAX_ROWS", 1000)
    if _memory_mode():
        logger.warning("Nexus usa un catálogo en memoria: no hay conexión a SQL Server.")
        return NexusService(InMemoryCatalog(), backup_dir, max_rows)
    from src.agents.database_agent.catalog import SqlServerCatalog
    from src.agents.security_agent.config import load_sqlserver_settings
    from src.agents.sqlserver import SqlServerClient

    client = SqlServerClient(load_sqlserver_settings(), _int_env("NEXUS_QUERY_TIMEOUT_SECONDS", 30))
    catalog = SqlServerCatalog(client, _int_env("NEXUS_BACKUP_TIMEOUT_SECONDS", 600))
    return NexusService(catalog, backup_dir, max_rows)


def build_connection_service(spec: ConnectionSpec) -> NexusService:
    backup_dir = os.getenv(f"NEXUS_BACKUP_DIR_{spec.nombre.upper()}") or os.getenv("NEXUS_BACKUP_DIR") or None
    catalog = build_catalog(spec, _int_env("NEXUS_QUERY_TIMEOUT_SECONDS", 30), _int_env("NEXUS_BACKUP_TIMEOUT_SECONDS", 600))
    return NexusService(catalog, backup_dir, _int_env("NEXUS_MAX_ROWS", 1000))


def connection_specs() -> Dict[str, ConnectionSpec]:
    """Conexiones adicionales del entorno; las mal configuradas quedan en invalid_connections() sin tumbar a las demás."""
    global _specs
    if _specs is None:
        specs: Dict[str, ConnectionSpec] = {}
        for name, url in connection_urls(os.environ).items():
            if name == DEFAULT_CONNECTION:
                _invalid[name] = f"{DEFAULT_CONNECTION} está reservada para la base de control (SQLSERVER_*)"
                continue
            try:
                specs[name] = parse_connection_url(name, url)
            except ValueError as e:
                _invalid[name] = str(e)
                logger.error("Conexión de Nexus %s inválida: %s", name, e)
        _specs = specs
    return _specs


def invalid_connections() -> Dict[str, str]:
    connection_specs()
    return dict(_invalid)


def connection_names() -> List[str]:
    extra = set(connection_specs()) | set(_services)
    extra.discard(DEFAULT_CONNECTION)
    return [DEFAULT_CONNECTION, *sorted(extra)]


def connection_view(name: str) -> Dict[str, Any]:
    """Datos públicos de la conexión (sin credenciales)."""
    spec = connection_specs().get(name)
    if spec is not None:
        return {**spec.public_view(), "por_defecto": False}
    view: Dict[str, Any] = {"nombre": name, "motor": get_nexus_service(name).motor, "host": None, "base_datos": None,
                            "por_defecto": name == DEFAULT_CONNECTION}
    if name == DEFAULT_CONNECTION and not _memory_mode():
        from src.agents.security_agent.config import load_sqlserver_settings

        settings = load_sqlserver_settings()
        view.update(host=settings.host, base_datos=settings.database)
    return view


def get_nexus_service(conexion: Optional[str] = None) -> NexusService:
    name = (conexion or DEFAULT_CONNECTION).strip().lower()
    service = _services.get(name)
    if service is not None:
        return service
    with _lock:
        if name not in _services:
            if name == DEFAULT_CONNECTION:
                _services[name] = build_default_service()
            else:
                spec = connection_specs().get(name)
                if spec is None:
                    detail = _invalid.get(name)
                    raise NotFoundError(f"Conexión mal configurada: {name} ({detail})" if detail
                                        else f"Conexión no encontrada: {name}")
                _services[name] = build_connection_service(spec)
        return _services[name]


def set_nexus_service(service: Optional[NexusService], conexion: str = DEFAULT_CONNECTION) -> None:
    if service is None:
        _services.pop(conexion, None)
    else:
        _services[conexion] = service


def reset_nexus_connections() -> None:
    """Olvida servicios y vuelve a leer NEXUS_CONEXION_* en el próximo uso."""
    global _specs
    with _lock:
        _services.clear()
        _invalid.clear()
        _specs = None


_apps_service: Optional[NexusAppService] = None


def _memory_server(nombre: str, motor: str) -> Server:
    return Server(nombre, motor, InMemoryProvisioner(), InMemoryDataStore(motor, create_on_write=True))


def build_app_servers() -> ServerCatalog:
    """kinetix (SQL Server) más cada NEXUS_CONEXION_*: son los servidores donde pueden vivir las aplicaciones."""
    specs = connection_specs()
    if _memory_mode():
        servers = [_memory_server(DEFAULT_CONNECTION, "sqlserver"), *(_memory_server(s.nombre, s.motor) for s in specs.values())]
        configured = {s.motor for s in servers}
        servers.extend(_memory_server(f"memoria_{motor}", motor) for motor in MOTORES if motor not in configured)
        return ServerCatalog(servers)
    from src.agents.database_agent.datastores import SqlServerDataStore, build_datastore
    from src.agents.database_agent.engine_provisioners import build_provisioner
    from src.agents.database_agent.provisioner import SqlServerProvisioner
    from src.agents.security_agent.config import load_sqlserver_settings

    deploy_timeout = _int_env("NEXUS_DEPLOY_TIMEOUT_SECONDS", 120)
    lock_timeout = _int_env("NEXUS_DEPLOY_LOCK_TIMEOUT_MS", 30000)
    copy_timeout = _int_env("NEXUS_COPY_TIMEOUT_SECONDS", 600)
    settings = load_sqlserver_settings()
    servers = [Server(DEFAULT_CONNECTION, "sqlserver", SqlServerProvisioner(settings, deploy_timeout, lock_timeout),
                      SqlServerDataStore(settings, copy_timeout))]
    servers.extend(Server(s.nombre, s.motor, build_provisioner(s, deploy_timeout, lock_timeout), build_datastore(s, copy_timeout))
                   for s in specs.values())
    return ServerCatalog(servers)


def build_default_apps_service() -> NexusAppService:
    if _memory_mode():
        logger.warning("Nexus usa un registro de aplicaciones en memoria: no se crean bases reales.")
        return NexusAppService(InMemoryAppRegistry(), build_app_servers())
    from src.agents.database_agent.app_registry import SqlServerAppRegistry
    from src.agents.security_agent.config import load_sqlserver_settings
    from src.agents.sqlserver import SqlServerClient

    registry = SqlServerAppRegistry(SqlServerClient(load_sqlserver_settings(), _int_env("NEXUS_QUERY_TIMEOUT_SECONDS", 30)))
    return NexusAppService(registry, build_app_servers(), copy_batch=_int_env("NEXUS_COPY_BATCH", 1000))


def get_nexus_apps_service() -> NexusAppService:
    global _apps_service
    if _apps_service is None:
        with _lock:
            if _apps_service is None:
                _apps_service = build_default_apps_service()
    return _apps_service


def set_nexus_apps_service(service: Optional[NexusAppService]) -> None:
    global _apps_service
    _apps_service = service
