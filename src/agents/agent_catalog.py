"""
Identidades canónicas de agentes AFP (codenames Kinetix Studio).

Los nombres públicos del proyecto son los codenames (Nexus, Synapse, …).
Los identificadores legacy (DatabaseAgent, …) se conservan en código/clases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class AgentProfile:
    codename: str
    legacy_id: str
    tagline: str
    route_key: str
    default_endpoints: int = 0


NEXUS = AgentProfile(
    "Nexus",
    "DatabaseAgent",
    "El núcleo de conexión de datos.",
    "database",
    6,
)
SYNAPSE = AgentProfile(
    "Synapse",
    "APIsAgent",
    "Los impulsos que conectan con el exterior.",
    "apis",
    6,
)
MATRIX = AgentProfile(
    "Matrix",
    "BusinessRulesAgent",
    "El motor que procesa las reglas del negocio.",
    "rules",
    8,
)
INSIGHT = AgentProfile(
    "Insight",
    "ReportingAgent",
    "El encargado de reflejar las métricas y reportes.",
    "reporting",
    8,
)
PRISM = AgentProfile(
    "Prism",
    "QAAgent",
    "El guardián que analiza y asegura la calidad.",
    "qa",
    8,
)
ORBIT = AgentProfile(
    "Orbit",
    "GitDeploymentAgent",
    "El que pone la aplicación en órbita (producción).",
    "git-deployment",
    8,
)
VECTOR = AgentProfile(
    "Vector",
    "DevelopmentAgent",
    "El taller principal donde se moldea el código.",
    "development",
    8,
)
GENESIS = AgentProfile(
    "Genesis",
    "CustomAIAgent",
    "Genera código y soluciones AI automáticamente.",
    "genesis",
    7,
)

ALL_AGENTS: Tuple[AgentProfile, ...] = (
    NEXUS,
    SYNAPSE,
    MATRIX,
    INSIGHT,
    PRISM,
    ORBIT,
    VECTOR,
    GENESIS,
)

BY_LEGACY: Dict[str, AgentProfile] = {p.legacy_id: p for p in ALL_AGENTS}
BY_CODENAME: Dict[str, AgentProfile] = {p.codename: p for p in ALL_AGENTS}


def openapi_tag(profile: AgentProfile) -> str:
    return f"{profile.codename} ({profile.legacy_id})"


def health_service_name(profile: AgentProfile, detail: str = "") -> str:
    """Nombre público en endpoints /health (codename primero)."""
    base = openapi_tag(profile)
    if detail:
        return f"{base} — {detail}"
    return base


def log_line(profile: AgentProfile, endpoints: int | None = None) -> str:
    count = profile.default_endpoints if endpoints is None else endpoints
    return (
        f"{profile.codename} ({profile.legacy_id}) – {profile.tagline} "
        f"({count} endpoints)"
    )


def agents_public_summary() -> Dict[str, Dict[str, object]]:
    return {
        profile.codename: {
            "legacy_id": profile.legacy_id,
            "descripcion": profile.tagline,
            "endpoints": profile.default_endpoints,
            "route_key": profile.route_key,
        }
        for profile in ALL_AGENTS
    }


def total_default_endpoints() -> int:
    return sum(p.default_endpoints for p in ALL_AGENTS)
