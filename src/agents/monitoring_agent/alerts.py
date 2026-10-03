"""Reglas de alerta de Argus: se abren mientras la condición se cumple y se resuelven solas al desaparecer."""

from __future__ import annotations

import os
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Deque, Dict, Iterable, List, Optional, Tuple

from src.agents.monitoring_agent.health import DOWN, AgentHealth

WARNING = "advertencia"
CRITICAL = "critica"
ACTIVE = "activa"
RESOLVED = "resuelta"


def _iso(ts: Optional[float]) -> Optional[str]:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts is not None else None


@dataclass(frozen=True)
class AlertThresholds:
    latency_ms: float = 1000
    error_rate_percent: float = 10
    min_requests_error_rate: int = 20
    min_requests_latency: int = 5
    cpu_percent: float = 80
    memory_percent: float = 85
    disk_percent: float = 90
    window_minutes: int = 5

    @classmethod
    def from_env(cls) -> "AlertThresholds":
        def value(name: str, default: float) -> float:
            raw = os.getenv(name)
            return float(raw) if raw and raw.strip() else default

        return cls(
            latency_ms=value("ARGUS_ALERTA_LATENCIA_MS", cls.latency_ms),
            error_rate_percent=value("ARGUS_ALERTA_TASA_ERROR", cls.error_rate_percent),
            cpu_percent=value("ARGUS_ALERTA_CPU", cls.cpu_percent),
            memory_percent=value("ARGUS_ALERTA_MEMORIA", cls.memory_percent),
            disk_percent=value("ARGUS_ALERTA_DISCO", cls.disk_percent),
        )


@dataclass
class Alert:
    id: str
    tipo: str
    severidad: str
    agente: str
    mensaje: str
    valor: float
    umbral: float
    desde: float
    ultima_vez: float
    estado: str = ACTIVE
    reconocida_por: Optional[str] = None
    reconocida_en: Optional[float] = None
    resuelta_en: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "tipo": self.tipo,
            "severidad": self.severidad,
            "agente": self.agente,
            "mensaje": self.mensaje,
            "valor": self.valor,
            "umbral": self.umbral,
            "estado": self.estado,
            "desde": _iso(self.desde),
            "ultima_vez": _iso(self.ultima_vez),
            "reconocida_por": self.reconocida_por,
            "reconocida_en": _iso(self.reconocida_en),
            "resuelta_en": _iso(self.resuelta_en),
        }


Condition = Tuple[str, str, float, float]


class AlertManager:
    def __init__(self, thresholds: AlertThresholds, clock: Callable[[], float] = time.time, max_resolved: int = 500) -> None:
        self.thresholds = thresholds
        self._clock = clock
        self._active: Dict[Tuple[str, str], Alert] = {}
        self._resolved: Deque[Alert] = deque(maxlen=max_resolved)

    def _conditions(
        self,
        agent_stats: Dict[str, Dict[str, float]],
        health: Iterable[AgentHealth],
        resources: Optional[Dict[str, Dict[str, float]]],
    ) -> Dict[Tuple[str, str], Condition]:
        t = self.thresholds
        found: Dict[Tuple[str, str], Condition] = {}
        for agent, stats in agent_stats.items():
            total = stats["total"]
            if total >= t.min_requests_latency and stats["latencia_promedio_ms"] > t.latency_ms:
                found[("latencia_alta", agent)] = (
                    WARNING, f"Latencia promedio de {agent}: {stats['latencia_promedio_ms']:.0f} ms",
                    stats["latencia_promedio_ms"], t.latency_ms,
                )
            if total >= t.min_requests_error_rate and stats["tasa_error_porcentaje"] > t.error_rate_percent:
                found[("tasa_error_alta", agent)] = (
                    CRITICAL, f"Tasa de errores 5xx de {agent}: {stats['tasa_error_porcentaje']:.1f}%",
                    stats["tasa_error_porcentaje"], t.error_rate_percent,
                )
        for item in health:
            if item.estado == DOWN:
                found[("agente_caido", item.codename)] = (
                    CRITICAL, f"{item.codename} no responde ({item.codigo_http or item.detalle})", 0.0, 1.0,
                )
        if resources:
            for key, label, limit in (
                ("cpu", "CPU", t.cpu_percent),
                ("memoria", "Memoria", t.memory_percent),
                ("disco", "Disco", t.disk_percent),
            ):
                usage = resources[key]["uso_porcentaje"]
                if usage > limit:
                    found[(f"{key}_alta", "Sistema")] = (WARNING, f"{label} al {usage:.1f}%", usage, limit)
        return found

    def evaluate(
        self,
        agent_stats: Dict[str, Dict[str, float]],
        health: Iterable[AgentHealth],
        resources: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> List[Alert]:
        now = self._clock()
        conditions = self._conditions(agent_stats, health, resources)
        for (tipo, agente), (severidad, mensaje, valor, umbral) in conditions.items():
            alert = self._active.get((tipo, agente))
            if alert is None:
                self._active[(tipo, agente)] = Alert(
                    uuid.uuid4().hex[:12], tipo, severidad, agente, mensaje, round(valor, 2), umbral, now, now
                )
            else:
                alert.mensaje, alert.valor, alert.ultima_vez = mensaje, round(valor, 2), now
        for key in [k for k in self._active if k not in conditions]:
            alert = self._active.pop(key)
            alert.estado, alert.resuelta_en = RESOLVED, now
            self._resolved.appendleft(alert)
        return self.active()

    def active(self) -> List[Alert]:
        return sorted(self._active.values(), key=lambda a: (a.severidad != CRITICAL, a.desde))

    def list(self, estado: Optional[str] = None, severidad: Optional[str] = None) -> List[Alert]:
        if estado == ACTIVE:
            alerts = self.active()
        elif estado == RESOLVED:
            alerts = list(self._resolved)
        else:
            alerts = self.active() + list(self._resolved)
        return [a for a in alerts if severidad is None or a.severidad == severidad]

    def acknowledge(self, alert_id: str, by: str) -> Alert:
        for alert in self._active.values():
            if alert.id == alert_id:
                alert.reconocida_por, alert.reconocida_en = by, self._clock()
                return alert
        if any(a.id == alert_id for a in self._resolved):
            raise ValueError("La alerta ya se resolvió")
        raise KeyError(alert_id)
