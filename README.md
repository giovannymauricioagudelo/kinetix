# Kinetix Studio

Plataforma AFP con agentes **Nexus**, **Synapse**, **Matrix**, **Insight**, **Prism**, **Orbit**, **Vector** y **Genesis** (ver [docs/AGENT_CODENAMES.md](docs/AGENT_CODENAMES.md)), expuestos por FastAPI.

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
