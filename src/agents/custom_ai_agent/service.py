"""
Casos de uso de Genesis: agentes de IA personalizados por empresa, generación de código/SQL/documentos revisada
por Vector (y commiteable en una rama vía Vector), cascada de modelos Anthropic/OpenAI y presupuesto mensual de tokens.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.agents.common import iso, new_id, utcnow
from src.agents.custom_ai_agent import review
from src.agents.custom_ai_agent.cascade import LEVELS, PROVIDERS, TIERS, ModelCatalog, complexity_tier
from src.agents.custom_ai_agent.providers import Completion, LLMProvider, ProviderError
from src.agents.custom_ai_agent.repository import CustomAgent, Generation, GenesisRepository, Invocation
from src.agents.development_agent import analyzer
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError, RateLimitedError

logger = logging.getLogger(__name__)

VERSION = "2.0.0"
AGENT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 _.-]{1,59}$")
LANGUAGES = {"codigo": ("python", "typescript", "javascript"), "sql": ("sql",), "documento": ("markdown",)}
EXTENSIONS = {"python": ".py", "typescript": ".ts", "javascript": ".js", "sql": ".sql", "markdown": ".md"}
DEFAULT_DIRS = {"python": "src/genesis", "typescript": "src/genesis", "javascript": "src/genesis", "sql": "sql/genesis",
                "markdown": "docs/genesis"}
SUGGESTED_PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,199}$")
MAX_PROMPT = 20_000
MAX_SYSTEM = 10_000
MAX_STORED = 20_000
BUDGET_ALERT = 0.8

_GENERATION_RULES = {
    "codigo": "Escribe código {lenguaje} listo para producción: tipado, funciones pequeñas, manejo explícito de errores y docstrings. "
              "Nunca incluyas credenciales; léelas de variables de entorno. Nada de eval/exec ni comandos de shell.",
    "sql": "Escribe T-SQL para SQL Server: idempotente (IF OBJECT_ID ... IS NULL), PK CLUSTERED, claves foráneas, consultas "
           "parametrizadas, sin DROP/TRUNCATE ni SQL dinámico concatenado. Comentarios con el formato --| DESCRIPCIÓN |.",
    "documento": "Escribe documentación en Markdown clara y concisa; los diagramas van en bloques Mermaid.",
}


class GenerationFailed(Exception):
    """Ningún proveedor pudo completar la solicitud."""


def month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month(now: datetime) -> datetime:
    start = month_start(now)
    return start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)


def agent_view(a: CustomAgent) -> Dict[str, Any]:
    return {"id_agente": a.id_agente, "nombre": a.nombre, "descripcion": a.descripcion, "prompt_sistema": a.prompt_sistema,
            "proveedor": a.proveedor, "nivel": a.nivel, "temperatura": a.temperatura, "max_tokens": a.max_tokens, "estado": a.estado,
            "version": a.version, "creado_por": a.creado_por, "fecha_creacion": iso(a.fecha_creacion),
            "fecha_modificacion": iso(a.fecha_modificacion)}


def invocation_view(i: Invocation, content: bool = False) -> Dict[str, Any]:
    view = {"id_invocacion": i.id_invocacion, "tipo": i.tipo, "id_agente": i.id_agente, "proveedor": i.proveedor, "modelo": i.modelo,
            "nivel": i.nivel, "tokens_entrada": i.tokens_entrada, "tokens_salida": i.tokens_salida, "costo_usd": i.costo_usd,
            "duracion_ms": i.duracion_ms, "estado": i.estado, "error": i.error, "usuario": i.usuario, "fecha": iso(i.fecha)}
    if content:
        view.update(prompt=i.prompt, respuesta=i.respuesta)
    return view


def generation_view(g: Generation, content: bool = True) -> Dict[str, Any]:
    view = {"id_generacion": g.id_generacion, "id_invocacion": g.id_invocacion, "tipo": g.tipo, "lenguaje": g.lenguaje,
            "descripcion": g.descripcion, "ruta_sugerida": g.ruta_sugerida, "puntuacion": g.puntuacion, "criticos": g.criticos,
            "estado": g.estado, "rama": g.rama, "commit": g.commit_git, "usuario": g.usuario, "fecha": iso(g.fecha)}
    if content:
        view.update(contenido=g.contenido, analisis=g.analisis)
    return view


def _slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower().translate(str.maketrans("áéíóúñü", "aeiounu")))
    return "_".join(words[:6])[:60] or "generado"


class GenesisService:
    def __init__(self, repository: GenesisRepository, providers: Dict[str, LLMProvider], catalog: ModelCatalog,
                 vector: Callable[[], Any], clock: Callable[[], datetime] = utcnow, default_budget: int = 2_000_000,
                 store_content: bool = True) -> None:
        self._repo = repository
        self._providers = providers
        self.catalog = catalog
        self._vector = vector
        self._clock = clock
        self.default_budget = default_budget
        self.store_content = store_content

    def ping(self) -> None:
        self._repo.ping()

    def providers_status(self) -> Dict[str, bool]:
        return {name: name in self._providers and self._providers[name].configured for name in PROVIDERS}

    # ================================================================ agentes

    def _agent_fields(self, data: Dict[str, Any], current: Optional[CustomAgent]) -> Dict[str, Any]:
        def pick(key: str, default: Any) -> Any:
            return data[key] if data.get(key) is not None else (getattr(current, key) if current else default)

        nombre = str(pick("nombre", "")).strip()
        if not AGENT_NAME.match(nombre):
            raise InvalidInputError("nombre: 2 a 60 caracteres, empieza con letra")
        prompt = str(pick("prompt_sistema", "")).strip()
        if not 10 <= len(prompt) <= MAX_SYSTEM:
            raise InvalidInputError(f"prompt_sistema: entre 10 y {MAX_SYSTEM} caracteres")
        descripcion = str(pick("descripcion", "")).strip()
        if len(descripcion) > 500:
            raise InvalidInputError("descripcion: máximo 500 caracteres")
        proveedor = pick("proveedor", "auto")
        if proveedor not in ("auto", *PROVIDERS):
            raise InvalidInputError(f"proveedor debe ser auto, {', '.join(PROVIDERS)}")
        nivel = pick("nivel", "auto")
        if nivel not in LEVELS:
            raise InvalidInputError(f"nivel debe ser {', '.join(LEVELS)}")
        temperatura = data["temperatura"] if "temperatura" in data else (current.temperatura if current else None)
        if temperatura is not None and (isinstance(temperatura, bool) or not 0 <= float(temperatura) <= 1):
            raise InvalidInputError("temperatura debe estar entre 0 y 1 (o null para el valor del modelo)")
        max_tokens = pick("max_tokens", 1024)
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 64 <= max_tokens <= 8192:
            raise InvalidInputError("max_tokens debe estar entre 64 y 8192")
        return {"nombre": nombre, "prompt_sistema": prompt, "descripcion": descripcion, "proveedor": proveedor, "nivel": nivel,
                "temperatura": float(temperatura) if temperatura is not None else None, "max_tokens": max_tokens}

    def create_agent(self, actor: str, id_empresa: str, data: Dict[str, Any]) -> Dict[str, Any]:
        now = self._clock()
        agent = CustomAgent(id_agente=new_id("gen"), id_empresa=id_empresa, fecha_creacion=now, fecha_modificacion=now, creado_por=actor,
                            **self._agent_fields(data, None))
        if not self._repo.create_agent(agent):
            raise ConflictError(f"Ya existe un agente llamado {agent.nombre}")
        return agent_view(agent)

    def list_agents(self, id_empresa: str, incluir_archivados: bool = False) -> Dict[str, Any]:
        items = self._repo.list_agents(id_empresa, incluir_archivados)
        return {"total": len(items), "agentes": [agent_view(a) for a in items]}

    def _agent(self, id_agente: str, id_empresa: str) -> CustomAgent:
        agent = self._repo.get_agent(id_agente, id_empresa)
        if agent is None:
            raise NotFoundError(f"Agente no encontrado: {id_agente}")
        return agent

    def get_agent(self, id_agente: str, id_empresa: str) -> Dict[str, Any]:
        return agent_view(self._agent(id_agente, id_empresa))

    def _save_agent(self, current: CustomAgent, updated: CustomAgent) -> Dict[str, Any]:
        if not self._repo.update_agent(updated, current.version):
            raise ConflictError("El agente cambió o el nombre ya está en uso; vuelve a leerlo")
        return agent_view(replace(updated, version=current.version + 1))

    def update_agent(self, id_agente: str, id_empresa: str, data: Dict[str, Any]) -> Dict[str, Any]:
        current = self._agent(id_agente, id_empresa)
        if data.get("version") is not None and data["version"] != current.version:
            raise ConflictError(f"El agente cambió (versión actual {current.version}); vuelve a leerlo")
        estado = data.get("estado") or current.estado
        if estado not in ("activo", "archivado"):
            raise InvalidInputError("estado debe ser activo o archivado")
        return self._save_agent(current, replace(current, estado=estado, fecha_modificacion=self._clock(), **self._agent_fields(data, current)))

    def archive_agent(self, id_agente: str, id_empresa: str) -> Dict[str, Any]:
        current = self._agent(id_agente, id_empresa)
        if current.estado == "archivado":
            raise ConflictError("El agente ya está archivado")
        return self._save_agent(current, replace(current, estado="archivado", fecha_modificacion=self._clock()))

    # ================================================================ presupuesto

    def usage(self, id_empresa: str) -> Dict[str, Any]:
        now = self._clock()
        rows = self._repo.usage(id_empresa, month_start(now))
        limit = self._repo.get_budget(id_empresa) or self.default_budget
        used = sum(r["tokens_entrada"] + r["tokens_salida"] for r in rows)
        ratio = used / limit if limit else 1.0
        per_model: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
        for r in rows:
            empty = {"proveedor": r["proveedor"], "modelo": r["modelo"], "invocaciones": 0, "errores": 0, "tokens": 0, "costo_usd": 0.0}
            row = per_model.setdefault((r["proveedor"], r["modelo"]), empty)
            row["invocaciones"] += r["invocaciones"]
            row["errores"] += r["invocaciones"] if r["estado"] != "exito" else 0
            row["tokens"] += r["tokens_entrada"] + r["tokens_salida"]
            row["costo_usd"] = round(row["costo_usd"] + r["costo_usd"], 6)
        return {"mes": month_start(now).strftime("%Y-%m"), "presupuesto_tokens": limit, "tokens_usados": used,
                "porcentaje_usado": round(100 * ratio, 2), "alerta": ratio >= BUDGET_ALERT, "agotado": used >= limit,
                "costo_estimado_usd": round(sum(r["costo_usd"] for r in rows), 6), "reinicia": iso(next_month(now)),
                "por_modelo": sorted((r for r in per_model.values() if r["modelo"]), key=lambda r: -r["tokens"])}

    def set_budget(self, actor: str, id_empresa: str, tokens: int) -> Dict[str, Any]:
        if isinstance(tokens, bool) or not isinstance(tokens, int) or not 1_000 <= tokens <= 1_000_000_000:
            raise InvalidInputError("tokens_mensuales debe estar entre 1.000 y 1.000.000.000")
        self._repo.set_budget(id_empresa, tokens, actor, self._clock())
        return self.usage(id_empresa)

    # ================================================================ invocación con cascada

    def _record(self, actor: str, id_empresa: str, tipo: str, estado: str, **fields: Any) -> Invocation:
        invocation = Invocation(id_invocacion=new_id("inv"), id_empresa=id_empresa, tipo=tipo, estado=estado, usuario=actor,
                                fecha=self._clock(), **fields)
        self._repo.record_invocation(invocation)
        return invocation

    def _complete(self, actor: str, id_empresa: str, *, tipo: str, complejidad: str, system: str, prompt: str, nivel: str,
                  proveedor: str, max_tokens: int, temperature: Optional[float], id_agente: Optional[str] = None
                  ) -> Tuple[Completion, Invocation, int]:
        if not prompt.strip() or len(prompt) > MAX_PROMPT:
            raise InvalidInputError(f"El prompt es obligatorio (máx. {MAX_PROMPT} caracteres)")
        clean, redacted = review.redact(prompt)
        tier = nivel if nivel in TIERS else complexity_tier(complejidad, clean)
        available = [name for name, ready in self.providers_status().items() if ready]
        if proveedor in PROVIDERS and proveedor not in available:
            raise ConflictError(f"El proveedor {proveedor} no está configurado (define {proveedor.upper()}_API_KEY)")
        candidates = self.catalog.candidates(tier, proveedor if proveedor in PROVIDERS else None, available)
        if not candidates:
            raise ConflictError("Genesis no tiene proveedores configurados: define ANTHROPIC_API_KEY u OPENAI_API_KEY")
        stored_prompt = clean[:MAX_STORED] if self.store_content else None
        status = self.usage(id_empresa)
        estimate = (len(system) + len(clean)) // 4 + max_tokens
        if status["tokens_usados"] + estimate > status["presupuesto_tokens"]:
            self._record(actor, id_empresa, tipo, "rechazada", id_agente=id_agente, nivel=tier, prompt=stored_prompt,
                         error=f"presupuesto mensual agotado ({status['tokens_usados']}/{status['presupuesto_tokens']} tokens)")
            wait = int((next_month(self._clock()) - self._clock()).total_seconds())
            raise RateLimitedError(f"Presupuesto mensual de tokens agotado ({status['tokens_usados']:,} de {status['presupuesto_tokens']:,}); "
                                   "se reinicia el próximo mes o un administrador puede ampliarlo", max(1, wait))
        errors: List[str] = []
        for choice in candidates:
            try:
                completion = self._providers[choice.proveedor].complete(choice.modelo, system, [{"role": "user", "content": clean}],
                                                                        max_tokens, temperature)
            except ProviderError as e:
                logger.warning("Genesis: %s/%s falló: %s", choice.proveedor, choice.modelo, e)
                errors.append(str(e))
                continue
            invocation = self._record(
                actor, id_empresa, tipo, "exito", id_agente=id_agente, proveedor=completion.proveedor, modelo=completion.modelo, nivel=tier,
                tokens_entrada=completion.tokens_entrada, tokens_salida=completion.tokens_salida,
                costo_usd=self.catalog.cost(choice.modelo, completion.tokens_entrada, completion.tokens_salida),
                duracion_ms=completion.duracion_ms, prompt=stored_prompt,
                respuesta=completion.texto[:MAX_STORED] if self.store_content else None,
            )
            return completion, invocation, redacted
        message = "; ".join(errors)[:1000]
        self._record(actor, id_empresa, tipo, "error", id_agente=id_agente, proveedor=candidates[-1].proveedor,
                     modelo=candidates[-1].modelo, nivel=tier, prompt=stored_prompt, error=message)
        raise GenerationFailed(f"Ningún proveedor pudo responder: {message}")

    def _result(self, completion: Completion, invocation: Invocation, redacted: int, id_empresa: str) -> Dict[str, Any]:
        usage = self.usage(id_empresa)
        budget = {k: usage[k] for k in ("tokens_usados", "presupuesto_tokens", "porcentaje_usado", "alerta")}
        return {"id_invocacion": invocation.id_invocacion, "proveedor": completion.proveedor, "modelo": completion.modelo,
                "nivel": invocation.nivel, "tokens_entrada": completion.tokens_entrada, "tokens_salida": completion.tokens_salida,
                "costo_usd": invocation.costo_usd, "duracion_ms": completion.duracion_ms, "motivo_fin": completion.motivo_fin,
                "datos_redactados": redacted, "presupuesto": budget}

    def invoke_agent(self, actor: str, id_empresa: str, id_agente: str, prompt: str, contexto: Optional[str] = None) -> Dict[str, Any]:
        agent = self._agent(id_agente, id_empresa)
        if agent.estado != "activo":
            raise ConflictError(f"El agente {agent.nombre} está archivado")
        message = prompt if not contexto else f"{prompt}\n\nContexto:\n{contexto}"
        completion, invocation, redacted = self._complete(
            actor, id_empresa, tipo="agente", complejidad="agente", system=agent.prompt_sistema, prompt=message, nivel=agent.nivel,
            proveedor=agent.proveedor, max_tokens=agent.max_tokens, temperature=agent.temperatura, id_agente=agent.id_agente)
        return {"agente": agent.nombre, "respuesta": completion.texto, **self._result(completion, invocation, redacted, id_empresa)}

    def list_invocations(self, id_empresa: str, id_agente: Optional[str] = None, limite: int = 50,
                         con_contenido: bool = False) -> Dict[str, Any]:
        items = self._repo.invocations(id_empresa, id_agente, max(1, min(limite, 200)))
        return {"total": len(items), "invocaciones": [invocation_view(i, con_contenido) for i in items]}

    # ================================================================ generación de código

    def _review(self, actor: str, content: str, lenguaje: str, path: str) -> Dict[str, Any]:
        if lenguaje != "python":
            return review.review_text(content, lenguaje, path)
        name = path.rsplit("/", 1)[-1]
        try:
            result = self._vector().analyze_code(actor, content, name)
        except Exception as e:
            logger.info("Genesis: análisis sin historial de Vector (%s)", type(e).__name__)
            result = analyzer.analyze_files({name: content})
        return {k: result.get(k) for k in ("id_analisis", "puntuacion", "por_severidad", "total_hallazgos", "hallazgos")}

    def generate(self, actor: str, id_empresa: str, data: Dict[str, Any]) -> Dict[str, Any]:
        tipo = data.get("tipo") or "codigo"
        if tipo not in LANGUAGES:
            raise InvalidInputError(f"tipo debe ser {', '.join(LANGUAGES)}")
        lenguaje = data.get("lenguaje") or LANGUAGES[tipo][0]
        if lenguaje not in LANGUAGES[tipo]:
            raise InvalidInputError(f"lenguaje para {tipo}: {', '.join(LANGUAGES[tipo])}")
        descripcion = str(data.get("descripcion") or "").strip()
        if not 10 <= len(descripcion) <= MAX_PROMPT:
            raise InvalidInputError(f"descripcion: entre 10 y {MAX_PROMPT} caracteres")
        path = str(data.get("ruta_sugerida") or f"{DEFAULT_DIRS[lenguaje]}/{_slug(descripcion)}{EXTENSIONS[lenguaje]}")
        if not SUGGESTED_PATH.match(path) or ".." in path.split("/") or not path.endswith(EXTENSIONS[lenguaje]):
            raise InvalidInputError(f"ruta_sugerida: ruta relativa que termine en {EXTENSIONS[lenguaje]}, sin '..'")
        nivel, proveedor = data.get("nivel") or "auto", data.get("proveedor") or "auto"
        if nivel not in LEVELS or proveedor not in ("auto", *PROVIDERS):
            raise InvalidInputError(f"nivel: {', '.join(LEVELS)} · proveedor: auto, {', '.join(PROVIDERS)}")
        system = ("Eres Genesis, el generador de Kinetix Studio. " + _GENERATION_RULES[tipo].format(lenguaje=lenguaje)
                  + f" Responde únicamente con un bloque de código ```{lenguaje}``` para el archivo {path}, sin texto adicional.")
        completion, invocation, redacted = self._complete(
            actor, id_empresa, tipo="generacion", complejidad=tipo, system=system, prompt=descripcion, nivel=nivel, proveedor=proveedor,
            max_tokens=int(data.get("max_tokens") or 4096), temperature=None)
        content = review.extract_code(completion.texto, lenguaje)
        if not content:
            raise GenerationFailed("El modelo no devolvió contenido")
        analysis = self._review(actor, content, lenguaje, path)
        criticals = (analysis.get("por_severidad") or {}).get("critica", 0)
        generation = Generation(id_generacion=new_id("gnr"), id_empresa=id_empresa, id_invocacion=invocation.id_invocacion, tipo=tipo,
                                lenguaje=lenguaje, descripcion=descripcion[:2000], ruta_sugerida=path, contenido=content, usuario=actor,
                                fecha=self._clock(), analisis=analysis, puntuacion=analysis.get("puntuacion"), criticos=criticals)
        self._repo.save_generation(generation)
        return {"generacion": generation_view(generation), "commiteable": criticals == 0,
                **self._result(completion, invocation, redacted, id_empresa)}

    def list_generations(self, id_empresa: str, limite: int = 50) -> Dict[str, Any]:
        items = self._repo.list_generations(id_empresa, max(1, min(limite, 200)))
        return {"total": len(items), "generaciones": [generation_view(g, content=False) for g in items]}

    def _generation(self, id_generacion: str, id_empresa: str) -> Generation:
        generation = self._repo.get_generation(id_generacion, id_empresa)
        if generation is None:
            raise NotFoundError(f"Generación no encontrada: {id_generacion}")
        return generation

    def get_generation(self, id_generacion: str, id_empresa: str) -> Dict[str, Any]:
        return generation_view(self._generation(id_generacion, id_empresa))

    def commit_generation(self, actor: str, id_empresa: str, id_generacion: str, rama: str, ruta: Optional[str] = None,
                          mensaje: Optional[str] = None, base: str = "HEAD") -> Dict[str, Any]:
        generation = self._generation(id_generacion, id_empresa)
        if generation.estado != "generada":
            raise ConflictError(f"La generación ya fue commiteada en {generation.rama} ({generation.commit_git})")
        if generation.criticos:
            raise ConflictError(f"La generación tiene {generation.criticos} hallazgos críticos; corrígela o genera una nueva versión")
        path = ruta or generation.ruta_sugerida
        if not path.endswith(EXTENSIONS[generation.lenguaje]):
            raise InvalidInputError(f"ruta debe terminar en {EXTENSIONS[generation.lenguaje]}")
        message = mensaje or f"Genesis: {generation.descripcion[:120]}"
        content = generation.contenido if generation.contenido.endswith("\n") else generation.contenido + "\n"
        result = self._vector().commit_files(actor, rama, {path: content}, message, base)
        if not self._repo.mark_committed(id_generacion, id_empresa, result["rama"], result["commit"]):
            raise ConflictError("La generación fue commiteada por otra solicitud al mismo tiempo")
        return {"id_generacion": id_generacion, "ruta": path, **result}
