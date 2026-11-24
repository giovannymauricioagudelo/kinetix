"""
Checklist fundamental de seguridad para toda aplicación generada por Kinetix.

Fuente operativa: `.cursor/rules/seguridad-por-aplicacion.mdc`.
Cortex lo usa en el sprint `seguridad` (apps media/alta) y en las acciones base de Sentinel/Synapse/Vector/Prism.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from src.agents.agent_catalog import (
    ARGUS,
    AURORA,
    NEXUS,
    ORBIT,
    PRISM,
    SENTINEL,
    SYNAPSE,
    VECTOR,
    AgentProfile,
)

RULE_FILE = "seguridad-por-aplicacion.mdc"
EVIDENCE_DOC = "docs/seguridad.md"

# Práctica → agente dueño (diseño / implementación / verificación).
OWNERSHIP: Tuple[Tuple[str, AgentProfile, str], ...] = (
    ("autenticacion", SENTINEL, "Autenticación (login, sesión, MFA en roles sensibles) y autorización por permiso efectivo."),
    ("contrasenas_hash", SENTINEL, "Contraseñas solo con hash fuerte (bcrypt/argon2); nunca en claro ni reversible."),
    ("cookies_sesion", SENTINEL, "Tokens de sesión en cookies HttpOnly + Secure + SameSite (o justificación auditada si no)."),
    ("https", SYNAPSE, "HTTPS obligatorio fuera de desarrollo local; HSTS en producción."),
    ("claves_api_servidor", SYNAPSE, "Claves API y secretos de terceros solo en servidor (.env / vault); nunca en el navegador ni en VITE_*/NEXT_PUBLIC_*."),
    ("cors", SYNAPSE, "CORS con orígenes explícitos (nunca '*' con credenciales); métodos y cabeceras mínimos."),
    ("limite_peticiones", SYNAPSE, "Límite de peticiones (rate limit) en auth, registro, formularios públicos y webhooks."),
    ("cabeceras", SYNAPSE, "Cabeceras: CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy."),
    ("validacion_servidor", VECTOR, "Validación y autorización en el servidor en cada mutación; el cliente no es de confianza."),
    ("xss", VECTOR, "Prevención XSS: escapado por defecto, sin HTML crudo no sanitizado, CSP sin unsafe-inline en prod."),
    ("csrf", VECTOR, "Protección CSRF alineada al modelo de sesión (SameSite + token si hay cookies de autenticación)."),
    ("archivos", VECTOR, "Subida de archivos: tipo/tamaño/magic bytes, sin path traversal, almacenamiento fuera de web root."),
    ("pagos_servidor", VECTOR, "Pagos solo en servidor; webhooks firmados; sin datos de tarjeta en la app."),
    ("secretos_git", ORBIT, "Secretos fuera de Git (.env ignorado, sin credenciales en el historial); rotación documentada."),
    ("dependencias", ORBIT, "Auditoría de dependencias en CI (npm audit / pip/uv; sin críticas conocidas sin remediar)."),
    ("datos_aislados", NEXUS, "Sin contraseñas en claro en tablas; RLS / SESSION_CONTEXT; acceso solo por procedimientos."),
    ("ui_sin_secretos", AURORA, "UI sin claves ni secretos; formularios sin exponer tokens; feedback seguro en errores."),
    ("pruebas_protecciones", PRISM, "Probar auth, XSS/CSRF, CORS, rate limit, cabeceras, archivos, webhooks y secretos; informe en docs/seguridad.md."),
    ("anomalias_acceso", ARGUS, "Alertas de picos 401/403/429 y fallos de autenticación anómalos."),
)


def actions_by_agent() -> Dict[str, str]:
    grouped: Dict[str, List[str]] = {}
    for _key, agent, text in OWNERSHIP:
        grouped.setdefault(agent.codename, []).append(text)
    return {
        codename: " ".join(parts) + f" Regla: {RULE_FILE}."
        for codename, parts in grouped.items()
    }


def sprint_tasks() -> Tuple[Tuple[AgentProfile, str], ...]:
    order = (SENTINEL, SYNAPSE, NEXUS, AURORA, VECTOR, ORBIT, PRISM, ARGUS)
    actions = actions_by_agent()
    return tuple((agent, actions[agent.codename]) for agent in order if agent.codename in actions)


def exit_criteria() -> str:
    return (
        "Protecciones OWASP del checklist en verde (auth, HTTPS, hash, validación servidor, XSS/CSRF, CORS, "
        f"cabeceras, cookies, rate limit, archivos, pagos servidor, dependencias, secretos fuera de Git) y "
        f"informe en {EVIDENCE_DOC}."
    )


def practices() -> List[Dict[str, str]]:
    return [
        {"id": key, "agente": agent.codename, "practica": text}
        for key, agent, text in OWNERSHIP
    ]
