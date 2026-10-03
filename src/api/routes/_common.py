"""Helpers compartidos por los routers de agentes protegidos con Sentinel."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from fastapi import Request
from fastapi.responses import Response


def client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"estado": "exito", **payload}


def health(codename: str, ping: Callable[[], None], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        ping()
        database = "conectada"
    except Exception:
        database = "no disponible"
    return {
        "agente": codename,
        "estado": "activo" if database == "conectada" else "degradado",
        "base_datos": database,
        **(extra or {}),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def attachment(content: str, filename: str, media_type: str) -> Response:
    """Descarga forzada (nunca se renderiza en el origen de la API)."""
    return Response(
        content=content.encode("utf-8"),
        media_type=f"{media_type}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff"},
    )
