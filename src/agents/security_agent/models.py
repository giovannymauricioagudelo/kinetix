"""Entidades y errores de dominio de Sentinel."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class User:
    id: str
    nombre_usuario: str
    id_empresa: str
    hash_contrasena: str
    estado: str = "activo"


@dataclass(frozen=True)
class MfaRecord:
    id_usuario: str
    secret: str
    habilitado: bool
    ultimo_paso: Optional[int] = None


@dataclass(frozen=True)
class AuditEntry:
    id_empresa: str
    accion: str
    resultado: str
    id_usuario: Optional[str] = None
    recurso: Optional[str] = None
    detalles: Optional[str] = None
    direccion_ip: Optional[str] = None
    fecha: Optional[datetime] = None


@dataclass(frozen=True)
class Principal:
    """Usuario autenticado extraído de un token de acceso válido."""

    id: str
    nombre_usuario: str
    id_empresa: str
    jti: str
    expira: datetime
    metodos: List[str] = field(default_factory=list)


class AuditResult:
    SUCCESS = "exito"
    BAD_CREDENTIALS = "fallo_credenciales"
    PERMISSION_DENIED = "fallo_permiso"
    DENIED = "denegada"


class SecurityError(Exception):
    """Base de los errores que Sentinel expone al cliente con un mensaje seguro."""


class AuthenticationError(SecurityError):
    pass


class PermissionDeniedError(SecurityError):
    pass


class ConflictError(SecurityError):
    pass


class InvalidInputError(SecurityError):
    pass


class NotFoundError(SecurityError):
    pass


class RateLimitedError(SecurityError):
    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
