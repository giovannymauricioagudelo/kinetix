# 🏗️ APPLICATION FACTORY PLATFORM - PROJECT STRUCTURE

## Estructura de Carpetas

```
application-factory-platform/
│
├── 📁 src/
│   ├── 📁 agents/
│   │   ├── 📁 database_agent/
│   │   │   ├── __init__.py
│   │   │   ├── agent.py           # Core logic
│   │   │   ├── schema_manager.py   # Schema operations
│   │   │   ├── migration_engine.py # Migrations
│   │   │   └── models.py           # Pydantic models
│   │   │
│   │   ├── 📁 apis_agent/
│   │   │   ├── __init__.py
│   │   │   ├── agent.py
│   │   │   ├── endpoint_generator.py
│   │   │   ├── openapi_builder.py
│   │   │   └── models.py
│   │   │
│   │   ├── 📁 rules_agent/
│   │   ├── 📁 reporting_agent/
│   │   ├── 📁 qa_agent/
│   │   ├── 📁 git_agent/
│   │   ├── 📁 deployment_agent/
│   │   ├── 📁 custom_agent/
│   │   │
│   │   ├── base_agent.py           # Abstract base class
│   │   ├── agent_registry.py       # Agent discovery
│   │   └── agent_orchestrator.py   # Orchestration
│   │
│   ├── 📁 database/
│   │   ├── __init__.py
│   │   ├── connection.py           # PostgreSQL connection
│   │   ├── models.py               # SQLAlchemy models
│   │   ├── schemas.py              # Database schemas
│   │   └── 📁 migrations/
│   │       └── alembic.ini
│   │
│   ├── 📁 events/
│   │   ├── __init__.py
│   │   ├── event_bus.py            # Event pub/sub
│   │   ├── event_models.py         # Event types
│   │   └── handlers.py             # Event handlers
│   │
│   ├── 📁 api/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app
│   │   ├── 📁 routes/
│   │   │   ├── __init__.py
│   │   │   ├── agents.py
│   │   │   ├── events.py
│   │   │   ├── health.py
│   │   │   └── webhooks.py
│   │   ├── middleware.py
│   │   ├── security.py
│   │   └── exceptions.py
│   │
│   ├── 📁 config/
│   │   ├── __init__.py
│   │   ├── settings.py             # Pydantic settings
│   │   ├── logging.py
│   │   └── constants.py
│   │
│   └── 📁 utils/
│       ├── __init__.py
│       ├── logger.py
│       ├── validators.py
│       ├── decorators.py
│       └── helpers.py
│
├── 📁 tests/
│   ├── __init__.py
│   ├── conftest.py                 # Pytest fixtures
│   ├── 📁 unit/
│   │   ├── test_database_agent.py
│   │   ├── test_apis_agent.py
│   │   └── test_event_bus.py
│   ├── 📁 integration/
│   │   ├── test_agent_flow.py
│   │   └── test_event_propagation.py
│   └── 📁 e2e/
│       └── test_full_workflow.py
│
├── 📁 docker/
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── entrypoint.sh
│
├── 📁 kubernetes/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── configmap.yaml
│
├── 📁 docs/
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── SETUP.md
│   ├── AGENTS.md
│   └── API.md
│
├── 📁 scripts/
│   ├── init_db.py
│   ├── seed_data.py
│   └── cleanup.py
│
├── .env.example
├── .gitignore
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── pytest.ini
├── docker-compose.yml
├── docker-compose.dev.yml
└── README.md
```

---

## 📦 Dependencias Python

### requirements.txt
```
# Framework
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0

# Database
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
alembic==1.12.1

# AI/ML & Orchestration
langchain==0.1.0
openai==1.3.0

# Events
pydantic-events==0.0.1

# Utilities
python-dotenv==1.0.0
httpx==0.25.1
logging-loki==0.3.2

# Validation
email-validator==2.1.0

# Async
aiohttp==3.9.1

# Monitoring
prometheus-client==0.19.0

# Testing dependencies go in requirements-dev.txt
```

### requirements-dev.txt
```
-r requirements.txt

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
pytest-xdist==3.5.0

# Code quality
black==23.12.0
flake8==6.1.0
isort==5.13.2
mypy==1.7.1

# Development
ipython==8.18.1
ipdb==0.13.13

# Documentation
mkdocs==1.5.3
mkdocs-material==9.4.14
```

---

## ⚙️ Configuración

### .env.example
```ini
# Environment
ENV=development
DEBUG=True

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/afp_dev
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# API
API_HOST=0.0.0.0
API_PORT=8000
API_PREFIX=/api/v1

# Security
SECRET_KEY=your-secret-key-here-change-in-production
JWT_EXPIRATION_HOURS=24

# OpenAI (para agentes con IA)
OPENAI_API_KEY=sk-...

# Event Bus (n8n)
N8N_WEBHOOK_URL=http://localhost:5678/webhook

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Cloud
AZURE_SUBSCRIPTION_ID=
AZURE_RESOURCE_GROUP=
AZURE_STORAGE_ACCOUNT=

# Features
ENABLE_CUSTOM_AGENTS=True
ENABLE_REPORTING_PDF=True
ENABLE_QA_SCANNING=True
```

### pyproject.toml
```toml
[project]
name = "application-factory-platform"
version = "0.1.0"
description = "Fábrica de Aplicaciones Inteligente - NO-CODE platform"
authors = [{name = "Giovanny", email = "your@email.com"}]
requires-python = ">=3.11"

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.black]
line-length = 100
target-version = ['py311']
include = '\.pyi?$'

[tool.isort]
profile = "black"
line_length = 100

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v --strict-markers --cov=src --cov-report=html"
```

---

## 🐳 Docker Setup

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/
COPY config/ ./config/

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run app
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.dev.yml
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: afp
      POSTGRES_PASSWORD: afp_dev
      POSTGRES_DB: afp_dev
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U afp"]
      interval: 10s
      timeout: 5s
      retries: 5

  afp-api:
    build:
      context: .
      dockerfile: docker/Dockerfile.dev
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://afp:afp_dev@postgres:5432/afp_dev
      ENV: development
      DEBUG: "True"
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./src:/app/src
      - ./tests:/app/tests
    command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

  n8n:
    image: n8nio/n8n
    ports:
      - "5678:5678"
    environment:
      DB_TYPE: postgresql
      DB_POSTGRESDB_HOST: postgres
      DB_POSTGRESDB_USER: afp
      DB_POSTGRESDB_PASSWORD: afp_dev
      DB_POSTGRESDB_DATABASE: n8n
    depends_on:
      - postgres

volumes:
  postgres_data:
```

---

## 📋 Próximos Pasos

1. **Clonar repo** (ya existe en GitHub)
2. **Crear estructura de carpetas** (usar esta plantilla)
3. **Copiar .env.example a .env** y configurar
4. **Instalar dependencias:** `pip install -r requirements-dev.txt`
5. **Iniciar PostgreSQL:** `docker-compose -f docker-compose.dev.yml up postgres`
6. **Correr la app:** `uvicorn src.api.main:app --reload`

---

## ✅ Checklist de Setup

- [ ] Carpetas creadas según estructura
- [ ] requirements.txt copiado
- [ ] .env.example copiado y renombrado a .env
- [ ] pyproject.toml en raíz
- [ ] docker-compose.dev.yml en raíz
- [ ] Dockerfile en docker/
- [ ] .github/workflows/ creado
- [ ] Primer test creado

**Siguiente:** Implementar Database Agent
