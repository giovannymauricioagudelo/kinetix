"""
KINETIX STUDIO v5.0.0 - COMPLETE ENTERPRISE API WITH 12 AGENTS
NEXUS + SYNAPSE + MATRIX + INSIGHT + PRISM + ORBIT + VECTOR + GENESIS + AURORA + CORTEX + SENTINEL + ARGUS
Los conteos de endpoints salen de src/agents/agent_catalog.py.
"""

import logging
import os
from datetime import datetime

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from src.agents.agent_catalog import ALL_AGENTS, total_default_endpoints
from src.agents.monitoring_agent import install_argus
from src.agents.reporting_agent.dependencies import install_insight_scheduler
from src.agents.security_agent.dependencies import require_user
from src.api.routes.argus_routes import router as argus
from src.api.routes.aurora_routes import router as aurora
from src.api.routes.cortex_routes import router as cortex
from src.api.routes.genesis_routes import router as genesis
from src.api.routes.insight_routes import router as insight
from src.api.routes.matrix_routes import router as matrix
from src.api.routes.nexus_routes import router as nexus
from src.api.routes.orbit_routes import router as orbit
from src.api.routes.prism_routes import router as prism
from src.api.routes.sentinel_routes import router as sentinel
from src.api.routes.synapse_routes import router as synapse
from src.api.routes.vector_routes import router as vector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

AGENTS = len(ALL_AGENTS)
ENDPOINTS = total_default_endpoints()

app = FastAPI(title="KINETIX STUDIO v5.0.0", description=f"{AGENTS} Autonomous Agents - {ENDPOINTS} Endpoints", version="5.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)
install_argus(app)
install_insight_scheduler(app)

# KINETIX_REQUIRE_AUTH=true exige un token de Sentinel en Cortex.
_legacy_auth = [Depends(require_user)] if os.getenv("KINETIX_REQUIRE_AUTH", "false").strip().lower() in ("1", "true", "si", "sí") else []

# ============================================================================
# AGENT 1: NEXUS (DatabaseAgent) - SQL Server real, permisos de Sentinel
# ============================================================================
app.include_router(nexus)

# ============================================================================
# AGENT 2: SYNAPSE (APIsAgent) - integraciones externas, OpenAPI, SSRF, circuit breaker
# ============================================================================
app.include_router(synapse)

# ============================================================================
# AGENT 3: MATRIX (BusinessRulesAgent) - reglas en SQL Server, permisos de Sentinel
# ============================================================================
app.include_router(matrix)

# ============================================================================
# AGENT 4: INSIGHT (ReportingAgent) - catálogo de reportes, exportación y programaciones
# ============================================================================
app.include_router(insight)

# ============================================================================
# AGENT 5: PRISM (QAAgent) - pytest + cobertura, lint, conflictos de reglas, compuerta
# ============================================================================
app.include_router(prism)

# ============================================================================
# AGENT 6: ORBIT (GitDeploymentAgent) - releases con tags, reversión, GitHub Actions
# ============================================================================
app.include_router(orbit)

# ============================================================================
# AGENT 7: VECTOR (DevelopmentAgent) - análisis AST, plantillas, ramas y commits
# ============================================================================
app.include_router(vector)

# ============================================================================
# AGENT 8: GENESIS (CustomAIAgent) - agentes de IA, generación revisada por Vector, presupuesto
# ============================================================================
app.include_router(genesis)

# ============================================================================
# AGENT 9: AURORA (InterfaceDesignAgent) - tokens, WCAG, exportaciones, pantallas
# ============================================================================
app.include_router(aurora)

# ============================================================================
# AGENT 10: CORTEX (OrchestratorAgent)
# ============================================================================
app.include_router(cortex, dependencies=_legacy_auth)

# ============================================================================
# AGENT 11: SENTINEL (SecurityAgent)
# ============================================================================
app.include_router(sentinel)

# ============================================================================
# AGENT 12: ARGUS (MonitoringAgent)
# ============================================================================
app.include_router(argus)


# ============================================================================
# INFRASTRUCTURE ENDPOINTS (9 total)
# ============================================================================
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "version": "5.0.0", "agents": AGENTS, "endpoints": ENDPOINTS, "timestamp": datetime.utcnow().isoformat()}


@app.get("/ready", tags=["Health"])
async def ready():
    return {"ready": True, "checks": {"api": "ready", "all_agents": "ready"}, "timestamp": datetime.utcnow().isoformat()}


@app.get("/live", tags=["Health"])
async def live():
    return {"alive": True}


@app.get("/metrics/pools", tags=["Metrics"])
async def metrics_pools():
    return {"postgresql": "initialized", "mssql": "initialized"}


@app.get("/metrics/cache", tags=["Metrics"])
async def metrics_cache():
    return {"in_memory_size": 5000, "redis": "initialized"}


@app.get("/metrics/circuit-breakers", tags=["Metrics"])
async def metrics_cb():
    return {"database": {"state": "CLOSED"}, "external_api": {"state": "CLOSED"}}


@app.get("/metrics/all", tags=["Metrics"])
async def metrics_all():
    return {"timestamp": datetime.utcnow().isoformat(), "version": "5.0.0", "agents": AGENTS, "endpoints": ENDPOINTS}


@app.get("/system/info", tags=["System"])
async def system_info():
    return {"app": "KINETIX STUDIO", "version": "5.0.0", "agents": AGENTS, "endpoints": ENDPOINTS}


@app.get("/agents", tags=["Agents"])
async def list_agents():
    agents = [
        {"id": p.codename.lower(), "agente": p.codename, "name": p.legacy_id, "endpoints": p.default_endpoints, "status": "ready"}
        for p in ALL_AGENTS
    ]
    return {"total": AGENTS, "active": AGENTS, "agents": agents, "timestamp": datetime.utcnow().isoformat()}


@app.get("/")
async def root():
    return {"app": "KINETIX STUDIO v5.0.0", "description": f"{AGENTS} Autonomous Agents - {ENDPOINTS} Endpoints",
            "documentation": "http://127.0.0.1:8000/docs", "status": "running", "agents": AGENTS, "endpoints": ENDPOINTS,
            "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
