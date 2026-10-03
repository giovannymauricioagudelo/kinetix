"""Historial de ejecuciones de pruebas de Prism (tabla prism_ejecuciones)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient

QUEUED, RUNNING = "en_cola", "ejecutando"
FINISHED = ("aprobada", "fallida", "error")


@dataclass(frozen=True)
class TestRun:
    __test__ = False

    id_ejecucion: str
    objetivos: List[str]
    filtro: Optional[str]
    con_cobertura: bool
    suite_completa: bool
    estado: str
    commit_git: Optional[str]
    arbol_limpio: bool
    iniciada_por: str
    fecha_inicio: datetime
    total: int = 0
    pasadas: int = 0
    fallidas: int = 0
    omitidas: int = 0
    errores: int = 0
    cobertura: Optional[float] = None
    duracion_s: float = 0.0
    fecha_fin: Optional[datetime] = None
    detalle: Dict[str, Any] = field(default_factory=dict)


class TestRunRepository(ABC):
    __test__ = False

    @abstractmethod
    def create(self, run: TestRun) -> None: ...

    @abstractmethod
    def update(self, run: TestRun) -> None: ...

    @abstractmethod
    def get(self, id_ejecucion: str) -> Optional[TestRun]: ...

    @abstractmethod
    def recent(self, limit: int, estado: Optional[str] = None) -> List[TestRun]: ...

    @abstractmethod
    def latest_full_run(self, commit: str) -> Optional[TestRun]:
        """Última ejecución terminada de la suite completa con cobertura para ese commit."""

    @abstractmethod
    def abandon_unfinished(self, now: datetime) -> int:
        """Marca como error las ejecuciones que quedaron a medias (reinicio del proceso)."""

    @abstractmethod
    def ping(self) -> None: ...


class InMemoryTestRunRepository(TestRunRepository):
    def __init__(self) -> None:
        self._runs: Dict[str, TestRun] = {}
        self._lock = threading.Lock()

    def create(self, run: TestRun) -> None:
        with self._lock:
            self._runs[run.id_ejecucion] = run

    def update(self, run: TestRun) -> None:
        with self._lock:
            self._runs[run.id_ejecucion] = run

    def get(self, id_ejecucion: str) -> Optional[TestRun]:
        return self._runs.get(id_ejecucion)

    def recent(self, limit: int, estado: Optional[str] = None) -> List[TestRun]:
        runs = sorted(self._runs.values(), key=lambda r: r.fecha_inicio, reverse=True)
        return [r for r in runs if estado is None or r.estado == estado][:limit]

    def latest_full_run(self, commit: str) -> Optional[TestRun]:
        return next((r for r in self.recent(10_000) if r.commit_git == commit and r.suite_completa
                     and r.con_cobertura and r.estado in FINISHED), None)

    def abandon_unfinished(self, now: datetime) -> int:
        with self._lock:
            stale = [r for r in self._runs.values() if r.estado in (QUEUED, RUNNING)]
            for run in stale:
                self._runs[run.id_ejecucion] = replace(run, estado="error", fecha_fin=now,
                                                       detalle={**run.detalle, "mensaje": "Ejecución interrumpida por reinicio"})
            return len(stale)

    def ping(self) -> None:
        return None


class SqlServerTestRunRepository(TestRunRepository):
    _COLUMNS = ("id_ejecucion, objetivos, filtro, con_cobertura, suite_completa, estado, commit_git, arbol_limpio, "
                "iniciada_por, fecha_inicio, total, pasadas, fallidas, omitidas, errores, cobertura, duracion_s, fecha_fin, detalle")

    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def ping(self) -> None:
        self._db.ping()

    @staticmethod
    def _params(run: TestRun) -> tuple:
        return (run.id_ejecucion, dumps(run.objetivos), run.filtro, run.con_cobertura, run.suite_completa, run.estado,
                run.commit_git, run.arbol_limpio, run.iniciada_por[:200], run.fecha_inicio, run.total, run.pasadas,
                run.fallidas, run.omitidas, run.errores, run.cobertura, run.duracion_s, run.fecha_fin, dumps(run.detalle))

    @staticmethod
    def _run(row) -> TestRun:
        return TestRun(
            id_ejecucion=row[0], objetivos=loads(row[1], []), filtro=row[2], con_cobertura=bool(row[3]),
            suite_completa=bool(row[4]), estado=row[5], commit_git=row[6], arbol_limpio=bool(row[7]),
            iniciada_por=row[8] or "", fecha_inicio=row[9], total=row[10] or 0, pasadas=row[11] or 0,
            fallidas=row[12] or 0, omitidas=row[13] or 0, errores=row[14] or 0,
            cobertura=float(row[15]) if row[15] is not None else None, duracion_s=float(row[16] or 0),
            fecha_fin=row[17], detalle=loads(row[18], {}),
        )

    def create(self, run: TestRun) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(f"INSERT INTO dbo.prism_ejecuciones ({self._COLUMNS}) VALUES ({', '.join('?' * 19)})", self._params(run))

    def update(self, run: TestRun) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.prism_ejecuciones SET estado = ?, total = ?, pasadas = ?, fallidas = ?, omitidas = ?, errores = ?, "
                "cobertura = ?, duracion_s = ?, fecha_fin = ?, detalle = ? WHERE id_ejecucion = ?",
                (run.estado, run.total, run.pasadas, run.fallidas, run.omitidas, run.errores, run.cobertura,
                 run.duracion_s, run.fecha_fin, dumps(run.detalle), run.id_ejecucion),
            )

    def get(self, id_ejecucion: str) -> Optional[TestRun]:
        with self._db.cursor() as cur:
            cur.execute(f"SELECT {self._COLUMNS} FROM dbo.prism_ejecuciones WHERE id_ejecucion = ?", (id_ejecucion,))
            row = cur.fetchone()
        return self._run(row) if row else None

    def recent(self, limit: int, estado: Optional[str] = None) -> List[TestRun]:
        sql = f"SELECT TOP (?) {self._COLUMNS} FROM dbo.prism_ejecuciones"
        params: List[Any] = [limit]
        if estado:
            sql += " WHERE estado = ?"
            params.append(estado)
        with self._db.cursor() as cur:
            cur.execute(sql + " ORDER BY fecha_inicio DESC", tuple(params))
            return [self._run(r) for r in cur.fetchall()]

    def latest_full_run(self, commit: str) -> Optional[TestRun]:
        with self._db.cursor() as cur:
            cur.execute(
                f"SELECT TOP 1 {self._COLUMNS} FROM dbo.prism_ejecuciones WHERE commit_git = ? AND suite_completa = 1 "
                "AND con_cobertura = 1 AND estado IN ('aprobada', 'fallida', 'error') ORDER BY fecha_inicio DESC",
                (commit,),
            )
            row = cur.fetchone()
        return self._run(row) if row else None

    def abandon_unfinished(self, now: datetime) -> int:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.prism_ejecuciones SET estado = 'error', fecha_fin = ?, "
                "detalle = JSON_MODIFY(COALESCE(detalle, '{}'), '$.mensaje', N'Ejecución interrumpida por reinicio') "
                "WHERE estado IN ('en_cola', 'ejecutando')",
                (now,),
            )
            return cur.rowcount
