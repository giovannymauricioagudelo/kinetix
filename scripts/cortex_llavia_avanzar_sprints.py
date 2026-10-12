"""Reconstruye la solicitud de Llavia en Cortex (memoria volátil) con los sprints ya cerrados y sus notas.

    .\\venv\\Scripts\\python.exe scripts\\cortex_llavia_avanzar_sprints.py

Tras cerrar un sprint nuevo, agrega su nota a NOTAS_SPRINTS para poder reconstruirlo si Cortex se reinicia.
El siguiente sprint queda pendiente: lo inicia un humano.
"""
from __future__ import annotations

import json
import sys

import httpx

from cortex_llavia_cerrar_sprint1 import ANSWERS, BASE, DESC, NOTAS_S1  # type: ignore

NOTAS_SPRINTS = {
    1: NOTAS_S1,
    2: "Grafo tenant, solicitudes, publicaciones, Habeas SQL, scripts siembra, CI 81%. Push ef6c471.",
    3: (
        "OpenAPI exportado (16 paths), rate limit auth, headers seguridad, clientes WhatsApp/pagos stub-HTTP, "
        "webhooks HMAC, persistencia factura_suscripcion/pago_suscripcion/destacado, CI >=80%. Push 210a200."
    ),
    4: "PWA MFA, destacados, E2E Playwright, GET publicaciones. Push 34e4695 en llavia.",
    5: (
        "Tablero Insight GET /reportes/tablero con alcance por rol, pantalla Reportes en PWA, dataset demo "
        "verificado en memoria y SQL (sembrar_analitica_demo.py --verificar OK), cobertura 82.45%, E2E 5 OK. "
        "Push 935a3c5 en llavia."
    ),
    6: (
        "IA sin LLM: POST /ia/dictado (reglas-1, voz es-CO en PWA, respaldo enchufable) y emparejamiento "
        "basico-1 (POST/GET /solicitudes/{id}/coincidencias, MERGE en coincidencia). Prism: dictado 40+16 casos "
        "y emparejamiento top-3 al 100%, paso en CI. Siembra demo SQL verificada, cobertura 88.47%, E2E 7 OK. "
        "Push 5d02594 en llavia."
    ),
    7: (
        "Cumplimiento: solicitudes del titular con plazos Ley 1581 en dias habiles (br_hd_005-008), auditoria "
        "encadenada SHA-256 inalterable y verificable, RBAC por endpoint con denegados auditados, MFA por rol "
        "(br_seg_001) y MFA reciente 15 min para exportar/auditoria, exportacion CSV auditada, retencion "
        "(archivar 10 anios). Matrix catalog_sprint07. Prism: bandit/pip-audit/npm audit en CI (0 hallazgos), "
        "verificar_cumplimiento.py 12/12 en SQL, 240 pruebas, cobertura 90.33%, E2E 7 OK, docs/cumplimiento.md. "
        "Push 7b6b05f en llavia."
    ),
}


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
        for numero, notas in sorted(NOTAS_SPRINTS.items()):
            c.post(f"{BASE}/requests/{rid}/sprints/{numero}/iniciar", json={"iniciado_por": "giovanny"}).raise_for_status()
            c.post(
                f"{BASE}/requests/{rid}/sprints/{numero}/completar",
                json={"completado_por": "giovanny", "notas": notas},
            ).raise_for_status()
        final = c.get(f"{BASE}/requests/{rid}").json()
    print(json.dumps({"request_id": rid, "progreso": final.get("progreso_sprints"),
                      "siguiente_paso": final.get("siguiente_paso")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
