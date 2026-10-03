"""Historial de análisis de código de Vector (tabla vector_analisis)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient


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
    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def ping(self) -> None:
        self._db.ping()

    def save(self, record: AnalysisRecord) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO dbo.vector_analisis (id_analisis, objetivo, archivos, lineas, puntuacion, criticos, altos, "
                "resumen, analizado_por, fecha) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record.id_analisis, record.objetivo[:500], record.archivos, record.lineas, record.puntuacion,
                 record.criticos, record.altos, dumps(record.resumen), record.analizado_por[:200], record.fecha),
            )

    def recent(self, limit: int) -> List[AnalysisRecord]:
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT TOP (?) id_analisis, objetivo, archivos, lineas, puntuacion, criticos, altos, analizado_por, fecha, resumen "
                "FROM dbo.vector_analisis ORDER BY fecha DESC",
                (limit,),
            )
            rows = cur.fetchall()
        return [AnalysisRecord(r[0], r[1], r[2], r[3], float(r[4]), r[5], r[6], r[7] or "", r[8], loads(r[9], {})) for r in rows]
