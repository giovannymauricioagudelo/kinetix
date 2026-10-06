"""Conexiones de Nexus: cada una se declara con una URL en NEXUS_CONEXION_<NOMBRE> y el esquema de la URL elige el motor.

  mssql://usuario:clave@host:1433/base?driver=ODBC+Driver+18+for+SQL+Server
  postgresql://usuario:clave@host:5432/base?sslmode=require
  firebird://SYSDBA:clave@host:3050/C:/datos/erp.fdb      (o un alias: firebird://u:c@host/erp)
  mongodb://usuario:clave@host:27017/base?authSource=admin  (también mongodb+srv://)

Caracteres especiales de la clave van codificados (%40 para @, %3A para :).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional
from urllib.parse import parse_qsl, unquote, urlsplit

from src.agents.security_agent.config import SqlServerSettings

logger = logging.getLogger(__name__)

CONNECTION_NAME = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
ENV_PREFIX = "NEXUS_CONEXION_"
SCHEMES = {
    "mssql": "sqlserver",
    "sqlserver": "sqlserver",
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "firebird": "firebird",
    "mongodb": "mongodb",
    "mongodb+srv": "mongodb",
}


@dataclass(frozen=True)
class PostgresSettings:
    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)
    sslmode: Optional[str] = None


@dataclass(frozen=True)
class FirebirdSettings:
    host: Optional[str]
    port: Optional[int]
    database: str
    user: str
    password: str = field(repr=False)
    charset: str = "UTF8"

    @property
    def dsn(self) -> str:
        if self.host and self.port:
            return f"{self.host}/{self.port}:{self.database}"
        return f"{self.host}:{self.database}" if self.host else self.database


@dataclass(frozen=True)
class MongoSettings:
    uri: str = field(repr=False)
    database: str = ""


@dataclass(frozen=True)
class ConnectionSpec:
    nombre: str
    motor: str
    settings: Any = field(repr=False)
    host: Optional[str]
    base_datos: str

    def public_view(self) -> Dict[str, Any]:
        """Sin usuario ni clave."""
        return {"nombre": self.nombre, "motor": self.motor, "host": self.host, "base_datos": self.base_datos}


def parse_connection_url(nombre: str, url: str) -> ConnectionSpec:
    if not CONNECTION_NAME.match(nombre or ""):
        raise ValueError(f"Nombre de conexión inválido: {nombre!r} (minúscula inicial, luego minúsculas, números o '_')")
    parts = urlsplit((url or "").strip())
    motor = SCHEMES.get(parts.scheme.lower())
    if motor is None:
        raise ValueError(f"Conexión {nombre}: esquema de URL no soportado {parts.scheme!r} (usa {', '.join(sorted(SCHEMES))})")
    user, password = unquote(parts.username or ""), unquote(parts.password or "")
    path = unquote(parts.path)
    query = dict(parse_qsl(parts.query))

    if motor == "mongodb":
        database = path.lstrip("/")
        if not database:
            raise ValueError(f"Conexión {nombre}: la URL de MongoDB debe indicar la base (mongodb://host/base)")
        host = parts.netloc.rsplit("@", 1)[-1]
        return ConnectionSpec(nombre, motor, MongoSettings(url.strip(), database), host, database)

    host, port = parts.hostname, parts.port
    if motor == "firebird":
        database = path[1:] if path.startswith("/") else path
        if not database:
            raise ValueError(f"Conexión {nombre}: la URL de Firebird debe indicar la ruta o el alias de la base")
        settings = FirebirdSettings(host, port, database, user or "SYSDBA", password, query.get("charset", "UTF8"))
        return ConnectionSpec(nombre, motor, settings, host, database)

    database = path.lstrip("/")
    if not database or "/" in database:
        raise ValueError(f"Conexión {nombre}: la URL debe terminar en /base")
    if motor == "postgresql":
        settings = PostgresSettings(host or "localhost", port or 5432, database, user, password, query.get("sslmode"))
        return ConnectionSpec(nombre, motor, settings, settings.host, database)
    server = f"{host or 'localhost'},{port}" if port else (host or "localhost")
    driver = query.get("driver", os.getenv("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server"))
    return ConnectionSpec(nombre, motor, SqlServerSettings(driver, server, database, user, password), server, database)


def connection_urls(environ: Mapping[str, str]) -> Dict[str, str]:
    """{nombre: url} de las variables NEXUS_CONEXION_<NOMBRE> no vacías."""
    found: Dict[str, str] = {}
    for key, value in environ.items():
        if key.upper().startswith(ENV_PREFIX) and value and value.strip():
            found[key[len(ENV_PREFIX):].lower()] = value.strip()
    return found


def build_catalog(spec: ConnectionSpec, query_timeout: int = 30, backup_timeout: int = 600):
    """Catálogo del motor; los drivers se importan aquí para que un motor sin driver instalado no afecte a los demás."""
    if spec.motor == "sqlserver":
        from src.agents.database_agent.catalog import SqlServerCatalog
        from src.agents.sqlserver import SqlServerClient

        return SqlServerCatalog(SqlServerClient(spec.settings, query_timeout), backup_timeout)
    if spec.motor == "postgresql":
        from src.agents.database_agent.postgres_catalog import PostgresCatalog

        return PostgresCatalog(spec.settings, query_timeout, backup_timeout)
    if spec.motor == "firebird":
        from src.agents.database_agent.firebird_catalog import FirebirdCatalog

        return FirebirdCatalog(spec.settings, query_timeout, backup_timeout)
    from src.agents.database_agent.mongo_catalog import MongoCatalog

    return MongoCatalog(spec.settings, query_timeout, backup_timeout)
