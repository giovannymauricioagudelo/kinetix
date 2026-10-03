"""Reportes guardados y programaciones de Insight (tablas insight_reportes e insight_programaciones)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient


@dataclass(frozen=True)
class SavedReport:
    id_reporte: str
    id_empresa: str
    tipo: str
    nombre: str
    parametros: Dict[str, Any]
    resultado: Dict[str, Any]
    filas: int
    origen: str
    generado_por: str
    fecha: datetime
    id_programacion: Optional[str] = None


@dataclass(frozen=True)
class Schedule:
    id_programacion: str
    id_empresa: str
    nombre: str
    tipo: str
    parametros: Dict[str, Any]
    frecuencia: str
    hora_utc: int
    activa: bool
    proxima_ejecucion: datetime
    id_usuario: str
    nombre_usuario: str
    fecha_creacion: datetime
    ultima_ejecucion: Optional[datetime] = None
    ultimo_estado: Optional[str] = None
    ultimo_error: Optional[str] = None


class InsightRepository(ABC):
    @abstractmethod
    def save_report(self, report: SavedReport) -> None: ...

    @abstractmethod
    def get_report(self, id_reporte: str, id_empresa: str) -> Optional[SavedReport]: ...

    @abstractmethod
    def list_reports(self, id_empresa: str, tipo: Optional[str], limit: int) -> List[SavedReport]:
        """Sin el resultado completo (solo metadatos) para que el listado sea liviano."""

    @abstractmethod
    def delete_report(self, id_reporte: str, id_empresa: str) -> bool: ...

    @abstractmethod
    def purge_reports(self, before: datetime) -> int: ...

    @abstractmethod
    def create_schedule(self, schedule: Schedule) -> None: ...

    @abstractmethod
    def get_schedule(self, id_programacion: str, id_empresa: Optional[str]) -> Optional[Schedule]: ...

    @abstractmethod
    def list_schedules(self, id_empresa: str) -> List[Schedule]: ...

    @abstractmethod
    def update_schedule(self, schedule: Schedule) -> None: ...

    @abstractmethod
    def delete_schedule(self, id_programacion: str, id_empresa: str) -> bool: ...

    @abstractmethod
    def due_schedules(self, now: datetime, limit: int) -> List[Schedule]: ...

    @abstractmethod
    def claim(self, id_programacion: str, expected_next: datetime, new_next: datetime) -> bool:
        """Avanza proxima_ejecucion solo si nadie lo hizo antes (evita ejecuciones duplicadas entre instancias)."""

    @abstractmethod
    def record_run(self, id_programacion: str, at: datetime, estado: str, error: Optional[str]) -> None: ...

    @abstractmethod
    def ping(self) -> None: ...


class InMemoryInsightRepository(InsightRepository):
    def __init__(self) -> None:
        self._reports: Dict[str, SavedReport] = {}
        self._schedules: Dict[str, Schedule] = {}
        self._lock = threading.Lock()

    def save_report(self, report: SavedReport) -> None:
        with self._lock:
            self._reports[report.id_reporte] = report

    def get_report(self, id_reporte: str, id_empresa: str) -> Optional[SavedReport]:
        report = self._reports.get(id_reporte)
        return report if report and report.id_empresa == id_empresa else None

    def list_reports(self, id_empresa: str, tipo: Optional[str], limit: int) -> List[SavedReport]:
        items = sorted((r for r in self._reports.values() if r.id_empresa == id_empresa and (tipo is None or r.tipo == tipo)),
                       key=lambda r: r.fecha, reverse=True)
        return [replace(r, resultado={}) for r in items[:limit]]

    def delete_report(self, id_reporte: str, id_empresa: str) -> bool:
        with self._lock:
            if self.get_report(id_reporte, id_empresa) is None:
                return False
            del self._reports[id_reporte]
            return True

    def purge_reports(self, before: datetime) -> int:
        with self._lock:
            old = [k for k, r in self._reports.items() if r.fecha < before]
            for key in old:
                del self._reports[key]
            return len(old)

    def create_schedule(self, schedule: Schedule) -> None:
        with self._lock:
            self._schedules[schedule.id_programacion] = schedule

    def get_schedule(self, id_programacion: str, id_empresa: Optional[str]) -> Optional[Schedule]:
        s = self._schedules.get(id_programacion)
        return s if s and (id_empresa is None or s.id_empresa == id_empresa) else None

    def list_schedules(self, id_empresa: str) -> List[Schedule]:
        return sorted((s for s in self._schedules.values() if s.id_empresa == id_empresa), key=lambda s: s.fecha_creacion)

    def update_schedule(self, schedule: Schedule) -> None:
        with self._lock:
            self._schedules[schedule.id_programacion] = schedule

    def delete_schedule(self, id_programacion: str, id_empresa: str) -> bool:
        with self._lock:
            if self.get_schedule(id_programacion, id_empresa) is None:
                return False
            del self._schedules[id_programacion]
            return True

    def due_schedules(self, now: datetime, limit: int) -> List[Schedule]:
        due = [s for s in self._schedules.values() if s.activa and s.proxima_ejecucion <= now]
        return sorted(due, key=lambda s: s.proxima_ejecucion)[:limit]

    def claim(self, id_programacion: str, expected_next: datetime, new_next: datetime) -> bool:
        with self._lock:
            s = self._schedules.get(id_programacion)
            if s is None or s.proxima_ejecucion != expected_next:
                return False
            self._schedules[id_programacion] = replace(s, proxima_ejecucion=new_next)
            return True

    def record_run(self, id_programacion: str, at: datetime, estado: str, error: Optional[str]) -> None:
        with self._lock:
            s = self._schedules.get(id_programacion)
            if s is not None:
                self._schedules[id_programacion] = replace(s, ultima_ejecucion=at, ultimo_estado=estado, ultimo_error=error)

    def ping(self) -> None:
        return None


class SqlServerInsightRepository(InsightRepository):
    _REPORT = "id_reporte, id_empresa, tipo, nombre, parametros, filas, origen, generado_por, fecha, id_programacion"
    _SCHEDULE = ("id_programacion, id_empresa, nombre, tipo, parametros, frecuencia, hora_utc, activa, proxima_ejecucion, "
                 "id_usuario, nombre_usuario, fecha_creacion, ultima_ejecucion, ultimo_estado, ultimo_error")

    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def ping(self) -> None:
        self._db.ping()

    @staticmethod
    def _report(row, resultado: Optional[str] = None) -> SavedReport:
        return SavedReport(
            id_reporte=row[0], id_empresa=row[1], tipo=row[2], nombre=row[3], parametros=loads(row[4], {}),
            filas=row[5] or 0, origen=row[6], generado_por=row[7] or "", fecha=row[8], id_programacion=row[9],
            resultado=loads(resultado, {}),
        )

    @staticmethod
    def _schedule(row) -> Schedule:
        return Schedule(
            id_programacion=row[0], id_empresa=row[1], nombre=row[2], tipo=row[3], parametros=loads(row[4], {}),
            frecuencia=row[5], hora_utc=row[6], activa=bool(row[7]), proxima_ejecucion=row[8], id_usuario=row[9],
            nombre_usuario=row[10] or "", fecha_creacion=row[11], ultima_ejecucion=row[12], ultimo_estado=row[13],
            ultimo_error=row[14],
        )

    def save_report(self, r: SavedReport) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                f"INSERT INTO dbo.insight_reportes ({self._REPORT}, resultado) VALUES ({', '.join('?' * 11)})",
                (r.id_reporte, r.id_empresa, r.tipo, r.nombre[:200], dumps(r.parametros), r.filas, r.origen,
                 r.generado_por[:200], r.fecha, r.id_programacion, dumps(r.resultado)),
            )

    def get_report(self, id_reporte: str, id_empresa: str) -> Optional[SavedReport]:
        with self._db.cursor() as cur:
            cur.execute(f"SELECT {self._REPORT}, resultado FROM dbo.insight_reportes WHERE id_reporte = ? AND id_empresa = ?",
                        (id_reporte, id_empresa))
            row = cur.fetchone()
        return self._report(row, row[10]) if row else None

    def list_reports(self, id_empresa: str, tipo: Optional[str], limit: int) -> List[SavedReport]:
        sql = f"SELECT TOP (?) {self._REPORT} FROM dbo.insight_reportes WHERE id_empresa = ?"
        params: List[Any] = [limit, id_empresa]
        if tipo:
            sql += " AND tipo = ?"
            params.append(tipo)
        with self._db.cursor() as cur:
            cur.execute(sql + " ORDER BY fecha DESC", tuple(params))
            return [self._report(r) for r in cur.fetchall()]

    def delete_report(self, id_reporte: str, id_empresa: str) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute("DELETE FROM dbo.insight_reportes WHERE id_reporte = ? AND id_empresa = ?", (id_reporte, id_empresa))
            return cur.rowcount == 1

    def purge_reports(self, before: datetime) -> int:
        with self._db.cursor(commit=True) as cur:
            cur.execute("DELETE FROM dbo.insight_reportes WHERE fecha < ?", (before,))
            return cur.rowcount

    def create_schedule(self, s: Schedule) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                f"INSERT INTO dbo.insight_programaciones ({self._SCHEDULE}) VALUES ({', '.join('?' * 15)})",
                (s.id_programacion, s.id_empresa, s.nombre[:200], s.tipo, dumps(s.parametros), s.frecuencia, s.hora_utc,
                 s.activa, s.proxima_ejecucion, s.id_usuario, s.nombre_usuario[:200], s.fecha_creacion, s.ultima_ejecucion,
                 s.ultimo_estado, s.ultimo_error),
            )

    def get_schedule(self, id_programacion: str, id_empresa: Optional[str]) -> Optional[Schedule]:
        sql = f"SELECT {self._SCHEDULE} FROM dbo.insight_programaciones WHERE id_programacion = ?"
        params: List[Any] = [id_programacion]
        if id_empresa is not None:
            sql += " AND id_empresa = ?"
            params.append(id_empresa)
        with self._db.cursor() as cur:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
        return self._schedule(row) if row else None

    def list_schedules(self, id_empresa: str) -> List[Schedule]:
        with self._db.cursor() as cur:
            cur.execute(f"SELECT {self._SCHEDULE} FROM dbo.insight_programaciones WHERE id_empresa = ? ORDER BY fecha_creacion",
                        (id_empresa,))
            return [self._schedule(r) for r in cur.fetchall()]

    def update_schedule(self, s: Schedule) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.insight_programaciones SET nombre = ?, parametros = ?, frecuencia = ?, hora_utc = ?, activa = ?, "
                "proxima_ejecucion = ? WHERE id_programacion = ? AND id_empresa = ?",
                (s.nombre[:200], dumps(s.parametros), s.frecuencia, s.hora_utc, s.activa, s.proxima_ejecucion,
                 s.id_programacion, s.id_empresa),
            )

    def delete_schedule(self, id_programacion: str, id_empresa: str) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute("DELETE FROM dbo.insight_programaciones WHERE id_programacion = ? AND id_empresa = ?",
                        (id_programacion, id_empresa))
            return cur.rowcount == 1

    def due_schedules(self, now: datetime, limit: int) -> List[Schedule]:
        with self._db.cursor() as cur:
            cur.execute(
                f"SELECT TOP (?) {self._SCHEDULE} FROM dbo.insight_programaciones "
                "WHERE activa = 1 AND proxima_ejecucion <= ? ORDER BY proxima_ejecucion",
                (limit, now),
            )
            return [self._schedule(r) for r in cur.fetchall()]

    def claim(self, id_programacion: str, expected_next: datetime, new_next: datetime) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.insight_programaciones SET proxima_ejecucion = ? "
                "WHERE id_programacion = ? AND proxima_ejecucion = ? AND activa = 1",
                (new_next, id_programacion, expected_next),
            )
            return cur.rowcount == 1

    def record_run(self, id_programacion: str, at: datetime, estado: str, error: Optional[str]) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.insight_programaciones SET ultima_ejecucion = ?, ultimo_estado = ?, ultimo_error = ? "
                "WHERE id_programacion = ?",
                (at, estado, (error or "")[:1000] or None, id_programacion),
            )
