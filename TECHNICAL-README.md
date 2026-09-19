# 🚀 AFP - Technical Documentation

## 📋 Quick Start (5 minutos)

### Opción 1: Ejecución Local (Python)

```bash
# 1. Clone repository
git clone https://github.com/[username]/application-factory-platform.git
cd application-factory-platform

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements-dev.txt

# 4. Download los 5 archivos (base_agent.py, database_agent.py, test_database_agent.py, database_agent_routes.py, main.py)
# Y copiarlos a /src/agents/

# 5. Run tests
pytest tests/ -v --cov=src

# 6. Run development server
python src/api/main.py

# 7. Open http://localhost:8000/docs
```

### Opción 2: Docker (10 minutos)

```bash
# 1. Clone repository
git clone https://github.com/[username]/application-factory-platform.git
cd application-factory-platform

# 2. Build image
docker build -f docker/Dockerfile -t afp:dev .

# 3. Run with docker-compose
docker-compose -f docker-compose.dev.yml up

# 4. Open http://localhost:8000/docs
```

### Opción 3: Azure Cloud (15 minutos)

```bash
# 1. Login to Azure
az login

# 2. Create resource group
az group create --name afp-rg --location eastus

# 3. Create App Service
az appservice plan create --name afp-plan --resource-group afp-rg --sku B1 --is-linux

# 4. Create web app
az webapp create --resource-group afp-rg --plan afp-plan --name afp-app --runtime "PYTHON|3.11"

# 5. Deploy code
cd application-factory-platform
az webapp up --name afp-app --resource-group afp-rg

# 6. Check: https://afp-app.azurewebsites.net/docs
```

---

## 📂 Estructura de Carpetas

```
src/
├── agents/
│   ├── __init__.py
│   ├── base_agent.py           # Abstract base class ✅ (Listo)
│   ├── agent_registry.py        # Agent discovery (Semana 3)
│   ├── agent_orchestrator.py    # Orchestration (Semana 3)
│   │
│   ├── database_agent/
│   │   ├── __init__.py
│   │   └── agent.py             # Database Agent ✅ (Listo)
│   │
│   ├── apis_agent/              # Coming Semana 3
│   ├── rules_agent/             # Coming Semana 3
│   ├── reporting_agent/         # Coming Semana 3
│   ├── qa_agent/                # Coming Semana 3
│   ├── git_agent/               # Coming Semana 3
│   ├── deployment_agent/        # Coming Semana 3
│   └── custom_agent/            # Coming Semana 3
│
├── api/
│   ├── main.py                  # FastAPI app ✅ (Listo)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── database.py          # Database routes ✅ (Listo)
│   │   ├── apis.py              # Coming Semana 3
│   │   ├── rules.py             # Coming Semana 3
│   │   ├── reporting.py         # Coming Semana 3
│   │   ├── qa.py                # Coming Semana 3
│   │   ├── git.py               # Coming Semana 3
│   │   ├── deployment.py        # Coming Semana 3
│   │   └── health.py            # Health checks ✅ (Listo)
│   │
│   ├── middleware.py            # CORS, auth, etc. ✅ (Listo)
│   ├── security.py              # JWT, API keys (Semana 3)
│   └── exceptions.py            # Error handling ✅ (Listo)
│
├── database/
│   ├── connection.py            # PostgreSQL (Semana 3)
│   ├── models.py                # SQLAlchemy (Semana 3)
│   └── migrations/              # Alembic (Semana 3)
│
├── events/
│   ├── event_bus.py             # n8n integration (Semana 2)
│   ├── event_models.py          # Event types ✅ (Semana 1)
│   └── handlers.py              # Event handlers (Semana 3)
│
├── config/
│   ├── settings.py              # Pydantic settings ✅ (Listo)
│   ├── logging.py               # Logging config ✅ (Listo)
│   └── constants.py             # Constants ✅ (Listo)
│
└── utils/
    ├── logger.py                # Centralized logging ✅ (Listo)
    ├── validators.py            # Input validation (Semana 3)
    ├── decorators.py            # Custom decorators (Semana 3)
    └── helpers.py               # Utility functions (Semana 3)

tests/
├── unit/
│   ├── test_database_agent.py   # ✅ (Listo - 20+ tests)
│   ├── test_apis_agent.py       # Coming Semana 3
│   └── test_event_bus.py        # Coming Semana 3
│
├── integration/
│   ├── test_agent_flow.py       # Coming Semana 3
│   └── test_event_propagation.py # Coming Semana 3
│
└── e2e/
    └── test_full_workflow.py    # Coming Semana 3
```

---

## 🔧 Development Workflow

### 1️⃣ Agregar Nuevo Agente (ejemplo: APIs Agent)

**Paso 1: Crear archivo agent**
```python
# src/agents/apis_agent/agent.py

from agents.base_agent import BaseAgent, AgentConfig, AgentInput, AgentOutput
import logging

logger = logging.getLogger(__name__)

class APIsAgentInput(AgentInput):
    """APIs Agent input"""
    action: str  # generate_endpoint, openapi, validate
    endpoint_definition: Optional[EndpointDefinition] = None

class APIsAgent(BaseAgent):
    """
    APIs Agent - Generates REST/SOAP endpoints
    """
    
    def __init__(self):
        config = AgentConfig(
            name="APIsAgent",
            version="0.1.0"
        )
        super().__init__(config)
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        # Implementation
        pass
    
    def validate_input(self, input_data: AgentInput) -> tuple[bool, Optional[str]]:
        # Validation
        pass
```

**Paso 2: Crear tests**
```python
# tests/unit/test_apis_agent.py

import pytest
from agents.apis_agent import APIsAgent

@pytest.fixture
def apis_agent():
    return APIsAgent()

@pytest.mark.asyncio
async def test_generate_endpoint(apis_agent):
    # Test implementation
    pass
```

**Paso 3: Crear routes**
```python
# src/api/routes/apis.py

from fastapi import APIRouter
from agents.apis_agent import APIsAgent

router = APIRouter(prefix="/api/v1/apis", tags=["apis"])

@router.post("/endpoints")
async def generate_endpoint(request: GenerateEndpointRequest):
    # Route implementation
    pass
```

**Paso 4: Incluir en main.py**
```python
# src/api/main.py
from api.routes import apis_router
app.include_router(apis_router)
```

**Paso 5: Correr tests**
```bash
pytest tests/unit/test_apis_agent.py -v
```

### 2️⃣ Agregar Integración con n8n Event Bus

```python
# src/events/event_bus.py

import httpx
from typing import Dict, Any

class EventBus:
    """Sends events to n8n webhook"""
    
    def __init__(self, n8n_url: str):
        self.n8n_url = n8n_url
    
    async def emit(self, event_type: str, payload: Dict[str, Any]):
        """Send event to n8n"""
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.n8n_url}/webhook/{event_type}",
                json=payload
            )

# En base_agent.py, actualizar emit_event():
async def emit_event(self, event_type: str, payload: Dict[str, Any]):
    from events.event_bus import EventBus
    bus = EventBus("http://localhost:5678")
    await bus.emit(event_type, payload)
```

### 3️⃣ Conectar con PostgreSQL

```python
# src/database/connection.py

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from config.settings import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG
)

# En agents, usar engine:
from database.connection import engine

async def execute_sql(sql: str):
    async with engine.begin() as conn:
        await conn.execute(sql)
```

---

## 🧪 Testing

### Ejecutar todos los tests
```bash
pytest tests/ -v
```

### Ejecutar con cobertura
```bash
pytest tests/ --cov=src --cov-report=html
```

### Ejecutar solo tests del Database Agent
```bash
pytest tests/unit/test_database_agent.py -v
```

### Ejecutar con markers
```bash
# Solo tests unitarios
pytest tests/ -m "not integration" -v

# Solo tests asincronos
pytest tests/ -k "asyncio" -v
```

### Debugging
```bash
# Stop on failure
pytest tests/ -x

# Show print statements
pytest tests/ -s

# Run with pdb on failure
pytest tests/ --pdb
```

---

## 🚢 Deployment

### Local Development
```bash
# 1. Activate venv
source venv/bin/activate

# 2. Run with hot reload
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# 3. Access: http://localhost:8000/docs
```

### Docker Development
```bash
# 1. Build
docker build -f docker/Dockerfile.dev -t afp:dev .

# 2. Run
docker run -p 8000:8000 -v $(pwd)/src:/app/src afp:dev

# 3. Access: http://localhost:8000/docs
```

### Docker Production
```bash
# 1. Build production image
docker build -f docker/Dockerfile -t afp:latest .

# 2. Run with environment
docker run \
  -p 8000:8000 \
  -e DATABASE_URL=postgresql://user:pass@postgres:5432/afp \
  -e ENV=production \
  afp:latest
```

### Azure App Service
```bash
# 1. Configure GitHub Actions (auto-deploy on push)
# 2. Deploy via Azure CLI
az webapp up --name afp-app --resource-group afp-rg

# 3. Check logs
az webapp log tail --name afp-app --resource-group afp-rg
```

### Kubernetes
```bash
# 1. Build and push image
docker build -t myregistry.azurecr.io/afp:latest .
docker push myregistry.azurecr.io/afp:latest

# 2. Apply manifests
kubectl apply -f kubernetes/

# 3. Check deployment
kubectl get pods
kubectl logs -f deployment/afp
```

---

## 🔍 API Documentation

### Swagger UI
```
http://localhost:8000/docs
```

### ReDoc
```
http://localhost:8000/redoc
```

### OpenAPI JSON
```
http://localhost:8000/openapi.json
```

### Example: Create Table via API

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/database/tables \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req_001",
    "table_definition": {
      "name": "clientes",
      "columns": [
        {
          "name": "cliente_id",
          "type": "bigint",
          "primary_key": true
        },
        {
          "name": "empresa_id",
          "type": "int",
          "nullable": false
        },
        {
          "name": "bodega_id",
          "type": "int",
          "nullable": false
        },
        {
          "name": "nombre",
          "type": "varchar",
          "nullable": false
        }
      ],
      "description": "Tabla de clientes"
    }
  }'
```

**Response:**
```json
{
  "request_id": "req_001",
  "status": "success",
  "data": {
    "table_name": "clientes",
    "columns": 4,
    "schema_hash": "a1b2c3d4e5f6g7h8",
    "ddl_script": "CREATE TABLE...",
    "created_at": "2026-09-12T10:00:00"
  },
  "execution_time_ms": 45.23
}
```

---

## 📊 Monitoring

### Logs
```bash
# Watch logs
docker logs -f $(docker ps | grep afp | awk '{print $1}')

# View logs in Azure
az webapp log tail --name afp-app
```

### Metrics
- Response time: `X-Process-Time` header
- Request ID: `X-Request-ID` header
- Execution time: `execution_time_ms` in response

### Health Checks
```bash
# Basic health
curl http://localhost:8000/health

# Detailed status
curl http://localhost:8000/status

# Database agent status
curl http://localhost:8000/api/v1/database/status
```

---

## 🐛 Troubleshooting

### "ModuleNotFoundError: No module named 'agents'"
```bash
# Add src to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Or run from src:
cd src
python -m api.main
```

### "Port 8000 already in use"
```bash
# Kill process on port 8000
lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Or use different port
uvicorn src.api.main:app --port 8001
```

### "PostgreSQL connection failed"
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Start postgres
docker-compose -f docker-compose.dev.yml up postgres -d

# Test connection
psql -h localhost -U afp -d afp_dev
```

### Tests failing with "RuntimeError: Event loop is closed"
```python
# Update pytest.ini
[pytest]
asyncio_mode = auto
```

---

## 📚 References

- **FastAPI Docs:** https://fastapi.tiangolo.com/
- **Pydantic:** https://docs.pydantic.dev/
- **SQLAlchemy:** https://docs.sqlalchemy.org/
- **Pytest:** https://docs.pytest.org/
- **Docker:** https://docs.docker.com/
- **Kubernetes:** https://kubernetes.io/docs/
- **Azure:** https://docs.microsoft.com/en-us/azure/

---

## 🎯 Roadmap Código

| Semana | Agente | Estado |
|--------|--------|--------|
| 2 | Database Agent | ✅ Completo |
| 2 | Tests + Routes | ✅ Completo |
| 2 | n8n Event Bus MVP | 🟡 En progreso |
| 3 | APIs Agent | ⏳ Coming |
| 3 | Business Rules Agent | ⏳ Coming |
| 3 | Reporting Agent | ⏳ Coming |
| 4 | QA Agent | ⏳ Coming |
| 4 | Git Deployment Agent | ⏳ Coming |
| 5 | Development Agent | ⏳ Coming |
| 5 | Custom AI Agents | ⏳ Coming |

---

**¿Preguntas técnicas?**

1. Abre issue en GitHub
2. Contacta a Giovanny
3. Revisa `/docs` en la API

**Último update:** 12 Sept, 2026
