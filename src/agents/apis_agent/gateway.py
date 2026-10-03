"""
Ejecución HTTP de Synapse: reintentos con backoff (solo métodos idempotentes o con clave de idempotencia),
circuit breaker y límite de tasa por integración, respuestas con tamaño máximo y sin seguir redirecciones.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Optional

import httpx

from src.agents.apis_agent.netguard import NetworkPolicy

IDEMPOTENT = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
RETRY_STATUS = frozenset({429, 502, 503, 504})
SAFE_RESPONSE_HEADERS = ("content-type", "content-length", "location", "retry-after", "x-request-id", "x-ratelimit-limit",
                         "x-ratelimit-remaining", "x-ratelimit-reset", "etag", "last-modified")


@dataclass
class CallResult:
    codigo_http: Optional[int]
    duracion_ms: float
    intentos: int
    cuerpo: Any = None
    tipo_contenido: Optional[str] = None
    truncado: bool = False
    encabezados: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def exito(self) -> bool:
        return self.codigo_http is not None and 200 <= self.codigo_http < 300

    @property
    def falla_remota(self) -> bool:
        """Cuenta para el circuit breaker: sin respuesta o error 5xx del proveedor."""
        return self.codigo_http is None or self.codigo_http >= 500


class CircuitBreaker:
    def __init__(self, threshold: int = 5, cooldown_seconds: float = 60, clock: Callable[[], float] = time.monotonic) -> None:
        self.threshold = threshold
        self.cooldown = cooldown_seconds
        self._clock = clock
        self._state: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> Optional[int]:
        """Segundos de espera si el circuito está abierto; None si se puede llamar (cerrado o semiabierto)."""
        with self._lock:
            state = self._state.get(key)
            if not state or state["abierto_en"] is None:
                return None
            remaining = self.cooldown - (self._clock() - state["abierto_en"])
            if remaining <= 0:
                if state["prueba_en_curso"]:
                    return 1
                state["prueba_en_curso"] = True
                return None
            return max(1, int(remaining + 0.999))

    def record(self, key: str, failed: bool) -> None:
        with self._lock:
            state = self._state.setdefault(key, {"fallos": 0, "abierto_en": None, "prueba_en_curso": False})
            state["prueba_en_curso"] = False
            if not failed:
                state.update(fallos=0, abierto_en=None)
                return
            state["fallos"] += 1
            if state["abierto_en"] is not None or state["fallos"] >= self.threshold:
                state["abierto_en"] = self._clock()

    def snapshot(self, key: str) -> Dict[str, Any]:
        with self._lock:
            state = self._state.get(key) or {"fallos": 0, "abierto_en": None}
            if state["abierto_en"] is None:
                status = "cerrado"
            else:
                status = "semiabierto" if self._clock() - state["abierto_en"] >= self.cooldown else "abierto"
            return {"estado": status, "fallos_consecutivos": state["fallos"]}


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str, per_minute: int) -> Optional[int]:
        """None si la llamada cabe en la ventana de 60 s; si no, los segundos hasta que haya cupo."""
        with self._lock:
            now = self._clock()
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= 60:
                hits.popleft()
            if len(hits) >= per_minute:
                return max(1, int(60 - (now - hits[0]) + 0.999))
            hits.append(now)
            return None


class HttpGateway:
    def __init__(self, policy: NetworkPolicy, transport: Optional[httpx.BaseTransport] = None, max_response_bytes: int = 1_000_000,
                 backoff_seconds: float = 0.5, sleep: Callable[[float], None] = time.sleep,
                 timer: Callable[[], float] = time.perf_counter) -> None:
        self.policy = policy
        self.max_response_bytes = max_response_bytes
        self._transport = transport
        self._backoff = backoff_seconds
        self._sleep = sleep
        self._timer = timer

    def _read(self, response: httpx.Response) -> tuple:
        chunks, size, truncated = [], 0, False
        for chunk in response.iter_bytes():
            room = self.max_response_bytes - size
            if len(chunk) > room:
                chunks.append(chunk[:room])
                truncated = True
                break
            chunks.append(chunk)
            size += len(chunk)
        raw = b"".join(chunks)
        content_type = response.headers.get("content-type", "")
        text = raw.decode(response.encoding or "utf-8", errors="replace")
        if "json" in content_type and not truncated and raw:
            try:
                return json.loads(text), truncated
            except ValueError:
                pass
        return text, truncated

    def send(self, method: str, url: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None,
             json_body: Any = None, timeout: float = 15, retries: int = 0, retry_unsafe: bool = False) -> CallResult:
        self.policy.check_url(url)
        attempts = 1 + (retries if method in IDEMPOTENT or retry_unsafe else 0)
        started = self._timer()
        error: Optional[str] = None
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False, transport=self._transport) as client:
                    request = client.build_request(method, url, params=params, headers=headers, json=json_body)
                    response = client.send(request, stream=True)
                    try:
                        body, truncated = self._read(response)
                    finally:
                        response.close()
            except httpx.TimeoutException:
                error = "tiempo de espera agotado"
            except httpx.HTTPError as e:
                error = f"error de conexión ({type(e).__name__})"
            else:
                if response.status_code in RETRY_STATUS and attempt < attempts:
                    self._sleep(self._backoff * 2 ** (attempt - 1))
                    continue
                return CallResult(
                    codigo_http=response.status_code, duracion_ms=round((self._timer() - started) * 1000, 2), intentos=attempt,
                    cuerpo=body, tipo_contenido=response.headers.get("content-type"), truncado=truncated,
                    encabezados={k: v for k, v in response.headers.items() if k.lower() in SAFE_RESPONSE_HEADERS},
                    error=None if response.status_code < 400 else f"el servicio respondió {response.status_code}",
                )
            if attempt < attempts:
                self._sleep(self._backoff * 2 ** (attempt - 1))
        return CallResult(codigo_http=None, duracion_ms=round((self._timer() - started) * 1000, 2), intentos=attempts, error=error)
