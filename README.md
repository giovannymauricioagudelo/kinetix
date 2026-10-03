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

Sentinel, Nexus y Matrix usan SQL Server (base `kinetix`). Configura `.env` a partir de `.env.example` y aplica una vez las migraciones incrementales (idempotentes):

```powershell
sqlcmd -S localhost -U sa -C -i SENTINEL_SCHEMA_PHASE2.sql
sqlcmd -S localhost -U sa -C -i NEXUS_MATRIX_SCHEMA.sql
```

Sin SQL Server, `SENTINEL_REPOSITORY=memory`, `NEXUS_CATALOG=memory` y `MATRIX_REPOSITORY=memory` arrancan con datos en memoria (solo desarrollo). Para comprobar Nexus y Matrix contra la base sin dejar cambios: `venv\Scripts\python.exe scripts\verify_nexus_matrix_sqlserver.py`.

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
