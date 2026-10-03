"""Proveedores de modelos de Genesis: Anthropic (Messages API) y OpenAI (Chat Completions) vía HTTP."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504, 529})


@dataclass(frozen=True)
class Completion:
    texto: str
    proveedor: str
    modelo: str
    tokens_entrada: int
    tokens_salida: int
    motivo_fin: Optional[str]
    duracion_ms: float


class ProviderError(Exception):
    def __init__(self, message: str, retryable: bool, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class LLMProvider(ABC):
    name: str = ""

    @property
    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    def complete(self, model: str, system: str, messages: List[Dict[str, str]], max_tokens: int,
                 temperature: Optional[float] = None) -> Completion: ...


class HttpProvider(LLMProvider):
    def __init__(self, api_key: Optional[str], base_url: str, timeout_seconds: float = 120,
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        self._api_key = (api_key or "").strip() or None
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def configured(self) -> bool:
        return self._api_key is not None

    def _headers(self) -> Dict[str, str]:
        raise NotImplementedError

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.configured:
            raise ProviderError(f"{self.name} no está configurado", retryable=True)
        try:
            with httpx.Client(base_url=self._base_url, timeout=self._timeout, transport=self._transport, trust_env=False) as client:
                response = client.post(path, json=payload, headers=self._headers())
        except httpx.TimeoutException:
            raise ProviderError(f"{self.name}: tiempo de espera agotado", retryable=True) from None
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name}: error de conexión ({type(e).__name__})", retryable=True) from None
        if response.status_code >= 400:
            try:
                error = response.json().get("error") or {}
                detail = error.get("message", "") if isinstance(error, dict) else str(error)
            except ValueError:
                detail = ""
            raise ProviderError(f"{self.name} respondió {response.status_code}: {detail[:300]}",
                                retryable=response.status_code in RETRYABLE_STATUS, status_code=response.status_code)
        try:
            return response.json()
        except ValueError:
            raise ProviderError(f"{self.name}: respuesta que no es JSON", retryable=True) from None


class AnthropicProvider(HttpProvider):
    name = "anthropic"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: Optional[str], base_url: str = "https://api.anthropic.com", **kwargs: Any) -> None:
        super().__init__(api_key, base_url, **kwargs)

    def _headers(self) -> Dict[str, str]:
        return {"x-api-key": self._api_key or "", "anthropic-version": self.API_VERSION, "content-type": "application/json"}

    def complete(self, model: str, system: str, messages: List[Dict[str, str]], max_tokens: int,
                 temperature: Optional[float] = None) -> Completion:
        payload: Dict[str, Any] = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature
        started = time.perf_counter()
        data = self._post("/v1/messages", payload)
        text = "".join(block.get("text", "") for block in data.get("content", []) if isinstance(block, dict) and block.get("type") == "text")
        usage = data.get("usage") or {}
        return Completion(texto=text, proveedor=self.name, modelo=data.get("model", model), tokens_entrada=int(usage.get("input_tokens", 0)),
                          tokens_salida=int(usage.get("output_tokens", 0)), motivo_fin=data.get("stop_reason"),
                          duracion_ms=round((time.perf_counter() - started) * 1000, 2))


class OpenAIProvider(HttpProvider):
    name = "openai"

    def __init__(self, api_key: Optional[str], base_url: str = "https://api.openai.com", **kwargs: Any) -> None:
        super().__init__(api_key, base_url, **kwargs)

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key or ''}", "content-type": "application/json"}

    def complete(self, model: str, system: str, messages: List[Dict[str, str]], max_tokens: int,
                 temperature: Optional[float] = None) -> Completion:
        payload: Dict[str, Any] = {"model": model, "max_completion_tokens": max_tokens,
                                   "messages": [{"role": "system", "content": system}, *messages]}
        if temperature is not None:
            payload["temperature"] = temperature
        started = time.perf_counter()
        data = self._post("/v1/chat/completions", payload)
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage") or {}
        return Completion(texto=(choice.get("message") or {}).get("content") or "", proveedor=self.name, modelo=data.get("model", model),
                          tokens_entrada=int(usage.get("prompt_tokens", 0)), tokens_salida=int(usage.get("completion_tokens", 0)),
                          motivo_fin=choice.get("finish_reason"), duracion_ms=round((time.perf_counter() - started) * 1000, 2))
