"""Registra solicitud Llavia en Cortex (memoria) y cierra sprint 1; inicia sprint 2."""
from __future__ import annotations

import json
import sys

import httpx

BASE = "http://127.0.0.1:8000/api/v1/cortex"
DESC = (
    "Construir Llavia: plataforma SaaS multiempresa web y movil PWA para intermediacion de arriendos. "
    "Reglas de negocio, integraciones pagos correo WhatsApp, reportes KPIs, componentes IA, "
    "habeas data DIAN auditoria OWASP ISO 27001. Alta complejidad."
)
ANSWERS = {
    "id_aplicacion": "llavia",
    "alcance": "datos reglas integraciones interfaz reportes ia seguridad monitoreo",
    "objetivo": "Intermediar arriendos multiempresa en Colombia",
    "usuarios_roles": "administrador intermediario propietario interesado",
    "plataformas": "web movil PWA API",
    "modelo_datos": "multiempresa",
    "motor_base_datos": "sql server",
    "volumen": "500 usuarios concurrentes",
    "integraciones": "pagos DIAN correo WhatsApp",
    "datos_existentes": "no aplica",
    "cumplimiento": "habeas data DIAN auditoria",
    "disponibilidad": "horario laboral",
    "plazo_presupuesto": "10 sprints",
}
NOTAS_S1 = (
    "Nexus v102 OK. Auth E2E SQL (ingresar, empresa gio, yo, refrescar). "
    "CI llavia >=80%. Push 030f914."
)


def main() -> int:
    with httpx.Client(timeout=60) as c:
        r = c.post(
            f"{BASE}/requests",
            json={"descripcion": DESC, "tipo_solicitud": "nueva_aplicacion"},
        )
        r.raise_for_status()
        rid = r.json()["id"]
        r = c.post(f"{BASE}/requests/{rid}/answers", json={"respuestas": ANSWERS})
        r.raise_for_status()
        body = r.json()
        if body.get("preguntas_pendientes"):
            print("Pendientes:", body["preguntas_pendientes"], file=sys.stderr)
            return 1
        if len(body.get("sprints") or []) != 10:
            print("Sprints esperados 10, got", len(body.get("sprints") or []), file=sys.stderr)
            return 1
        c.post(f"{BASE}/requests/{rid}/approve", json={"aprobado_por": "giovanny"}).raise_for_status()
        c.post(f"{BASE}/requests/{rid}/sprints/1/iniciar", json={"iniciado_por": "giovanny"}).raise_for_status()
        fin = c.post(
            f"{BASE}/requests/{rid}/sprints/1/completar",
            json={"completado_por": "giovanny", "notas": NOTAS_S1},
        )
        fin.raise_for_status()
        c.post(f"{BASE}/requests/{rid}/sprints/2/iniciar", json={"iniciado_por": "giovanny"}).raise_for_status()
        final = c.get(f"{BASE}/requests/{rid}").json()
        apps = c.get(f"{BASE}/apps/llavia/sprints").json()
    print(json.dumps({"request_id": rid, "progreso": final.get("progreso_sprints"), "apps": apps}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
