"""Registro de métricas de Argus: formato Prometheus + ventana en memoria para consultas y alertas."""

from __future__ import annotations

import math
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Iterable, List

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from src.agents.agent_catalog import ALL_AGENTS

PLATFORM = "Plataforma"
UNMATCHED_ROUTE = "sin_ruta"

_SEGMENT_TO_AGENT: Dict[str, str] = {}
for _profile in ALL_AGENTS:
    _SEGMENT_TO_AGENT[_profile.codename.lower()] = _profile.codename
    _SEGMENT_TO_AGENT.setdefault(_profile.route_key, _profile.codename)
_API_SEGMENT = re.compile(r"^/api/v1/([^/]+)")


def agent_for_route(route: str) -> str:
    match = _API_SEGMENT.match(route)
    return _SEGMENT_TO_AGENT.get(match.group(1), PLATFORM) if match else PLATFORM


@dataclass(frozen=True)
class RequestSample:
    ts: float
    agent: str
    method: str
    route: str
    status: int
    duration_ms: float


def _percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(pct / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


def summarize(samples: Iterable[RequestSample]) -> Dict[str, float]:
    samples = list(samples)
    durations = sorted(s.duration_ms for s in samples)
    total = len(samples)
    errors_5xx = sum(1 for s in samples if s.status >= 500)
    errors_4xx = sum(1 for s in samples if 400 <= s.status < 500)
    return {
        "total": total,
        "exitosas": total - errors_5xx - errors_4xx,
        "errores_4xx": errors_4xx,
        "errores_5xx": errors_5xx,
        "tasa_error_porcentaje": round(100 * errors_5xx / total, 2) if total else 0.0,
        "latencia_promedio_ms": round(sum(durations) / total, 2) if total else 0.0,
        "latencia_p95_ms": round(_percentile(durations, 95), 2),
        "latencia_p99_ms": round(_percentile(durations, 99), 2),
        "latencia_max_ms": round(durations[-1], 2) if durations else 0.0,
    }


def summarize_by(samples: Iterable[RequestSample], key: Callable[[RequestSample], str]) -> Dict[str, Dict[str, float]]:
    groups: Dict[str, List[RequestSample]] = defaultdict(list)
    for sample in samples:
        groups[key(sample)].append(sample)
    return {name: summarize(group) for name, group in sorted(groups.items())}


class MetricsCollector:
    def __init__(self, retention_hours: int = 24, max_samples: int = 200_000, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._retention_seconds = retention_hours * 3600
        self._samples: Deque[RequestSample] = deque(maxlen=max_samples)
        self._lock = threading.Lock()
        self.started_at = clock()

        self.registry = CollectorRegistry()
        self.requests_total = Counter(
            "kinetix_http_requests_total", "Peticiones HTTP atendidas", ["agent", "method", "route", "status"],
            registry=self.registry,
        )
        self.request_duration = Histogram(
            "kinetix_http_request_duration_seconds", "Latencia de peticiones HTTP", ["agent", "route"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=self.registry,
        )
        self.agent_up = Gauge("kinetix_agent_up", "1 si el agente responde, 0 si no", ["agent"], registry=self.registry)
        self.agent_probe_latency = Gauge(
            "kinetix_agent_probe_latency_ms", "Latencia de la última sonda de salud", ["agent"], registry=self.registry
        )
        self.cpu_percent = Gauge("kinetix_system_cpu_percent", "Uso de CPU del host", registry=self.registry)
        self.memory_percent = Gauge("kinetix_system_memory_percent", "Uso de memoria del host", registry=self.registry)
        self.disk_percent = Gauge("kinetix_system_disk_percent", "Uso de disco del host", registry=self.registry)
        self.active_alerts = Gauge("kinetix_active_alerts", "Alertas activas", ["severity"], registry=self.registry)
        self.uptime_seconds = Gauge("kinetix_process_uptime_seconds", "Tiempo desde el arranque del proceso", registry=self.registry)
        self.uptime_seconds.set_function(lambda: self._clock() - self.started_at)

    def record(self, agent: str, method: str, route: str, status: int, duration_ms: float) -> None:
        self.requests_total.labels(agent, method, route, str(status)).inc()
        self.request_duration.labels(agent, route).observe(duration_ms / 1000)
        with self._lock:
            self._samples.append(RequestSample(self._clock(), agent, method, route, status, duration_ms))

    def samples_since(self, seconds: float) -> List[RequestSample]:
        now = self._clock()
        with self._lock:
            while self._samples and now - self._samples[0].ts > self._retention_seconds:
                self._samples.popleft()
            return [s for s in self._samples if now - s.ts <= seconds]

    def uptime(self) -> float:
        return self._clock() - self.started_at

    def render(self) -> bytes:
        return generate_latest(self.registry)
