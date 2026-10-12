"""
Persistencia de Sentinel en SQL Server (base kinetix) mediante los procedimientos del esquema sentinel.

KINETIX_PROCEDIMIENTOS.sql agrega las columnas opcionales de bases antiguas (roles.estado, fichas_acceso.ficha_hash,
usuarios.actualizado_en...), así que los procedimientos usan siempre el mismo esquema.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, List, Optional, Tuple

import pyodbc

from src.agents.security_agent.config import SqlServerSettings
from src.agents.security_agent.models import AuditEntry, AuditResult, MfaRecord, User
from src.agents.security_agent.repository import SESSION_STARTED, SecurityRepository
from src.agents.sqlserver import afectadas, ejecutar


def _token_hash(jti: str, kind: str) -> str:
    return hashlib.sha256(f"{kind}:{jti}".encode()).hexdigest()


class SqlServerSecurityRepository(SecurityRepository):
    def __init__(self, settings: SqlServerSettings) -> None:
        self._connection_string = settings.connection_string()

    @contextmanager
    def _cursor(self, commit: bool = False) -> Iterator[pyodbc.Cursor]:
        conn = pyodbc.connect(self._connection_string, timeout=5)
        try:
            cursor = conn.cursor()
            yield cursor
            if commit:
                conn.commit()
        finally:
            conn.close()

    def ping(self) -> None:
        with self._cursor() as cur:
            cur.execute("SELECT 1")

    # ---- usuarios
    def _user_from_row(self, row) -> Optional[User]:
        return User(row[0], row[1], row[2], row[3], row[4] or "activo") if row else None

    def get_user(self, nombre_usuario: str, id_empresa: str) -> Optional[User]:
        with self._cursor() as cur:
            ejecutar(cur, "sentinel.usuario_por_nombre", nombre_usuario=nombre_usuario, id_empresa=id_empresa)
            return self._user_from_row(cur.fetchone())

    def get_user_by_id(self, id_usuario: str) -> Optional[User]:
        with self._cursor() as cur:
            ejecutar(cur, "sentinel.usuario_obtener", id_usuario=id_usuario)
            return self._user_from_row(cur.fetchone())

    def count_users_with_mfa(self, id_empresa: str) -> Tuple[int, int]:
        with self._cursor() as cur:
            row = ejecutar(cur, "sentinel.usuarios_mfa_contar", id_empresa=id_empresa).fetchone()
            return int(row[0] or 0), int(row[1] or 0)

    # ---- MFA
    def get_mfa(self, id_usuario: str) -> Optional[MfaRecord]:
        with self._cursor() as cur:
            row = ejecutar(cur, "sentinel.mfa_obtener", id_usuario=id_usuario).fetchone()
            return MfaRecord(row[0], row[1], bool(row[2]), row[3]) if row else None

    def save_pending_mfa(self, id_usuario: str, secret: str, now: datetime) -> None:
        with self._cursor(commit=True) as cur:
            ejecutar(cur, "sentinel.mfa_guardar_pendiente", id_usuario=id_usuario, secreto=secret, ahora=now)

    def enable_mfa(self, id_usuario: str, now: datetime) -> None:
        with self._cursor(commit=True) as cur:
            ejecutar(cur, "sentinel.mfa_cambiar", id_usuario=id_usuario, habilitado=True, ahora=now)

    def disable_mfa(self, id_usuario: str, now: datetime) -> None:
        with self._cursor(commit=True) as cur:
            ejecutar(cur, "sentinel.mfa_cambiar", id_usuario=id_usuario, habilitado=False, ahora=now)

    def claim_totp_step(self, id_usuario: str, step: int) -> bool:
        with self._cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "sentinel.mfa_reclamar_paso", id_usuario=id_usuario, paso=step)) == 1

    # ---- fichas
    @staticmethod
    def _insert_token(cur: pyodbc.Cursor, jti: str, id_usuario: str, kind: str, expira: datetime,
                      revoked_at: Optional[datetime]) -> None:
        ejecutar(cur, "sentinel.ficha_insertar", id=jti, id_usuario=id_usuario, tipo_ficha=kind, expira_en=expira,
                 ficha_hash=_token_hash(jti, kind), revocada_en=revoked_at)

    def store_refresh_token(self, jti: str, id_usuario: str, expira: datetime) -> None:
        with self._cursor(commit=True) as cur:
            self._insert_token(cur, jti, id_usuario, "Refresh", expira, None)

    def get_refresh_token(self, jti: str) -> Optional[Tuple[str, bool]]:
        with self._cursor() as cur:
            row = ejecutar(cur, "sentinel.ficha_refresco_obtener", id=jti).fetchone()
            return (row[0], bool(row[1])) if row else None

    def revoke_refresh_token(self, jti: str, now: datetime) -> bool:
        with self._cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "sentinel.ficha_refresco_revocar", id=jti, ahora=now)) == 1

    def revoke_all_refresh_tokens(self, id_usuario: str, now: datetime) -> int:
        with self._cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "sentinel.fichas_refresco_revocar_usuario", id_usuario=id_usuario, ahora=now))

    def revoke_access_token(self, jti: str, id_usuario: str, expira: datetime, now: datetime) -> None:
        with self._cursor(commit=True) as cur:
            self._insert_token(cur, jti, id_usuario, "Bearer", expira, now)

    def is_access_token_revoked(self, jti: str) -> bool:
        with self._cursor() as cur:
            return ejecutar(cur, "sentinel.ficha_acceso_revocada", id=jti).fetchone() is not None

    # ---- RBAC
    def get_roles_and_permissions(self, id_usuario: str) -> Tuple[List[str], List[str]]:
        with self._cursor() as cur:
            ejecutar(cur, "sentinel.roles_y_permisos", id_usuario=id_usuario)
            roles, permisos = set(), set()
            for role_id, recurso, accion in cur.fetchall():
                roles.add(role_id)
                if recurso and accion:
                    permisos.add(f"{recurso}:{accion}")
            return sorted(roles), sorted(permisos)

    def get_role_tenant(self, id_rol: str) -> Optional[str]:
        with self._cursor() as cur:
            row = ejecutar(cur, "sentinel.rol_empresa", id_rol=id_rol).fetchone()
            return row[0] if row else None

    def permission_exists(self, id_permiso: str) -> bool:
        with self._cursor() as cur:
            return ejecutar(cur, "sentinel.permiso_existe", id_permiso=id_permiso).fetchone() is not None

    def assign_role(self, id_usuario: str, id_rol: str) -> bool:
        with self._cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "sentinel.rol_asignar", id_usuario=id_usuario, id_rol=id_rol)) == 1

    def grant_permission(self, id_rol: str, id_permiso: str) -> bool:
        with self._cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "sentinel.permiso_conceder", id_rol=id_rol, id_permiso=id_permiso)) == 1

    # ---- auditoría
    def add_audit(self, entry: AuditEntry) -> None:
        with self._cursor(commit=True) as cur:
            ejecutar(cur, "sentinel.auditoria_insertar", id_usuario=entry.id_usuario, id_empresa=entry.id_empresa,
                     accion=entry.accion, recurso=entry.recurso, resultado=entry.resultado, detalles=entry.detalles,
                     fecha=entry.fecha, direccion_ip=entry.direccion_ip)

    def login_failures_since(self, recurso: str, since: datetime) -> List[datetime]:
        with self._cursor() as cur:
            ejecutar(cur, "sentinel.auditoria_fallos_acceso", recurso=recurso, resultado_fallo=AuditResult.BAD_CREDENTIALS,
                     desde=since, accion_sesion=SESSION_STARTED, resultado_exito=AuditResult.SUCCESS)
            return [row[0] for row in cur.fetchall()]

    def list_audit(self, id_empresa, desde, hasta, accion, id_usuario, resultado, limit, offset):
        with self._cursor() as cur:
            ejecutar(cur, "sentinel.auditoria_listar", id_empresa=id_empresa, desde=desde, hasta=hasta, accion=accion,
                     id_usuario=id_usuario, resultado=resultado, limite=limit, desplazamiento=offset)
            total = int(cur.fetchone()[0])
            cur.nextset()
            entries = [AuditEntry(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in cur.fetchall()]
        return total, entries

    def audit_summary(self, id_empresa: str, desde: datetime) -> List[Tuple[str, str, int]]:
        with self._cursor() as cur:
            ejecutar(cur, "sentinel.auditoria_resumen", id_empresa=id_empresa, desde=desde)
            return [(r[0], r[1], int(r[2])) for r in cur.fetchall()]
