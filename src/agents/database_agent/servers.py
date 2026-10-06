"""Servidores donde Nexus crea las bases de las aplicaciones: la conexión kinetix (SQL Server) y las NEXUS_CONEXION_*."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from src.agents.database_agent.datastores import DataStore
from src.agents.database_agent.provisioner import Provisioner
from src.agents.security_agent.models import InvalidInputError, NotFoundError

DEFAULT_SERVER = "kinetix"


@dataclass(frozen=True)
class Server:
    nombre: str
    motor: str
    provisioner: Provisioner
    datos: Optional[DataStore] = None


class ServerCatalog:
    def __init__(self, servers: Iterable[Server]) -> None:
        self._servers: Dict[str, Server] = {s.nombre: s for s in servers}

    def get(self, nombre: str) -> Server:
        server = self._servers.get(nombre)
        if server is None:
            raise NotFoundError(f"Conexión no configurada: {nombre}")
        return server

    def names(self) -> List[str]:
        return sorted(self._servers)

    def motors(self) -> List[str]:
        return sorted({s.motor for s in self._servers.values()})

    def default_for(self, motor: str) -> str:
        """Conexión por defecto del motor: kinetix para SQL Server; en otro motor, la única configurada."""
        if motor == "sqlserver" and DEFAULT_SERVER in self._servers:
            return DEFAULT_SERVER
        candidates = sorted(s.nombre for s in self._servers.values() if s.motor == motor)
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise InvalidInputError(f"No hay ninguna conexión {motor} configurada (NEXUS_CONEXION_<NOMBRE>)")
        raise InvalidInputError(f"Hay varias conexiones {motor} ({', '.join(candidates)}): indica conexion")

    def resolve(self, motor: str, conexion: Optional[str]) -> Server:
        server = self.get(conexion) if conexion else self.get(self.default_for(motor))
        if server.motor != motor:
            raise InvalidInputError(f"La conexión {server.nombre} es {server.motor}, no {motor}")
        return server

    def views(self) -> List[Dict[str, str]]:
        return [{"nombre": s.nombre, "motor": s.motor} for s in sorted(self._servers.values(), key=lambda s: s.nombre)]
