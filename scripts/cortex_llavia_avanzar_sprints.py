"""Registra Llavia en Cortex, cierra sprint 1 y 2, inicia sprint 3 (memoria volátil)."""
from __future__ import annotations

import json
import sys

import httpx

from cortex_llavia_cerrar_sprint1 import ANSWERS, BASE, DESC, NOTAS_S1  # type: ignore

NOTAS_S2 = (
    "Grafo tenant, solicitudes, publicaciones, Habeas SQL, scripts siembra, CI 81%. Push ef6c471."
)


def main() -> int:
    try:
        with httpx.Client(timeout=5) as probe:
            probe.get("http://127.0.0.1:8000/health").raise_for_status()
    except httpx.HTTPError as exc:
        print(
            "Cortex no responde en http://127.0.0.1:8000.\n"
            "En otra terminal: cd D:\\Desarrollo\\kinetix-studio\n"
            "  .\\venv\\Scripts\\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000\n"
            f"Detalle: {exc}",
            file=sys.stderr,
        )
        return 1

    with httpx.Client(timeout=60) as c:
        r = c.post(f"{BASE}/requests", json={"descripcion": DESC, "tipo_solicitud": "nueva_aplicacion"})
        r.raise_for_status()
        rid = r.json()["id"]
        c.post(f"{BASE}/requests/{rid}/answers", json={"respuestas": ANSWERS}).raise_for_status()
        c.post(f"{BASE}/requests/{rid}/approve", json={"aprobado_por": "giovanny"}).raise_for_status()
        c.post(f"{BASE}/requests/{rid}/sprints/1/iniciar", json={"iniciado_por": "giovanny"}).raise_for_status()
        c.post(
            f"{BASE}/requests/{rid}/sprints/1/completar",
            json={"completado_por": "giovanny", "notas": NOTAS_S1},
        ).raise_for_status()
        c.post(f"{BASE}/requests/{rid}/sprints/2/iniciar", json={"iniciado_por": "giovanny"}).raise_for_status()
        c.post(
            f"{BASE}/requests/{rid}/sprints/2/completar",
            json={"completado_por": "giovanny", "notas": NOTAS_S2},
        ).raise_for_status()
        c.post(f"{BASE}/requests/{rid}/sprints/3/iniciar", json={"iniciado_por": "giovanny"}).raise_for_status()
        final = c.get(f"{BASE}/requests/{rid}").json()
    print(json.dumps({"request_id": rid, "progreso": final.get("progreso_sprints")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
