"""
Catálogo cerrado de reportes de Insight. Cada reporte lee de los servicios de otros agentes (nunca SQL arbitrario):
Matrix (reglas), Sentinel (bitácora, limitada a la empresa del usuario y al permiso auditoria:ver), Argus
(rendimiento y disponibilidad), Prism (pruebas), Orbit (despliegues) y Vector (análisis de código).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from src.agents.security_agent.models import InvalidInputError, Principal
from src.agents.security_agent.repository import SESSION_STARTED
from src.agents.security_agent.service import MAX_AUDIT_PAGE

MAX_AUDIT_ROWS = 5000


@dataclass(frozen=True)
class Param:
    tipo: str
    defecto: Any = None
    minimo: Optional[int] = None
    maximo: Optional[int] = None
    opciones: Tuple[str, ...] = ()
    max_largo: int = 100

    def clean(self, name: str, value: Any) -> Any:
        if value is None or value == "":
            return self.defecto
        if self.tipo == "int":
            try:
                number = int(value)
            except (TypeError, ValueError):
                raise InvalidInputError(f"{name} debe ser un entero") from None
            if (self.minimo is not None and number < self.minimo) or (self.maximo is not None and number > self.maximo):
                raise InvalidInputError(f"{name} debe estar entre {self.minimo} y {self.maximo}")
            return number
        text = str(value).strip()
        if self.opciones and text not in self.opciones:
            raise InvalidInputError(f"{name} debe ser uno de: {', '.join(self.opciones)}")
        if len(text) > self.max_largo:
            raise InvalidInputError(f"{name}: máximo {self.max_largo} caracteres")
        return text

    def describe(self) -> Dict[str, Any]:
        spec: Dict[str, Any] = {"tipo": self.tipo, "defecto": self.defecto}
        if self.minimo is not None:
            spec.update(minimo=self.minimo, maximo=self.maximo)
        if self.opciones:
            spec["opciones"] = list(self.opciones)
        return spec


@dataclass
class Sources:
    """Accesos perezosos a los servicios de los demás agentes (los tests inyectan dobles)."""

    rules: Callable[[], Any]
    security: Callable[[], Any]
    monitoring: Callable[[], Any]
    prism: Callable[[], Any]
    orbit: Callable[[], Any]
    vector: Callable[[], Any]
    now: Callable[[], datetime]


@dataclass
class ReportData:
    filas: List[Dict[str, Any]]
    resumen: Dict[str, Any] = field(default_factory=dict)

    def columns(self) -> List[str]:
        seen: Dict[str, None] = {}
        for row in self.filas:
            seen.update(dict.fromkeys(row))
        return list(seen)


ReportFn = Callable[[Sources, Principal, Dict[str, Any]], ReportData]


@dataclass(frozen=True)
class ReportDefinition:
    id: str
    nombre: str
    descripcion: str
    agente: str
    parametros: Dict[str, Param]
    build: ReportFn

    def clean(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        params = params or {}
        unknown = set(params) - set(self.parametros)
        if unknown:
            raise InvalidInputError(f"Parámetros no admitidos en {self.id}: {', '.join(sorted(unknown))}")
        return {name: spec.clean(name, params.get(name)) for name, spec in self.parametros.items()}

    def describe(self) -> Dict[str, Any]:
        return {"id": self.id, "nombre": self.nombre, "descripcion": self.descripcion, "agente": self.agente,
                "parametros": {n: p.describe() for n, p in self.parametros.items()}}


DIAS = Param("int", 30, 1, 365)


def _day(moment: Optional[datetime]) -> Optional[str]:
    return moment.date().isoformat() if moment else None


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip("Z")).replace(tzinfo=None)
    except ValueError:
        return None


def _rate(part: int, total: int) -> Optional[float]:
    return round(100 * part / total, 2) if total else None


# ================================================================ Matrix

def rule_evaluations(src: Sources, actor: Principal, p: Dict[str, Any]) -> ReportData:
    records = src.rules().evaluation_records(p["id_regla"], p["dias"], 100_000)
    key: Callable[[Any], Any] = {
        "dia": lambda r: _day(r.fecha), "regla": lambda r: r.id_regla,
        "decision": lambda r: r.decision or "sin_decision", "empresa": lambda r: r.id_empresa,
    }[p["agrupacion"]]
    groups: Dict[Any, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in records:
        g = groups[key(r)]
        g["evaluaciones"] += 1
        g["cumplidas"] += int(r.condiciones_cumplidas)
        g["bloqueadas"] += int(r.decision == "bloqueada")
        g["tiempo_ms"] += r.tiempo_ejecucion_ms
    rows = [
        {p["agrupacion"]: k, "evaluaciones": int(g["evaluaciones"]), "cumplidas": int(g["cumplidas"]),
         "bloqueadas": int(g["bloqueadas"]), "tasa_cumplimiento": _rate(int(g["cumplidas"]), int(g["evaluaciones"])),
         "tiempo_promedio_ms": round(g["tiempo_ms"] / g["evaluaciones"], 3)}
        for k, g in groups.items()
    ]
    if p["agrupacion"] == "dia":
        rows.sort(key=lambda r: r["dia"] or "")
    else:
        rows.sort(key=lambda r: -r["evaluaciones"])
    return ReportData(rows, {"evaluaciones": len(records), "bloqueadas": sum(r["bloqueadas"] for r in rows),
                             "tiempo_promedio_ms": round(sum(r.tiempo_ejecucion_ms for r in records) / len(records), 3) if records else None})


def rule_status(src: Sources, actor: Principal, p: Dict[str, Any]) -> ReportData:
    service = src.rules()
    usage = {r["id_regla"]: r for r in service.analytics(p["dias"])["por_regla"]}
    rows = []
    for rule in service.list_rules()["reglas"]:
        stats = usage.get(rule["id_regla"], {})
        rows.append({"id_regla": rule["id_regla"], "nombre": rule["nombre"], "estado": rule["estado"],
                     "nivel_alcance": rule["nivel_alcance"], "prioridad": rule["prioridad"],
                     "evaluaciones": stats.get("evaluaciones", 0), "tasa_cumplimiento": stats.get("tasa_cumplimiento_porcentaje")})
    by_state: Dict[str, int] = defaultdict(int)
    for row in rows:
        by_state[row["estado"]] += 1
    unused = [r["id_regla"] for r in rows if r["estado"] == "activa" and not r["evaluaciones"]]
    return ReportData(rows, {"total": len(rows), "por_estado": dict(by_state), "activas_sin_uso": unused})


# ================================================================ Sentinel

def _audit_entries(src: Sources, actor: Principal, dias: int, accion: Optional[str] = None) -> List[Dict[str, Any]]:
    since = src.now() - timedelta(days=dias)
    entries: List[Dict[str, Any]] = []
    while len(entries) < MAX_AUDIT_ROWS:
        page = src.security().audit_log(actor, desde=since, accion=accion, limit=MAX_AUDIT_PAGE, offset=len(entries))
        entries += page["registros"]
        if len(page["registros"]) < MAX_AUDIT_PAGE or len(entries) >= page["total"]:
            break
    return entries


def security_audit(src: Sources, actor: Principal, p: Dict[str, Any]) -> ReportData:
    group = p["agrupacion"]
    if group == "accion":
        counts = src.security().audit_counts(actor, p["dias"])
        per_action: Dict[str, Dict[str, Any]] = {}
        for accion, resultado, total in counts:
            row = per_action.setdefault(accion, {"accion": accion, "total": 0, "exitosas": 0, "fallidas": 0})
            row["total"] += total
            row["exitosas" if resultado == "exito" else "fallidas"] += total
        rows = sorted(per_action.values(), key=lambda r: -r["total"])
    else:
        key = {"dia": lambda e: (e["fecha"] or "")[:10], "usuario": lambda e: e["id_usuario"] or "desconocido",
               "resultado": lambda e: e["resultado"]}[group]
        grouped: Dict[str, Dict[str, Any]] = {}
        for e in _audit_entries(src, actor, p["dias"]):
            row = grouped.setdefault(key(e), {group: key(e), "total": 0, "exitosas": 0, "fallidas": 0})
            row["total"] += 1
            row["exitosas" if e["resultado"] == "exito" else "fallidas"] += 1
        rows = sorted(grouped.values(), key=lambda r: r[group] if group == "dia" else -r["total"])
    total = sum(r["total"] for r in rows)
    failed = sum(r["fallidas"] for r in rows)
    return ReportData(rows, {"eventos": total, "fallidos": failed, "tasa_fallo": _rate(failed, total), "empresa": actor.id_empresa})


def user_access(src: Sources, actor: Principal, p: Dict[str, Any]) -> ReportData:
    users: Dict[str, Dict[str, Any]] = {}

    def row(user: Optional[str]) -> Dict[str, Any]:
        name = user or "desconocido"
        return users.setdefault(name, {"id_usuario": name, "inicios_sesion": 0, "fallos": 0, "ultimo_acceso": None, "ips": set()})

    for e in _audit_entries(src, actor, p["dias"], SESSION_STARTED):
        r = row(e["id_usuario"])
        if e["resultado"] == "exito":
            r["inicios_sesion"] += 1
            r["ultimo_acceso"] = max(filter(None, [r["ultimo_acceso"], e["fecha"]]), default=None)
        if e["direccion_ip"]:
            r["ips"].add(e["direccion_ip"])
    for e in _audit_entries(src, actor, p["dias"], "autenticar"):
        if e["resultado"] != "exito":
            row(e["id_usuario"])["fallos"] += 1
    rows = [{**r, "ips": len(r["ips"])} for r in users.values()]
    rows.sort(key=lambda r: -(r["inicios_sesion"] + r["fallos"]))
    return ReportData(rows, {"usuarios": len(rows), "inicios_sesion": sum(r["inicios_sesion"] for r in rows),
                             "fallos": sum(r["fallos"] for r in rows), "empresa": actor.id_empresa})


# ================================================================ Argus

def api_performance(src: Sources, actor: Principal, p: Dict[str, Any]) -> ReportData:
    report = src.monitoring().performance_report(p["horas"])
    rows = [{"agente": name, **stats} for name, stats in sorted(report["por_agente"].items())]
    return ReportData(rows, {"resumen": report["resumen"], "endpoints_mas_lentos": report["endpoints_mas_lentos"][:5],
                             "datos_desde": report["datos_desde"], "nota": report.get("nota")})


def availability(src: Sources, actor: Principal, p: Dict[str, Any]) -> ReportData:
    report = src.monitoring().availability_report()
    rows = [{"agente": name, **stats} for name, stats in sorted(report["por_agente"].items())]
    return ReportData(rows, {"disponibilidad_total": report["disponibilidad_total_porcentaje"], "sla": report["sla"],
                             "no_desplegados": report["agentes_no_desplegados"]})


# ================================================================ Prism, Orbit, Vector

def _within(items: Iterable[Dict[str, Any]], date_key: str, since: datetime) -> List[Dict[str, Any]]:
    return [i for i in items if (_parse_iso(i.get(date_key)) or datetime.min) >= since]


def test_quality(src: Sources, actor: Principal, p: Dict[str, Any]) -> ReportData:
    since = src.now() - timedelta(days=p["dias"])
    runs = _within(src.prism().list_runs(200)["ejecuciones"], "fecha_inicio", since)
    columns = ("id_ejecucion", "fecha_inicio", "estado", "suite_completa", "commit", "total", "pasadas", "fallidas",
               "errores", "cobertura", "duracion_s", "iniciada_por")
    metrics = src.prism().metrics(p["dias"])
    return ReportData([{c: r.get(c) for c in columns} for r in runs],
                      {k: metrics[k] for k in ("ejecuciones", "tasa_aprobacion", "cobertura_actual", "cobertura_minima",
                                               "duracion_promedio_s", "pruebas_mas_fallidas")})


def deployments(src: Sources, actor: Principal, p: Dict[str, Any]) -> ReportData:
    since = src.now() - timedelta(days=p["dias"])
    items = _within(src.orbit().list_deployments(p["entorno"], None, 200)["despliegues"], "fecha_inicio", since)
    columns = ("id_despliegue", "fecha_inicio", "entorno", "tipo", "estado", "commit", "tag", "tag_publicado", "iniciado_por")
    by_state: Dict[str, int] = defaultdict(int)
    for d in items:
        by_state[d["estado"]] += 1
    return ReportData([{c: d.get(c) for c in columns} for d in items],
                      {"total": len(items), "por_estado": dict(by_state),
                       "reversiones": sum(1 for d in items if d["tipo"] == "reversion"),
                       "tasa_exito": _rate(by_state.get("exitoso", 0), len(items))})


def code_analysis(src: Sources, actor: Principal, p: Dict[str, Any]) -> ReportData:
    since = src.now() - timedelta(days=p["dias"])
    items = _within(src.vector().history(200)["analisis"], "fecha", since)
    rows = [{k: a[k] for k in ("id_analisis", "fecha", "objetivo", "archivos", "lineas", "puntuacion", "criticos", "altos",
                               "analizado_por")} for a in items]
    scores = [r["puntuacion"] for r in rows]
    return ReportData(rows, {"analisis": len(rows), "puntuacion_promedio": round(sum(scores) / len(scores), 2) if scores else None,
                             "ultima_puntuacion": scores[0] if scores else None,
                             "criticos_totales": sum(r["criticos"] for r in rows)})


CATALOG: Dict[str, ReportDefinition] = {d.id: d for d in (
    ReportDefinition("evaluaciones_reglas", "Evaluaciones de reglas", "Evaluaciones de Matrix agrupadas por día, regla, decisión o empresa",
                     "Matrix", {"dias": DIAS, "agrupacion": Param("str", "dia", opciones=("dia", "regla", "decision", "empresa")),
                                "id_regla": Param("str", None)}, rule_evaluations),
    ReportDefinition("estado_reglas", "Estado de las reglas", "Inventario de reglas con su uso en el periodo y las activas sin uso",
                     "Matrix", {"dias": DIAS}, rule_status),
    ReportDefinition("auditoria_seguridad", "Auditoría de seguridad", "Bitácora de Sentinel de tu empresa (requiere auditoria:ver)",
                     "Sentinel", {"dias": DIAS, "agrupacion": Param("str", "accion", opciones=("accion", "resultado", "dia", "usuario"))},
                     security_audit),
    ReportDefinition("accesos_usuarios", "Accesos de usuarios",
                     "Inicios de sesión, fallos de credenciales e IPs por usuario (requiere auditoria:ver)",
                     "Sentinel", {"dias": DIAS}, user_access),
    ReportDefinition("rendimiento_api", "Rendimiento de la API", "Peticiones, errores y latencias por agente medidos por Argus",
                     "Argus", {"horas": Param("int", 24, 1, 168)}, api_performance),
    ReportDefinition("disponibilidad", "Disponibilidad", "Disponibilidad por agente según las sondas de Argus y cumplimiento del SLA",
                     "Argus", {}, availability),
    ReportDefinition("calidad_pruebas", "Calidad y pruebas", "Ejecuciones de pruebas de Prism con cobertura y tasa de aprobación",
                     "Prism", {"dias": DIAS}, test_quality),
    ReportDefinition("despliegues", "Despliegues", "Despliegues y reversiones de Orbit por entorno",
                     "Orbit", {"dias": DIAS, "entorno": Param("str", None, opciones=("staging", "produccion"))}, deployments),
    ReportDefinition("analisis_codigo", "Análisis de código", "Puntuación y hallazgos de los análisis estáticos de Vector",
                     "Vector", {"dias": DIAS}, code_analysis),
)}
