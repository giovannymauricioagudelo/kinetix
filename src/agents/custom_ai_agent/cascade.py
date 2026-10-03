"""
Cascada de modelos de Genesis: tareas simples van al nivel económico y las complejas (código o SQL extensos,
arquitectura, seguridad, migraciones) al premium. Si el proveedor preferido falla, se intenta el otro.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

PROVIDERS = ("anthropic", "openai")
TIERS = ("economico", "premium")
LEVELS = ("auto", *TIERS)

DEFAULT_MODELS: Dict[Tuple[str, str], str] = {
    ("anthropic", "economico"): "claude-haiku-4-5",
    ("anthropic", "premium"): "claude-sonnet-4-5",
    ("openai", "economico"): "gpt-4o-mini",
    ("openai", "premium"): "gpt-4o",
}
# USD por millón de tokens (entrada, salida); estimación configurable con GENESIS_PRECIOS
DEFAULT_PRICES: Dict[str, Tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4o": (2.5, 10.0),
}
_COMPLEX = re.compile(r"(?i)\b(arquitectur\w*|segur\w*|migraci\w*|refactor\w*|concurrencia|transacci\w*|escalab\w*|optimiz\w*|"
                      r"algoritmo|criptograf\w*|rendimiento|architecture|security|migration|performance)\b")


@dataclass(frozen=True)
class ModelChoice:
    proveedor: str
    modelo: str
    nivel: str


def complexity_tier(tipo: str, prompt: str) -> str:
    long_code = tipo in ("codigo", "sql") and len(prompt) > 600
    return "premium" if long_code or len(prompt) > 4000 or _COMPLEX.search(prompt) else "economico"


class ModelCatalog:
    def __init__(self, models: Optional[Dict[Tuple[str, str], str]] = None, prices: Optional[Dict[str, Tuple[float, float]]] = None,
                 preferred: Iterable[str] = PROVIDERS) -> None:
        self.models = {**DEFAULT_MODELS, **(models or {})}
        self.prices = {**DEFAULT_PRICES, **(prices or {})}
        order = [p for p in preferred if p in PROVIDERS]
        self.preferred = order + [p for p in PROVIDERS if p not in order]

    def candidates(self, nivel: str, proveedor: Optional[str], available: Iterable[str]) -> List[ModelChoice]:
        ready = set(available)
        order = [proveedor] + [p for p in self.preferred if p != proveedor] if proveedor in PROVIDERS else self.preferred
        return [ModelChoice(p, self.models[(p, nivel)], nivel) for p in order if p in ready]

    def cost(self, model: str, tokens_in: int, tokens_out: int) -> Optional[float]:
        price = self.prices.get(model)
        if price is None:
            return None
        return round((tokens_in * price[0] + tokens_out * price[1]) / 1_000_000, 6)

    def describe(self) -> Dict[str, Dict[str, str]]:
        return {p: {t: self.models[(p, t)] for t in TIERS} for p in PROVIDERS}


def catalog_from_env() -> ModelCatalog:
    models = {(p, t): os.environ[f"GENESIS_{p.upper()}_MODELO_{t.upper()}"]
              for p in PROVIDERS for t in TIERS if os.getenv(f"GENESIS_{p.upper()}_MODELO_{t.upper()}")}
    prices: Dict[str, Tuple[float, float]] = {}
    raw = os.getenv("GENESIS_PRECIOS")
    if raw:
        try:
            prices = {k: (float(v[0]), float(v[1])) for k, v in json.loads(raw).items()}
        except (ValueError, TypeError, IndexError, AttributeError):
            raise ValueError('GENESIS_PRECIOS debe ser JSON: {"modelo": [entrada_usd_millon, salida_usd_millon]}') from None
    preferred = [p.strip() for p in os.getenv("GENESIS_PROVEEDOR_PREFERIDO", "anthropic").split(",")]
    return ModelCatalog(models, prices, preferred)
