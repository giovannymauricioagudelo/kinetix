"""Synapse (APIsAgent): SSRF, credenciales cifradas, OpenAPI, reintentos, circuit breaker, límite de tasa y API protegida."""

import base64
import socket
from datetime import datetime, timedelta

import httpx
import pytest
from cryptography.fernet import Fernet

from src.agents.apis_agent import openapi
from src.agents.apis_agent.crypto import CredentialCipher
from src.agents.apis_agent.dependencies import set_synapse_service
from src.agents.apis_agent.gateway import CircuitBreaker, HttpGateway, RateLimiter
from src.agents.apis_agent.netguard import NetworkPolicy, check_path
from src.agents.apis_agent.repository import InMemoryIntegrationRepository
from src.agents.apis_agent.service import SynapseService
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError, RateLimitedError
from src.api.routes import synapse_routes
from tests.unit.agent_api import build_api, headers

HOSTS = {
    "api.example.com": ["93.184.216.34"],
    "legacy.example.com": ["93.184.216.35"],
    "interno.local": ["10.0.0.5"],
    "mixto.example.com": ["93.184.216.34", "127.0.0.1"],
    "mapeado.example.com": ["::ffff:192.168.1.1"],
}
TOKEN = "tok-prueba-synapse-123"

SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Clientes", "version": "1.2"},
    "servers": [{"url": "https://api.example.com/v1"}],
    "components": {"parameters": {"Id": {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}}},
    "paths": {
        "/clientes": {
            "get": {"operationId": "listarClientes", "summary": "Lista clientes",
                    "parameters": [{"name": "activo", "in": "query", "schema": {"type": "boolean"}}]},
            "post": {"operationId": "crearCliente", "requestBody": {"required": True, "content": {}}},
        },
        "/clientes/{id}": {
            "parameters": [{"$ref": "#/components/parameters/Id"}],
            "get": {"summary": "Detalle"},
            "delete": {"operationId": "borrarCliente", "deprecated": True},
        },
    },
}

SWAGGER_YAML = """
swagger: "2.0"
info: {title: Legacy, version: "1"}
host: legacy.example.com
basePath: /api
schemes: [https]
paths:
  /pedidos:
    post:
      operationId: crearPedido
      parameters:
        - {name: cuerpo, in: body, required: true, schema: {type: object}}
        - {name: X-Canal, in: header, type: string}
"""


def resolver(host, port):
    if host not in HOSTS:
        raise socket.gaierror("desconocido")
    return HOSTS[host]


class Tick:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class StepClock:
    def __init__(self):
        self.now = datetime(2026, 10, 3, 12, 0, 0)

    def __call__(self):
        self.now += timedelta(seconds=1)
        return self.now


class FakeApi:
    def __init__(self):
        self.requests = []
        self.routes = {}

    def queue(self, path, *responses):
        self.routes[path] = list(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        queue = self.routes.get(request.url.path)
        if queue:
            item = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(item, Exception):
                raise item
            return item if isinstance(item, httpx.Response) else httpx.Response(item, json={"codigo": item})
        return httpx.Response(200, json={"ok": True, "ruta": request.url.path}, headers={"set-cookie": "sesion=1"})


def make_service(api, max_bytes=10_000, **kwargs):
    tick = Tick()
    gateway = HttpGateway(NetworkPolicy(resolver=resolver), transport=httpx.MockTransport(api.handler),
                          max_response_bytes=max_bytes, sleep=lambda s: None)
    service = SynapseService(InMemoryIntegrationRepository(), CredentialCipher([Fernet.generate_key().decode()]), gateway,
                             breaker=CircuitBreaker(2, 30, clock=tick), limiter=RateLimiter(clock=tick), clock=StepClock(), **kwargs)
    return service, tick


@pytest.fixture
def api():
    return FakeApi()


@pytest.fixture
def synapse(api):
    return make_service(api)


def create(service, nombre="clientes", **data):
    return service.create_integration("ana", "gio", {"nombre": nombre, "url_base": "https://api.example.com/v1", **data})


def test_network_policy_blocks_private_and_unsafe_destinations(synapse):
    service, _ = synapse
    policy = NetworkPolicy(resolver=resolver)
    assert policy.check_base_url("https://API.example.com/v1/") == "https://api.example.com/v1"
    for url in ("http://api.example.com", "https://user:pw@api.example.com", "https://api.example.com/v1?x=1",
                "https://api.example.com/a/../b", "ftp://api.example.com"):
        with pytest.raises(InvalidInputError):
            policy.check_base_url(url)
    for host in ("interno.local", "mixto.example.com", "mapeado.example.com"):
        with pytest.raises(InvalidInputError, match="no pública"):
            policy.check_url(f"https://{host}/x")
    with pytest.raises(InvalidInputError, match="resolver"):
        policy.check_url("https://no-existe.example.com/")
    NetworkPolicy(allowed_private_hosts=["interno.local"], resolver=resolver).check_url("https://interno.local/x")
    assert NetworkPolicy(allow_http=True, resolver=resolver).check_base_url("http://api.example.com") == "http://api.example.com"
    for path in ("//evil.com/x", "/a/../b", "/v1?x=1", "https://evil.com"):
        with pytest.raises(InvalidInputError):
            check_path(path)
    assert check_path("/v1/clientes") == "/v1/clientes"
    with pytest.raises(InvalidInputError, match="no pública"):
        service.create_integration("ana", "gio", {"nombre": "interno", "url_base": "https://interno.local"})


def test_credentials_are_encrypted_never_returned_and_rotate(synapse, api):
    service, _ = synapse
    with pytest.raises(InvalidInputError, match="credenciales obligatorias"):
        create(service, tipo_auth="bearer")
    with pytest.raises(InvalidInputError, match="no lleva credenciales"):
        create(service, credenciales={"token": TOKEN})
    view = create(service, tipo_auth="bearer", credenciales={"token": TOKEN})
    assert view["credencial_configurada"] and TOKEN not in str(view)
    stored = service._repo.get(view["id_integracion"], "gio")
    assert TOKEN not in stored.credencial
    service.call("ana", view["id_integracion"], "gio", {"ruta": "/x"})
    assert api.requests[-1].headers["Authorization"] == f"Bearer {TOKEN}"
    updated = service.update_integration(view["id_integracion"], "gio", {"descripcion": "sin tocar la llave", "version": 1})
    assert updated["version"] == 2 and service._repo.get(view["id_integracion"], "gio").credencial == stored.credencial

    basic = create(service, "basica", tipo_auth="basic", credenciales={"usuario": "u", "contrasena": "p:1"})
    service.call("ana", basic["id_integracion"], "gio", {"ruta": "/x"})
    assert api.requests[-1].headers["Authorization"] == "Basic " + base64.b64encode(b"u:p:1").decode()
    key = create(service, "llave", tipo_auth="api_key", auth={"ubicacion": "query", "nombre": "api_key"}, credenciales={"valor": "v1"})
    service.call("ana", key["id_integracion"], "gio", {"ruta": "/x"})
    assert api.requests[-1].url.params["api_key"] == "v1"
    with pytest.raises(InvalidInputError):
        create(service, "malo", tipo_auth="api_key", auth={"ubicacion": "header", "nombre": "Authorization"}, credenciales={"valor": "v"})

    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    token = CredentialCipher([old]).encrypt({"token": "t"})
    rotated = CredentialCipher([new, old]).rotate(token)
    assert CredentialCipher([new]).decrypt(rotated) == {"token": "t"}
    with pytest.raises(ConflictError, match="descifrar"):
        CredentialCipher([new]).decrypt(token)
    with pytest.raises(ConflictError, match="SYNAPSE_ENCRYPTION_KEY"):
        CredentialCipher([]).encrypt({"token": "t"})
    with pytest.raises(ValueError):
        CredentialCipher(["no-es-una-llave"])


def test_openapi_parsing_for_openapi3_and_swagger2():
    spec = openapi.parse_spec(SPEC)
    assert spec["formato"] == "openapi 3.0.3" and spec["titulo"] == "Clientes" and len(spec["operaciones"]) == 4
    ops = {o["id_operacion"]: o for o in spec["operaciones"]}
    assert set(ops) == {"listarClientes", "crearCliente", "get_clientes_id", "borrarCliente"}
    assert ops["crearCliente"]["cuerpo_requerido"] and ops["borrarCliente"]["obsoleta"]
    assert openapi.build_call(ops["get_clientes_id"], {"id": "42"}) == ("/clientes/42", {}, {})
    assert openapi.build_call(ops["listarClientes"], {"activo": "true"}) == ("/clientes", {"activo": True}, {})
    for params, message in (({}, "obligatorio"), ({"id": "abc"}, "integer"), ({"id": 1, "x": 2}, "no declarados")):
        with pytest.raises(InvalidInputError, match=message):
            openapi.build_call(ops["get_clientes_id"], params)
    assert openapi.match_operation(spec["operaciones"], "DELETE", "/clientes/9")["id_operacion"] == "borrarCliente"
    assert openapi.match_operation(spec["operaciones"], "GET", "/clientes/9/extra") is None

    legacy = openapi.parse_spec(openapi.load_text(SWAGGER_YAML))
    assert legacy["formato"] == "swagger 2.0" and legacy["servidores"] == ["https://legacy.example.com/api"]
    pedido = legacy["operaciones"][0]
    assert pedido["cuerpo_requerido"] and [p["nombre"] for p in pedido["parametros"]] == ["X-Canal"]
    assert openapi.build_call(pedido, {"X-Canal": "web"}) == ("/pedidos", {}, {"X-Canal": "web"})
    for bad in ("[1, 2", "- a\n- b"):
        with pytest.raises(InvalidInputError):
            openapi.load_text(bad)
    with pytest.raises(InvalidInputError, match="OpenAPI"):
        openapi.parse_spec({"info": {}, "paths": {"/x": {"get": {}}}})


def test_calls_are_validated_against_the_imported_spec(synapse, api):
    service, _ = synapse
    integration = create(service)["id_integracion"]
    with pytest.raises(NotFoundError):
        service.operations(integration, "gio")
    imported = service.import_spec("ana", integration, "gio", {"especificacion": SPEC})
    assert imported["operaciones"] == 4 and service.get_integration(integration, "gio")["operaciones"] == 4
    assert service.operations(integration, "gio", "detalle")["total"] == 1

    result = service.call("ana", integration, "gio", {"id_operacion": "listarClientes", "parametros": {"activo": "true"}})
    assert result["exito"] and result["id_operacion"] == "listarClientes" and result["cuerpo"]["ruta"] == "/v1/clientes"
    assert api.requests[-1].url.params["activo"] == "true" and "set-cookie" not in result["encabezados"]
    assert service.call("ana", integration, "gio", {"metodo": "GET", "ruta": "/clientes/7"})["id_operacion"] == "get_clientes_id"
    for data, error in (({"metodo": "GET", "ruta": "/admin"}, InvalidInputError), ({"id_operacion": "crearCliente"}, InvalidInputError),
                        ({"id_operacion": "noExiste"}, NotFoundError), ({"ruta": "/clientes", "cuerpo": {"a": 1}}, InvalidInputError),
                        ({"ruta": "/clientes", "encabezados": {"Host": "evil"}}, InvalidInputError),
                        ({"ruta": "/clientes", "parametros": {"x": 1}}, InvalidInputError)):
        with pytest.raises(error):
            service.call("ana", integration, "gio", data)
    calls = service.list_calls("gio", integration)
    assert calls["total"] == 2 and "cuerpo" not in calls["llamadas"][0]

    yaml_import = service.import_spec("ana", create(service, "legado")["id_integracion"], "gio", {"contenido": SWAGGER_YAML})
    assert yaml_import["formato"] == "swagger 2.0"
    api.queue("/openapi.json", httpx.Response(200, json=SPEC))
    remote = service.import_spec("ana", integration, "gio", {"url": "https://api.example.com/openapi.json"})
    assert remote["titulo"] == "Clientes"
    with pytest.raises(InvalidInputError, match="exactamente una fuente"):
        service.import_spec("ana", integration, "gio", {"especificacion": SPEC, "contenido": SWAGGER_YAML})
    with pytest.raises(NotFoundError):
        service.call("ana", integration, "otra_empresa", {"ruta": "/clientes"})


def test_retries_only_for_idempotent_methods_or_with_idempotency_key(synapse, api):
    service, _ = synapse
    integration = create(service)["id_integracion"]
    api.queue("/v1/inestable", 503, 200)
    assert service.call("ana", integration, "gio", {"ruta": "/inestable"})["intentos"] == 2
    api.queue("/v1/inestable", 503, 200)
    post = service.call("ana", integration, "gio", {"metodo": "POST", "ruta": "/inestable", "cuerpo": {"a": 1}})
    assert post["intentos"] == 1 and post["codigo_http"] == 503 and not post["exito"]
    api.queue("/v1/inestable", 503, 200)
    keyed = service.call("ana", integration, "gio", {"metodo": "POST", "ruta": "/inestable", "cuerpo": {"a": 1},
                                                     "clave_idempotencia": "pedido-0001"})
    assert keyed["intentos"] == 2 and keyed["exito"] and api.requests[-1].headers["Idempotency-Key"] == "pedido-0001"
    with pytest.raises(InvalidInputError, match="clave_idempotencia"):
        service.call("ana", integration, "gio", {"metodo": "POST", "ruta": "/x", "clave_idempotencia": "corta"})
    api.queue("/v1/lento", httpx.ConnectTimeout("lento"))
    slow = service.call("ana", integration, "gio", {"ruta": "/lento"})
    assert slow["codigo_http"] is None and slow["intentos"] == 3 and slow["error"] == "tiempo de espera agotado"


def test_circuit_breaker_and_rate_limit(synapse, api):
    service, tick = synapse
    integration = create(service, reintentos=0)["id_integracion"]
    api.queue("/v1/caido", 500)
    for _ in range(2):
        assert service.call("ana", integration, "gio", {"ruta": "/caido"})["codigo_http"] == 500
    with pytest.raises(RateLimitedError, match="Circuito abierto") as error:
        service.call("ana", integration, "gio", {"ruta": "/ok"})
    assert error.value.retry_after_seconds == 30
    assert service.get_integration(integration, "gio")["circuito"]["estado"] == "abierto"
    tick.now += 31
    assert service.get_integration(integration, "gio")["circuito"]["estado"] == "semiabierto"
    assert service.call("ana", integration, "gio", {"ruta": "/ok"})["exito"]
    assert service.get_integration(integration, "gio")["circuito"] == {"estado": "cerrado", "fallos_consecutivos": 0}

    breaker = CircuitBreaker(1, 10, clock=tick)
    breaker.record("k", True)
    tick.now += 11
    assert breaker.retry_after("k") is None and breaker.retry_after("k") == 1
    breaker.record("k", True)
    assert breaker.snapshot("k")["estado"] == "abierto"

    limited = create(service, "limitada", limite_por_minuto=2)["id_integracion"]
    for _ in range(2):
        service.call("ana", limited, "gio", {"ruta": "/ok"})
    with pytest.raises(RateLimitedError, match="límite de 2") as error:
        service.call("ana", limited, "gio", {"ruta": "/ok"})
    assert error.value.retry_after_seconds == 60
    tick.now += 61
    assert service.call("ana", limited, "gio", {"ruta": "/ok"})["exito"]


def test_truncation_redirects_health_checks_and_metrics(api):
    service, _ = make_service(api, max_bytes=100, max_integrations=3)
    integration = create(service, reintentos=0)["id_integracion"]
    api.queue("/v1/grande", httpx.Response(200, text="x" * 500))
    big = service.call("ana", integration, "gio", {"ruta": "/grande"})
    assert big["truncado"] and len(big["cuerpo"]) == 100
    api.queue("/v1/redir", httpx.Response(302, headers={"Location": "https://interno.local/"}))
    before = len(api.requests)
    redirect = service.call("ana", integration, "gio", {"ruta": "/redir"})
    assert redirect["codigo_http"] == 302 and not redirect["exito"] and len(api.requests) == before + 1
    assert redirect["encabezados"]["location"] == "https://interno.local/"

    assert service.test_connection("ana", integration, "gio")["salud"] == "saludable"
    api.queue("/v1/caido", 500)
    assert service.test_connection("ana", integration, "gio", "/caido")["salud"] == "caida"
    api.queue("/v1/nf", 404)
    assert service.test_connection("ana", integration, "gio", "/nf", "HEAD")["salud"] == "degradada"
    assert service.get_integration(integration, "gio")["salud"] == "degradada"
    with pytest.raises(InvalidInputError):
        service.test_connection("ana", integration, "gio", "/", "POST")

    metrics = service.metrics("gio")
    assert metrics["llamadas"] == 5 and metrics["tasa_exito"] == 40.0
    assert metrics["por_integracion"][0]["nombre"] == "clientes" and metrics["por_integracion"][0]["latencia_p50_ms"] is not None

    with pytest.raises(ConflictError, match="versión actual"):
        service.update_integration(integration, "gio", {"version": 7, "descripcion": "x"})
    service.update_integration(integration, "gio", {"estado": "inactiva"})
    with pytest.raises(ConflictError, match="inactiva"):
        service.call("ana", integration, "gio", {"ruta": "/ok"})
    create(service, "otra")
    with pytest.raises(ConflictError, match="Ya existe"):
        create(service, "otra")
    create(service, "tercera")
    with pytest.raises(ConflictError, match="máximo"):
        create(service, "cuarta")
    assert service.delete_integration(integration, "gio")["eliminada"]
    with pytest.raises(NotFoundError):
        service.delete_integration(integration, "gio")


@pytest.fixture
def client(synapse):
    client, repo, _ = build_api([synapse_routes.router], [("integraciones", "ver"), ("integraciones", "gestionar"),
                                                          ("integraciones", "invocar")])
    set_synapse_service(synapse[0])
    yield client, repo
    set_synapse_service(None)
    set_security_service(None)


def test_api_permissions_errors_and_audit(client):
    client, repo = client
    health = client.get("/api/v1/synapse/salud").json()
    assert health["estado"] == "activo" and health["cifrado"] == "configurado"
    assert client.get("/api/v1/synapse/integraciones").status_code == 401
    assert client.get("/api/v1/synapse/integraciones", headers=headers(client, "luis")).status_code == 403
    auth = headers(client)
    assert client.get("/api/v1/synapse/info", headers=auth).json()["esquemas_permitidos"] == ["https"]
    body = {"nombre": "clientes", "url_base": "https://api.example.com/v1", "tipo_auth": "bearer", "credenciales": {"token": TOKEN},
            "limite_por_minuto": 2}
    created = client.post("/api/v1/synapse/integraciones", json=body, headers=auth)
    assert created.status_code == 201 and TOKEN not in created.text
    integration = created.json()["integracion"]["id_integracion"]
    assert client.post("/api/v1/synapse/integraciones", json={**body, "nombre": "interno", "url_base": "https://interno.local"},
                       headers=auth).status_code == 400
    assert client.post("/api/v1/synapse/integraciones", json=body, headers=auth).status_code == 409

    spec = client.post(f"/api/v1/synapse/integraciones/{integration}/especificacion", json={"especificacion": SPEC}, headers=auth)
    assert spec.status_code == 200 and spec.json()["operaciones"] == 4
    assert client.get(f"/api/v1/synapse/integraciones/{integration}/operaciones", headers=auth).json()["total"] == 4
    call = client.post(f"/api/v1/synapse/integraciones/{integration}/llamar", json={"id_operacion": "listarClientes"}, headers=auth)
    assert call.status_code == 200 and call.json()["exito"]
    assert client.post(f"/api/v1/synapse/integraciones/{integration}/probar", json={}, headers=auth).json()["salud"] == "saludable"
    limited = client.post(f"/api/v1/synapse/integraciones/{integration}/llamar", json={"ruta": "/clientes"}, headers=auth)
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
    assert client.get("/api/v1/synapse/llamadas", headers=auth).json()["total"] == 2
    assert client.get("/api/v1/synapse/metricas", headers=auth).json()["llamadas"] == 2

    stale = client.put(f"/api/v1/synapse/integraciones/{integration}", json={"version": 9, "descripcion": "x"}, headers=auth)
    assert stale.status_code == 409
    current = client.get(f"/api/v1/synapse/integraciones/{integration}", headers=auth).json()["integracion"]["version"]
    assert client.put(f"/api/v1/synapse/integraciones/{integration}", json={"version": current, "descripcion": "x"},
                      headers=auth).status_code == 200
    assert client.delete(f"/api/v1/synapse/integraciones/{integration}", headers=auth).json()["eliminada"]
    assert client.get(f"/api/v1/synapse/integraciones/{integration}", headers=auth).status_code == 404

    _, entries = repo.list_audit("gio", None, None, None, None, None, 50, 0)
    actions = {e.accion for e in entries}
    assert {"synapse_integracion_crear", "synapse_especificacion_importar", "synapse_integracion_actualizar",
            "synapse_integracion_eliminar"} <= actions
    assert all(TOKEN not in (e.detalles or "") for e in entries)
