"""Alias de compatibilidad: la aplicación completa (12 agentes) vive en src/api/main.py."""

import uvicorn

from src.api.main import app  # noqa: F401

if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
