"""Persistencia de Sentinel en SQL Server (base kinetix, esquema SENTINEL_SCHEMA_*.sql)."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, List, Optional, Tuple

import pyodbc

from src.agents.security_agent.config import SqlServerSettings
from src.agents.security_agent.models import AuditEntry, AuditResult, MfaRecord, User
from src.agents.security_agent.repository import SESSION_STARTED, SecurityRepository


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
        return User(row[0], row[1], row[2], row[3], row[4]) if row else None

    def get_user(self, nombre_usuario: str, id_empresa: str) -> Optional[User]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT id, nombre_usuario, id_empresa, hash_contrasena, estado FROM dbo.usuarios "
                "WHERE nombre_usuario = ? AND id_empresa = ?",
                (nombre_usuario, id_empresa),
            )
            return self._user_from_row(cur.fetchone())

    def get_user_by_id(self, id_usuario: str) -> Optional[User]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT id, nombre_usuario, id_empresa, hash_contrasena, estado FROM dbo.usuarios WHERE id = ?",
                (id_usuario,),
            )
            return self._user_from_row(cur.fetchone())

    def count_users_with_mfa(self, id_empresa: str) -> Tuple[int, int]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), SUM(CASE WHEN m.habilitado = 1 THEN 1 ELSE 0 END) "
                "FROM dbo.usuarios u LEFT JOIN dbo.mfa_secrets m ON m.id_usuario = u.id "
                "WHERE u.id_empresa = ? AND u.estado = 'activo'",
                (id_empresa,),
            )
            row = cur.fetchone()
            return int(row[0] or 0), int(row[1] or 0)

    # ---- MFA
    def get_mfa(self, id_usuario: str) -> Optional[MfaRecord]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT id_usuario, secret_totp, habilitado, ultimo_paso_totp FROM dbo.mfa_secrets WHERE id_usuario = ?",
                (id_usuario,),
            )
            row = cur.fetchone()
            return MfaRecord(row[0], row[1], bool(row[2]), row[3]) if row else None

    def save_pending_mfa(self, id_usuario: str, secret: str, now: datetime) -> None:
        with self._cursor(commit=True) as cur:
            cur.execute(
                """
                MERGE dbo.mfa_secrets AS target
                USING (SELECT ? AS id_usuario) AS source ON target.id_usuario = source.id_usuario
                WHEN MATCHED AND target.habilitado = 0 THEN
                    UPDATE SET secret_totp = ?, ultimo_paso_totp = NULL, fecha_creacion = ?, fecha_confirmacion = NULL
                WHEN NOT MATCHED THEN
                    INSERT (id_usuario, secret_totp, habilitado, fecha_creacion) VALUES (?, ?, 0, ?);
                """,
                (id_usuario, secret, now, id_usuario, secret, now),
            )

    def enable_mfa(self, id_usuario: str, now: datetime) -> None:
        with self._cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.mfa_secrets SET habilitado = 1, fecha_confirmacion = ? WHERE id_usuario = ?",
                (now, id_usuario),
            )
            cur.execute("UPDATE dbo.usuarios SET mfa_habilitado = 1, actualizado_en = ? WHERE id = ?", (now, id_usuario))

    def disable_mfa(self, id_usuario: str, now: datetime) -> None:
        with self._cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.mfa_secrets SET habilitado = 0, fecha_deshabilitacion = ? WHERE id_usuario = ?",
                (now, id_usuario),
            )
            cur.execute("UPDATE dbo.usuarios SET mfa_habilitado = 0, actualizado_en = ? WHERE id = ?", (now, id_usuario))

    def claim_totp_step(self, id_usuario: str, step: int) -> bool:
        with self._cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.mfa_secrets SET ultimo_paso_totp = ? "
                "WHERE id_usuario = ? AND (ultimo_paso_totp IS NULL OR ultimo_paso_totp < ?)",
                (step, id_usuario, step),
            )
            return cur.rowcount == 1

    # ---- fichas
    def store_refresh_token(self, jti: str, id_usuario: str, expira: datetime) -> None:
        with self._cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO dbo.fichas_acceso (id, id_usuario, tipo_ficha, ficha_hash, expira_en) VALUES (?, ?, 'Refresh', ?, ?)",
                (jti, id_usuario, _token_hash(jti, "Refresh"), expira),
            )

    def get_refresh_token(self, jti: str) -> Optional[Tuple[str, bool]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT id_usuario, revocada FROM dbo.fichas_acceso WHERE id = ? AND tipo_ficha = 'Refresh'",
                (jti,),
            )
            row = cur.fetchone()
            return (row[0], bool(row[1])) if row else None

    def revoke_refresh_token(self, jti: str, now: datetime) -> bool:
        with self._cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.fichas_acceso SET revocada = 1, revocada_en = ? "
                "WHERE id = ? AND tipo_ficha = 'Refresh' AND revocada = 0",
                (now, jti),
            )
            return cur.rowcount == 1

    def revoke_all_refresh_tokens(self, id_usuario: str, now: datetime) -> int:
        with self._cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.fichas_acceso SET revocada = 1, revocada_en = ? "
                "WHERE id_usuario = ? AND tipo_ficha = 'Refresh' AND revocada = 0",
                (now, id_usuario),
            )
            return cur.rowcount

    def revoke_access_token(self, jti: str, id_usuario: str, expira: datetime, now: datetime) -> None:
        with self._cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO dbo.fichas_acceso (id, id_usuario, tipo_ficha, ficha_hash, expira_en, revocada, revocada_en) "
                "SELECT ?, ?, 'Bearer', ?, ?, 1, ? WHERE NOT EXISTS (SELECT 1 FROM dbo.fichas_acceso WHERE id = ?)",
                (jti, id_usuario, _token_hash(jti, "Bearer"), expira, now, jti),
            )

    def is_access_token_revoked(self, jti: str) -> bool:
        with self._cursor() as cur:
            cur.execute(
                "SELECT 1 FROM dbo.fichas_acceso WHERE id = ? AND tipo_ficha = 'Bearer' AND revocada = 1",
                (jti,),
            )
            return cur.fetchone() is not None

    # ---- RBAC
    def get_roles_and_permissions(self, id_usuario: str) -> Tuple[List[str], List[str]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT r.id, p.recurso, p.accion FROM dbo.usuarios_roles ur "
                "JOIN dbo.roles r ON r.id = ur.id_rol AND r.estado = 'activo' "
                "LEFT JOIN dbo.roles_permisos rp ON rp.id_rol = r.id "
                "LEFT JOIN dbo.permisos p ON p.id = rp.id_permiso "
                "WHERE ur.id_usuario = ?",
                (id_usuario,),
            )
            roles, permisos = set(), set()
            for role_id, recurso, accion in cur.fetchall():
                roles.add(role_id)
                if recurso and accion:
                    permisos.add(f"{recurso}:{accion}")
            return sorted(roles), sorted(permisos)

    def get_role_tenant(self, id_rol: str) -> Optional[str]:
        with self._cursor() as cur:
            cur.execute("SELECT id_empresa FROM dbo.roles WHERE id = ? AND estado = 'activo'", (id_rol,))
            row = cur.fetchone()
            return row[0] if row else None

    def permission_exists(self, id_permiso: str) -> bool:
        with self._cursor() as cur:
            cur.execute("SELECT 1 FROM dbo.permisos WHERE id = ?", (id_permiso,))
            return cur.fetchone() is not None

    def assign_role(self, id_usuario: str, id_rol: str) -> bool:
        with self._cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO dbo.usuarios_roles (id_usuario, id_rol) SELECT ?, ? "
                "WHERE NOT EXISTS (SELECT 1 FROM dbo.usuarios_roles WHERE id_usuario = ? AND id_rol = ?)",
                (id_usuario, id_rol, id_usuario, id_rol),
            )
            return cur.rowcount == 1

    def grant_permission(self, id_rol: str, id_permiso: str) -> bool:
        with self._cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO dbo.roles_permisos (id_rol, id_permiso) SELECT ?, ? "
                "WHERE NOT EXISTS (SELECT 1 FROM dbo.roles_permisos WHERE id_rol = ? AND id_permiso = ?)",
                (id_rol, id_permiso, id_rol, id_permiso),
            )
            return cur.rowcount == 1

    # ---- auditoría
    def add_audit(self, entry: AuditEntry) -> None:
        with self._cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO dbo.bitacora_auditoria "
                "(id_usuario, id_empresa, accion, recurso, resultado, detalles, fecha_auditoria, direccion_ip) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (entry.id_usuario, entry.id_empresa, entry.accion, entry.recurso, entry.resultado,
                 entry.detalles, entry.fecha, entry.direccion_ip),
            )

    def login_failures_since(self, recurso: str, since: datetime) -> List[datetime]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT fecha_auditoria FROM dbo.bitacora_auditoria "
                "WHERE recurso = ? AND resultado = ? AND fecha_auditoria > ? "
                "AND id > COALESCE((SELECT MAX(id) FROM dbo.bitacora_auditoria "
                "  WHERE recurso = ? AND accion = ? AND resultado = ?), 0) "
                "ORDER BY fecha_auditoria",
                (recurso, AuditResult.BAD_CREDENTIALS, since, recurso, SESSION_STARTED, AuditResult.SUCCESS),
            )
            return [row[0] for row in cur.fetchall()]

    def list_audit(self, id_empresa, desde, hasta, accion, id_usuario, resultado, limit, offset):
        clauses, params = ["id_empresa = ?"], [id_empresa]
        for column, operator, value in (
            ("fecha_auditoria", ">=", desde),
            ("fecha_auditoria", "<=", hasta),
            ("accion", "=", accion),
            ("id_usuario", "=", id_usuario),
            ("resultado", "=", resultado),
        ):
            if value is not None:
                clauses.append(f"{column} {operator} ?")
                params.append(value)
        where = " AND ".join(clauses)
        with self._cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM dbo.bitacora_auditoria WHERE {where}", params)
            total = int(cur.fetchone()[0])
            cur.execute(
                "SELECT id_empresa, accion, resultado, id_usuario, recurso, detalles, direccion_ip, fecha_auditoria "
                f"FROM dbo.bitacora_auditoria WHERE {where} "
                "ORDER BY fecha_auditoria DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
                [*params, offset, limit],
            )
            entries = [AuditEntry(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in cur.fetchall()]
        return total, entries

    def audit_summary(self, id_empresa: str, desde: datetime) -> List[Tuple[str, str, int]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT accion, resultado, COUNT(*) FROM dbo.bitacora_auditoria "
                "WHERE id_empresa = ? AND fecha_auditoria >= ? GROUP BY accion, resultado ORDER BY accion, resultado",
                (id_empresa, desde),
            )
            return [(r[0], r[1], int(r[2])) for r in cur.fetchall()]
