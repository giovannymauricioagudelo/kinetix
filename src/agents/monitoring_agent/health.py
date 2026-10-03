"""Sondas de salud de Argus: consulta en proceso el endpoint de cada agente del catálogo."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Deque, Dict, List, Optional, Tuple

import httpx

from src.agents.agent_catalog import (
    ALL_AGENTS, ARGUS, AURORA, INSIGHT, MATRIX, NEXUS, ORBIT, PRISM, SENTINEL, VECTOR, AgentProfile,
)
from src.agents.monitoring_agent.collector import MetricsCollector
from src.agents.monitoring_agent.middleware import PROBE_HEADER, PROBE_TOKEN

UP = "activo"
SLOW = "lento"
DOWN = "caido"
NOT_DEPLOYED = "no_desplegado"

_PROBE_SUFFIX = {p.codename: "/salud" for p in (NEXUS, MATRIX, INSIGHT, PRISM, ORBIT, VECTOR, AURORA, SENTINEL, ARGUS)}


def probe_path(profile: AgentProfile) -> str:
    return f"/api/v1/{profile.codename.lower()}{_PROBE_SUFFIX.get(profile.codename, '/info')}"


@dataclass(frozen=True)
class AgentHealth:
    codename: str
    legacy_id: str
    estado: str
    latencia_ms: Optional[float]
    codigo_http: Optional[int]
    revisado_en: float
    detalle: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "agente": self.codename,
            "legacy_id": self.legacy_id,
            "estado": self.estado,
            "latencia_ms": self.latencia_ms,
            "codigo_http": self.codigo_http,
            "sonda": probe_path(next(p for p in ALL_AGENTS if p.codename == self.codename)),
            "revisado_en": datetime.fromtimestamp(self.revisado_en, tz=timezone.utc).isoformat(),
            "detalle": self.detalle,
        }


class AgentHealthMonitor:
    def __init__(
        self,
        collector: MetricsCollector,
        slow_ms: float = 1000,
        timeout_seconds: float = 5,
        history_size: int = 20_000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._collector = collector
        self._slow_ms = slow_ms
        self._timeout = timeout_seconds
        self._clock = clock
        self._latest: Dict[str, AgentHealth] = {}
        self._history: Dict[str, Deque[Tuple[float, bool]]] = {p.codename: deque(maxlen=history_size) for p in ALL_AGENTS}
        self._last_probe: float = 0.0
        self._probe_lock = asyncio.Lock()

    @property
    def last_probe(self) -> float:
        return self._last_probe

    async def probe_all(self, app) -> List[AgentHealth]:
        async with self._probe_lock:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://argus.internal", timeout=self._timeout) as client:
                results = await asyncio.gather(*(self._probe(client, p) for p in ALL_AGENTS))
            self._last_probe = self._clock()
            return list(results)

    async def _probe(self, client: httpx.AsyncClient, profile: AgentProfile) -> AgentHealth:
        start = time.perf_counter()
        status_code: Optional[int] = None
        detail: Optional[str] = None
        try:
            response = await client.get(probe_path(profile), headers={PROBE_HEADER: PROBE_TOKEN})
            status_code = response.status_code
        except Exception as e:
            detail = type(e).__name__
        latency = round((time.perf_counter() - start) * 1000, 2)

        if status_code == 404:
            state = NOT_DEPLOYED
        elif status_code is None or status_code >= 500:
            state = DOWN
        else:
            state = SLOW if latency > self._slow_ms else UP

        health = AgentHealth(profile.codename, profile.legacy_id, state, latency, status_code, self._clock(), detail)
        self._latest[profile.codename] = health
        if state != NOT_DEPLOYED:
            self._history[profile.codename].append((health.revisado_en, state != DOWN))
            self._collector.agent_up.labels(profile.codename).set(0 if state == DOWN else 1)
            self._collector.agent_probe_latency.labels(profile.codename).set(latency)
        return health

    def latest(self) -> List[AgentHealth]:
        return [self._latest[p.codename] for p in ALL_AGENTS if p.codename in self._latest]

    def get(self, codename: str) -> Optional[AgentHealth]:
        return self._latest.get(codename)

    def availability(self) -> Dict[str, Dict[str, object]]:
        report: Dict[str, Dict[str, object]] = {}
        for codename, history in self._history.items():
            if not history:
                continue
            up = sum(1 for _, ok in history if ok)
            report[codename] = {
                "disponibilidad_porcentaje": round(100 * up / len(history), 3),
                "sondas": len(history),
                "sondas_fallidas": len(history) - up,
                "desde": datetime.fromtimestamp(history[0][0], tz=timezone.utc).isoformat(),
            }
        return report
