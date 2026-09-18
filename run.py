"""
Arranque local de Kinetix Studio.
Usar con el venv activo: python run.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _in_virtualenv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _venv_python() -> Path | None:
    candidates = [
        ROOT / "venv" / "Scripts" / "python.exe",
        ROOT / "venv" / "bin" / "python",
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _reexec_in_venv_if_needed() -> None:
    if _in_virtualenv():
        return
    venv_py = _venv_python()
    if venv_py is None:
        return
    os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])


def _print_setup_help() -> None:
    is_windows = os.name == "nt"
    activate = r".\venv\Scripts\Activate.ps1" if is_windows else "source venv/bin/activate"
    print("")
    print("No se encontraron las dependencias (uvicorn / FastAPI).")
    print("Crea e instala el entorno desde la raíz del repo:")
    print("")
    print("  python -m venv venv")
    print(f"  {activate}")
    print("  python -m pip install --upgrade pip")
    print("  pip install -r requirements-dev.txt")
    print("  python run.py")
    print("")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    _reexec_in_venv_if_needed()

    try:
        import uvicorn
    except ModuleNotFoundError:
        _print_setup_help()
        sys.exit(1)

    print("")
    print("=" * 70)
    print("Kinetix Studio starting")
    print("=" * 70)
    print("")
    print("Swagger UI: http://localhost:8000/docs")
    print("ReDoc:      http://localhost:8000/redoc")
    print("")
    print("=" * 70)
    print("")

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
