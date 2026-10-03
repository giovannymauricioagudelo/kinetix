"""Configuración de Sentinel leída del entorno (.env en la raíz del proyecto)."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw and raw.strip() else default


@dataclass(frozen=True)
class SecuritySettings:
    secret_key: str
    issuer: str = "kinetix-sentinel"
    algorithm: str = "HS256"
    access_minutes: int = 15
    refresh_days: int = 7
    mfa_ticket_minutes: int = 5
    max_failed_attempts: int = 5
    lockout_window_minutes: int = 15
    totp_issuer: str = "Sentinel - Kinetix"


@dataclass(frozen=True)
class SqlServerSettings:
    driver: str
    host: str
    database: str
    user: str
    password: str

    def connection_string(self) -> str:
        return (
            f"Driver={{{self.driver}}};Server={self.host};Database={self.database};"
            f"UID={self.user};PWD={self.password};TrustServerCertificate=yes"
        )


def load_security_settings() -> SecuritySettings:
    secret = os.getenv("SENTINEL_SECRET_KEY")
    if not secret:
        logger.warning("SENTINEL_SECRET_KEY no definida: se usa una clave temporal y los tokens se invalidan al reiniciar.")
        secret = secrets.token_urlsafe(48)
    return SecuritySettings(
        secret_key=secret,
        access_minutes=_int_env("SENTINEL_ACCESS_MINUTES", 15),
        refresh_days=_int_env("SENTINEL_REFRESH_DAYS", 7),
        mfa_ticket_minutes=_int_env("SENTINEL_MFA_TICKET_MINUTES", 5),
        max_failed_attempts=_int_env("SENTINEL_MAX_FAILED_ATTEMPTS", 5),
        lockout_window_minutes=_int_env("SENTINEL_LOCKOUT_MINUTES", 15),
    )


def load_sqlserver_settings() -> SqlServerSettings:
    return SqlServerSettings(
        driver=os.getenv("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server"),
        host=os.getenv("SQLSERVER_HOST", "localhost"),
        database=os.getenv("SQLSERVER_DATABASE", "kinetix"),
        user=os.getenv("SQLSERVER_USER", "sa"),
        password=os.getenv("SQLSERVER_PASSWORD", ""),
    )
