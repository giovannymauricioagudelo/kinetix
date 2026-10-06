"""Catálogo de Nexus sobre PostgreSQL (psycopg2): esquema, funciones/procedimientos, DDL y respaldos con pg_dump."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

from src.agents.database_agent.catalog import DatabaseCatalog, ProcedureParameter, ProcedureResult, json_value
from src.agents.database_agent.engines import PostgresSettings
from src.agents.database_agent.file_backups import backup_entry, backup_target, list_backup_files, run_tool, tool_path
from src.agents.security_agent.models import InvalidInputError

_USER_SCHEMAS = "n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg\\_%%'"
_INPUT_MODES = {"i", "b", "v"}


def _message(error: Exception) -> str:
    primary = getattr(getattr(error, "diag", None), "message_primary", None)
    lines = str(error).strip().splitlines()
    return (primary or (lines[0] if lines else "") or "Error de PostgreSQL")[:500]


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class PostgresCatalog(DatabaseCatalog):
    motor = "postgresql"

    def __init__(self, settings: PostgresSettings, timeout_seconds: int = 30, backup_timeout_seconds: int = 600) -> None:
        self._settings = settings
        self._timeout = timeout_seconds
        self._backup_timeout = backup_timeout_seconds

    @contextmanager
    def _cursor(self, commit: bool = False) -> Iterator[Any]:
        import psycopg2

        s = self._settings
        kwargs: Dict[str, Any] = {
            "host": s.host, "port": s.port, "dbname": s.database, "user": s.user, "password": s.password,
            "connect_timeout": min(self._timeout, 30), "application_name": "kinetix-nexus",
            "options": f"-c statement_timeout={self._timeout * 1000}",
        }
        if s.sslmode:
            kwargs["sslmode"] = s.sslmode
        conn = psycopg2.connect(**kwargs)
        try:
            cur = conn.cursor()
            yield cur
            if commit:
                conn.commit()
            else:
                conn.rollback()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _statement_error(error: Exception) -> bool:
        import psycopg2

        return isinstance(error, (psycopg2.ProgrammingError, psycopg2.IntegrityError, psycopg2.DataError,
                                  psycopg2.InternalError))

    def ping(self) -> None:
        with self._cursor() as cur:
            cur.execute("SELECT 1")

    # ================================================================ tablas

    def list_tables(self) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT n.nspname, c.relname, GREATEST(c.reltuples, 0)::bigint FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                f"WHERE c.relkind IN ('r', 'p') AND {_USER_SCHEMAS} ORDER BY 1, 2"
            )
            return [{"esquema": r[0], "tabla": r[1], "filas": int(r[2]), "creada": None, "modificada": None}
                    for r in cur.fetchall()]

    def describe_table(self, schema: Optional[str], table: str) -> Optional[Dict[str, Any]]:
        schema = schema or "public"
        with self._cursor() as cur:
            cur.execute(
                "SELECT c.oid, GREATEST(c.reltuples, 0)::bigint FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relname = %s AND c.relkind IN ('r', 'p')",
                (schema, table),
            )
            found = cur.fetchone()
            if found is None:
                return None
            oid, rows = found
            cur.execute(
                "SELECT column_name, data_type, character_maximum_length, numeric_precision, numeric_scale, "
                "is_nullable = 'YES', is_identity = 'YES' OR COALESCE(column_default, '') LIKE 'nextval(%%', column_default "
                "FROM information_schema.columns WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
                (schema, table),
            )
            columns = [
                {
                    "nombre": r[0], "tipo": r[1], "longitud": r[2],
                    "precision": r[3] if r[1] == "numeric" else None, "escala": r[4] if r[1] == "numeric" else None,
                    "nulable": bool(r[5]), "identidad": bool(r[6]), "default": r[7],
                }
                for r in cur.fetchall()
            ]
            cur.execute(
                "SELECT i.relname, am.amname, ix.indisunique, ix.indisprimary, a.attname FROM pg_index ix "
                "JOIN pg_class i ON i.oid = ix.indexrelid JOIN pg_am am ON am.oid = i.relam "
                "JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ord) ON true "
                "JOIN pg_attribute a ON a.attrelid = ix.indrelid AND a.attnum = k.attnum "
                "WHERE ix.indrelid = %s ORDER BY i.relname, k.ord",
                (oid,),
            )
            indexes: Dict[str, Dict[str, Any]] = {}
            for name, kind, unique, primary, column in cur.fetchall():
                entry = indexes.setdefault(name, {"nombre": name, "tipo": kind, "unico": bool(unique),
                                                  "clave_primaria": bool(primary), "columnas": []})
                entry["columnas"].append(column)
            cur.execute(
                "SELECT con.conname, a.attname, rn.nspname, rc.relname, ra.attname FROM pg_constraint con "
                "JOIN LATERAL unnest(con.conkey, con.confkey) WITH ORDINALITY AS k(col, refcol, ord) ON true "
                "JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.col "
                "JOIN pg_class rc ON rc.oid = con.confrelid JOIN pg_namespace rn ON rn.oid = rc.relnamespace "
                "JOIN pg_attribute ra ON ra.attrelid = con.confrelid AND ra.attnum = k.refcol "
                "WHERE con.contype = 'f' AND con.conrelid = %s ORDER BY con.conname, k.ord",
                (oid,),
            )
            foreign_keys = [{"nombre": r[0], "columna": r[1], "referencia": f"{r[2]}.{r[3]}", "columna_referenciada": r[4]}
                            for r in cur.fetchall()]
        primary = next((i["columnas"] for i in indexes.values() if i["clave_primaria"]), [])
        return {
            "esquema": schema, "tabla": table, "filas": int(rows), "filas_estimadas": True, "columnas": columns,
            "clave_primaria": primary, "indices": list(indexes.values()), "claves_foraneas": foreign_keys,
        }

    # ================================================================ funciones y procedimientos

    def list_procedures(self) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT n.nspname, p.proname, p.prokind, p.proargnames, p.proargmodes::text[] FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid = p.pronamespace "
                "LEFT JOIN pg_depend d ON d.objid = p.oid AND d.deptype = 'e' "
                f"WHERE p.prokind IN ('f', 'p') AND d.objid IS NULL AND {_USER_SCHEMAS} ORDER BY 1, 2"
            )
            rows = cur.fetchall()
        result = []
        for schema, name, kind, arg_names, arg_modes in rows:
            names = arg_names or []
            modes = arg_modes or ["i"] * len(names)
            result.append({
                "esquema": schema, "nombre": name, "tipo": "procedimiento" if kind == "p" else "funcion",
                "parametros": [f"@{n}" for n, m in zip(names, modes) if n and m in _INPUT_MODES],
                "creado": None, "modificado": None,
            })
        return result

    def _routine(self, cur, schema: str, name: str) -> Optional[Tuple[int, str, List[ProcedureParameter]]]:
        """Primera sobrecarga (por oid) de la rutina: (oid, prokind, parámetros sin las columnas de RETURNS TABLE)."""
        cur.execute(
            "SELECT p.oid, p.prokind, p.proargnames, p.proargmodes::text[], p.pronargdefaults, "
            "ARRAY(SELECT format_type(t, NULL) FROM unnest(COALESCE(p.proallargtypes, p.proargtypes::oid[])) "
            "WITH ORDINALITY AS u(t, o) ORDER BY o) "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = %s AND p.proname = %s AND p.prokind IN ('f', 'p') ORDER BY p.oid LIMIT 1",
            (schema, name),
        )
        row = cur.fetchone()
        if row is None:
            return None
        oid, kind, arg_names, arg_modes, n_defaults, types = row
        types = types or []
        names = arg_names or [None] * len(types)
        modes = arg_modes or ["i"] * len(types)
        inputs = [i for i, m in enumerate(modes) if m in _INPUT_MODES]
        with_default = set(inputs[len(inputs) - (n_defaults or 0):]) if n_defaults else set()
        parameters = [
            ProcedureParameter(f"@{names[i] or f'${i + 1}'}", types[i], None, modes[i] == "o", i in with_default)
            for i in range(len(types)) if modes[i] != "t"
        ]
        return oid, kind, parameters

    def procedure_parameters(self, schema: Optional[str], name: str) -> Optional[List[ProcedureParameter]]:
        with self._cursor() as cur:
            routine = self._routine(cur, schema or "public", name)
            return None if routine is None else routine[2]

    def procedure_definition(self, schema: Optional[str], name: str) -> Optional[str]:
        with self._cursor() as cur:
            routine = self._routine(cur, schema or "public", name)
            if routine is None:
                return None
            cur.execute("SELECT pg_get_functiondef(%s)", (routine[0],))
            return cur.fetchone()[0]

    def execute_procedure(self, schema: Optional[str], name: str, arguments: Dict[str, Any], max_rows: int) -> ProcedureResult:
        schema = schema or "public"
        target = f"{_quote(schema)}.{_quote(name)}"
        named = ", ".join(f"{_quote(param.lstrip('@'))} => %s" for param in arguments)
        result = ProcedureResult()
        try:
            with self._cursor(commit=True) as cur:
                routine = self._routine(cur, schema, name)
                if routine is None:
                    raise InvalidInputError(f"La rutina {schema}.{name} no existe")
                sql = f"CALL {target}({named})" if routine[1] == "p" else f"SELECT * FROM {target}({named})"
                cur.execute(sql, tuple(arguments.values()))
                if cur.description:
                    rows = cur.fetchmany(max_rows + 1)
                    result.conjuntos.append({
                        "columnas": [d[0] for d in cur.description],
                        "filas": [[json_value(v) for v in row] for row in rows[:max_rows]],
                        "truncado": len(rows) > max_rows,
                    })
        except InvalidInputError:
            raise
        except Exception as e:
            if self._statement_error(e):
                raise InvalidInputError(f"La rutina falló: {_message(e)}") from None
            raise
        return result

    # ================================================================ DDL y respaldos

    def apply_ddl(self, script: str) -> None:
        try:
            with self._cursor(commit=True) as cur:
                cur.execute(script)
        except Exception as e:
            if self._statement_error(e):
                raise InvalidInputError(f"PostgreSQL rechazó el DDL: {_message(e)}") from None
            raise

    def _tool_env(self) -> Dict[str, str]:
        env = {"PGPASSWORD": self._settings.password, "PGAPPNAME": "kinetix-nexus"}
        if self._settings.sslmode:
            env["PGSSLMODE"] = self._settings.sslmode
        return env

    def backup(self, directory: Optional[str], label: str) -> Dict[str, Any]:
        s = self._settings
        path = backup_target(directory, s.database, label, ".dump")
        started = datetime.now(timezone.utc)
        run_tool([tool_path("pg_dump"), "--format=custom", "--no-password", f"--file={path}", f"--host={s.host}",
                  f"--port={s.port}", f"--username={s.user}", f"--dbname={s.database}"],
                 self._tool_env(), self._backup_timeout)
        run_tool([tool_path("pg_restore"), "--list", str(path)], None, self._backup_timeout)
        return backup_entry(path, s.database, started, verified=True)

    def list_backups(self, directory: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return list_backup_files(directory, self._settings.database, ".dump", limit)
