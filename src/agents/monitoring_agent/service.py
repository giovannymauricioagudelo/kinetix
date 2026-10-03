"""
Argus (MonitoringAgent) — observa la plataforma: métricas HTTP reales, salud de cada agente,
recursos del host, alertas y reportes de rendimiento y disponibilidad.

Los datos viven en memoria desde el arranque del proceso (retención 24 h). Para histórico largo,
un servidor Prometheus debe raspar GET /api/v1/argus/metricas.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI

from src.agents.agent_catalog import ALL_AGENTS, ARGUS
from src.agents.monitoring_agent.alerts import CRITICAL, WARNING, AlertManager, AlertThresholds
from src.agents.monitoring_agent.collector import MetricsCollector, summarize, summarize_by
from src.agents.monitoring_agent.health import DOWN, NOT_DEPLOYED, AgentHealthMonitor
from src.agents.monitoring_agent.middleware import ArgusMiddleware
from src.agents.monitoring_agent.system import read_system_resources

logger = logging.getLogger(__name__)

DATA_NOTE = "Datos en memoria desde el arranque del proceso (retención 24 h); para histórico largo, raspa /metricas con Prometheus."


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


class MonitoringService:
    def __init__(
        self,
        collector: Optional[MetricsCollector] = None,
        health: Optional[AgentHealthMonitor] = None,
        alerts: Optional[AlertManager] = None,
        sla_target: Optional[float] = None,
    ) -> None:
        self.name = ARGUS.codename
        self.version = "1.0.0"
        self.collector = collector or MetricsCollector()
        thresholds = alerts.thresholds if alerts else AlertThresholds.from_env()
        self.health = health or AgentHealthMonitor(self.collector, slow_ms=thresholds.latency_ms)
        self.alerts = alerts or AlertManager(thresholds)
        self.sla_target = sla_target if sla_target is not None else float(os.getenv("ARGUS_SLA_OBJETIVO", "99.9"))

    # ------------------------------------------------------------ ciclo de observación

    async def refresh(self, app: FastAPI) -> None:
        health = await self.health.probe_all(app)
        resources = self.resources()
        window = self.alerts.thresholds.window_minutes * 60
        agent_stats = summarize_by(self.collector.samples_since(window), lambda s: s.agent)
        active = self.alerts.evaluate(agent_stats, health, resources)
        for severity in (CRITICAL, WARNING):
            self.collector.active_alerts.labels(severity).set(sum(1 for a in active if a.severidad == severity))

    async def ensure_fresh(self, app: FastAPI, max_age_seconds: float = 15) -> None:
        if time.time() - self.health.last_probe > max_age_seconds:
            await self.refresh(app)

    async def run_periodic(self, app: FastAPI, interval_seconds: int) -> None:
        while True:
            try:
                await self.refresh(app)
            except Exception:
                logger.exception("Argus: fallo en el ciclo de observación")
            await asyncio.sleep(interval_seconds)

    def resources(self) -> Dict[str, Dict[str, float]]:
        resources = read_system_resources()
        self.collector.cpu_percent.set(resources["cpu"]["uso_porcentaje"])
        self.collector.memory_percent.set(resources["memoria"]["uso_porcentaje"])
        self.collector.disk_percent.set(resources["disco"]["uso_porcentaje"])
        return resources

    # ------------------------------------------------------------ vistas

    def overall_status(self) -> Dict[str, object]:
        health = self.health.latest()
        deployed = [h for h in health if h.estado != NOT_DEPLOYED]
        down = [h for h in deployed if h.estado == DOWN]
        critical = [a for a in self.alerts.active() if a.severidad == CRITICAL]
        if down or critical:
            status = "critico"
        elif self.alerts.active():
            status = "degradado"
        else:
            status = "ok"
        return {
            "estado": status,
            "agentes_desplegados": len(deployed),
            "agentes_activos": len(deployed) - len(down),
            "alertas_criticas": len(critical),
        }

    def agents_view(self, window_minutes: int = 60) -> List[Dict[str, object]]:
        stats = summarize_by(self.collector.samples_since(window_minutes * 60), lambda s: s.agent)
        return [
            {**h.to_dict(), "trafico": stats.get(h.codename, summarize([]))}
            for h in self.health.latest()
        ]

    def agent_detail(self, codename: str, window_minutes: int = 60) -> Optional[Dict[str, object]]:
        health = self.health.get(codename)
        if health is None:
            return None
        samples = [s for s in self.collector.samples_since(window_minutes * 60) if s.agent == codename]
        routes = summarize_by(samples, lambda s: f"{s.method} {s.route}")
        return {
            **health.to_dict(),
            "ventana_minutos": window_minutes,
            "trafico": summarize(samples),
            "endpoints": [{"endpoint": name, **values} for name, values in routes.items()],
            "disponibilidad": self.health.availability().get(codename),
            "alertas_activas": [a.to_dict() for a in self.alerts.active() if a.agente == codename],
        }

    def metrics_json(self, window_minutes: int = 60) -> Dict[str, object]:
        samples = self.collector.samples_since(window_minutes * 60)
        return {
            "ventana_minutos": window_minutes,
            "tiempo_activo_segundos": round(self.collector.uptime(), 1),
            "peticiones": summarize(samples),
            "por_agente": summarize_by(samples, lambda s: s.agent),
            "estado_general": self.overall_status(),
            "nota": DATA_NOTE,
        }

    def performance_report(self, hours: int = 24) -> Dict[str, object]:
        samples = self.collector.samples_since(hours * 3600)
        by_route = summarize_by(samples, lambda s: f"{s.method} {s.route}")
        slowest = sorted(by_route.items(), key=lambda kv: kv[1]["latencia_p95_ms"], reverse=True)[:10]
        failing = sorted(
            ((k, v) for k, v in by_route.items() if v["errores_5xx"]), key=lambda kv: kv[1]["errores_5xx"], reverse=True
        )[:10]
        return {
            "periodo_horas": hours,
            "datos_desde": _iso(samples[0].ts) if samples else None,
            "resumen": summarize(samples),
            "por_agente": summarize_by(samples, lambda s: s.agent),
            "endpoints_mas_lentos": [{"endpoint": k, **v} for k, v in slowest],
            "endpoints_con_mas_errores": [{"endpoint": k, **v} for k, v in failing],
            "nota": DATA_NOTE,
        }

    def availability_report(self) -> Dict[str, object]:
        per_agent = self.health.availability()
        total_probes = sum(v["sondas"] for v in per_agent.values())
        total_up = sum(v["sondas"] - v["sondas_fallidas"] for v in per_agent.values())
        overall = round(100 * total_up / total_probes, 3) if total_probes else None
        not_deployed = [h.codename for h in self.health.latest() if h.estado == NOT_DEPLOYED]
        return {
            "disponibilidad_total_porcentaje": overall,
            "por_agente": per_agent,
            "agentes_no_desplegados": not_deployed,
            "sla": {
                "objetivo_porcentaje": self.sla_target,
                "actual_porcentaje": overall,
                "cumple": overall is not None and overall >= self.sla_target,
                "incumplen": [name for name, v in per_agent.items() if v["disponibilidad_porcentaje"] < self.sla_target],
            },
            "nota": DATA_NOTE,
        }

    def live_frame(self) -> Dict[str, object]:
        last_minute = self.collector.samples_since(60)
        stats = summarize(last_minute)
        resources = self.resources()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "peticiones_por_segundo": round(stats["total"] / 60, 2),
            "errores_5xx_por_segundo": round(stats["errores_5xx"] / 60, 3),
            "latencia_promedio_ms": stats["latencia_promedio_ms"],
            "cpu_porcentaje": resources["cpu"]["uso_porcentaje"],
            "memoria_porcentaje": resources["memoria"]["uso_porcentaje"],
            **self.overall_status(),
        }


_service: Optional[MonitoringService] = None
_service_lock = threading.Lock()


def get_monitoring_service() -> MonitoringService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = MonitoringService()
    return _service


def set_monitoring_service(service: Optional[MonitoringService]) -> None:
    global _service
    _service = service


def install_argus(app: FastAPI, service: Optional[MonitoringService] = None) -> MonitoringService:
    """Instrumenta la aplicación y arranca el ciclo periódico de sondas (ARGUS_PROBE_INTERVAL_SECONDS, 0 = apagado)."""
    if service is not None:
        set_monitoring_service(service)
    service = get_monitoring_service()
    app.add_middleware(ArgusMiddleware, collector=service.collector, routes_app=app)
    interval = int(os.getenv("ARGUS_PROBE_INTERVAL_SECONDS", "30"))
    if interval > 0:
        @app.on_event("startup")
        async def _start_argus() -> None:
            app.state.argus_task = asyncio.create_task(service.run_periodic(app, interval))

        @app.on_event("shutdown")
        async def _stop_argus() -> None:
            task = getattr(app.state, "argus_task", None)
            if task:
                task.cancel()
    return service
