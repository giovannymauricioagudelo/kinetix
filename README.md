# Kinetix Studio

Plataforma para generar y gestionar esquemas de base de datos y especificaciones REST mediante agentes (Database Agent y APIs Agent) expuestos por FastAPI.

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
src/agents/database_agent/   Database Agent
src/agents/apis_agent/       APIs Agent
src/api/main.py              App FastAPI
src/api/routes/              Rutas REST
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
