"""Contrato de persistencia de Sentinel y su implementación en memoria (pruebas y desarrollo)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import replace
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import bcrypt

from src.agents.security_agent.models import AuditEntry, AuditResult, MfaRecord, User

SESSION_STARTED = "inicio_sesion"


class SecurityRepository(ABC):
    # ---- usuarios
    @abstractmethod
    def get_user(self, nombre_usuario: str, id_empresa: str) -> Optional[User]: ...

    @abstractmethod
    def get_user_by_id(self, id_usuario: str) -> Optional[User]: ...

    @abstractmethod
    def count_users_with_mfa(self, id_empresa: str) -> Tuple[int, int]:
        """(usuarios activos, usuarios activos con MFA habilitado)."""

    # ---- MFA
    @abstractmethod
    def get_mfa(self, id_usuario: str) -> Optional[MfaRecord]: ...

    @abstractmethod
    def save_pending_mfa(self, id_usuario: str, secret: str, now: datetime) -> None: ...

    @abstractmethod
    def enable_mfa(self, id_usuario: str, now: datetime) -> None: ...

    @abstractmethod
    def disable_mfa(self, id_usuario: str, now: datetime) -> None: ...

    @abstractmethod
    def claim_totp_step(self, id_usuario: str, step: int) -> bool:
        """Registra el paso TOTP usado; False si ya se usó ese paso o uno posterior."""

    # ---- fichas
    @abstractmethod
    def store_refresh_token(self, jti: str, id_usuario: str, expira: datetime) -> None: ...

    @abstractmethod
    def get_refresh_token(self, jti: str) -> Optional[Tuple[str, bool]]:
        """(id_usuario, revocada) o None si la ficha no existe."""

    @abstractmethod
    def revoke_refresh_token(self, jti: str, now: datetime) -> bool:
        """Revoca la ficha; True si estaba activa."""

    @abstractmethod
    def revoke_all_refresh_tokens(self, id_usuario: str, now: datetime) -> int: ...

    @abstractmethod
    def revoke_access_token(self, jti: str, id_usuario: str, expira: datetime, now: datetime) -> None: ...

    @abstractmethod
    def is_access_token_revoked(self, jti: str) -> bool: ...

    # ---- RBAC
    @abstractmethod
    def get_roles_and_permissions(self, id_usuario: str) -> Tuple[List[str], List[str]]:
        """(ids de rol, permisos 'recurso:accion')."""

    @abstractmethod
    def get_role_tenant(self, id_rol: str) -> Optional[str]: ...

    @abstractmethod
    def permission_exists(self, id_permiso: str) -> bool: ...

    @abstractmethod
    def assign_role(self, id_usuario: str, id_rol: str) -> bool:
        """False si el usuario ya tenía el rol."""

    @abstractmethod
    def grant_permission(self, id_rol: str, id_permiso: str) -> bool:
        """False si el rol ya tenía el permiso."""

    # ---- auditoría
    @abstractmethod
    def add_audit(self, entry: AuditEntry) -> None: ...

    @abstractmethod
    def login_failures_since(self, recurso: str, since: datetime) -> List[datetime]:
        """Fallos de credenciales de una cuenta desde `since` e insertados después de su último inicio de sesión."""

    @abstractmethod
    def list_audit(
        self,
        id_empresa: str,
        desde: Optional[datetime],
        hasta: Optional[datetime],
        accion: Optional[str],
        id_usuario: Optional[str],
        resultado: Optional[str],
        limit: int,
        offset: int,
    ) -> Tuple[int, List[AuditEntry]]: ...

    @abstractmethod
    def audit_summary(self, id_empresa: str, desde: datetime) -> List[Tuple[str, str, int]]:
        """Conteos (accion, resultado, total) desde una fecha."""

    def ping(self) -> None:
        """Lanza excepción si la persistencia no está disponible."""


class InMemorySecurityRepository(SecurityRepository):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users: Dict[str, User] = {}
        self._mfa: Dict[str, MfaRecord] = {}
        self._refresh: Dict[str, Tuple[str, datetime, bool]] = {}
        self._revoked_access: Dict[str, datetime] = {}
        self._roles: Dict[str, str] = {}
        self._permissions: Dict[str, str] = {}
        self._user_roles: Dict[str, Set[str]] = {}
        self._role_permissions: Dict[str, Set[str]] = {}
        self._audit: List[AuditEntry] = []

    # ---- datos semilla
    def add_user(self, id_usuario: str, nombre_usuario: str, id_empresa: str, contrasena: str, estado: str = "activo") -> User:
        hashed = bcrypt.hashpw(contrasena.encode(), bcrypt.gensalt(rounds=4)).decode()
        user = User(id_usuario, nombre_usuario, id_empresa, hashed, estado)
        self._users[id_usuario] = user
        return user

    def add_role(self, id_rol: str, id_empresa: str) -> None:
        self._roles[id_rol] = id_empresa

    def add_permission(self, id_permiso: str, recurso: str, accion: str) -> None:
        self._permissions[id_permiso] = f"{recurso}:{accion}"

    # ---- usuarios
    def get_user(self, nombre_usuario: str, id_empresa: str) -> Optional[User]:
        return next(
            (u for u in self._users.values() if u.nombre_usuario == nombre_usuario and u.id_empresa == id_empresa),
            None,
        )

    def get_user_by_id(self, id_usuario: str) -> Optional[User]:
        return self._users.get(id_usuario)

    def count_users_with_mfa(self, id_empresa: str) -> Tuple[int, int]:
        active = [u for u in self._users.values() if u.id_empresa == id_empresa and u.estado == "activo"]
        with_mfa = [u for u in active if (r := self._mfa.get(u.id)) is not None and r.habilitado]
        return len(active), len(with_mfa)

    # ---- MFA
    def get_mfa(self, id_usuario: str) -> Optional[MfaRecord]:
        return self._mfa.get(id_usuario)

    def save_pending_mfa(self, id_usuario: str, secret: str, now: datetime) -> None:
        self._mfa[id_usuario] = MfaRecord(id_usuario, secret, False, None)

    def enable_mfa(self, id_usuario: str, now: datetime) -> None:
        self._mfa[id_usuario] = replace(self._mfa[id_usuario], habilitado=True)

    def disable_mfa(self, id_usuario: str, now: datetime) -> None:
        self._mfa[id_usuario] = replace(self._mfa[id_usuario], habilitado=False)

    def claim_totp_step(self, id_usuario: str, step: int) -> bool:
        with self._lock:
            record = self._mfa.get(id_usuario)
            if record is None or (record.ultimo_paso is not None and record.ultimo_paso >= step):
                return False
            self._mfa[id_usuario] = replace(record, ultimo_paso=step)
            return True

    # ---- fichas
    def store_refresh_token(self, jti: str, id_usuario: str, expira: datetime) -> None:
        self._refresh[jti] = (id_usuario, expira, False)

    def get_refresh_token(self, jti: str) -> Optional[Tuple[str, bool]]:
        token = self._refresh.get(jti)
        return (token[0], token[2]) if token else None

    def revoke_refresh_token(self, jti: str, now: datetime) -> bool:
        with self._lock:
            token = self._refresh.get(jti)
            if token is None or token[2]:
                return False
            self._refresh[jti] = (token[0], token[1], True)
            return True

    def revoke_all_refresh_tokens(self, id_usuario: str, now: datetime) -> int:
        revoked = 0
        for jti, (owner, expira, is_revoked) in list(self._refresh.items()):
            if owner == id_usuario and not is_revoked:
                self._refresh[jti] = (owner, expira, True)
                revoked += 1
        return revoked

    def revoke_access_token(self, jti: str, id_usuario: str, expira: datetime, now: datetime) -> None:
        self._revoked_access[jti] = expira

    def is_access_token_revoked(self, jti: str) -> bool:
        return jti in self._revoked_access

    # ---- RBAC
    def get_roles_and_permissions(self, id_usuario: str) -> Tuple[List[str], List[str]]:
        roles = sorted(self._user_roles.get(id_usuario, set()))
        permisos = {
            self._permissions[p]
            for r in roles
            for p in self._role_permissions.get(r, set())
            if p in self._permissions
        }
        return roles, sorted(permisos)

    def get_role_tenant(self, id_rol: str) -> Optional[str]:
        return self._roles.get(id_rol)

    def permission_exists(self, id_permiso: str) -> bool:
        return id_permiso in self._permissions

    def assign_role(self, id_usuario: str, id_rol: str) -> bool:
        roles = self._user_roles.setdefault(id_usuario, set())
        if id_rol in roles:
            return False
        roles.add(id_rol)
        return True

    def grant_permission(self, id_rol: str, id_permiso: str) -> bool:
        permisos = self._role_permissions.setdefault(id_rol, set())
        if id_permiso in permisos:
            return False
        permisos.add(id_permiso)
        return True

    # ---- auditoría
    def add_audit(self, entry: AuditEntry) -> None:
        self._audit.append(entry)

    def login_failures_since(self, recurso: str, since: datetime) -> List[datetime]:
        failures: List[datetime] = []
        for entry in self._audit:
            if entry.recurso != recurso:
                continue
            if entry.accion == SESSION_STARTED and entry.resultado == AuditResult.SUCCESS:
                failures.clear()
            elif entry.resultado == AuditResult.BAD_CREDENTIALS and entry.fecha > since:
                failures.append(entry.fecha)
        return sorted(failures)

    def list_audit(self, id_empresa, desde, hasta, accion, id_usuario, resultado, limit, offset):
        matches = [
            e for e in self._audit
            if e.id_empresa == id_empresa
            and (desde is None or e.fecha >= desde)
            and (hasta is None or e.fecha <= hasta)
            and (accion is None or e.accion == accion)
            and (id_usuario is None or e.id_usuario == id_usuario)
            and (resultado is None or e.resultado == resultado)
        ]
        matches.sort(key=lambda e: e.fecha, reverse=True)
        return len(matches), matches[offset:offset + limit]

    def audit_summary(self, id_empresa: str, desde: datetime) -> List[Tuple[str, str, int]]:
        counts = Counter(
            (e.accion, e.resultado) for e in self._audit if e.id_empresa == id_empresa and e.fecha >= desde
        )
        return [(accion, resultado, total) for (accion, resultado), total in sorted(counts.items())]
