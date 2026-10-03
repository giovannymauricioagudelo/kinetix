"""Cliente SQL Server compartido por los agentes que persisten en la base kinetix."""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Dict, Iterator, Optional, Tuple

import pyodbc

from src.agents.security_agent.config import SqlServerSettings

_DRIVER_PREFIX = re.compile(r"^(\[[^\]]*\]\s*)+")
_DRIVER_SUFFIX = re.compile(r"\s*\((SQLExecDirectW|SQLExecute|SQLMoreResults|SQLFetch)\)\s*$")


class SqlServerClient:
    def __init__(self, settings: SqlServerSettings, timeout_seconds: int = 30) -> None:
        self._connection_string = settings.connection_string()
        self._timeout = timeout_seconds
        self._columns: Dict[Tuple[str, str], bool] = {}

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

    def has_column(self, table: str, column: str) -> bool:
        key = (table, column)
        if key not in self._columns:
            with self.cursor() as cur:
                cur.execute("SELECT COL_LENGTH(?, ?)", (f"dbo.{table}", column))
                self._columns[key] = cur.fetchone()[0] is not None
        return self._columns[key]


def server_message(error: pyodbc.Error) -> str:
    """Mensaje de SQL Server sin los prefijos del driver ODBC."""
    raw = str(error.args[1]) if len(error.args) > 1 else str(error)
    first = raw.split("; ")[0]
    message = _DRIVER_SUFFIX.sub("", _DRIVER_PREFIX.sub("", first)).strip()
    return message[:500] or "Error de SQL Server"


def is_statement_error(error: Exception) -> bool:
    """True si el error lo produjo la sentencia (datos, sintaxis, restricciones) y no la conexión."""
    return isinstance(error, (pyodbc.ProgrammingError, pyodbc.IntegrityError, pyodbc.DataError))
