"""
Sentinel (SecurityAgent) — autenticación, MFA, sesiones, RBAC y auditoría.

Reglas que este servicio garantiza:
- Con MFA habilitado, la contraseña sola nunca entrega una sesión: solo una ficha MFA de corta duración.
- Cambiar o deshabilitar el MFA exige reautenticación (contraseña + código vigente).
- El bloqueo cuenta solo fallos de credenciales, persiste en la bitácora y se reinicia con un inicio de sesión.
- Cada paso TOTP se acepta una sola vez por usuario.
- Las fichas de refresco rotan en cada uso; reutilizar una ya revocada cierra todas las sesiones del usuario.
"""

from __future__ import annotations

import base64
import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Callable, Dict, List, Optional, Tuple

import bcrypt
import jwt
import pyotp
import qrcode

from src.agents.agent_catalog import SENTINEL
from src.agents.security_agent.config import SecuritySettings
from src.agents.security_agent.models import (
    AuditEntry,
    AuditResult,
    AuthenticationError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    Principal,
    RateLimitedError,
    User,
)
from src.agents.security_agent.repository import SESSION_STARTED, SecurityRepository

logger = logging.getLogger(__name__)

TOKEN_ACCESS = "access"
TOKEN_REFRESH = "refresh"
TOKEN_MFA = "mfa"

PERM_ASSIGN_ROLES = "roles:asignar"
PERM_GRANT_PERMISSIONS = "permisos:otorgar"
PERM_READ_AUDIT = "auditoria:ver"

MAX_AUDIT_PAGE = 200


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive_utc(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is None or moment.tzinfo is None:
        return moment
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def _epoch(moment: datetime) -> int:
    return int(moment.replace(tzinfo=timezone.utc).timestamp())


def _check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _account(nombre_usuario: str, id_empresa: str) -> str:
    return f"cuenta:{id_empresa}:{nombre_usuario}"


class SecurityService:
    def __init__(
        self,
        repository: SecurityRepository,
        settings: SecuritySettings,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.name = SENTINEL.codename
        self.version = "2.0.0"
        self._repo = repository
        self._settings = settings
        self._now = clock or _utcnow
        self._dummy_hash = bcrypt.hashpw(b"sentinel-timing-equalizer", bcrypt.gensalt()).decode()

    @property
    def settings(self) -> SecuritySettings:
        return self._settings

    def ping(self) -> None:
        self._repo.ping()

    # ================================================================ fichas JWT

    def _encode(self, claims: Dict[str, object], lifetime: timedelta) -> Tuple[str, str, datetime]:
        now = self._now()
        expires = now + lifetime
        jti = uuid.uuid4().hex
        payload = {**claims, "jti": jti, "iat": _epoch(now), "exp": _epoch(expires), "iss": self._settings.issuer}
        return jwt.encode(payload, self._settings.secret_key, algorithm=self._settings.algorithm), jti, expires

    def _decode(self, token: str, expected_type: str) -> Dict[str, object]:
        try:
            claims = jwt.decode(
                token,
                self._settings.secret_key,
                algorithms=[self._settings.algorithm],
                issuer=self._settings.issuer,
                options={"verify_exp": False, "verify_iat": False, "require": ["exp", "jti", "sub", "typ"]},
            )
        except jwt.InvalidTokenError:
            raise AuthenticationError("Token inválido")
        if claims.get("typ") != expected_type:
            raise AuthenticationError("Token inválido")
        if int(claims["exp"]) <= _epoch(self._now()):
            raise AuthenticationError("Token expirado")
        return claims

    def validate_access_token(self, token: str) -> Principal:
        claims = self._decode(token, TOKEN_ACCESS)
        if self._repo.is_access_token_revoked(str(claims["jti"])):
            raise AuthenticationError("Token revocado")
        return Principal(
            id=str(claims["sub"]),
            nombre_usuario=str(claims.get("usr", "")),
            id_empresa=str(claims.get("emp", "")),
            jti=str(claims["jti"]),
            expira=datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc).replace(tzinfo=None),
            metodos=list(claims.get("amr", [])),
        )

    # ================================================================ auditoría y bloqueo

    def _audit(
        self,
        id_empresa: str,
        accion: str,
        resultado: str,
        id_usuario: Optional[str] = None,
        recurso: Optional[str] = None,
        detalles: Optional[str] = None,
        ip: Optional[str] = None,
    ) -> None:
        self._repo.add_audit(
            AuditEntry(id_empresa, accion, resultado, id_usuario, recurso, detalles, ip, self._now())
        )

    def _recent_failures(self, account: str) -> List[datetime]:
        window = timedelta(minutes=self._settings.lockout_window_minutes)
        return self._repo.login_failures_since(account, self._now() - window)

    def _ensure_not_locked(self, account: str, id_empresa: str, ip: Optional[str]) -> None:
        failures = self._recent_failures(account)
        limit = self._settings.max_failed_attempts
        if len(failures) < limit:
            return
        unlock_at = failures[-limit] + timedelta(minutes=self._settings.lockout_window_minutes)
        retry_after = max(1, int((unlock_at - self._now()).total_seconds()))
        self._audit(id_empresa, "autenticar", AuditResult.DENIED, recurso=account,
                    detalles="cuenta bloqueada temporalmente por intentos fallidos", ip=ip)
        raise RateLimitedError("Demasiados intentos fallidos. Intenta más tarde.", retry_after)

    # ================================================================ autenticación

    def authenticate(self, nombre_usuario: str, contrasena: str, id_empresa: str, ip: Optional[str] = None) -> Dict[str, object]:
        account = _account(nombre_usuario, id_empresa)
        self._ensure_not_locked(account, id_empresa, ip)

        user = self._repo.get_user(nombre_usuario, id_empresa)
        password_ok = _check_password(contrasena, user.hash_contrasena if user else self._dummy_hash)
        if user is None or not password_ok or user.estado != "activo":
            reason = "usuario inexistente" if user is None else ("contraseña inválida" if not password_ok else f"usuario {user.estado}")
            self._audit(id_empresa, "autenticar", AuditResult.BAD_CREDENTIALS,
                        user.id if user else None, account, reason, ip)
            raise AuthenticationError("Credenciales inválidas")

        mfa = self._repo.get_mfa(user.id)
        if mfa and mfa.habilitado:
            ticket, _, expires = self._encode(
                {"sub": user.id, "usr": user.nombre_usuario, "emp": user.id_empresa, "typ": TOKEN_MFA},
                timedelta(minutes=self._settings.mfa_ticket_minutes),
            )
            self._audit(id_empresa, "autenticar", AuditResult.SUCCESS, user.id, account,
                        "contraseña válida; falta el segundo factor", ip)
            return {
                "mfa_requerido": True,
                "ficha_mfa": ticket,
                "ficha_mfa_expira_en": expires.isoformat() + "Z",
                "siguiente_paso": "Envía ficha_mfa y codigo_mfa a POST /api/v1/sentinel/autenticar-mfa",
            }
        return self._start_session(user, ["pwd"], account, ip)

    def verify_mfa(self, ficha_mfa: str, codigo: str, ip: Optional[str] = None) -> Dict[str, object]:
        claims = self._decode(ficha_mfa, TOKEN_MFA)
        user = self._repo.get_user_by_id(str(claims["sub"]))
        if user is None or user.estado != "activo":
            raise AuthenticationError("Token inválido")
        account = _account(user.nombre_usuario, user.id_empresa)
        self._ensure_not_locked(account, user.id_empresa, ip)

        mfa = self._repo.get_mfa(user.id)
        if mfa is None or not mfa.habilitado:
            raise AuthenticationError("MFA no está habilitado para este usuario")
        if not self._verify_totp(user.id, mfa.secret, codigo):
            self._audit(user.id_empresa, "autenticar_mfa", AuditResult.BAD_CREDENTIALS, user.id, account,
                        "código MFA inválido o reutilizado", ip)
            raise AuthenticationError("Código MFA inválido")
        return self._start_session(user, ["pwd", "otp"], account, ip)

    def _verify_totp(self, id_usuario: str, secret: str, codigo: str) -> bool:
        code = (codigo or "").strip()
        if not (len(code) == 6 and code.isdigit()):
            return False
        totp = pyotp.TOTP(secret)
        now = self._now().replace(tzinfo=timezone.utc)
        for offset in (0, -1, 1):
            moment = now + timedelta(seconds=offset * totp.interval)
            if hmac.compare_digest(totp.at(moment), code):
                return self._repo.claim_totp_step(id_usuario, totp.timecode(moment))
        return False

    def _issue_tokens(self, user: User, methods: List[str]) -> Dict[str, object]:
        base = {"sub": user.id, "usr": user.nombre_usuario, "emp": user.id_empresa, "amr": methods}
        access_lifetime = timedelta(minutes=self._settings.access_minutes)
        access, _, _ = self._encode({**base, "typ": TOKEN_ACCESS}, access_lifetime)
        refresh, refresh_jti, refresh_expires = self._encode(
            {**base, "typ": TOKEN_REFRESH}, timedelta(days=self._settings.refresh_days)
        )
        self._repo.store_refresh_token(refresh_jti, user.id, refresh_expires)
        return {
            "mfa_requerido": False,
            "tipo_token": "Bearer",
            "token_acceso": access,
            "token_refresco": refresh,
            "expira_en_segundos": int(access_lifetime.total_seconds()),
            "usuario": user.nombre_usuario,
            "id_empresa": user.id_empresa,
            "metodos": methods,
        }

    def _start_session(self, user: User, methods: List[str], account: str, ip: Optional[str]) -> Dict[str, object]:
        tokens = self._issue_tokens(user, methods)
        self._audit(user.id_empresa, SESSION_STARTED, AuditResult.SUCCESS, user.id, account,
                    f"métodos: {'+'.join(methods)}", ip)
        return tokens

    def refresh(self, token_refresco: str, ip: Optional[str] = None) -> Dict[str, object]:
        claims = self._decode(token_refresco, TOKEN_REFRESH)
        jti = str(claims["jti"])
        stored = self._repo.get_refresh_token(jti)
        if stored is None:
            raise AuthenticationError("Token de refresco inválido")
        owner, revoked = stored
        user = self._repo.get_user_by_id(owner)
        tenant = user.id_empresa if user else str(claims.get("emp", ""))
        if revoked or not self._repo.revoke_refresh_token(jti, self._now()):
            closed = self._repo.revoke_all_refresh_tokens(owner, self._now())
            self._audit(tenant, "refrescar_token", AuditResult.DENIED, owner, None,
                        f"reutilización de un token revocado; se cerraron {closed} sesiones", ip)
            raise AuthenticationError("Token de refresco revocado")
        if user is None or user.estado != "activo":
            raise AuthenticationError("Token de refresco inválido")
        self._audit(tenant, "refrescar_token", AuditResult.SUCCESS, owner, None, None, ip)
        return self._issue_tokens(user, list(claims.get("amr", ["pwd"])))

    def logout(self, principal: Principal, token_refresco: Optional[str] = None,
               todas_las_sesiones: bool = False, ip: Optional[str] = None) -> Dict[str, object]:
        now = self._now()
        self._repo.revoke_access_token(principal.jti, principal.id, principal.expira, now)
        closed = 0
        if todas_las_sesiones:
            closed = self._repo.revoke_all_refresh_tokens(principal.id, now)
        elif token_refresco:
            claims = self._decode(token_refresco, TOKEN_REFRESH)
            if claims["sub"] != principal.id:
                raise PermissionDeniedError("El token de refresco no pertenece a esta sesión")
            closed = int(self._repo.revoke_refresh_token(str(claims["jti"]), now))
        self._audit(principal.id_empresa, "cerrar_sesion", AuditResult.SUCCESS, principal.id, None,
                    f"sesiones de refresco cerradas: {closed}", ip)
        return {"sesion_cerrada": True, "sesiones_refresco_cerradas": closed}

    # ================================================================ MFA

    def setup_mfa(self, principal: Principal) -> Dict[str, object]:
        current = self._repo.get_mfa(principal.id)
        if current and current.habilitado:
            raise ConflictError("El MFA ya está habilitado. Para reconfigurarlo, deshabilítalo primero con tu contraseña y un código vigente.")
        secret = pyotp.random_base32()
        self._repo.save_pending_mfa(principal.id, secret, self._now())
        uri = pyotp.TOTP(secret).provisioning_uri(name=principal.nombre_usuario, issuer_name=self._settings.totp_issuer)
        self._audit(principal.id_empresa, "configurar_mfa", AuditResult.SUCCESS, principal.id)
        return {
            "secret": secret,
            "uri": uri,
            "qr_code": f"data:image/png;base64,{_qr_png_base64(uri)}",
            "instrucciones": [
                "1. Abre Google Authenticator o Microsoft Authenticator.",
                "2. Escanea el código QR.",
                "3. Confirma con el código de 6 dígitos en POST /api/v1/sentinel/confirmar-mfa.",
            ],
        }

    def confirm_mfa(self, principal: Principal, codigo: str) -> Dict[str, object]:
        record = self._repo.get_mfa(principal.id)
        if record is None:
            raise ConflictError("Primero configura el MFA con POST /api/v1/sentinel/configurar-mfa")
        if record.habilitado:
            raise ConflictError("El MFA ya está habilitado")
        if not self._verify_totp(principal.id, record.secret, codigo):
            self._audit(principal.id_empresa, "confirmar_mfa", AuditResult.BAD_CREDENTIALS, principal.id,
                        detalles="código inválido")
            raise InvalidInputError("Código MFA inválido o expirado")
        self._repo.enable_mfa(principal.id, self._now())
        self._audit(principal.id_empresa, "confirmar_mfa", AuditResult.SUCCESS, principal.id)
        return {"mfa_habilitado": True, "usuario": principal.nombre_usuario}

    def disable_mfa(self, principal: Principal, contrasena: str, codigo: str, ip: Optional[str] = None) -> Dict[str, object]:
        record = self._repo.get_mfa(principal.id)
        if record is None or not record.habilitado:
            raise ConflictError("El MFA no está habilitado")
        user = self._repo.get_user_by_id(principal.id)
        if user is None:
            raise AuthenticationError("Token inválido")
        account = _account(user.nombre_usuario, user.id_empresa)
        self._ensure_not_locked(account, user.id_empresa, ip)
        if not _check_password(contrasena, user.hash_contrasena) or not self._verify_totp(user.id, record.secret, codigo):
            self._audit(user.id_empresa, "deshabilitar_mfa", AuditResult.BAD_CREDENTIALS, user.id, account,
                        "reautenticación fallida", ip)
            raise PermissionDeniedError("Contraseña o código MFA inválido")
        now = self._now()
        self._repo.disable_mfa(user.id, now)
        closed = self._repo.revoke_all_refresh_tokens(user.id, now)
        self._audit(user.id_empresa, "deshabilitar_mfa", AuditResult.SUCCESS, user.id, account,
                    f"sesiones de refresco cerradas: {closed}", ip)
        return {"mfa_habilitado": False, "sesiones_refresco_cerradas": closed}

    def rate_limit_status(self, principal: Principal) -> Dict[str, object]:
        failures = self._recent_failures(_account(principal.nombre_usuario, principal.id_empresa))
        limit = self._settings.max_failed_attempts
        locked = len(failures) >= limit
        unlock_at = failures[-limit] + timedelta(minutes=self._settings.lockout_window_minutes) if locked else None
        return {
            "usuario": principal.nombre_usuario,
            "intentos_fallidos_recientes": len(failures),
            "intentos_restantes": max(0, limit - len(failures)),
            "ventana_minutos": self._settings.lockout_window_minutes,
            "bloqueado": locked,
            "desbloqueo_en": unlock_at.isoformat() + "Z" if unlock_at else None,
        }

    # ================================================================ autorización (RBAC)

    def permissions(self, principal: Principal) -> Dict[str, object]:
        roles, permisos = self._repo.get_roles_and_permissions(principal.id)
        return {"usuario": principal.nombre_usuario, "id_empresa": principal.id_empresa, "roles": roles, "permisos": permisos}

    def authorize(self, principal: Principal, permiso: str, ip: Optional[str] = None) -> bool:
        _, permisos = self._repo.get_roles_and_permissions(principal.id)
        allowed = permiso in permisos
        if not allowed:
            self._audit(principal.id_empresa, "autorizar", AuditResult.PERMISSION_DENIED, principal.id, permiso, None, ip)
        return allowed

    def require(self, principal: Principal, permiso: str, ip: Optional[str] = None) -> None:
        if not self.authorize(principal, permiso, ip):
            raise PermissionDeniedError(f"Se requiere el permiso '{permiso}'")

    def assign_role(self, actor: Principal, id_usuario: str, id_rol: str) -> Dict[str, object]:
        self.require(actor, PERM_ASSIGN_ROLES)
        target = self._repo.get_user_by_id(id_usuario)
        if target is None or target.id_empresa != actor.id_empresa:
            raise NotFoundError("Usuario no encontrado")
        if self._repo.get_role_tenant(id_rol) != actor.id_empresa:
            raise NotFoundError("Rol no encontrado")
        created = self._repo.assign_role(id_usuario, id_rol)
        self._audit(actor.id_empresa, "asignar_rol", AuditResult.SUCCESS, actor.id, f"usuario:{id_usuario}",
                    f"rol {id_rol} {'asignado' if created else 'ya estaba asignado'}")
        return {"id_usuario": id_usuario, "id_rol": id_rol, "asignado": created}

    def grant_permission(self, actor: Principal, id_rol: str, id_permiso: str) -> Dict[str, object]:
        self.require(actor, PERM_GRANT_PERMISSIONS)
        if self._repo.get_role_tenant(id_rol) != actor.id_empresa:
            raise NotFoundError("Rol no encontrado")
        if not self._repo.permission_exists(id_permiso):
            raise NotFoundError("Permiso no encontrado")
        created = self._repo.grant_permission(id_rol, id_permiso)
        self._audit(actor.id_empresa, "otorgar_permiso", AuditResult.SUCCESS, actor.id, f"rol:{id_rol}",
                    f"permiso {id_permiso} {'otorgado' if created else 'ya estaba otorgado'}")
        return {"id_rol": id_rol, "id_permiso": id_permiso, "otorgado": created}

    # ================================================================ cumplimiento

    def audit_log(
        self,
        actor: Principal,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        accion: Optional[str] = None,
        id_usuario: Optional[str] = None,
        resultado: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, object]:
        self.require(actor, PERM_READ_AUDIT)
        limit = max(1, min(limit, MAX_AUDIT_PAGE))
        total, entries = self._repo.list_audit(
            actor.id_empresa, _naive_utc(desde), _naive_utc(hasta), accion, id_usuario, resultado, limit, max(0, offset)
        )
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "registros": [
                {
                    "fecha": e.fecha.isoformat() + "Z" if e.fecha else None,
                    "accion": e.accion,
                    "resultado": e.resultado,
                    "id_usuario": e.id_usuario,
                    "recurso": e.recurso,
                    "detalles": e.detalles,
                    "direccion_ip": e.direccion_ip,
                }
                for e in entries
            ],
        }

    def compliance_report(self, actor: Principal, dias: int = 30) -> Dict[str, object]:
        self.require(actor, PERM_READ_AUDIT)
        dias = max(1, min(dias, 365))
        since = self._now() - timedelta(days=dias)
        rows = self._repo.audit_summary(actor.id_empresa, since)

        def total(accion: Optional[str] = None, resultado: Optional[str] = None) -> int:
            return sum(n for a, r, n in rows if (accion is None or a == accion) and (resultado is None or r == resultado))

        usuarios, con_mfa = self._repo.count_users_with_mfa(actor.id_empresa)
        adopcion = round(100 * con_mfa / usuarios, 1) if usuarios else 0.0
        resumen = {
            "inicios_sesion": total(SESSION_STARTED, AuditResult.SUCCESS),
            "fallos_credenciales": total(resultado=AuditResult.BAD_CREDENTIALS),
            "bloqueos_por_intentos": total("autenticar", AuditResult.DENIED),
            "reutilizacion_tokens_revocados": total("refrescar_token", AuditResult.DENIED),
            "accesos_denegados_por_permiso": total(resultado=AuditResult.PERMISSION_DENIED),
            "cambios_de_roles_y_permisos": total("asignar_rol") + total("otorgar_permiso"),
        }
        hallazgos = []
        if usuarios and con_mfa < usuarios:
            hallazgos.append(f"{usuarios - con_mfa} de {usuarios} usuarios activos no tienen MFA habilitado.")
        if resumen["reutilizacion_tokens_revocados"]:
            hallazgos.append("Se detectó reutilización de tokens de refresco revocados (posible robo de sesión).")
        if resumen["bloqueos_por_intentos"]:
            hallazgos.append(f"{resumen['bloqueos_por_intentos']} intentos rechazados por bloqueo de cuenta.")
        return {
            "id_empresa": actor.id_empresa,
            "periodo_dias": dias,
            "desde": since.isoformat() + "Z",
            "mfa": {"usuarios_activos": usuarios, "con_mfa": con_mfa, "adopcion_porcentaje": adopcion},
            "resumen": resumen,
            "hallazgos": hallazgos,
            "detalle": [{"accion": a, "resultado": r, "total": n} for a, r, n in rows],
        }


def _qr_png_base64(data: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    buffer = BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()
