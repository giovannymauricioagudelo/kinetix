"""Instancia compartida de GenesisService (GENESIS_REPOSITORY=memory para desarrollo sin SQL Server)."""

from __future__ import annotations

import logging
import os
from typing import Optional

from src.agents.common import Lazy, env_bool, env_int, sqlserver_client, use_memory
from src.agents.custom_ai_agent.cascade import catalog_from_env
from src.agents.custom_ai_agent.providers import AnthropicProvider, OpenAIProvider
from src.agents.custom_ai_agent.repository import GenesisRepository, InMemoryGenesisRepository
from src.agents.custom_ai_agent.service import GenesisService

logger = logging.getLogger(__name__)


def _vector():
    from src.agents.development_agent.dependencies import get_vector_service

    return get_vector_service()


def build_default_service() -> GenesisService:
    repository: GenesisRepository
    if use_memory("GENESIS_REPOSITORY"):
        logger.warning("Genesis usa un repositorio en memoria: agentes, uso y generaciones se pierden al reiniciar.")
        repository = InMemoryGenesisRepository()
    else:
        from src.agents.custom_ai_agent.repository import SqlServerGenesisRepository

        repository = SqlServerGenesisRepository(sqlserver_client("GENESIS_QUERY_TIMEOUT_SECONDS"))
    timeout = env_int("GENESIS_TIMEOUT_SECONDS", 120)
    providers = {
        "anthropic": AnthropicProvider(os.getenv("ANTHROPIC_API_KEY"), os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                                       timeout_seconds=timeout),
        "openai": OpenAIProvider(os.getenv("OPENAI_API_KEY"), os.getenv("OPENAI_BASE_URL", "https://api.openai.com"),
                                 timeout_seconds=timeout),
    }
    return GenesisService(repository, providers, catalog_from_env(), _vector,
                          default_budget=env_int("GENESIS_PRESUPUESTO_TOKENS_MENSUAL", 2_000_000),
                          store_content=env_bool("GENESIS_GUARDAR_CONTENIDO", True))


_service: Lazy[GenesisService] = Lazy(build_default_service)


def get_genesis_service() -> GenesisService:
    return _service.get()


def set_genesis_service(service: Optional[GenesisService]) -> None:
    _service.set(service)
