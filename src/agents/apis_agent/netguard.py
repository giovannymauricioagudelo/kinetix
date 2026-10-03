"""
Protección SSRF de Synapse: solo URLs http(s) hacia direcciones públicas, sin credenciales embebidas ni rutas
que escapen de la URL base. El host se resuelve antes de cada llamada y las redirecciones nunca se siguen.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Callable, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit

from src.agents.security_agent.models import InvalidInputError

Resolver = Callable[[str, int], List[str]]

_PATH = re.compile(r"^/[A-Za-z0-9\-._~!$&'()*+,;=:@%/]*$")
MAX_PATH = 2000


def system_resolver(host: str, port: int) -> List[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


def _is_public(raw_ip: str) -> bool:
    address = ipaddress.ip_address(raw_ip.split("%", 1)[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


class NetworkPolicy:
    def __init__(self, allow_http: bool = False, allowed_private_hosts: Iterable[str] = (),
                 resolver: Resolver = system_resolver) -> None:
        self.allow_http = allow_http
        self.allowed_private_hosts = frozenset(h.strip().lower() for h in allowed_private_hosts if h.strip())
        self._resolve = resolver

    def check_base_url(self, url: str) -> str:
        parts = urlsplit((url or "").strip())
        schemes = ("https", "http") if self.allow_http else ("https",)
        if parts.scheme not in schemes:
            raise InvalidInputError(f"url_base debe usar {' o '.join(schemes)}")
        if not parts.hostname or parts.username or parts.password:
            raise InvalidInputError("url_base debe tener un host y no puede incluir usuario ni contraseña")
        if parts.query or parts.fragment:
            raise InvalidInputError("url_base no puede tener parámetros de consulta ni fragmento")
        try:
            parts.port
        except ValueError:
            raise InvalidInputError("url_base tiene un puerto inválido") from None
        path = parts.path.rstrip("/")
        if (path and not _PATH.match(path)) or ".." in path.split("/"):
            raise InvalidInputError("url_base tiene una ruta inválida")
        return urlunsplit((parts.scheme, parts.netloc.lower(), path, "", ""))

    def check_host(self, host: Optional[str], port: int) -> None:
        if not host:
            raise InvalidInputError("Destino sin host")
        if host.lower() in self.allowed_private_hosts:
            return
        try:
            addresses = self._resolve(host, port)
        except (socket.gaierror, UnicodeError, OSError):
            raise InvalidInputError(f"No se pudo resolver el host {host}") from None
        if not addresses:
            raise InvalidInputError(f"No se pudo resolver el host {host}")
        for raw in addresses:
            if not _is_public(raw):
                raise InvalidInputError(f"{host} resuelve a una dirección no pública ({raw}). Si es intencional, agrega el host a "
                                        "SYNAPSE_HOSTS_PRIVADOS_PERMITIDOS")

    def check_url(self, url: str) -> None:
        parts = urlsplit(url)
        self.check_host(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))


def check_path(path: str) -> str:
    path = (path or "").strip() or "/"
    if len(path) > MAX_PATH or not _PATH.match(path) or path.startswith("//") or ".." in path.split("/"):
        raise InvalidInputError("ruta inválida: debe empezar con '/', sin '..', esquema ni host (los parámetros van en 'consulta')")
    return path
