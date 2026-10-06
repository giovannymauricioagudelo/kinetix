"""Respaldos por archivo para motores sin BACKUP en el servidor (pg_dump, gbak, mongodump).
Los archivos quedan en el equipo de la API, en NEXUS_BACKUP_DIR; las herramientas se buscan en el PATH
o en NEXUS_<HERRAMIENTA>_PATH (p. ej. NEXUS_PG_DUMP_PATH)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.agents.security_agent.models import InvalidInputError

_UNSAFE = re.compile(r"[^A-Za-z0-9_\-]+")


def safe_stem(name: str) -> str:
    """Prefijo de archivo a partir del nombre de la base (una ruta de Firebird queda en su nombre de archivo)."""
    stem = Path(name.replace("\\", "/")).stem or "base"
    return _UNSAFE.sub("_", stem)[:60]


def tool_path(tool: str) -> str:
    override = os.getenv(f"NEXUS_{tool.upper()}_PATH")
    found = override or shutil.which(tool)
    if not found:
        raise InvalidInputError(f"No se encontró {tool}: instálalo en el servidor de la API o define NEXUS_{tool.upper()}_PATH")
    return found


def run_tool(args: Sequence[str], env: Optional[Mapping[str, str]], timeout: int) -> str:
    """Ejecuta sin shell; las credenciales viajan por variables de entorno o archivo, nunca en args."""
    try:
        completed = subprocess.run(
            list(args), env={**os.environ, **(env or {})}, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        raise InvalidInputError(f"{Path(args[0]).name} superó {timeout} s") from None
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise InvalidInputError(f"{Path(args[0]).name} falló: {(detail[-1] if detail else 'sin detalle')[:500]}")
    return completed.stdout


def backup_target(directory: Optional[str], database: str, label: str, extension: str) -> Path:
    if not directory:
        raise InvalidInputError("Define NEXUS_BACKUP_DIR: carpeta del servidor de la API donde guardar los respaldos")
    folder = Path(directory)
    if not folder.is_dir():
        raise InvalidInputError(f"La carpeta de respaldos no existe: {folder}")
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return folder / f"{safe_stem(database)}_{stamp}_{label}{extension}"


def backup_entry(path: Path, database: str, started: datetime, verified: bool) -> Dict[str, Any]:
    return {
        "base_datos": database,
        "archivo": str(path),
        "nombre": path.stem,
        "tamano_bytes": path.stat().st_size if path.exists() else None,
        "inicio": started.isoformat(),
        "fin": datetime.now(timezone.utc).isoformat(),
        "verificado": verified,
        "solo_copia": True,
    }


def list_backup_files(directory: Optional[str], database: str, extension: str, limit: int) -> List[Dict[str, Any]]:
    if not directory or not Path(directory).is_dir():
        return []
    files = sorted(Path(directory).glob(f"{safe_stem(database)}_*{extension}"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "id": path.name, "nombre": path.stem, "tipo": "completo", "solo_copia": True, "inicio": None,
            "fin": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "tamano_bytes": path.stat().st_size, "archivo": str(path),
        }
        for path in files[:limit]
    ]
