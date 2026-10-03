"""Genesis (CustomAIAgent): proveedores, cascada, redacción, presupuesto, agentes, generación revisada por Vector y API."""

import json
from datetime import datetime, timedelta

import httpx
import pytest

from src.agents.custom_ai_agent import review
from src.agents.custom_ai_agent.cascade import ModelCatalog, catalog_from_env, complexity_tier
from src.agents.custom_ai_agent.dependencies import set_genesis_service
from src.agents.custom_ai_agent.providers import AnthropicProvider, OpenAIProvider, ProviderError
from src.agents.custom_ai_agent.repository import InMemoryGenesisRepository
from src.agents.custom_ai_agent.service import GenerationFailed, GenesisService
from src.agents.development_agent.repository import InMemoryAnalysisRepository
from src.agents.development_agent.service import VectorService
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError, RateLimitedError
from src.api.routes import genesis_routes
from tests.unit.agent_api import build_api, git, headers, init_repo

CODE = 'Aquí está:\n```python\ndef doble(x: int) -> int:\n    """Duplica."""\n    return x * 2\n```\n'
AGENT = {"nombre": "Soporte", "prompt_sistema": "Eres un asistente de soporte técnico.", "temperatura": 0.3}


class StepClock:
    def __init__(self):
        self.now = datetime(2026, 10, 3, 12, 0, 0)

    def __call__(self):
        self.now += timedelta(seconds=1)
        return self.now


class FakeLLM:
    """Respuestas encoladas por proveedor: texto, código de estado HTTP o excepción de httpx."""

    def __init__(self):
        self.requests = []
        self.queues = {"anthropic": [], "openai": []}
        self.usage = (100, 50)

    def _next(self, provider, request):
        payload = json.loads(request.content)
        self.requests.append((provider, request, payload))
        queue = self.queues[provider]
        item = queue.pop(0) if queue else f"respuesta de {provider}"
        if isinstance(item, Exception):
            raise item
        if isinstance(item, int):
            return payload, httpx.Response(item, json={"error": {"type": "error", "message": "sobrecargado"}})
        return payload, item

    def anthropic(self, request):
        payload, item = self._next("anthropic", request)
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, json={"model": payload["model"], "content": [{"type": "text", "text": item}],
                                         "usage": {"input_tokens": self.usage[0], "output_tokens": self.usage[1]}, "stop_reason": "end_turn"})

    def openai(self, request):
        payload, item = self._next("openai", request)
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, json={"model": payload["model"], "choices": [{"message": {"content": item}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": self.usage[0], "completion_tokens": self.usage[1]}})

    def providers(self, keys=("anthropic", "openai")):
        return {
            "anthropic": AnthropicProvider("ak-prueba" if "anthropic" in keys else None, transport=httpx.MockTransport(self.anthropic)),
            "openai": OpenAIProvider("ok-prueba" if "openai" in keys else None, transport=httpx.MockTransport(self.openai)),
        }


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def vector(tmp_path):
    return VectorService(init_repo(tmp_path / "repo"), InMemoryAnalysisRepository()), tmp_path / "repo"


def make(llm, vector=None, keys=("anthropic", "openai"), budget=2_000_000, clock=None):
    return GenesisService(InMemoryGenesisRepository(), llm.providers(keys), ModelCatalog(), lambda: vector, clock=clock or StepClock(),
                          default_budget=budget)


def test_providers_send_expected_payloads_and_map_errors(llm):
    providers = llm.providers()
    completion = providers["anthropic"].complete("claude-haiku-4-5", "sistema", [{"role": "user", "content": "hola"}], 100, 0.2)
    assert (completion.texto, completion.tokens_entrada, completion.tokens_salida, completion.motivo_fin) == \
        ("respuesta de anthropic", 100, 50, "end_turn")
    _, request, payload = llm.requests[-1]
    assert request.url.path == "/v1/messages" and request.headers["x-api-key"] == "ak-prueba"
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert payload["system"] == "sistema" and payload["temperature"] == 0.2 and payload["max_tokens"] == 100

    completion = providers["openai"].complete("gpt-4o-mini", "sistema", [{"role": "user", "content": "hola"}], 100)
    assert completion.proveedor == "openai" and completion.tokens_entrada == 100 and completion.motivo_fin == "stop"
    _, request, payload = llm.requests[-1]
    assert request.url.path == "/v1/chat/completions" and request.headers["Authorization"] == "Bearer ok-prueba"
    assert "temperature" not in payload and payload["max_completion_tokens"] == 100
    assert payload["messages"][0] == {"role": "system", "content": "sistema"}

    llm.queues["anthropic"] = [529, 400, httpx.ReadTimeout("lento")]
    for retryable, status, message in ((True, 529, "sobrecargado"), (False, 400, "400"), (True, None, "tiempo de espera")):
        with pytest.raises(ProviderError, match=message) as error:
            providers["anthropic"].complete("m", "s", [], 10)
        assert error.value.retryable is retryable and error.value.status_code == status
    unconfigured = llm.providers(keys=())["openai"]
    assert not unconfigured.configured
    with pytest.raises(ProviderError, match="no está configurado"):
        unconfigured.complete("m", "s", [], 10)


def test_cascade_tiers_catalog_and_env(monkeypatch):
    assert complexity_tier("agente", "hola") == "economico"
    assert complexity_tier("codigo", "x" * 700) == "premium"
    assert complexity_tier("documento", "x" * 700) == "economico"
    assert complexity_tier("agente", "revisa la arquitectura del módulo") == "premium"
    catalog = ModelCatalog(preferred=["openai"])
    assert [(c.proveedor, c.modelo) for c in catalog.candidates("premium", None, ["anthropic", "openai"])] == \
        [("openai", "gpt-4o"), ("anthropic", "claude-sonnet-4-5")]
    assert [c.modelo for c in catalog.candidates("economico", "anthropic", ["openai"])] == ["gpt-4o-mini"]
    assert catalog.cost("gpt-4o", 1_000_000, 0) == 2.5 and catalog.cost("desconocido", 1, 1) is None

    monkeypatch.setenv("GENESIS_OPENAI_MODELO_PREMIUM", "gpt-x")
    monkeypatch.setenv("GENESIS_PRECIOS", '{"gpt-x": [1, 2]}')
    monkeypatch.setenv("GENESIS_PROVEEDOR_PREFERIDO", "openai")
    configured = catalog_from_env()
    assert configured.describe()["openai"]["premium"] == "gpt-x" and configured.preferred == ["openai", "anthropic"]
    assert configured.cost("gpt-x", 1_000_000, 1_000_000) == 3.0
    monkeypatch.setenv("GENESIS_PRECIOS", "no-es-json")
    with pytest.raises(ValueError, match="GENESIS_PRECIOS"):
        catalog_from_env()


def test_redaction_code_extraction_and_text_review():
    text, count = review.redact("password=Sup3rS3creta; api_key: abcdefghijklmnop1234 y Bearer abcdefghijklmnopqrstuvwxyz")
    assert count == 3 and "Sup3rS3creta" not in text and "abcdefghijklmnop1234" not in text and "qrstuvwxyz" not in text
    key, keys = review.redact("-----BEGIN RSA PRIVATE KEY-----\nAAAA\n-----END RSA PRIVATE KEY-----")
    assert keys == 1 and "AAAA" not in key
    assert review.extract_code("Mira:\n```bash\nls\n```\n```python\nx = 1\n```", "python") == "x = 1"
    assert review.extract_code("  sin bloque  ", "python") == "sin bloque"

    sql = "DELETE FROM clientes;\nUPDATE t SET a = 1 WHERE id = @id;\nDROP TABLE x;\nSELECT * FROM y"
    result = review.review_text(sql, "sql", "x.sql")
    rules = [f["regla"] for f in result["hallazgos"]]
    assert sorted(rules) == ["sql_drop", "sql_select_asterisco", "sql_sin_where"] and result["por_severidad"]["critica"] == 1
    cascade = "ALTER TABLE a ADD CONSTRAINT fk FOREIGN KEY (b) REFERENCES c(id) ON DELETE CASCADE ON UPDATE NO ACTION;"
    assert review.review_text(cascade, "sql", "x.sql")["total_hallazgos"] == 0
    assert review.review_text('const apiKey = "abcdef1234567890xyz";', "typescript", "a.ts")["por_severidad"]["critica"] == 1
    assert review.review_text("const token = process.env.API_TOKEN_VALUE;", "typescript", "a.ts")["total_hallazgos"] == 0


def test_agents_crud_invocation_redaction_and_provider_fallback(llm):
    service = make(llm)
    agent = service.create_agent("ana", "gio", AGENT)
    for data, error in (({**AGENT}, ConflictError), ({**AGENT, "nombre": "Otro", "nivel": "maximo"}, InvalidInputError),
                        ({**AGENT, "nombre": "Otro", "max_tokens": 10}, InvalidInputError),
                        ({**AGENT, "nombre": "Otro", "prompt_sistema": "corto"}, InvalidInputError)):
        with pytest.raises(error):
            service.create_agent("ana", "gio", data)

    result = service.invoke_agent("ana", "gio", agent["id_agente"], "¿Cómo reinicio el router? password=abc12345")
    assert result["respuesta"] == "respuesta de anthropic" and result["modelo"] == "claude-haiku-4-5" and result["nivel"] == "economico"
    assert result["datos_redactados"] == 1 and result["costo_usd"] == 0.00035
    _, _, payload = llm.requests[-1]
    assert "abc12345" not in payload["messages"][0]["content"] and payload["system"] == AGENT["prompt_sistema"]
    assert payload["temperature"] == 0.3

    llm.queues["anthropic"] = [503]
    assert service.invoke_agent("ana", "gio", agent["id_agente"], "hola")["proveedor"] == "openai"
    llm.queues["anthropic"], llm.queues["openai"] = [500], [500]
    with pytest.raises(GenerationFailed, match="Ningún proveedor"):
        service.invoke_agent("ana", "gio", agent["id_agente"], "hola")
    states = [i["estado"] for i in service.list_invocations("gio")["invocaciones"]]
    assert sorted(states) == ["error", "exito", "exito"]
    stored = service.list_invocations("gio", agent["id_agente"], con_contenido=True)["invocaciones"]
    assert all("abc12345" not in (i["prompt"] or "") for i in stored)

    updated = service.update_agent(agent["id_agente"], "gio", {"version": 1, "nivel": "premium", "proveedor": "openai"})
    assert updated["version"] == 2
    assert service.invoke_agent("ana", "gio", agent["id_agente"], "hola")["modelo"] == "gpt-4o"
    with pytest.raises(ConflictError, match="versión actual"):
        service.update_agent(agent["id_agente"], "gio", {"version": 1, "descripcion": "x"})
    service.archive_agent(agent["id_agente"], "gio")
    with pytest.raises(ConflictError, match="archivado"):
        service.invoke_agent("ana", "gio", agent["id_agente"], "hola")
    with pytest.raises(ConflictError):
        service.archive_agent(agent["id_agente"], "gio")
    assert service.list_agents("gio")["total"] == 0 and service.list_agents("gio", True)["total"] == 1
    with pytest.raises(NotFoundError):
        service.get_agent(agent["id_agente"], "otra_empresa")

    only_anthropic = make(llm, keys=("anthropic",))
    pinned = only_anthropic.create_agent("ana", "gio", {**AGENT, "proveedor": "openai"})
    with pytest.raises(ConflictError, match="OPENAI_API_KEY"):
        only_anthropic.invoke_agent("ana", "gio", pinned["id_agente"], "hola")
    none = make(llm, keys=())
    lonely = none.create_agent("ana", "gio", AGENT)
    with pytest.raises(ConflictError, match="no tiene proveedores"):
        none.invoke_agent("ana", "gio", lonely["id_agente"], "hola")
    assert none.providers_status() == {"anthropic": False, "openai": False}


def test_monthly_budget_alerts_rejects_and_resets(llm):
    clock = StepClock()
    service = make(llm, budget=1200, clock=clock)
    agent = service.create_agent("ana", "gio", {**AGENT, "max_tokens": 64})["id_agente"]
    llm.usage = (900, 100)
    first = service.invoke_agent("ana", "gio", agent, "hola")["presupuesto"]
    assert first["alerta"] and first["porcentaje_usado"] == 83.33
    service.invoke_agent("ana", "gio", agent, "hola")
    usage = service.usage("gio")
    assert usage["agotado"] and usage["tokens_usados"] == 2000 and usage["por_modelo"][0]["modelo"] == "claude-haiku-4-5"
    with pytest.raises(RateLimitedError, match="Presupuesto mensual") as error:
        service.invoke_agent("ana", "gio", agent, "hola")
    assert error.value.retry_after_seconds > 24 * 3600
    rejected = service.list_invocations("gio")["invocaciones"][0]
    assert rejected["estado"] == "rechazada" and rejected["modelo"] is None
    assert len(service.usage("gio")["por_modelo"]) == 1

    with pytest.raises(InvalidInputError):
        service.set_budget("ana", "gio", 500)
    assert service.set_budget("ana", "gio", 5000)["presupuesto_tokens"] == 5000
    assert service.invoke_agent("ana", "gio", agent, "hola")["presupuesto"]["tokens_usados"] == 3000
    clock.now = datetime(2026, 11, 1, 0, 0, 0)
    reset = service.usage("gio")
    assert reset["mes"] == "2026-11" and reset["tokens_usados"] == 0 and reset["presupuesto_tokens"] == 5000


def test_generation_is_reviewed_by_vector_and_committed_to_a_branch(llm, vector):
    vector_service, path = vector
    service = make(llm, vector_service)
    llm.queues["anthropic"] = [CODE]
    result = service.generate("ana", "gio", {"descripcion": "Función que duplica un número entero"})
    generation = result["generacion"]
    assert result["commiteable"] and generation["lenguaje"] == "python" and generation["contenido"].startswith("def doble")
    assert generation["ruta_sugerida"] == "src/genesis/funcion_que_duplica_un_numero_entero.py"
    assert generation["analisis"]["id_analisis"] and generation["criticos"] == 0 and result["nivel"] == "economico"
    assert "```python" in llm.requests[-1][2]["system"]

    with pytest.raises((InvalidInputError, ConflictError)):
        service.commit_generation("ana", "gio", generation["id_generacion"], "master")
    committed = service.commit_generation("ana", "gio", generation["id_generacion"], "feature/genesis-doble")
    assert committed["rama"] == "feature/genesis-doble" and committed["ruta"] == generation["ruta_sugerida"]
    assert "def doble" in git(path, "show", f"feature/genesis-doble:{generation['ruta_sugerida']}")
    assert git(path, "rev-parse", "--abbrev-ref", "HEAD") == "master"
    assert service.get_generation(generation["id_generacion"], "gio")["estado"] == "commiteada"
    with pytest.raises(ConflictError, match="ya fue commiteada"):
        service.commit_generation("ana", "gio", generation["id_generacion"], "feature/otra")

    llm.queues["anthropic"] = ["```python\nresultado = eval(entrada)\n```"]
    dangerous = service.generate("ana", "gio", {"descripcion": "Evalúa una expresión del usuario", "ruta_sugerida": "src/genesis/evalua.py"})
    assert not dangerous["commiteable"] and dangerous["generacion"]["criticos"] >= 1
    with pytest.raises(ConflictError, match="críticos"):
        service.commit_generation("ana", "gio", dangerous["generacion"]["id_generacion"], "feature/eval")

    llm.queues["anthropic"] = ["```sql\nDELETE FROM clientes;\n```", "```sql\nDROP TABLE clientes;\n```"]
    sql = service.generate("ana", "gio", {"tipo": "sql", "descripcion": "Borra los clientes inactivos"})
    assert sql["commiteable"] and sql["generacion"]["ruta_sugerida"].startswith("sql/genesis/")
    assert [f["regla"] for f in sql["generacion"]["analisis"]["hallazgos"]] == ["sql_sin_where"]
    assert not service.generate("ana", "gio", {"tipo": "sql", "descripcion": "Elimina la tabla de clientes"})["commiteable"]
    assert service.list_generations("gio")["total"] == 4 and "contenido" not in service.list_generations("gio")["generaciones"][0]

    llm.queues["anthropic"] = [""]
    with pytest.raises(GenerationFailed, match="no devolvió"):
        service.generate("ana", "gio", {"descripcion": "Una función cualquiera"})
    for data in ({"descripcion": "Una función cualquiera", "ruta_sugerida": "../fuera.py"},
                 {"descripcion": "Una función cualquiera", "ruta_sugerida": "src/x.ts"},
                 {"tipo": "sql", "lenguaje": "python", "descripcion": "Una consulta cualquiera"},
                 {"descripcion": "corta"}):
        with pytest.raises(InvalidInputError):
            service.generate("ana", "gio", data)

    def broken_vector():
        raise RuntimeError("sin repositorio")

    fallback = GenesisService(InMemoryGenesisRepository(), llm.providers(), ModelCatalog(), broken_vector, clock=StepClock())
    llm.queues["anthropic"] = [CODE]
    analysis = fallback.generate("ana", "gio", {"descripcion": "Función que duplica un número entero"})["generacion"]["analisis"]
    assert analysis["id_analisis"] is None and analysis["puntuacion"] is not None


@pytest.fixture
def api(llm, vector):
    client, repo, _ = build_api([genesis_routes.router], [("ia", "ver"), ("ia", "gestionar"), ("ia", "invocar")])
    set_genesis_service(make(llm, vector[0]))
    yield client, repo
    set_genesis_service(None)
    set_security_service(None)


def test_api_permissions_commit_permission_errors_and_audit(api, llm):
    client, repo = api
    health = client.get("/api/v1/genesis/salud").json()
    assert health["estado"] == "activo" and health["proveedores"] == {"anthropic": True, "openai": True}
    assert client.get("/api/v1/genesis/agentes").status_code == 401
    assert client.get("/api/v1/genesis/agentes", headers=headers(client, "luis")).status_code == 403
    auth = headers(client)
    assert client.get("/api/v1/genesis/info", headers=auth).json()["modelos"]["anthropic"]["premium"] == "claude-sonnet-4-5"

    created = client.post("/api/v1/genesis/agentes", json=AGENT, headers=auth)
    assert created.status_code == 201
    agent = created.json()["agente"]["id_agente"]
    assert client.put(f"/api/v1/genesis/agentes/{agent}", json={"version": 5, "descripcion": "x"}, headers=auth).status_code == 409
    assert client.put(f"/api/v1/genesis/agentes/{agent}", json={"version": 1, "descripcion": "x"}, headers=auth).status_code == 200
    invoked = client.post(f"/api/v1/genesis/agentes/{agent}/invocar", json={"prompt": "hola"}, headers=auth)
    assert invoked.status_code == 200 and invoked.json()["respuesta"] == "respuesta de anthropic"
    assert client.get("/api/v1/genesis/invocaciones", headers=auth).json()["total"] == 1

    llm.queues["anthropic"] = [CODE]
    generated = client.post("/api/v1/genesis/generaciones", json={"descripcion": "Función que duplica un número entero"}, headers=auth)
    assert generated.status_code == 201
    generation = generated.json()["generacion"]["id_generacion"]
    assert client.get("/api/v1/genesis/generaciones", headers=auth).json()["total"] == 1
    assert "def doble" in client.get(f"/api/v1/genesis/generaciones/{generation}", headers=auth).json()["generacion"]["contenido"]
    commit = {"rama": "feature/genesis-api"}
    assert client.post(f"/api/v1/genesis/generaciones/{generation}/commit", json=commit, headers=auth).status_code == 403
    repo.add_permission("p_codigo_escribir", "codigo", "escribir")
    repo.grant_permission("rol_admin", "p_codigo_escribir")
    auth = headers(client)
    committed = client.post(f"/api/v1/genesis/generaciones/{generation}/commit", json=commit, headers=auth)
    assert committed.status_code == 200 and committed.json()["rama"] == "feature/genesis-api"

    llm.queues["anthropic"], llm.queues["openai"] = [500], [500]
    assert client.post(f"/api/v1/genesis/agentes/{agent}/invocar", json={"prompt": "hola"}, headers=auth).status_code == 502
    assert client.put("/api/v1/genesis/presupuesto", json={"tokens_mensuales": 1000}, headers=auth).status_code == 200
    limited = client.post(f"/api/v1/genesis/agentes/{agent}/invocar", json={"prompt": "hola"}, headers=auth)
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
    usage = client.get("/api/v1/genesis/uso", headers=auth).json()
    assert usage["presupuesto_tokens"] == 1000 and usage["tokens_usados"] == 300
    assert client.delete(f"/api/v1/genesis/agentes/{agent}", headers=auth).json()["agente"]["estado"] == "archivado"

    _, entries = repo.list_audit("gio", None, None, None, None, None, 50, 0)
    assert {"genesis_agente_crear", "genesis_agente_actualizar", "genesis_generacion_commit", "genesis_presupuesto_actualizar",
            "genesis_agente_archivar"} <= {e.accion for e in entries}
