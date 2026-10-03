# Kinetix Studio

Plataforma AFP con agentes **Nexus**, **Synapse**, **Matrix**, **Insight**, **Prism**, **Orbit**, **Vector**, **Genesis**, **Aurora**, **Cortex**, **Sentinel** y **Argus** (ver [docs/AGENT_CODENAMES.md](docs/AGENT_CODENAMES.md)), expuestos por FastAPI.

## Requisitos

- Python 3.9 o superior (el entorno local de referencia usa 3.9.7)
- Git

## Instalación (3 pasos)

```bash
git clone https://github.com/giovannymauricioagudelo/kinetix.git
cd kinetix
```

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

**Linux / macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

`requirements.txt` tiene las dependencias de ejecución. `requirements-dev.txt` incluye esas más pytest y herramientas de calidad.

Los mensajes de commit llevan al final la marca de tiempo local `ddMMyyyy HH:MM:SS` (p. ej. `20092026 21:48:05`). Tras clonar, activa el hook una vez:

```bash
git config core.hooksPath .githooks
```

(en Linux/macOS también: `chmod +x .githooks/prepare-commit-msg`)

## Uso

Con el entorno virtual **activado**:

```bash
python run.py
```

Si no activas el venv y existe `venv/` en la raíz, `run.py` intenta usarlo solo.

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health

Sentinel, Nexus, Synapse, Matrix, Aurora, Vector, Prism, Orbit, Insight y Genesis usan SQL Server (base `kinetix`). Configura `.env` a partir de `.env.example` y aplica una vez las migraciones incrementales (idempotentes); el script lee las credenciales de `.env`:

```powershell
venv\Scripts\python.exe scripts\apply_sql_migration.py SENTINEL_SCHEMA_PHASE2.sql
venv\Scripts\python.exe scripts\apply_sql_migration.py NEXUS_MATRIX_SCHEMA.sql
venv\Scripts\python.exe scripts\apply_sql_migration.py PLATFORM_AGENTS_SCHEMA.sql
venv\Scripts\python.exe scripts\apply_sql_migration.py SYNAPSE_GENESIS_SCHEMA.sql
```

Synapse necesita `SYNAPSE_ENCRYPTION_KEY` para cifrar las credenciales de las integraciones y Genesis al menos una de `ANTHROPIC_API_KEY` u `OPENAI_API_KEY` (ver `.env.example`).

Sin SQL Server, cada agente acepta su variable en `memory` (`SENTINEL_REPOSITORY`, `NEXUS_CATALOG`, `SYNAPSE_REPOSITORY`, `MATRIX_REPOSITORY`, `AURORA_REPOSITORY`, `VECTOR_REPOSITORY`, `PRISM_REPOSITORY`, `ORBIT_REPOSITORY`, `INSIGHT_REPOSITORY`, `GENESIS_REPOSITORY`) y arranca con datos en memoria (solo desarrollo; Synapse usa entonces una llave de cifrado temporal). Para comprobar Nexus y Matrix contra la base sin dejar cambios: `venv\Scripts\python.exe scripts\verify_nexus_matrix_sqlserver.py`; para ver permisos, roles y tablas de los agentes: `venv\Scripts\python.exe scripts\check_agent_permissions.py`.

Solo runtime (sin tests):

```bash
pip install -r requirements.txt
python run.py
```

## Tests

```bash
pytest tests/ -v
```

## Estructura

```
src/agents/agent_catalog.py  Codenames (Nexus, Synapse, …)
src/agents/database_agent/   Nexus (DatabaseAgent)
src/agents/apis_agent/       Synapse (APIsAgent)
src/agents/business_rules_agent/  Matrix (BusinessRulesAgent)
src/agents/reporting_agent/  Insight (ReportingAgent)
src/agents/qa_agent/         Prism (QAAgent)
src/agents/git_deployment_agent/  Orbit (GitDeploymentAgent)
src/agents/development_agent/  Vector (DevelopmentAgent)
src/agents/interface_design_agent/  Aurora (InterfaceDesignAgent)
src/agents/custom_ai_agent/  Genesis (CustomAIAgent)
src/agents/orchestrator_agent/  Cortex (OrchestratorAgent)
src/agents/security_agent/   Sentinel (SecurityAgent)
src/agents/monitoring_agent/ Argus (MonitoringAgent)
src/api/main.py              App FastAPI
src/api/routes/              Rutas REST por agente
tests/unit/                  Pruebas
run.py                       Arranque local
```

## Solución rápida: `ModuleNotFoundError: uvicorn`

Ese error aparece al usar el Python del sistema, no el del `venv`. Activa el entorno e instala dependencias:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python run.py
```
