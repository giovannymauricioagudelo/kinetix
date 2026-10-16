"""Registra en Cortex la mejora del portal público de inmuebles de Llavia (req-8e92e7a7).

Cortex guarda solicitudes en memoria: tras reiniciar la API hay que volver a correr este script.
No aprueba el plan ni inicia sprints; eso lo decide un humano.

    .\\venv\\Scripts\\python.exe scripts\\cortex_llavia_portal_publico.py
"""
from __future__ import annotations

import json
import sys

import httpx

BASE = "http://127.0.0.1:8000/api/v1/cortex"

DESC = (
    "Mejora en Llavia: portal web de inmuebles integrado o desplegable desde la misma aplicación PWA. "
    "El visitante anónimo (sin login) ve propiedades publicadas con fotos, características, precio y filtros "
    "(tipo, ciudad, zona, canon, habitaciones, etc.). El portal ofrece acceso a la aplicación (registro/ingreso). "
    "El visitante puede marcar bienes (favoritos/selección) y enviar un resumen por correo electrónico. "
    "Respeta la matriz de visibilidad por campo (público / registrados / tras contacto / privado), la vigencia "
    "de publicaciones y el anti-scraping. Incluye listado, galería y ficha; opcionalmente mapa en una etapa "
    "posterior. Criterio de marca: puede abrirse desde la app de la agencia o como portal público de la misma."
)

ANSWERS = {
    "funcionalidad": (
        "El visitante anonimo abre el portal (integrado o desplegable desde la PWA de Llavia) sin login y ve "
        "inmuebles publicados: fotos, caracteristicas, precio y filtros (tipo, ciudad, zona, barrio, canon, "
        "area, habitaciones, banos, parqueadero, estrato, mascotas, amoblado). Puede abrir la ficha, marcar "
        "bienes (favoritos/seleccion) y enviar un resumen por correo (integracion SMTP / servicio externo). "
        "Desde el portal puede acceder a la aplicacion (registro o ingreso). Solo se muestran campos con "
        "visibilidad publica segun la matriz; anti-scraping y vigencia de publicacion. Listado, galeria y "
        "ficha; mapa en etapa posterior. Incluye reglas de negocio de publicacion y migraciones de datos."
    ),
    "criterios_aceptacion": (
        "1) GET publico de listado y ficha sin sesion, con filtros y paginacion. "
        "2) Fotos y datos respetan matriz de visibilidad (publico/registrados/tras contacto/privado). "
        "3) Marcar y desmarcar inmuebles; enviar resumen por correo con los marcados. "
        "4) Enlaces a registro e ingreso. "
        "5) Portal usable desde la misma app (ruta/desplegable). "
        "6) Opciones nuevas en permisos_catalogo (portal/favoritos/envio) sincronizadas. "
        "7) Prism: E2E visitante sin login, prueba de rutas publicas marcadas, sin SQL en linea, cobertura."
    ),
    "alcance": "datos reglas seguridad integraciones interfaz",
    "usuarios_afectados": (
        "Visitante anonimo, interesado, intermediario y administrador de agencia (publican y configuran). "
        "Roles de portal y permisos de la empresa."
    ),
    "impacto_datos": (
        "Si: tablas y procedimientos de favoritos de portal, seleccion temporal sin cuenta, registro de envio "
        "de resumen por correo; migraciones Nexus sobre publicacion e inmueble ya existentes. Modelo "
        "multiempresa con seguridad por fila y habeas data."
    ),
    "compatibilidad": (
        "No hay clientes externos del portal publico aun; la API autenticada de publicaciones e inmuebles se "
        "mantiene. El portal usa rutas nuevas publicas (/portal, API publica de listado/ficha) sin romper el "
        "panel de agencia ni el portal de interesado/propietario con sesion."
    ),
    "plazo": (
        "Siguiente ciclo de sprints de Llavia, en cuanto se apruebe el plan; prioridad alta de negocio "
        "(MVP del requerimiento original seccion 6)."
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
        r = c.post(
            f"{BASE}/requests",
            json={"descripcion": DESC, "app_id": "llavia", "tipo_solicitud": "mejora"},
        )
        r.raise_for_status()
        rid = r.json()["id"]
        body = c.post(f"{BASE}/requests/{rid}/answers", json={"respuestas": ANSWERS}).json()
        if body.get("preguntas_pendientes"):
            print("Pendientes:", body["preguntas_pendientes"], file=sys.stderr)
            return 1
        if body.get("estado") != "plan_propuesto":
            print("Estado inesperado:", body.get("estado"), file=sys.stderr)
            return 1
        sprints = body.get("sprints") or []
        resumen = {
            "request_id": rid,
            "estado": body["estado"],
            "complejidad": body.get("complejidad"),
            "aplicacion": body.get("aplicacion"),
            "capacidades": body.get("capacidades_detectadas"),
            "sprints": [
                {
                    "numero": s["numero"],
                    "nombre": s["nombre"],
                    "objetivo": s["objetivo"],
                    "entregable": s["entregable"],
                }
                for s in sprints
            ],
            "siguiente_paso": body.get("siguiente_paso"),
            "nota": (
                "Aprueba con POST /requests/{id}/approve {aprobado_por: giovanny}. "
                "Inicia Sprint 1 con POST .../sprints/1/iniciar. "
                "Entregables sprint 1 en llavia: docs/adr/ADR-004-portal-publico.md y docs/portal_aceptacion.md."
            ),
        }
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
