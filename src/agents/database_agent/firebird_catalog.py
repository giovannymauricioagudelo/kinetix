"""Catálogo de Nexus sobre Firebird 3+ (firebird-driver, requiere la librería cliente fbclient):
tablas del sistema RDB$, procedimientos, DDL en formato isql y respaldos con gbak.
Firebird no tiene esquemas: el esquema recibido se ignora."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

from src.agents.database_agent.catalog import DatabaseCatalog, ProcedureParameter, ProcedureResult, json_value
from src.agents.database_agent.dialects import firebird_statements
from src.agents.database_agent.engines import FirebirdSettings
from src.agents.database_agent.file_backups import backup_entry, backup_target, list_backup_files, run_tool, tool_path
from src.agents.security_agent.models import InvalidInputError

FIELD_TYPES = {
    7: "smallint", 8: "integer", 16: "bigint", 26: "int128", 10: "float", 27: "double precision",
    12: "date", 13: "time", 35: "timestamp", 28: "time with time zone", 29: "timestamp with time zone",
    14: "char", 37: "varchar", 261: "blob", 23: "boolean", 24: "decfloat(16)", 25: "decfloat(34)",
}
_SCALED = {7, 8, 16, 26}
SELECTABLE = 1


def field_type(code: int, subtype: Optional[int]) -> str:
    if code in _SCALED and subtype in (1, 2):
        return "numeric" if subtype == 1 else "decimal"
    if code == 261 and subtype == 1:
        return "blob sub_type text"
    return FIELD_TYPES.get(code, f"tipo_{code}")


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _default(source: Optional[str]) -> Optional[str]:
    if not source:
        return None
    text = str(source).strip()
    return text[7:].strip() if text.upper().startswith("DEFAULT") else text


def _message(error: Exception) -> str:
    lines = [line.strip() for line in str(error).splitlines() if line.strip()]
    return (" ".join(lines[:3]) or "Error de Firebird")[:500]


class FirebirdCatalog(DatabaseCatalog):
    motor = "firebird"

    def __init__(self, settings: FirebirdSettings, timeout_seconds: int = 30, backup_timeout_seconds: int = 600) -> None:
        self._settings = settings
        self._timeout = timeout_seconds
        self._backup_timeout = backup_timeout_seconds

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        from firebird.driver import connect

        s = self._settings
        conn = connect(s.dsn, user=s.user, password=s.password, charset=s.charset)
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def _cursor(self, commit: bool = False) -> Iterator[Any]:
        with self._connection() as conn:
            cur = conn.cursor()
            yield cur
            if commit:
                conn.commit()
            else:
                conn.rollback()

    @staticmethod
    def _statement_error(error: Exception) -> bool:
        from firebird.driver import DataError, DatabaseError, IntegrityError, OperationalError, ProgrammingError

        if isinstance(error, (ProgrammingError, IntegrityError, DataError)):
            return True
        # Los errores de sentencia (sintaxis, excepciones de PSQL, metadatos) llegan como DatabaseError genérico.
        return isinstance(error, DatabaseError) and not isinstance(error, OperationalError)

    def ping(self) -> None:
        with self._cursor() as cur:
            cur.execute("SELECT 1 FROM RDB$DATABASE")
            cur.fetchone()

    # ================================================================ tablas

    def list_tables(self) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT TRIM(RDB$RELATION_NAME) FROM RDB$RELATIONS "
                "WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0 AND RDB$VIEW_BLR IS NULL ORDER BY 1"
            )
            return [{"esquema": None, "tabla": r[0], "filas": None, "creada": None, "modificada": None}
                    for r in cur.fetchall()]

    @staticmethod
    def _resolve(cur, system_table: str, column: str, name: str, extra: str = "") -> Optional[str]:
        """Nombre real: exacto si existe (creado con comillas), si no en mayúsculas (sin comillas)."""
        cur.execute(
            f"SELECT TRIM({column}) FROM {system_table} WHERE ({column} = ? OR {column} = ?){extra} "
            f"ORDER BY CASE WHEN {column} = ? THEN 0 ELSE 1 END",
            (name, name.upper(), name),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def describe_table(self, schema: Optional[str], table: str) -> Optional[Dict[str, Any]]:
        with self._cursor() as cur:
            name = self._resolve(cur, "RDB$RELATIONS", "RDB$RELATION_NAME", table,
                                 " AND RDB$VIEW_BLR IS NULL AND COALESCE(RDB$SYSTEM_FLAG, 0) = 0")
            if name is None:
                return None
            cur.execute(
                "SELECT TRIM(rf.RDB$FIELD_NAME), f.RDB$FIELD_TYPE, f.RDB$FIELD_SUB_TYPE, f.RDB$CHARACTER_LENGTH, "
                "f.RDB$FIELD_PRECISION, f.RDB$FIELD_SCALE, COALESCE(rf.RDB$NULL_FLAG, f.RDB$NULL_FLAG, 0), "
                "rf.RDB$IDENTITY_TYPE, COALESCE(rf.RDB$DEFAULT_SOURCE, f.RDB$DEFAULT_SOURCE) "
                "FROM RDB$RELATION_FIELDS rf JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = rf.RDB$FIELD_SOURCE "
                "WHERE rf.RDB$RELATION_NAME = ? ORDER BY rf.RDB$FIELD_POSITION",
                (name,),
            )
            columns = []
            for col, code, subtype, length, precision, scale, not_null, identity, default in cur.fetchall():
                kind = field_type(code, subtype)
                scaled = kind in ("numeric", "decimal")
                columns.append({
                    "nombre": col, "tipo": kind, "longitud": length,
                    "precision": precision if scaled else None, "escala": -scale if scaled and scale else None,
                    "nulable": not not_null, "identidad": identity is not None, "default": _default(default),
                })
            cur.execute(
                "SELECT TRIM(i.RDB$INDEX_NAME), COALESCE(i.RDB$UNIQUE_FLAG, 0), TRIM(rc.RDB$CONSTRAINT_TYPE), "
                "TRIM(s.RDB$FIELD_NAME), COALESCE(i.RDB$INDEX_TYPE, 0) FROM RDB$INDICES i "
                "JOIN RDB$INDEX_SEGMENTS s ON s.RDB$INDEX_NAME = i.RDB$INDEX_NAME "
                "LEFT JOIN RDB$RELATION_CONSTRAINTS rc ON rc.RDB$INDEX_NAME = i.RDB$INDEX_NAME "
                "WHERE i.RDB$RELATION_NAME = ? ORDER BY i.RDB$INDEX_NAME, s.RDB$FIELD_POSITION",
                (name,),
            )
            indexes: Dict[str, Dict[str, Any]] = {}
            for index, unique, constraint, column, descending in cur.fetchall():
                entry = indexes.setdefault(index, {
                    "nombre": index, "tipo": "descendente" if descending else "ascendente", "unico": bool(unique),
                    "clave_primaria": constraint == "PRIMARY KEY", "columnas": [],
                })
                entry["columnas"].append(column)
            cur.execute(
                "SELECT TRIM(rc.RDB$CONSTRAINT_NAME), TRIM(s.RDB$FIELD_NAME), TRIM(ref.RDB$RELATION_NAME), TRIM(rs.RDB$FIELD_NAME) "
                "FROM RDB$RELATION_CONSTRAINTS rc "
                "JOIN RDB$REF_CONSTRAINTS fk ON fk.RDB$CONSTRAINT_NAME = rc.RDB$CONSTRAINT_NAME "
                "JOIN RDB$RELATION_CONSTRAINTS ref ON ref.RDB$CONSTRAINT_NAME = fk.RDB$CONST_NAME_UQ "
                "JOIN RDB$INDEX_SEGMENTS s ON s.RDB$INDEX_NAME = rc.RDB$INDEX_NAME "
                "JOIN RDB$INDEX_SEGMENTS rs ON rs.RDB$INDEX_NAME = ref.RDB$INDEX_NAME AND rs.RDB$FIELD_POSITION = s.RDB$FIELD_POSITION "
                "WHERE rc.RDB$CONSTRAINT_TYPE = 'FOREIGN KEY' AND rc.RDB$RELATION_NAME = ? "
                "ORDER BY 1, s.RDB$FIELD_POSITION",
                (name,),
            )
            foreign_keys = [{"nombre": r[0], "columna": r[1], "referencia": r[2], "columna_referenciada": r[3]}
                            for r in cur.fetchall()]
        primary = next((i["columnas"] for i in indexes.values() if i["clave_primaria"]), [])
        return {
            "esquema": None, "tabla": name, "filas": None, "columnas": columns, "clave_primaria": primary,
            "indices": list(indexes.values()), "claves_foraneas": foreign_keys,
        }

    # ================================================================ procedimientos

    _PARAMETERS_SQL = (
        "SELECT TRIM(pp.RDB$PROCEDURE_NAME), TRIM(pp.RDB$PARAMETER_NAME), pp.RDB$PARAMETER_TYPE, f.RDB$FIELD_TYPE, "
        "f.RDB$FIELD_SUB_TYPE, f.RDB$CHARACTER_LENGTH, COALESCE(pp.RDB$DEFAULT_SOURCE, f.RDB$DEFAULT_SOURCE) "
        "FROM RDB$PROCEDURE_PARAMETERS pp JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = pp.RDB$FIELD_SOURCE "
        "WHERE pp.RDB$PACKAGE_NAME IS NULL"
    )

    @staticmethod
    def _parameter(row) -> ProcedureParameter:
        _, name, direction, code, subtype, length, default = row
        return ProcedureParameter(f"@{name}", field_type(code, subtype), length, direction == 1, default is not None)

    def list_procedures(self) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT TRIM(RDB$PROCEDURE_NAME), RDB$PROCEDURE_TYPE FROM RDB$PROCEDURES "
                "WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0 AND RDB$PACKAGE_NAME IS NULL ORDER BY 1"
            )
            procedures = cur.fetchall()
            cur.execute(f"{self._PARAMETERS_SQL} AND pp.RDB$PARAMETER_TYPE = 0 "
                        "ORDER BY pp.RDB$PROCEDURE_NAME, pp.RDB$PARAMETER_NUMBER")
            params: Dict[str, List[str]] = {}
            for row in cur.fetchall():
                params.setdefault(row[0], []).append(f"@{row[1]}")
        return [
            {"esquema": None, "nombre": name, "tipo": "seleccionable" if kind == SELECTABLE else "ejecutable",
             "parametros": params.get(name, []), "creado": None, "modificado": None}
            for name, kind in procedures
        ]

    def _procedure(self, cur, name: str) -> Optional[Tuple[str, int, List[ProcedureParameter]]]:
        real = self._resolve(cur, "RDB$PROCEDURES", "RDB$PROCEDURE_NAME", name, " AND RDB$PACKAGE_NAME IS NULL")
        if real is None:
            return None
        cur.execute("SELECT RDB$PROCEDURE_TYPE FROM RDB$PROCEDURES WHERE RDB$PROCEDURE_NAME = ? AND RDB$PACKAGE_NAME IS NULL",
                    (real,))
        kind = cur.fetchone()[0]
        cur.execute(f"{self._PARAMETERS_SQL} AND pp.RDB$PROCEDURE_NAME = ? "
                    "ORDER BY pp.RDB$PARAMETER_TYPE, pp.RDB$PARAMETER_NUMBER", (real,))
        return real, kind, [self._parameter(row) for row in cur.fetchall()]

    def procedure_parameters(self, schema: Optional[str], name: str) -> Optional[List[ProcedureParameter]]:
        with self._cursor() as cur:
            found = self._procedure(cur, name)
            return None if found is None else found[2]

    def procedure_definition(self, schema: Optional[str], name: str) -> Optional[str]:
        with self._cursor() as cur:
            real = self._resolve(cur, "RDB$PROCEDURES", "RDB$PROCEDURE_NAME", name, " AND RDB$PACKAGE_NAME IS NULL")
            if real is None:
                return None
            cur.execute("SELECT RDB$PROCEDURE_SOURCE FROM RDB$PROCEDURES WHERE RDB$PROCEDURE_NAME = ? "
                        "AND RDB$PACKAGE_NAME IS NULL", (real,))
            source = cur.fetchone()[0]
            return None if source is None else str(source)

    @staticmethod
    def positional_values(inputs: List[ProcedureParameter], arguments: Dict[str, Any]) -> List[Any]:
        """Firebird pasa los parámetros por posición: solo se pueden omitir los últimos, y si tienen default."""
        provided = {k.lower(): v for k, v in arguments.items()}
        last = max((i for i, p in enumerate(inputs) if p.nombre.lower() in provided), default=-1)
        values = []
        for i, param in enumerate(inputs):
            if param.nombre.lower() in provided:
                values.append(provided[param.nombre.lower()])
            elif i < last or not param.tiene_default:
                raise InvalidInputError(f"Falta el parámetro {param.nombre} (Firebird pasa los parámetros por posición)")
        return values

    def execute_procedure(self, schema: Optional[str], name: str, arguments: Dict[str, Any], max_rows: int) -> ProcedureResult:
        result = ProcedureResult()
        try:
            with self._cursor(commit=True) as cur:
                found = self._procedure(cur, name)
                if found is None:
                    raise InvalidInputError(f"El procedimiento {name} no existe")
                real, kind, parameters = found
                values = self.positional_values([p for p in parameters if not p.salida], arguments)
                marks = ", ".join("?" for _ in values)
                if kind == SELECTABLE:
                    sql = f"SELECT * FROM {_quote(real)}" + (f"({marks})" if values else "")
                else:
                    sql = f"EXECUTE PROCEDURE {_quote(real)}" + (f" {marks}" if values else "")
                cur.execute(sql, values)
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
                raise InvalidInputError(f"El procedimiento falló: {_message(e)}") from None
            raise
        return result

    # ================================================================ DDL y respaldos

    def apply_ddl(self, script: str) -> None:
        """Script isql (SET TERM ^): cada sentencia se ejecuta y COMMIT confirma, porque Firebird aplica los metadatos al confirmar."""
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                for statement in firebird_statements(script):
                    if statement.upper() == "COMMIT":
                        conn.commit()
                        cur = conn.cursor()
                    else:
                        cur.execute(statement)
                conn.commit()
        except Exception as e:
            if self._statement_error(e):
                raise InvalidInputError(f"Firebird rechazó el DDL: {_message(e)}") from None
            raise

    def backup(self, directory: Optional[str], label: str) -> Dict[str, Any]:
        s = self._settings
        path = backup_target(directory, s.database, label, ".fbk")
        started = datetime.now(timezone.utc)
        run_tool([tool_path("gbak"), "-b", "-g", s.dsn, str(path)],
                 {"ISC_USER": s.user, "ISC_PASSWORD": s.password}, self._backup_timeout)
        if not path.exists() or path.stat().st_size == 0:
            raise InvalidInputError(f"gbak no generó el archivo de respaldo {path}")
        return backup_entry(path, s.database, started, verified=False)

    def list_backups(self, directory: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return list_backup_files(directory, self._settings.database, ".fbk", limit)
