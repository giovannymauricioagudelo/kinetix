"""Historial de ejecuciones de pruebas de Prism (tabla prism_ejecuciones)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient, afectadas, ejecutar

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
    """Persistencia sobre los procedimientos del esquema prism de la base kinetix."""

    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def ping(self) -> None:
        self._db.ping()

    @staticmethod
    def _results(run: TestRun) -> Dict[str, Any]:
        return dict(id_ejecucion=run.id_ejecucion, estado=run.estado, total=run.total, pasadas=run.pasadas,
                    fallidas=run.fallidas, omitidas=run.omitidas, errores=run.errores, cobertura=run.cobertura,
                    duracion_s=run.duracion_s, fecha_fin=run.fecha_fin, detalle=dumps(run.detalle))

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
            ejecutar(cur, "prism.ejecucion_insertar", **self._results(run), objetivos=dumps(run.objetivos), filtro=run.filtro,
                     con_cobertura=run.con_cobertura, suite_completa=run.suite_completa, commit_git=run.commit_git,
                     arbol_limpio=run.arbol_limpio, iniciada_por=run.iniciada_por[:200], fecha_inicio=run.fecha_inicio)

    def update(self, run: TestRun) -> None:
        with self._db.cursor(commit=True) as cur:
            ejecutar(cur, "prism.ejecucion_actualizar", **self._results(run))

    def get(self, id_ejecucion: str) -> Optional[TestRun]:
        with self._db.cursor() as cur:
            row = ejecutar(cur, "prism.ejecucion_obtener", id_ejecucion=id_ejecucion).fetchone()
        return self._run(row) if row else None

    def recent(self, limit: int, estado: Optional[str] = None) -> List[TestRun]:
        with self._db.cursor() as cur:
            return [self._run(r) for r in ejecutar(cur, "prism.ejecucion_listar", estado=estado or None, limite=limit).fetchall()]

    def latest_full_run(self, commit: str) -> Optional[TestRun]:
        with self._db.cursor() as cur:
            row = ejecutar(cur, "prism.ejecucion_completa_ultima", commit_git=commit).fetchone()
        return self._run(row) if row else None

    def abandon_unfinished(self, now: datetime) -> int:
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "prism.ejecucion_abandonar", ahora=now))
