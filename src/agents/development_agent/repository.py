"""Historial de análisis de código de Vector (tabla vector_analisis)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient, ejecutar


@dataclass(frozen=True)
class AnalysisRecord:
    id_analisis: str
    objetivo: str
    archivos: int
    lineas: int
    puntuacion: float
    criticos: int
    altos: int
    analizado_por: str
    fecha: datetime
    resumen: Dict[str, Any] = field(default_factory=dict)


class AnalysisRepository(ABC):
    @abstractmethod
    def save(self, record: AnalysisRecord) -> None: ...

    @abstractmethod
    def recent(self, limit: int) -> List[AnalysisRecord]: ...

    @abstractmethod
    def ping(self) -> None: ...


class InMemoryAnalysisRepository(AnalysisRepository):
    def __init__(self) -> None:
        self._records: List[AnalysisRecord] = []
        self._lock = threading.Lock()

    def save(self, record: AnalysisRecord) -> None:
        with self._lock:
            self._records.append(record)

    def recent(self, limit: int) -> List[AnalysisRecord]:
        return list(reversed(self._records))[:limit]

    def ping(self) -> None:
        return None


class SqlServerAnalysisRepository(AnalysisRepository):
    """Persistencia sobre los procedimientos del esquema vector de la base kinetix."""

    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def ping(self) -> None:
        self._db.ping()

    def save(self, record: AnalysisRecord) -> None:
        r = record
        with self._db.cursor(commit=True) as cur:
            ejecutar(cur, "vector.analisis_insertar", id_analisis=r.id_analisis, objetivo=r.objetivo[:500], archivos=r.archivos,
                     lineas=r.lineas, puntuacion=r.puntuacion, criticos=r.criticos, altos=r.altos, resumen=dumps(r.resumen),
                     analizado_por=r.analizado_por[:200], fecha=r.fecha)

    def recent(self, limit: int) -> List[AnalysisRecord]:
        with self._db.cursor() as cur:
            rows = ejecutar(cur, "vector.analisis_listar", limite=limit).fetchall()
        return [AnalysisRecord(r[0], r[1], r[2], r[3], float(r[4]), r[5], r[6], r[7] or "", r[8], loads(r[9], {})) for r in rows]
