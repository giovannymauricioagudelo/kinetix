"""Unit tests for Sentinel (SecurityAgent)."""

from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agents.security_agent import InMemorySecurityRepository, SecurityService
from src.agents.security_agent.config import SecuritySettings
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import (
    AuthenticationError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
)
from src.api.routes import sentinel_routes

PASSWORDS = {"ana": "Clave-Segura-1", "luis": "Clave-Segura-2"}


class Clock:
    def __init__(self):
        self.now = datetime.now(timezone.utc).replace(tzinfo=None)

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


def seeded_repository() -> InMemorySecurityRepository:
    repo = InMemorySecurityRepository()
    repo.add_user("u1", "ana", "gio", PASSWORDS["ana"])
    repo.add_user("u2", "luis", "gio", PASSWORDS["luis"])
    repo.add_user("u3", "eva", "otra", "Clave-Segura-3")
    repo.add_role("rol_admin", "gio")
    repo.add_role("rol_usuario", "gio")
    repo.add_role("rol_otra", "otra")
    for perm_id, recurso, accion in (
        ("p_roles", "roles", "asignar"),
        ("p_perm", "permisos", "otorgar"),
        ("p_audit", "auditoria", "ver"),
        ("p_mon", "monitoreo", "ver"),
        ("p_ack", "alertas", "reconocer"),
        ("p_ped", "pedidos_venta", "crear"),
    ):
        repo.add_permission(perm_id, recurso, accion)
    for perm_id in ("p_roles", "p_perm", "p_audit", "p_mon", "p_ack"):
        repo.grant_permission("rol_admin", perm_id)
    repo.assign_role("u1", "rol_admin")
    return repo


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def repo():
    return seeded_repository()


@pytest.fixture
def service(repo, clock):
    return SecurityService(repo, SecuritySettings(secret_key="sentinel-test-secret-" + "x" * 32), clock=clock)


def login(service, user="ana"):
    return service.authenticate(user, PASSWORDS[user], "gio")


def principal(service, user="ana"):
    return service.validate_access_token(login(service, user)["token_acceso"])


def code_at(secret, clock, offset_seconds=0):
    return pyotp.TOTP(secret).at((clock.now + timedelta(seconds=offset_seconds)).replace(tzinfo=timezone.utc))


def enable_mfa(service, clock, user="ana"):
    p = principal(service, user)
    secret = service.setup_mfa(p)["secret"]
    service.confirm_mfa(p, code_at(secret, clock))
    clock.advance(seconds=30)
    return secret


# ------------------------------------------------------------------ autenticación


def test_uses_sentinel_codename(service):
    assert service.name == "Sentinel"


def test_login_without_mfa_returns_session(service):
    result = login(service)
    assert result["mfa_requerido"] is False
    assert result["expira_en_segundos"] == 15 * 60
    assert service.validate_access_token(result["token_acceso"]).id == "u1"


def test_unknown_user_and_wrong_password_look_the_same(service):
    with pytest.raises(AuthenticationError) as wrong_password:
        service.authenticate("ana", "incorrecta", "gio")
    with pytest.raises(AuthenticationError) as unknown_user:
        service.authenticate("nadie", "incorrecta", "gio")
    assert str(wrong_password.value) == str(unknown_user.value) == "Credenciales inválidas"


def test_password_alone_never_opens_a_session_when_mfa_is_enabled(service, clock):
    enable_mfa(service, clock)
    result = login(service)
    assert result["mfa_requerido"] is True
    assert "token_acceso" not in result
    with pytest.raises(AuthenticationError):
        service.validate_access_token(result["ficha_mfa"])


def test_mfa_ticket_plus_code_opens_session(service, clock):
    secret = enable_mfa(service, clock)
    ticket = login(service)["ficha_mfa"]
    session = service.verify_mfa(ticket, code_at(secret, clock))
    assert session["metodos"] == ["pwd", "otp"]
    assert service.validate_access_token(session["token_acceso"]).metodos == ["pwd", "otp"]


def test_totp_code_cannot_be_replayed(service, clock):
    secret = enable_mfa(service, clock)
    code = code_at(secret, clock)
    service.verify_mfa(login(service)["ficha_mfa"], code)
    with pytest.raises(AuthenticationError):
        service.verify_mfa(login(service)["ficha_mfa"], code)


# ------------------------------------------------------------------ gestión de MFA


def test_disable_mfa_requires_password_and_current_code(service, clock, repo):
    secret = enable_mfa(service, clock)
    session = service.verify_mfa(login(service)["ficha_mfa"], code_at(secret, clock))
    p = service.validate_access_token(session["token_acceso"])
    clock.advance(seconds=30)

    with pytest.raises(PermissionDeniedError):
        service.disable_mfa(p, "incorrecta", code_at(secret, clock))
    with pytest.raises(PermissionDeniedError):
        service.disable_mfa(p, PASSWORDS["ana"], "000000")
    assert repo.get_mfa("u1").habilitado

    service.disable_mfa(p, PASSWORDS["ana"], code_at(secret, clock))
    assert not repo.get_mfa("u1").habilitado


def test_setup_mfa_cannot_reset_an_enabled_mfa(service, clock, repo):
    secret = enable_mfa(service, clock)
    session = service.verify_mfa(login(service)["ficha_mfa"], code_at(secret, clock))
    with pytest.raises(ConflictError):
        service.setup_mfa(service.validate_access_token(session["token_acceso"]))
    record = repo.get_mfa("u1")
    assert record.habilitado and record.secret == secret


def test_confirm_mfa_with_wrong_code_is_rejected(service):
    p = principal(service)
    service.setup_mfa(p)
    with pytest.raises(InvalidInputError):
        service.confirm_mfa(p, "123456")


# ------------------------------------------------------------------ bloqueo por intentos


def fail(service, times, user="ana"):
    for _ in range(times):
        with pytest.raises(AuthenticationError):
            service.authenticate(user, "incorrecta", "gio")


def test_successful_logins_never_lock_the_account(service):
    for _ in range(10):
        login(service)


def test_lockout_counts_failures_and_resets_after_login(service, clock):
    fail(service, 4)
    login(service)
    fail(service, 4)
    login(service)

    fail(service, 5)
    with pytest.raises(RateLimitedError) as locked:
        login(service)
    assert locked.value.retry_after_seconds > 0

    clock.advance(minutes=15, seconds=1)
    login(service)


def test_lockout_survives_a_new_service_instance(service, repo, clock):
    fail(service, 5)
    restarted = SecurityService(repo, service.settings, clock=clock)
    with pytest.raises(RateLimitedError):
        login(restarted)


def test_failed_mfa_codes_count_toward_lockout(service, clock):
    enable_mfa(service, clock)
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            service.verify_mfa(login(service)["ficha_mfa"], "000000")
    with pytest.raises(RateLimitedError):
        login(service)


def test_rate_limit_status_reflects_failures_after_login(service):
    ana = principal(service)
    fail(service, 2)
    fail(service, 1, user="luis")
    status = service.rate_limit_status(ana)
    assert status["intentos_fallidos_recientes"] == 2
    assert status["intentos_restantes"] == 3
    assert status["bloqueado"] is False


# ------------------------------------------------------------------ sesiones


def test_access_token_expires(service, clock):
    token = login(service)["token_acceso"]
    clock.advance(minutes=16)
    with pytest.raises(AuthenticationError, match="expirado"):
        service.validate_access_token(token)


def test_refresh_rotates_and_reuse_closes_every_session(service):
    first = login(service)
    second = service.refresh(first["token_refresco"])
    assert second["token_refresco"] != first["token_refresco"]

    with pytest.raises(AuthenticationError):
        service.refresh(first["token_refresco"])
    with pytest.raises(AuthenticationError):
        service.refresh(second["token_refresco"])


def test_logout_revokes_access_and_refresh_tokens(service):
    session = login(service)
    p = service.validate_access_token(session["token_acceso"])
    service.logout(p, session["token_refresco"])
    with pytest.raises(AuthenticationError, match="revocado"):
        service.validate_access_token(session["token_acceso"])
    with pytest.raises(AuthenticationError):
        service.refresh(session["token_refresco"])


# ------------------------------------------------------------------ RBAC


def test_permissions_and_authorize(service):
    ana, luis = principal(service), principal(service, "luis")
    assert "roles:asignar" in service.permissions(ana)["permisos"]
    assert service.authorize(ana, "auditoria:ver")
    assert not service.authorize(luis, "auditoria:ver")


def test_assign_role_requires_permission_and_same_tenant(service, repo):
    ana, luis = principal(service), principal(service, "luis")
    with pytest.raises(PermissionDeniedError):
        service.assign_role(luis, "u2", "rol_admin")

    assert service.assign_role(ana, "u2", "rol_usuario")["asignado"] is True
    assert service.assign_role(ana, "u2", "rol_usuario")["asignado"] is False
    with pytest.raises(NotFoundError):
        service.assign_role(ana, "u3", "rol_usuario")
    with pytest.raises(NotFoundError):
        service.assign_role(ana, "u2", "rol_otra")


def test_grant_permission(service):
    ana, luis = principal(service), principal(service, "luis")
    service.assign_role(ana, "u2", "rol_usuario")
    service.grant_permission(ana, "rol_usuario", "p_ped")
    assert service.authorize(luis, "pedidos_venta:crear")
    with pytest.raises(NotFoundError):
        service.grant_permission(ana, "rol_usuario", "no_existe")


# ------------------------------------------------------------------ cumplimiento


def test_audit_log_requires_permission_and_is_tenant_scoped(service):
    fail(service, 1)
    ana, luis = principal(service), principal(service, "luis")
    log = service.audit_log(ana, accion="autenticar")
    assert log["total"] == 1
    assert log["registros"][0]["resultado"] == "fallo_credenciales"
    with pytest.raises(PermissionDeniedError):
        service.audit_log(luis)


def test_compliance_report_flags_users_without_mfa(service, clock):
    enable_mfa(service, clock, user="luis")
    fail(service, 5, user="luis")
    with pytest.raises(RateLimitedError):
        login(service, "luis")
    report = service.compliance_report(principal(service))
    assert report["mfa"] == {"usuarios_activos": 2, "con_mfa": 1, "adopcion_porcentaje": 50.0}
    assert report["resumen"]["bloqueos_por_intentos"] == 1
    assert any("no tienen MFA" in h for h in report["hallazgos"])


# ------------------------------------------------------------------ API


@pytest.fixture
def client(service):
    set_security_service(service)
    sentinel_routes._ip_limiter._hits.clear()
    app = FastAPI()
    app.include_router(sentinel_routes.router)
    yield TestClient(app)
    set_security_service(None)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_api_full_mfa_flow(client, clock):
    assert client.get("/api/v1/sentinel/permisos").status_code == 401
    assert client.get("/api/v1/sentinel/info").status_code == 401
    assert client.get("/api/v1/sentinel/salud").status_code == 200

    session = client.post("/api/v1/sentinel/autenticar", json={"nombre_usuario": "ana", "contrasena": PASSWORDS["ana"], "id_empresa": "gio"}).json()
    headers = bearer(session["token_acceso"])
    secret = client.post("/api/v1/sentinel/configurar-mfa", headers=headers).json()["secret"]
    assert client.post("/api/v1/sentinel/confirmar-mfa", headers=headers, json={"codigo": code_at(secret, clock)}).status_code == 200
    clock.advance(seconds=30)

    step_one = client.post("/api/v1/sentinel/autenticar", json={"nombre_usuario": "ana", "contrasena": PASSWORDS["ana"], "id_empresa": "gio"}).json()
    assert step_one["mfa_requerido"] is True and "token_acceso" not in step_one
    step_two = client.post("/api/v1/sentinel/autenticar-mfa", json={"ficha_mfa": step_one["ficha_mfa"], "codigo_mfa": code_at(secret, clock)})
    assert step_two.status_code == 200

    permisos = client.get("/api/v1/sentinel/permisos", headers=bearer(step_two.json()["token_acceso"])).json()
    assert "auditoria:ver" in permisos["permisos"]


def test_api_lockout_returns_429_with_retry_after(client):
    body = {"nombre_usuario": "luis", "contrasena": "incorrecta", "id_empresa": "gio"}
    for _ in range(5):
        assert client.post("/api/v1/sentinel/autenticar", json=body).status_code == 401
    locked = client.post("/api/v1/sentinel/autenticar", json={**body, "contrasena": PASSWORDS["luis"]})
    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) > 0


def test_api_limits_requests_per_ip(client, monkeypatch):
    monkeypatch.setattr(sentinel_routes._ip_limiter, "per_minute", 3)
    body = {"nombre_usuario": "nadie", "contrasena": "x", "id_empresa": "gio"}
    codes = [client.post("/api/v1/sentinel/autenticar", json=body).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]


def test_api_never_leaks_internal_errors(client, repo, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("Login failed for user 'sa' PWD=super-secreta")

    monkeypatch.setattr(repo, "get_user", broken)
    response = client.post("/api/v1/sentinel/autenticar", json={"nombre_usuario": "ana", "contrasena": "x", "id_empresa": "gio"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Servicio de seguridad no disponible temporalmente"
