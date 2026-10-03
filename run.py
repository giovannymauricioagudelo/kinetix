"""
Script para ejecutar AFP desde la raíz del proyecto
Ejecutar: python run.py
O mejor aún: python -m uvicorn src.api.main:app --reload
"""

import os
import subprocess
import sys
from pathlib import Path

# Agregar la raíz al path
root = Path(__file__).parent
sys.path.insert(0, str(root))

VENV = root / "venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _relaunch_in_venv() -> None:
    """Si existe venv/ y no se está usando, relanza con su intérprete (el reload de uvicorn hereda sys.executable)."""
    if not VENV_PYTHON.exists() or Path(sys.prefix).resolve() == VENV.resolve():
        return
    print(f"Usando el entorno virtual: {VENV_PYTHON}")
    process = subprocess.Popen([str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])
    while True:
        try:
            sys.exit(process.wait())
        except KeyboardInterrupt:
            continue


# Ahora importar y ejecutar
if __name__ == "__main__":
    _relaunch_in_venv()

    import uvicorn
    
    print("")
    print("=" * 70)
    print("🚀 AFP APPLICATION STARTING")
    print("=" * 70)
    print("")
    print("📚 Swagger UI: http://localhost:8000/docs")
    print("📚 ReDoc:      http://localhost:8000/redoc")
    print("")
    print("=" * 70)
    print("")
    
    # Usar string de importación para evitar warning
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
