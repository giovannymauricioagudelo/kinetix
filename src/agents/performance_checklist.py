"""
Checklist fundamental de rendimiento para toda aplicación generada por Kinetix.

Fuente operativa: `.cursor/rules/rendimiento-por-aplicacion.mdc`.
Cortex lo usa en el sprint `rendimiento` y en las acciones base de interfaz/fundaciones.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from src.agents.agent_catalog import (
    ARGUS,
    AURORA,
    INSIGHT,
    NEXUS,
    ORBIT,
    PRISM,
    SYNAPSE,
    VECTOR,
    AgentProfile,
)

RULE_FILE = "rendimiento-por-aplicacion.mdc"
EVIDENCE_DOC = "docs/rendimiento.md"

# Práctica → agente dueño (validación y entrega).
OWNERSHIP: Tuple[Tuple[str, AgentProfile, str], ...] = (
    ("esqueletos_carga", AURORA, "Esqueletos de carga (skeleton/placeholder) en listados, fichas y tableros."),
    ("imagenes_modernas", AURORA, "Imágenes en WebP o AVIF con fallback; sin PNG/JPEG pesados en la ruta crítica."),
    ("listas_virtualizadas", AURORA, "Listas y tablas largas virtualizadas (ventana visible, no DOM completo)."),
    ("render_servidor", AURORA, "SSR o shell crítico hidratado: primer paint útil sin esperar todo el JS."),
    ("indices", NEXUS, "Índices estratégicos, planes de consulta y RCSI donde aplique el volumen."),
    ("evitar_n_plus_1", NEXUS, "Procedimientos y consultas sin N+1 (JOIN/lote; nada de 1 query por fila en la app)."),
    ("pool_conexiones", NEXUS, "Pool de conexiones dimensionado; la app no abre/cierra conexiones por petición."),
    ("brotli", SYNAPSE, "Compresión Brotli (o gzip de respaldo) en respuestas HTTP estáticas y API."),
    ("cdn", SYNAPSE, "Assets estáticos e imágenes por CDN; Cache-Control e invalidación definidos."),
    ("cola_trabajos", SYNAPSE, "Trabajos lentos (correo, IA, reportes pesados, sellados) en cola asíncrona."),
    ("opentelemetry", ARGUS, "Trazas y métricas OpenTelemetry (o equivalentes) con p95/p99 por ruta."),
    ("cache", VECTOR, "Caché de lecturas calientes (tablero, catálogos, permisos efectivos) con invalidación explícita."),
    ("implementacion", VECTOR, "Implementar esqueletos, formatos de imagen, virtualización, pool, cola, Brotli y caché."),
    ("cache_reportes", INSIGHT, "KPIs y agregaciones pesadas con caché o materialización; sin recalcular en cada hit."),
    ("pruebas_carga", PRISM, "Prueba de carga contra el objetivo (usuarios concurrentes, p95 lectura/escritura, error %)."),
    ("pruebas_movil_red_lenta", PRISM, "Pruebas en viewport móvil y red lenta (throttling 3G/Slow 4G); evidencia en docs/rendimiento.md."),
    ("despliegue_cdn_workers", ORBIT, "CDN, workers de cola y compresión en el despliegue; plan de reversión."),
)

DEFAULT_OBJECTIVES = {
    "usuarios_concurrentes": 100,
    "p95_lectura_ms": 500,
    "p95_escritura_ms": 1000,
    "error_pct_max": 1.0,
}


def actions_by_agent() -> Dict[str, str]:
    """Una acción consolidada por agente para el sprint de rendimiento."""
    grouped: Dict[str, List[str]] = {}
    for _key, agent, text in OWNERSHIP:
        grouped.setdefault(agent.codename, []).append(text)
    return {
        codename: " ".join(parts) + f" Regla: {RULE_FILE}."
        for codename, parts in grouped.items()
    }


def sprint_tasks() -> Tuple[Tuple[AgentProfile, str], ...]:
    """Orden de tareas del sprint rendimiento (dependencias las resuelve Cortex)."""
    order = (NEXUS, SYNAPSE, AURORA, INSIGHT, VECTOR, PRISM, ORBIT, ARGUS)
    actions = actions_by_agent()
    return tuple((agent, actions[agent.codename]) for agent in order if agent.codename in actions)


def exit_criteria() -> str:
    return (
        f"Objetivo de carga cumplido (p95 lectura ≤ {DEFAULT_OBJECTIVES['p95_lectura_ms']} ms, "
        f"escritura ≤ {DEFAULT_OBJECTIVES['p95_escritura_ms']} ms, errores < {DEFAULT_OBJECTIVES['error_pct_max']} %), "
        f"prueba móvil/red lenta en verde y evidencia en {EVIDENCE_DOC}."
    )


def practices() -> List[Dict[str, str]]:
    return [
        {"id": key, "agente": agent.codename, "practica": text}
        for key, agent, text in OWNERSHIP
    ]
