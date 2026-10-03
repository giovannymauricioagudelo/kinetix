"""
Casos de uso de Insight: generar reportes del catálogo, exportarlos, guardarlos por empresa y programarlos.
Las ejecuciones programadas corren con la identidad de quien las creó y vuelven a verificar sus permisos.
"""

from __future__ import annotations

import calendar
import logging
import re
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.agents.common import iso, new_id, utcnow
from src.agents.reporting_agent import exporters
from src.agents.reporting_agent.reports import CATALOG, ReportDefinition, Sources
from src.agents.reporting_agent.repository import InsightRepository, SavedReport, Schedule
from src.agents.security_agent.models import InvalidInputError, NotFoundError, PermissionDeniedError, Principal

logger = logging.getLogger(__name__)

VERSION = "1.0.0"
FREQUENCIES = ("diaria", "semanal", "mensual")
PERM_SCHEDULE = "reportes:programar"
NAME = re.compile(r"^[\w áéíóúÁÉÍÓÚñÑüÜ().,:/-]{1,200}$")


def add_month(moment: datetime) -> datetime:
    year, month = (moment.year + 1, 1) if moment.month == 12 else (moment.year, moment.month + 1)
    return moment.replace(year=year, month=month, day=min(moment.day, calendar.monthrange(year, month)[1]))


def advance(moment: datetime, frecuencia: str) -> datetime:
    if frecuencia == "mensual":
        return add_month(moment)
    return moment + timedelta(days=7 if frecuencia == "semanal" else 1)


def first_run(hora_utc: int, now: datetime) -> datetime:
    candidate = now.replace(hour=hora_utc, minute=0, second=0, microsecond=0)
    return candidate if candidate > now else candidate + timedelta(days=1)


def next_after(scheduled: datetime, frecuencia: str, now: datetime) -> datetime:
    following = advance(scheduled, frecuencia)
    while following <= now:
        following = advance(following, frecuencia)
    return following


def schedule_view(s: Schedule) -> Dict[str, Any]:
    return {
        "id_programacion": s.id_programacion, "nombre": s.nombre, "tipo": s.tipo, "parametros": s.parametros,
        "frecuencia": s.frecuencia, "hora_utc": s.hora_utc, "activa": s.activa, "proxima_ejecucion": iso(s.proxima_ejecucion),
        "ultima_ejecucion": iso(s.ultima_ejecucion), "ultimo_estado": s.ultimo_estado, "ultimo_error": s.ultimo_error,
        "creada_por": s.nombre_usuario, "fecha_creacion": iso(s.fecha_creacion),
    }


def saved_view(r: SavedReport, full: bool = False) -> Dict[str, Any]:
    view = {"id_reporte": r.id_reporte, "tipo": r.tipo, "nombre": r.nombre, "parametros": r.parametros, "filas": r.filas,
            "origen": r.origen, "id_programacion": r.id_programacion, "generado_por": r.generado_por, "fecha": iso(r.fecha)}
    if full:
        view["resultado"] = r.resultado
    return view


class InsightService:
    def __init__(self, repository: InsightRepository, sources: Sources, clock: Callable = utcnow,
                 max_rows: int = 5000, retention_days: int = 90) -> None:
        self._repo = repository
        self._src = sources
        self._clock = clock
        self.max_rows = max_rows
        self.retention_days = retention_days

    def ping(self) -> None:
        self._repo.ping()

    @staticmethod
    def catalog() -> Dict[str, Any]:
        return {"total": len(CATALOG), "reportes": [d.describe() for d in CATALOG.values()]}

    @staticmethod
    def _definition(tipo: str) -> ReportDefinition:
        definition = CATALOG.get(tipo)
        if definition is None:
            raise NotFoundError(f"Reporte desconocido: {tipo!r}. Consulta el catálogo")
        return definition

    def _build(self, actor: Principal, tipo: str, parametros: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        definition = self._definition(tipo)
        params = definition.clean(parametros)
        data = definition.build(self._src, actor, params)
        rows = data.filas[: self.max_rows]
        return {
            "tipo": tipo, "nombre": definition.nombre, "agente": definition.agente, "parametros": params,
            "generado_en": iso(self._clock()), "generado_por": actor.nombre_usuario, "columnas": data.columns(),
            "filas": rows, "total_filas": len(data.filas), "filas_truncadas": len(data.filas) > len(rows), "resumen": data.resumen,
        }

    def _save(self, actor: Principal, report: Dict[str, Any], nombre: Optional[str], origen: str,
              id_programacion: Optional[str] = None) -> SavedReport:
        name = (nombre or "").strip() or f"{report['nombre']} {self._clock():%Y-%m-%d %H:%M}"
        if not NAME.match(name):
            raise InvalidInputError("nombre: hasta 200 caracteres (letras, números, espacios y . , : ( ) / -)")
        saved = SavedReport(
            id_reporte=new_id("ir"), id_empresa=actor.id_empresa, tipo=report["tipo"], nombre=name,
            parametros=report["parametros"], resultado=report, filas=len(report["filas"]), origen=origen,
            generado_por=actor.nombre_usuario, fecha=self._clock(), id_programacion=id_programacion,
        )
        self._repo.save_report(saved)
        return saved

    def generate(self, actor: Principal, tipo: str, parametros: Optional[Dict[str, Any]] = None,
                 guardar: bool = False, nombre: Optional[str] = None) -> Dict[str, Any]:
        report = self._build(actor, tipo, parametros)
        if guardar:
            report["id_reporte"] = self._save(actor, report, nombre, "manual").id_reporte
        return report

    @staticmethod
    def _file(report: Dict[str, Any], formato: str, stem: str) -> Tuple[str, str, str]:
        if formato not in exporters.FORMATS:
            raise InvalidInputError(f"formato debe ser {' o '.join(exporters.FORMATS)}")
        return exporters.export(report, formato), f"{stem}.{formato}", exporters.MEDIA_TYPES[formato]

    def export(self, actor: Principal, tipo: str, parametros: Optional[Dict[str, Any]], formato: str) -> Tuple[str, str, str]:
        report = self._build(actor, tipo, parametros)
        return self._file(report, formato, f"insight_{tipo}_{self._clock():%Y%m%d_%H%M%S}")

    # ================================================================ guardados

    def list_saved(self, id_empresa: str, tipo: Optional[str] = None, limite: int = 50) -> Dict[str, Any]:
        items = self._repo.list_reports(id_empresa, tipo, max(1, min(limite, 200)))
        return {"total": len(items), "reportes": [saved_view(r) for r in items]}

    def _saved(self, id_reporte: str, id_empresa: str) -> SavedReport:
        report = self._repo.get_report(id_reporte, id_empresa)
        if report is None:
            raise NotFoundError(f"Reporte guardado no encontrado: {id_reporte}")
        return report

    def get_saved(self, id_reporte: str, id_empresa: str) -> Dict[str, Any]:
        return saved_view(self._saved(id_reporte, id_empresa), full=True)

    def export_saved(self, id_reporte: str, id_empresa: str, formato: str) -> Tuple[str, str, str]:
        report = self._saved(id_reporte, id_empresa)
        return self._file(report.resultado, formato, f"insight_{report.tipo}_{report.fecha:%Y%m%d_%H%M%S}")

    def delete_saved(self, id_reporte: str, id_empresa: str) -> Dict[str, Any]:
        if not self._repo.delete_report(id_reporte, id_empresa):
            raise NotFoundError(f"Reporte guardado no encontrado: {id_reporte}")
        return {"id_reporte": id_reporte, "eliminado": True}

    def purge(self) -> int:
        return self._repo.purge_reports(self._clock() - timedelta(days=self.retention_days))

    # ================================================================ programaciones

    @staticmethod
    def _schedule_fields(data: Dict[str, Any], current: Optional[Schedule] = None) -> Dict[str, Any]:
        nombre = (data.get("nombre") if data.get("nombre") is not None else (current.nombre if current else "")).strip()
        if not NAME.match(nombre):
            raise InvalidInputError("nombre: obligatorio, hasta 200 caracteres (letras, números, espacios y . , : ( ) / -)")
        frecuencia = data.get("frecuencia") or (current.frecuencia if current else "diaria")
        if frecuencia not in FREQUENCIES:
            raise InvalidInputError(f"frecuencia debe ser {', '.join(FREQUENCIES)}")
        hora = data.get("hora_utc") if data.get("hora_utc") is not None else (current.hora_utc if current else 6)
        if not isinstance(hora, int) or not 0 <= hora <= 23:
            raise InvalidInputError("hora_utc debe estar entre 0 y 23")
        return {"nombre": nombre, "frecuencia": frecuencia, "hora_utc": hora}

    def create_schedule(self, actor: Principal, data: Dict[str, Any]) -> Dict[str, Any]:
        definition = self._definition(data.get("tipo", ""))
        params = definition.clean(data.get("parametros"))
        fields = self._schedule_fields(data)
        now = self._clock()
        schedule = Schedule(
            id_programacion=new_id("ip"), id_empresa=actor.id_empresa, tipo=definition.id, parametros=params,
            activa=bool(data.get("activa", True)), proxima_ejecucion=first_run(fields["hora_utc"], now),
            id_usuario=actor.id, nombre_usuario=actor.nombre_usuario, fecha_creacion=now, **fields,
        )
        self._repo.create_schedule(schedule)
        return schedule_view(schedule)

    def list_schedules(self, id_empresa: str) -> Dict[str, Any]:
        items = self._repo.list_schedules(id_empresa)
        return {"total": len(items), "programaciones": [schedule_view(s) for s in items]}

    def _schedule(self, id_programacion: str, id_empresa: str) -> Schedule:
        schedule = self._repo.get_schedule(id_programacion, id_empresa)
        if schedule is None:
            raise NotFoundError(f"Programación no encontrada: {id_programacion}")
        return schedule

    def update_schedule(self, id_programacion: str, id_empresa: str, data: Dict[str, Any]) -> Dict[str, Any]:
        current = self._schedule(id_programacion, id_empresa)
        fields = self._schedule_fields(data, current)
        params = self._definition(current.tipo).clean(data["parametros"]) if data.get("parametros") is not None else current.parametros
        timing_changed = (fields["frecuencia"], fields["hora_utc"]) != (current.frecuencia, current.hora_utc)
        activa = current.activa if data.get("activa") is None else bool(data["activa"])
        reactivated = activa and not current.activa
        next_run = first_run(fields["hora_utc"], self._clock()) if timing_changed or reactivated else current.proxima_ejecucion
        updated = replace(current, **fields, parametros=params, activa=activa, proxima_ejecucion=next_run)
        self._repo.update_schedule(updated)
        return schedule_view(updated)

    def delete_schedule(self, id_programacion: str, id_empresa: str) -> Dict[str, Any]:
        if not self._repo.delete_schedule(id_programacion, id_empresa):
            raise NotFoundError(f"Programación no encontrada: {id_programacion}")
        return {"id_programacion": id_programacion, "eliminada": True}

    def _owner(self, schedule: Schedule) -> Principal:
        return Principal(id=schedule.id_usuario, nombre_usuario=schedule.nombre_usuario, id_empresa=schedule.id_empresa,
                         jti=f"insight:{schedule.id_programacion}", expira=self._clock() + timedelta(minutes=10),
                         metodos=["programacion"])

    def _execute(self, schedule: Schedule) -> Dict[str, Any]:
        owner = self._owner(schedule)
        now = self._clock()
        try:
            if not self._src.security().authorize(owner, PERM_SCHEDULE):
                raise PermissionDeniedError(f"{schedule.nombre_usuario} ya no tiene el permiso {PERM_SCHEDULE}")
            report = self._build(owner, schedule.tipo, schedule.parametros)
            saved = self._save(owner, report, f"{schedule.nombre} {now:%Y-%m-%d %H:%M}", "programado", schedule.id_programacion)
        except Exception as e:
            message = str(e) if isinstance(e, (PermissionDeniedError, InvalidInputError, NotFoundError)) else type(e).__name__
            self._repo.record_run(schedule.id_programacion, now, "error", message)
            logger.warning("Insight: la programación %s falló: %s", schedule.id_programacion, message)
            return {"id_programacion": schedule.id_programacion, "estado": "error", "error": message}
        self._repo.record_run(schedule.id_programacion, now, "exito", None)
        return {"id_programacion": schedule.id_programacion, "estado": "exito", "id_reporte": saved.id_reporte, "filas": saved.filas}

    def run_schedule_now(self, id_programacion: str, id_empresa: str) -> Dict[str, Any]:
        return self._execute(self._schedule(id_programacion, id_empresa))

    def run_due(self, limit: int = 20) -> List[Dict[str, Any]]:
        now = self._clock()
        results = []
        for schedule in self._repo.due_schedules(now, limit):
            following = next_after(schedule.proxima_ejecucion, schedule.frecuencia, now)
            if self._repo.claim(schedule.id_programacion, schedule.proxima_ejecucion, following):
                results.append(self._execute(schedule))
        return results

    # ================================================================ KPIs

    def _section(self, build: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        try:
            return {"disponible": True, **build()}
        except Exception as e:
            logger.info("Insight: KPI no disponible (%s)", type(e).__name__)
            return {"disponible": False, "motivo": type(e).__name__}

    def kpis(self, dias: int = 7) -> Dict[str, Any]:
        dias = max(1, min(dias, 90))

        def rules() -> Dict[str, Any]:
            data = self._src.rules().analytics(dias)
            return {"reglas_activas": data["reglas_activas"], "evaluaciones": data["evaluaciones"], "bloqueos": data["bloqueos"],
                    "activas_sin_uso": len(data["reglas_activas_sin_uso"])}

        def api() -> Dict[str, Any]:
            monitoring = self._src.monitoring()
            summary = monitoring.performance_report(24)["resumen"]
            return {"peticiones_24h": summary["total"], "tasa_error_porcentaje": summary["tasa_error_porcentaje"],
                    "latencia_p95_ms": summary["latencia_p95_ms"],
                    "disponibilidad_porcentaje": monitoring.availability_report()["disponibilidad_total_porcentaje"]}

        def quality() -> Dict[str, Any]:
            data = self._src.prism().metrics(dias)
            return {k: data[k] for k in ("ejecuciones", "tasa_aprobacion", "cobertura_actual", "cobertura_minima")}

        def deployments() -> Dict[str, Any]:
            items = self._src.orbit().list_deployments(None, None, 200)["despliegues"]
            since = self._clock() - timedelta(days=dias)
            recent = [d for d in items if d["fecha_inicio"] and datetime.fromisoformat(d["fecha_inicio"]) >= since]
            current = {env: next((d["tag"] for d in items if d["entorno"] == env and d["estado"] == "exitoso"), None)
                       for env in ("staging", "produccion")}
            return {"despliegues": len(recent), "exitosos": sum(1 for d in recent if d["estado"] == "exitoso"),
                    "rechazados": sum(1 for d in recent if d["estado"] == "rechazado"),
                    "reversiones": sum(1 for d in recent if d["tipo"] == "reversion"), "version_actual": current}

        def code() -> Dict[str, Any]:
            items = self._src.vector().history(1)["analisis"]
            last = items[0] if items else None
            return {"ultima_puntuacion": last["puntuacion"] if last else None, "criticos": last["criticos"] if last else None,
                    "fecha": last["fecha"] if last else None}

        return {"dias": dias, "generado_en": iso(self._clock()), "reglas": self._section(rules), "api": self._section(api),
                "calidad": self._section(quality), "despliegues": self._section(deployments), "codigo": self._section(code)}
