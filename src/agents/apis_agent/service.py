"""
Casos de uso de Synapse: integraciones con APIs externas por empresa, credenciales cifradas, importación de
OpenAPI, llamadas protegidas (SSRF, límite de tasa, circuit breaker, reintentos), pruebas de conexión y métricas.
"""

from __future__ import annotations

import base64
import re
from dataclasses import replace
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.agents.apis_agent import openapi
from src.agents.apis_agent.crypto import CredentialCipher
from src.agents.apis_agent.gateway import CallResult, CircuitBreaker, HttpGateway, RateLimiter
from src.agents.apis_agent.netguard import check_path
from src.agents.apis_agent.repository import CallRecord, Integration, IntegrationRepository
from src.agents.common import iso, new_id, utcnow
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError, RateLimitedError

VERSION = "2.0.0"
AUTH_TYPES = ("none", "bearer", "api_key", "basic")
STATES = ("activa", "inactiva")
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
BODY_METHODS = ("POST", "PUT", "PATCH", "DELETE")
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,59}$")
HEADER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{0,63}$")
QUERY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_\-:.]{8,100}$")
FORBIDDEN_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie", "host", "content-length", "transfer-encoding",
                               "connection", "upgrade", "te", "trailer", "keep-alive", "x-forwarded-for", "x-forwarded-host",
                               "x-real-ip", "forwarded"})
MAX_HEADERS = 20
MAX_HEADER_VALUE = 500


def _secret_fields(tipo: str) -> Tuple[str, ...]:
    return {"bearer": ("token",), "api_key": ("valor",), "basic": ("usuario", "contrasena")}.get(tipo, ())


def _check_headers(headers: Any, label: str = "encabezados") -> Dict[str, str]:
    if headers is None:
        return {}
    if not isinstance(headers, dict) or len(headers) > MAX_HEADERS:
        raise InvalidInputError(f"{label}: objeto con máximo {MAX_HEADERS} encabezados")
    clean: Dict[str, str] = {}
    for name, value in headers.items():
        if not isinstance(name, str) or not HEADER_NAME.match(name) or name.lower() in FORBIDDEN_HEADERS:
            raise InvalidInputError(f"{label}: encabezado no permitido {name!r}")
        text = str(value)
        if len(text) > MAX_HEADER_VALUE or "\r" in text or "\n" in text:
            raise InvalidInputError(f"{label}: valor inválido para {name}")
        clean[name] = text
    return clean


def _bounded(data: Dict[str, Any], key: str, default: Any, low: float, high: float, kind: type = int) -> Any:
    value = data.get(key)
    if value is None:
        return default
    try:
        number = kind(value)
    except (TypeError, ValueError):
        raise InvalidInputError(f"{key} debe ser numérico") from None
    if isinstance(value, bool) or not low <= number <= high:
        raise InvalidInputError(f"{key} debe estar entre {low:g} y {high:g}")
    return number


def call_view(c: CallRecord) -> Dict[str, Any]:
    return {"id_llamada": c.id_llamada, "id_integracion": c.id_integracion, "metodo": c.metodo, "ruta": c.ruta,
            "id_operacion": c.id_operacion, "codigo_http": c.codigo_http, "exito": c.exito, "duracion_ms": c.duracion_ms,
            "intentos": c.intentos, "error": c.error, "origen": c.origen, "usuario": c.usuario, "fecha": iso(c.fecha)}


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))], 2)


class SynapseService:
    def __init__(self, repository: IntegrationRepository, cipher: CredentialCipher, gateway: HttpGateway,
                 breaker: Optional[CircuitBreaker] = None, limiter: Optional[RateLimiter] = None, clock: Callable = utcnow,
                 max_integrations: int = 100) -> None:
        self._repo = repository
        self._cipher = cipher
        self._gateway = gateway
        self._breaker = breaker or CircuitBreaker()
        self._limiter = limiter or RateLimiter()
        self._clock = clock
        self.max_integrations = max_integrations

    def ping(self) -> None:
        self._repo.ping()

    @property
    def encryption_configured(self) -> bool:
        return self._cipher.configured

    @property
    def allowed_schemes(self) -> List[str]:
        return ["https", "http"] if self._gateway.policy.allow_http else ["https"]

    # ================================================================ vistas

    def _view(self, i: Integration, detail: bool = False) -> Dict[str, Any]:
        spec = i.especificacion or {}
        view = {
            "id_integracion": i.id_integracion, "nombre": i.nombre, "descripcion": i.descripcion, "url_base": i.url_base,
            "tipo_auth": i.tipo_auth, "auth": i.auth_meta, "credencial_configurada": bool(i.credencial), "estado": i.estado,
            "timeout_s": i.timeout_s, "reintentos": i.reintentos, "limite_por_minuto": i.limite_por_minuto,
            "operaciones": len(spec.get("operaciones", [])), "especificacion": spec.get("titulo") or None, "version": i.version,
            "salud": i.ultimo_estado_salud, "ultima_verificacion": iso(i.ultima_verificacion), "circuito": self._breaker.snapshot(i.id_integracion),
            "creado_por": i.creado_por, "fecha_creacion": iso(i.fecha_creacion), "fecha_modificacion": iso(i.fecha_modificacion),
        }
        if detail:
            view["encabezados"] = i.encabezados
            view["especificacion_detalle"] = {k: spec.get(k) for k in ("formato", "titulo", "version_api", "servidores")} if spec else None
        return view

    def _get(self, id_integracion: str, id_empresa: str) -> Integration:
        integration = self._repo.get(id_integracion, id_empresa)
        if integration is None:
            raise NotFoundError(f"Integración no encontrada: {id_integracion}")
        return integration

    # ================================================================ configuración

    def _auth(self, tipo: str, data: Dict[str, Any], current: Optional[Integration]) -> Tuple[Dict[str, Any], Optional[str]]:
        if tipo not in AUTH_TYPES:
            raise InvalidInputError(f"tipo_auth debe ser {', '.join(AUTH_TYPES)}")
        meta: Dict[str, Any] = {}
        if tipo == "api_key":
            source = data.get("auth") if data.get("auth") is not None else (current.auth_meta if current else {})
            ubicacion = (source or {}).get("ubicacion", "header")
            nombre = (source or {}).get("nombre", "X-API-Key")
            if ubicacion not in ("header", "query"):
                raise InvalidInputError("auth.ubicacion debe ser header o query")
            valid = isinstance(nombre, str) and (QUERY_NAME.match(nombre) if ubicacion == "query" else
                                                 HEADER_NAME.match(nombre) and nombre.lower() not in FORBIDDEN_HEADERS)
            if not valid:
                raise InvalidInputError("auth.nombre: nombre de encabezado o parámetro inválido")
            meta = {"ubicacion": ubicacion, "nombre": nombre}
        credentials = data.get("credenciales")
        fields = _secret_fields(tipo)
        if credentials is None:
            same_type = current is not None and current.tipo_auth == tipo
            if fields and not same_type:
                raise InvalidInputError(f"credenciales obligatorias para {tipo}: {', '.join(fields)}")
            return meta, current.credencial if same_type and fields else None
        if not fields:
            raise InvalidInputError("tipo_auth none no lleva credenciales")
        if not isinstance(credentials, dict) or set(credentials) != set(fields):
            raise InvalidInputError(f"credenciales para {tipo} deben tener exactamente: {', '.join(fields)}")
        secret = {k: str(credentials[k]) for k in fields}
        if any(not v or len(v) > 4000 or "\r" in v or "\n" in v for v in secret.values()):
            raise InvalidInputError("credenciales: valores vacíos, demasiado largos o con saltos de línea")
        return meta, self._cipher.encrypt(secret)

    def _fields(self, data: Dict[str, Any], current: Optional[Integration]) -> Dict[str, Any]:
        def pick(key: str, default: Any) -> Any:
            return data[key] if data.get(key) is not None else (getattr(current, key) if current else default)

        nombre = str(pick("nombre", "")).strip()
        if not NAME.match(nombre):
            raise InvalidInputError("nombre: 2 a 60 caracteres, empieza con letra (letras, números, '_' o '-')")
        descripcion = str(pick("descripcion", "")).strip()
        if len(descripcion) > 500:
            raise InvalidInputError("descripcion: máximo 500 caracteres")
        url_base = self._gateway.policy.check_base_url(str(pick("url_base", "")))
        if current is None or url_base != current.url_base:
            self._gateway.policy.check_url(url_base)
        estado = pick("estado", "activa")
        if estado not in STATES:
            raise InvalidInputError("estado debe ser activa o inactiva")
        tipo = pick("tipo_auth", "none")
        meta, credential = self._auth(tipo, data, current)
        return {
            "nombre": nombre, "descripcion": descripcion, "url_base": url_base, "estado": estado, "tipo_auth": tipo, "auth_meta": meta,
            "credencial": credential,
            "encabezados": _check_headers(data["encabezados"]) if data.get("encabezados") is not None else (current.encabezados if current else {}),
            "timeout_s": _bounded(data, "timeout_s", current.timeout_s if current else 15.0, 1, 60, float),
            "reintentos": _bounded(data, "reintentos", current.reintentos if current else 2, 0, 3),
            "limite_por_minuto": _bounded(data, "limite_por_minuto", current.limite_por_minuto if current else 60, 1, 600),
        }

    def create_integration(self, actor: str, id_empresa: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if self._repo.count(id_empresa) >= self.max_integrations:
            raise ConflictError(f"La empresa alcanzó el máximo de {self.max_integrations} integraciones")
        now = self._clock()
        integration = Integration(id_integracion=new_id("syn"), id_empresa=id_empresa, fecha_creacion=now, fecha_modificacion=now,
                                  creado_por=actor, **self._fields(data, None))
        if not self._repo.create(integration):
            raise ConflictError(f"Ya existe una integración llamada {integration.nombre}")
        return self._view(integration, detail=True)

    def list_integrations(self, id_empresa: str) -> Dict[str, Any]:
        items = self._repo.list(id_empresa)
        return {"total": len(items), "integraciones": [self._view(i) for i in items]}

    def get_integration(self, id_integracion: str, id_empresa: str) -> Dict[str, Any]:
        return self._view(self._get(id_integracion, id_empresa), detail=True)

    def update_integration(self, id_integracion: str, id_empresa: str, data: Dict[str, Any]) -> Dict[str, Any]:
        current = self._get(id_integracion, id_empresa)
        expected = data.get("version")
        if expected is not None and expected != current.version:
            raise ConflictError(f"La integración cambió (versión actual {current.version}); vuelve a leerla")
        updated = replace(current, fecha_modificacion=self._clock(), **self._fields(data, current))
        if not self._repo.update(updated, current.version):
            raise ConflictError("La integración cambió o el nombre ya está en uso; vuelve a leerla")
        return self._view(replace(updated, version=current.version + 1), detail=True)

    def delete_integration(self, id_integracion: str, id_empresa: str) -> Dict[str, Any]:
        if not self._repo.delete(id_integracion, id_empresa):
            raise NotFoundError(f"Integración no encontrada: {id_integracion}")
        return {"id_integracion": id_integracion, "eliminada": True}

    # ================================================================ OpenAPI

    def import_spec(self, actor: str, id_integracion: str, id_empresa: str, data: Dict[str, Any]) -> Dict[str, Any]:
        current = self._get(id_integracion, id_empresa)
        sources = [k for k in ("especificacion", "contenido", "url") if data.get(k)]
        if len(sources) != 1:
            raise InvalidInputError("Envía exactamente una fuente: especificacion (objeto), contenido (JSON/YAML) o url")
        if sources[0] == "especificacion":
            if not isinstance(data["especificacion"], dict):
                raise InvalidInputError("especificacion debe ser un objeto")
            raw = data["especificacion"]
        elif sources[0] == "contenido":
            raw = openapi.load_text(str(data["contenido"]))
        else:
            url = self._gateway.policy.check_base_url(str(data["url"]))
            result = self._gateway.send("GET", url, timeout=current.timeout_s, retries=current.reintentos)
            if not result.exito or result.truncado:
                raise InvalidInputError(f"No se pudo descargar la especificación: {result.error or 'respuesta demasiado grande'}")
            raw = result.cuerpo if isinstance(result.cuerpo, dict) else openapi.load_text(str(result.cuerpo))
        spec = openapi.parse_spec(raw)
        updated = replace(current, especificacion=spec, fecha_modificacion=self._clock())
        if not self._repo.update(updated, current.version):
            raise ConflictError("La integración cambió mientras se importaba la especificación; reintenta")
        return {"id_integracion": id_integracion, "formato": spec["formato"], "titulo": spec["titulo"], "version_api": spec["version_api"],
                "operaciones": len(spec["operaciones"]), "servidores": spec["servidores"], "importado_por": actor}

    def operations(self, id_integracion: str, id_empresa: str, filtro: Optional[str] = None) -> Dict[str, Any]:
        spec = self._get(id_integracion, id_empresa).especificacion
        if not spec:
            raise NotFoundError("La integración no tiene una especificación OpenAPI importada")
        items = spec["operaciones"]
        if filtro:
            needle = filtro.lower()
            items = [o for o in items if needle in o["id_operacion"].lower() or needle in o["ruta"].lower() or needle in o["resumen"].lower()]
        return {"titulo": spec["titulo"], "total": len(items), "operaciones": items}

    # ================================================================ llamadas

    def _resolve_request(self, integration: Integration, data: Dict[str, Any],
                         enforce_spec: bool) -> Tuple[str, str, Optional[str], Dict[str, Any], Dict[str, str]]:
        operations = (integration.especificacion or {}).get("operaciones", [])
        query = dict(data.get("consulta") or {})
        if not isinstance(query, dict) or len(query) > 50:
            raise InvalidInputError("consulta: objeto con máximo 50 parámetros")
        if data.get("id_operacion"):
            op = next((o for o in operations if o["id_operacion"] == data["id_operacion"]), None)
            if op is None:
                raise NotFoundError(f"Operación no declarada: {data['id_operacion']}")
            path, op_query, op_headers = openapi.build_call(op, dict(data.get("parametros") or {}))
            if op["cuerpo_requerido"] and data.get("cuerpo") is None:
                raise InvalidInputError(f"{op['id_operacion']} requiere cuerpo")
            return op["metodo"], path, op["id_operacion"], {**query, **op_query}, op_headers
        method = str(data.get("metodo") or "GET").upper()
        if method not in METHODS:
            raise InvalidInputError(f"metodo debe ser {', '.join(METHODS)}")
        path = check_path(str(data.get("ruta") or "/"))
        if data.get("parametros"):
            raise InvalidInputError("parametros solo aplica con id_operacion; usa consulta para la cadena de consulta")
        op = openapi.match_operation(operations, method, path) if operations else None
        if enforce_spec and operations and op is None:
            raise InvalidInputError(f"{method} {path} no está declarada en la especificación importada")
        return method, path, op["id_operacion"] if op else None, query, {}

    def _auth_headers(self, integration: Integration, query: Dict[str, Any]) -> Dict[str, str]:
        if integration.tipo_auth == "none" or not integration.credencial:
            return {}
        secret = self._cipher.decrypt(integration.credencial)
        if integration.tipo_auth == "bearer":
            return {"Authorization": f"Bearer {secret['token']}"}
        if integration.tipo_auth == "basic":
            raw = f"{secret['usuario']}:{secret['contrasena']}".encode("utf-8")
            return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}
        if integration.auth_meta.get("ubicacion") == "query":
            query[integration.auth_meta["nombre"]] = secret["valor"]
            return {}
        return {integration.auth_meta["nombre"]: secret["valor"]}

    def _execute(self, actor: str, integration: Integration, data: Dict[str, Any], origen: str) -> Tuple[CallResult, CallRecord]:
        if integration.estado != "activa":
            raise ConflictError(f"La integración {integration.nombre} está inactiva")
        # Las pruebas de conexión (solo GET/HEAD) pueden sondear rutas fuera de la especificación, p. ej. "/".
        method, path, id_operacion, query, op_headers = self._resolve_request(integration, data, enforce_spec=origen != "prueba")
        body = data.get("cuerpo")
        if body is not None and method not in BODY_METHODS:
            raise InvalidInputError(f"{method} no admite cuerpo")
        idempotency = data.get("clave_idempotencia")
        if idempotency is not None and not IDEMPOTENCY_KEY.match(str(idempotency)):
            raise InvalidInputError("clave_idempotencia: 8 a 100 caracteres (letras, números, _ - : .)")
        wait = self._limiter.acquire(integration.id_integracion, integration.limite_por_minuto)
        if wait is not None:
            raise RateLimitedError(f"{integration.nombre} superó su límite de {integration.limite_por_minuto} llamadas por minuto", wait)
        wait = self._breaker.retry_after(integration.id_integracion)
        if wait is not None:
            raise RateLimitedError(f"Circuito abierto para {integration.nombre} tras fallos consecutivos; reintenta más tarde", wait)
        headers = {**integration.encabezados, **_check_headers(data.get("encabezados"), "encabezados de la llamada"),
                   **_check_headers(op_headers, "parámetros de encabezado")}
        if idempotency:
            headers["Idempotency-Key"] = str(idempotency)
        headers.update(self._auth_headers(integration, query))
        try:
            result = self._gateway.send(method, integration.url_base + path, params=query or None,
                                        headers=headers, json_body=body, timeout=integration.timeout_s,
                                        retries=integration.reintentos, retry_unsafe=bool(idempotency))
        except InvalidInputError as e:
            result = CallResult(codigo_http=None, duracion_ms=0, intentos=0, error=f"destino bloqueado: {e}")
            self._log(actor, integration, method, path, id_operacion, result, origen)
            raise
        self._breaker.record(integration.id_integracion, result.falla_remota)
        return result, self._log(actor, integration, method, path, id_operacion, result, origen)

    def _log(self, actor: str, integration: Integration, method: str, path: str, id_operacion: Optional[str], result: CallResult,
             origen: str) -> CallRecord:
        record = CallRecord(id_llamada=new_id("call"), id_integracion=integration.id_integracion, id_empresa=integration.id_empresa,
                            metodo=method, ruta=path, id_operacion=id_operacion, codigo_http=result.codigo_http, exito=result.exito,
                            duracion_ms=result.duracion_ms, intentos=result.intentos, error=result.error, origen=origen, usuario=actor,
                            fecha=self._clock())
        self._repo.log_call(record)
        return record

    def call(self, actor: str, id_integracion: str, id_empresa: str, data: Dict[str, Any]) -> Dict[str, Any]:
        result, record = self._execute(actor, self._get(id_integracion, id_empresa), data, "llamada")
        return {"id_llamada": record.id_llamada, "metodo": record.metodo, "ruta": record.ruta, "id_operacion": record.id_operacion,
                "codigo_http": result.codigo_http, "exito": result.exito, "duracion_ms": result.duracion_ms, "intentos": result.intentos,
                "tipo_contenido": result.tipo_contenido, "encabezados": result.encabezados, "cuerpo": result.cuerpo,
                "truncado": result.truncado, "error": result.error}

    def test_connection(self, actor: str, id_integracion: str, id_empresa: str, ruta: str = "/", metodo: str = "GET") -> Dict[str, Any]:
        integration = self._get(id_integracion, id_empresa)
        if metodo.upper() not in ("GET", "HEAD"):
            raise InvalidInputError("La prueba de conexión solo usa GET o HEAD")
        result, _ = self._execute(actor, integration, {"metodo": metodo, "ruta": ruta}, "prueba")
        status = "saludable" if result.exito else ("degradada" if result.codigo_http and result.codigo_http < 500 else "caida")
        self._repo.set_health(integration.id_integracion, status, self._clock())
        return {"id_integracion": id_integracion, "salud": status, "codigo_http": result.codigo_http, "duracion_ms": result.duracion_ms,
                "intentos": result.intentos, "error": result.error, "circuito": self._breaker.snapshot(id_integracion)}

    def list_calls(self, id_empresa: str, id_integracion: Optional[str] = None, limite: int = 50) -> Dict[str, Any]:
        items = self._repo.calls(id_empresa, id_integracion, None, max(1, min(limite, 500)))
        return {"total": len(items), "llamadas": [call_view(c) for c in items]}

    def metrics(self, id_empresa: str, horas: int = 24) -> Dict[str, Any]:
        horas = max(1, min(horas, 168))
        since = self._clock() - timedelta(hours=horas)
        calls = self._repo.calls(id_empresa, None, since, 10_000)
        names = {i.id_integracion: i.nombre for i in self._repo.list(id_empresa)}
        groups: Dict[str, List[CallRecord]] = {}
        for c in calls:
            groups.setdefault(c.id_integracion, []).append(c)
        per_integration = []
        for id_integracion, items in groups.items():
            durations = [c.duracion_ms for c in items]
            ok_count = sum(1 for c in items if c.exito)
            per_integration.append({
                "id_integracion": id_integracion, "nombre": names.get(id_integracion), "llamadas": len(items), "exitosas": ok_count,
                "tasa_exito": round(100 * ok_count / len(items), 2), "latencia_p50_ms": _percentile(durations, 50),
                "latencia_p95_ms": _percentile(durations, 95), "reintentos": sum(max(0, c.intentos - 1) for c in items),
                "circuito": self._breaker.snapshot(id_integracion),
            })
        per_integration.sort(key=lambda r: -r["llamadas"])
        total_ok = sum(r["exitosas"] for r in per_integration)
        return {"horas": horas, "llamadas": len(calls), "tasa_exito": round(100 * total_ok / len(calls), 2) if calls else None,
                "latencia_p95_ms": _percentile([c.duracion_ms for c in calls], 95), "por_integracion": per_integration}
