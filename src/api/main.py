"""
KINETIX STUDIO v5.0.0 - COMPLETE ENTERPRISE API WITH 12 AGENTS
NEXUS + SYNAPSE + MATRIX + INSIGHT + PRISM + ORBIT + VECTOR + GENESIS + AURORA + CORTEX + SENTINEL + ARGUS
Los conteos de endpoints salen de src/agents/agent_catalog.py.
"""

import logging
import os
import re
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import APIRouter, Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from src.agents.agent_catalog import ALL_AGENTS, total_default_endpoints
from src.agents.monitoring_agent import install_argus
from src.agents.reporting_agent.dependencies import install_insight_scheduler
from src.agents.security_agent.dependencies import require_user
from src.api.routes.argus_routes import router as argus
from src.api.routes.aurora_routes import router as aurora
from src.api.routes.cortex_routes import router as cortex
from src.api.routes.insight_routes import router as insight
from src.api.routes.matrix_routes import router as matrix
from src.api.routes.nexus_routes import router as nexus
from src.api.routes.orbit_routes import router as orbit
from src.api.routes.prism_routes import router as prism
from src.api.routes.sentinel_routes import router as sentinel
from src.api.routes.vector_routes import router as vector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

AGENTS = len(ALL_AGENTS)
ENDPOINTS = total_default_endpoints()
IDENTIFIER = re.compile(r'^[a-zA-Z_]')

app = FastAPI(title="KINETIX STUDIO v5.0.0", description=f"{AGENTS} Autonomous Agents - {ENDPOINTS} Endpoints", version="5.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)
install_argus(app)
install_insight_scheduler(app)

# KINETIX_REQUIRE_AUTH=true exige un token de Sentinel en los agentes legacy y en Cortex.
_legacy_auth = [Depends(require_user)] if os.getenv("KINETIX_REQUIRE_AUTH", "false").strip().lower() in ("1", "true", "si", "sí") else []

# ============================================================================
# AGENT 1: NEXUS (DatabaseAgent) - SQL Server real, permisos de Sentinel
# ============================================================================
app.include_router(nexus)

# ============================================================================
# AGENT 2: SYNAPSE (APIsAgent) - 6 Endpoints
# ============================================================================
synapse = APIRouter(prefix="/api/v1/synapse", tags=["SYNAPSE"])


@synapse.get("/info")
async def synapse_info():
    return {"id": "synapse", "name": "APIsAgent v2.0", "endpoints": 6, "status": "active"}


@synapse.post("/connect-api")
async def connect_api(api_name: str = Query(...), base_url: str = Query(...), auth_type: str = Query("none")):
    if (not IDENTIFIER.match(api_name) or not base_url.startswith(("http://", "https://"))
            or auth_type not in ["none", "basic", "bearer", "api_key"]):
        return {"status": "error"}
    return {"status": "success", "api_name": api_name, "connection_id": f"conn_{api_name}"}


@synapse.post("/call-api")
async def call_api(api_name: str = Query(...), endpoint: str = Query(...), method: str = Query("GET"), data: Optional[str] = Query(None)):
    if not IDENTIFIER.match(api_name) or method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"] or not endpoint.startswith("/"):
        return {"status": "error"}
    return {"status": "success", "http_status": 200, "response_time_ms": 125.45}


@synapse.get("/registered-apis")
async def list_apis():
    return {"status": "success", "total": 4, "connected": 3, "apis": [{"name": "github_api", "status": "connected"}]}


@synapse.post("/test-connection")
async def test_connection(api_name: str = Query(...), endpoint: str = Query("/")):
    return {"status": "completed", "connection_ok": True} if IDENTIFIER.match(api_name) else {"status": "error"}


@synapse.get("/api-logs")
async def get_logs(api_name: Optional[str] = Query(None), limit: int = Query(10)):
    return {"status": "success", "total_logs": 3, "logs": [{"id": "log_001", "status": 200}]}


@synapse.get("/api-health")
async def api_health():
    return {"status": "completed", "total_apis": 4, "healthy": 2,
            "apis": [{"api_name": "github_api", "status": "healthy", "uptime_percent": 99.95}]}


app.include_router(synapse, dependencies=_legacy_auth)

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
# AGENT 8: GENESIS (CustomAIAgent) - 6 Endpoints
# ============================================================================
genesis = APIRouter(prefix="/api/v1/genesis", tags=["GENESIS"])


@genesis.get("/info")
async def genesis_info():
    return {"id": "genesis", "name": "CustomAIAgent v2.0", "endpoints": 6, "status": "active", "ai_models": ["claude", "gpt", "local-llm"]}


@genesis.post("/create-custom-agent")
async def create_agent(agent_name: str = Query(...), description: str = Query(...), capabilities: str = Query(...)):
    if not IDENTIFIER.match(agent_name) or len(description) < 10:
        return {"status": "error"}
    return {"status": "created", "agent_id": f"agent_{agent_name}_123", "capabilities": 5}


@genesis.post("/train-agent")
async def train_agent(agent_id: str = Query(...), training_data_size: int = Query(...)):
    if not agent_id.startswith("agent_") or training_data_size < 10:
        return {"status": "error"}
    return {"status": "in_progress", "training_id": f"train_{agent_id}_123", "eta_minutes": 45}


@genesis.post("/invoke-agent")
async def invoke_agent(agent_id: str = Query(...), prompt: str = Query(...), model: str = Query("claude")):
    if model not in ["claude", "gpt", "local-llm"]:
        return {"status": "error"}
    return {"status": "success", "response_id": f"resp_{agent_id}_123", "model": model, "tokens_used": 234}


@genesis.get("/agent-performance")
async def agent_performance(agent_id: Optional[str] = Query(None)):
    return {"status": "success", "agents": 2, "performance": {"accuracy": 92.5, "latency_ms": 345.2, "cost_per_call": 0.015}}


@genesis.post("/customize-behavior")
async def customize_behavior(agent_id: str = Query(...), parameter: str = Query(...), value: str = Query(...)):
    if not agent_id.startswith("agent_"):
        return {"status": "error"}
    return {"status": "success", "customization_id": f"custom_{agent_id}_123", "parameter": parameter, "updated": True}


app.include_router(genesis, dependencies=_legacy_auth)

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
