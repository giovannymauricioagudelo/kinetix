"""Reportes guardados y programaciones de Insight (tablas insight_reportes e insight_programaciones)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient, afectadas, ejecutar


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
    """Persistencia sobre los procedimientos del esquema insight de la base kinetix."""

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
            ejecutar(cur, "insight.reporte_insertar", id_reporte=r.id_reporte, id_empresa=r.id_empresa, tipo=r.tipo,
                     nombre=r.nombre[:200], parametros=dumps(r.parametros), filas=r.filas, origen=r.origen,
                     generado_por=r.generado_por[:200], fecha=r.fecha, id_programacion=r.id_programacion,
                     resultado=dumps(r.resultado))

    def get_report(self, id_reporte: str, id_empresa: str) -> Optional[SavedReport]:
        with self._db.cursor() as cur:
            row = ejecutar(cur, "insight.reporte_obtener", id_reporte=id_reporte, id_empresa=id_empresa).fetchone()
        return self._report(row, row[10]) if row else None

    def list_reports(self, id_empresa: str, tipo: Optional[str], limit: int) -> List[SavedReport]:
        with self._db.cursor() as cur:
            rows = ejecutar(cur, "insight.reporte_listar", id_empresa=id_empresa, tipo=tipo or None, limite=limit).fetchall()
        return [self._report(r) for r in rows]

    def delete_report(self, id_reporte: str, id_empresa: str) -> bool:
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "insight.reporte_eliminar", id_reporte=id_reporte, id_empresa=id_empresa)) == 1

    def purge_reports(self, before: datetime) -> int:
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "insight.reporte_purgar", antes=before))

    def create_schedule(self, s: Schedule) -> None:
        with self._db.cursor(commit=True) as cur:
            ejecutar(cur, "insight.programacion_insertar", id_programacion=s.id_programacion, id_empresa=s.id_empresa,
                     nombre=s.nombre[:200], tipo=s.tipo, parametros=dumps(s.parametros), frecuencia=s.frecuencia,
                     hora_utc=s.hora_utc, activa=s.activa, proxima_ejecucion=s.proxima_ejecucion, id_usuario=s.id_usuario,
                     nombre_usuario=s.nombre_usuario[:200], fecha_creacion=s.fecha_creacion, ultima_ejecucion=s.ultima_ejecucion,
                     ultimo_estado=s.ultimo_estado, ultimo_error=s.ultimo_error)

    def get_schedule(self, id_programacion: str, id_empresa: Optional[str]) -> Optional[Schedule]:
        with self._db.cursor() as cur:
            row = ejecutar(cur, "insight.programacion_obtener", id_programacion=id_programacion, id_empresa=id_empresa).fetchone()
        return self._schedule(row) if row else None

    def list_schedules(self, id_empresa: str) -> List[Schedule]:
        with self._db.cursor() as cur:
            return [self._schedule(r) for r in ejecutar(cur, "insight.programacion_listar", id_empresa=id_empresa).fetchall()]

    def update_schedule(self, s: Schedule) -> None:
        with self._db.cursor(commit=True) as cur:
            ejecutar(cur, "insight.programacion_actualizar", id_programacion=s.id_programacion, id_empresa=s.id_empresa,
                     nombre=s.nombre[:200], parametros=dumps(s.parametros), frecuencia=s.frecuencia, hora_utc=s.hora_utc,
                     activa=s.activa, proxima_ejecucion=s.proxima_ejecucion)

    def delete_schedule(self, id_programacion: str, id_empresa: str) -> bool:
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "insight.programacion_eliminar", id_programacion=id_programacion,
                                      id_empresa=id_empresa)) == 1

    def due_schedules(self, now: datetime, limit: int) -> List[Schedule]:
        with self._db.cursor() as cur:
            return [self._schedule(r) for r in ejecutar(cur, "insight.programacion_vencidas", ahora=now, limite=limit).fetchall()]

    def claim(self, id_programacion: str, expected_next: datetime, new_next: datetime) -> bool:
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "insight.programacion_reclamar", id_programacion=id_programacion,
                                      proxima_esperada=expected_next, proxima_nueva=new_next)) == 1

    def record_run(self, id_programacion: str, at: datetime, estado: str, error: Optional[str]) -> None:
        with self._db.cursor(commit=True) as cur:
            ejecutar(cur, "insight.programacion_registrar_ejecucion", id_programacion=id_programacion, fecha=at, estado=estado,
                     error=(error or "")[:1000] or None)
