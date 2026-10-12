"""Cliente SQL Server compartido por los agentes que persisten en la base kinetix.

Todo acceso a datos pasa por procedimientos de los esquemas de cada agente (KINETIX_PROCEDIMIENTOS.sql):
el rol kinetix_app_rol solo tiene EXECUTE sobre ellos.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

import pyodbc

from src.agents.security_agent.config import SqlServerSettings

_DRIVER_PREFIX = re.compile(r"^(\[[^\]]*\]\s*)+")
_DRIVER_SUFFIX = re.compile(r"\s*\((SQLExecDirectW|SQLExecute|SQLMoreResults|SQLFetch)\)\s*$")
ESQUEMAS = ("sentinel", "nexus", "matrix", "synapse", "genesis", "insight", "aurora", "prism", "orbit", "vector")
_PROCEDIMIENTO = re.compile(rf"(?:{'|'.join(ESQUEMAS)})\.[a-z][a-z0-9_]*")
_PARAMETRO = re.compile(r"[a-z][a-z0-9_]*")


def llamada(procedimiento: str, parametros: Sequence[str]) -> str:
    """`EXEC esquema.x @a = ?, ...`: solo se componen nombres validados; los valores siempre viajan como parámetros."""
    if not _PROCEDIMIENTO.fullmatch(procedimiento) or not all(_PARAMETRO.fullmatch(p) for p in parametros):
        raise ValueError(f"Procedimiento o parámetro no válido: {procedimiento} {list(parametros)}")
    return " ".join(("EXEC", procedimiento, ", ".join(f"@{p} = ?" for p in parametros))).rstrip()


def ejecutar(cur: Any, procedimiento: str, **parametros: Any) -> Any:
    """Ejecuta un procedimiento de un agente y devuelve el cursor para leer su resultado."""
    return cur.execute(llamada(procedimiento, list(parametros)), tuple(parametros.values()))


def afectadas(cur: Any) -> int:
    """Filas afectadas que devuelve el procedimiento (con SET NOCOUNT ON el rowcount del driver no sirve)."""
    return int(cur.fetchone()[0])


class SqlServerClient:
    def __init__(self, settings: SqlServerSettings, timeout_seconds: int = 30) -> None:
        self._connection_string = settings.connection_string()
        self._timeout = timeout_seconds

    @contextmanager
    def cursor(self, commit: bool = False, autocommit: bool = False, timeout: Optional[int] = None) -> Iterator[pyodbc.Cursor]:
        conn = pyodbc.connect(self._connection_string, autocommit=autocommit)
        conn.timeout = self._timeout if timeout is None else timeout
        try:
            cur = conn.cursor()
            yield cur
            if commit and not autocommit:
                conn.commit()
        except Exception:
            if not autocommit:
                conn.rollback()
            raise
        finally:
            conn.close()

    def ping(self) -> None:
        with self.cursor() as cur:
            cur.execute("SELECT 1")


def server_message(error: pyodbc.Error) -> str:
    """Mensaje de SQL Server sin los prefijos del driver ODBC."""
    raw = str(error.args[1]) if len(error.args) > 1 else str(error)
    first = raw.split("; ")[0]
    message = _DRIVER_SUFFIX.sub("", _DRIVER_PREFIX.sub("", first)).strip()
    return message[:500] or "Error de SQL Server"


def is_statement_error(error: Exception) -> bool:
    """True si el error lo produjo la sentencia (datos, sintaxis, restricciones) y no la conexión."""
    return isinstance(error, (pyodbc.ProgrammingError, pyodbc.IntegrityError, pyodbc.DataError))
