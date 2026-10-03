"""Instancia compartida de SynapseService (SYNAPSE_REPOSITORY=memory para desarrollo sin SQL Server)."""

from __future__ import annotations

import logging
import os
from typing import Optional

from src.agents.apis_agent.crypto import cipher_from_env
from src.agents.apis_agent.gateway import CircuitBreaker, HttpGateway
from src.agents.apis_agent.netguard import NetworkPolicy
from src.agents.apis_agent.repository import InMemoryIntegrationRepository, IntegrationRepository
from src.agents.apis_agent.service import SynapseService
from src.agents.common import Lazy, env_bool, env_int, sqlserver_client, use_memory

logger = logging.getLogger(__name__)


def policy_from_env() -> NetworkPolicy:
    return NetworkPolicy(allow_http=env_bool("SYNAPSE_PERMITIR_HTTP"),
                         allowed_private_hosts=os.getenv("SYNAPSE_HOSTS_PRIVADOS_PERMITIDOS", "").split(","))


def build_default_service() -> SynapseService:
    memory = use_memory("SYNAPSE_REPOSITORY")
    repository: IntegrationRepository
    if memory:
        logger.warning("Synapse usa un repositorio en memoria: las integraciones se pierden al reiniciar.")
        repository = InMemoryIntegrationRepository()
    else:
        from src.agents.apis_agent.repository import SqlServerIntegrationRepository

        repository = SqlServerIntegrationRepository(sqlserver_client("SYNAPSE_QUERY_TIMEOUT_SECONDS"))
    gateway = HttpGateway(policy_from_env(), max_response_bytes=env_int("SYNAPSE_MAX_RESPUESTA_BYTES", 1_000_000))
    breaker = CircuitBreaker(env_int("SYNAPSE_CIRCUITO_FALLOS", 5), env_int("SYNAPSE_CIRCUITO_ESPERA_SEGUNDOS", 60))
    return SynapseService(repository, cipher_from_env(ephemeral_ok=memory), gateway, breaker=breaker,
                          max_integrations=env_int("SYNAPSE_MAX_INTEGRACIONES", 100))


_service: Lazy[SynapseService] = Lazy(build_default_service)


def get_synapse_service() -> SynapseService:
    return _service.get()


def set_synapse_service(service: Optional[SynapseService]) -> None:
    _service.set(service)
