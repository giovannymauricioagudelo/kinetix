# Rendimiento por aplicación (plantilla fundamental)

Toda aplicación generada por Kinetix nace con prácticas de velocidad percibida y de carga. Una app lenta pierde usuarios.

Regla operativa: `.cursor/rules/rendimiento-por-aplicacion.mdc`  
Checklist canónico: `src/agents/performance_checklist.py`

## Objetivos por defecto

| Métrica | Objetivo |
| --- | --- |
| Usuarios concurrentes (referencia) | ≥ 100 (o el del dominio) |
| p95 lecturas | ≤ 500 ms |
| p95 escrituras | ≤ 1 s |
| Errores bajo carga | < 1 % |
| Móvil + red lenta | Flujos críticos usables con throttling 3G / Slow 4G |

Evidencia al cerrar el sprint: `docs/rendimiento.md` en el repositorio de la aplicación.

## Agentes y prácticas

| Práctica | Agente |
| --- | --- |
| Esqueletos de carga | Aurora → Vector |
| WebP / AVIF | Aurora → Vector |
| Listas virtualizadas | Aurora → Vector |
| SSR / shell crítico | Aurora → Vector |
| Índices, RCSI, sin N+1 en procs | Nexus |
| Pool de conexiones | Nexus + Vector |
| Brotli, CDN, cola de trabajos | Synapse → Vector → Orbit |
| Caché de lecturas / KPIs | Vector + Insight |
| OpenTelemetry / p95 | Argus |
| Pruebas de carga y móvil/red lenta | Prism |
| CDN / workers en despliegue | Orbit |

## Cortex

- Apps nuevas de complejidad **media** o **alta**: sprint `rendimiento` obligatorio (antes solo si el prompt hablaba de «millones de usuarios»).
- Tareas: `performance_checklist.sprint_tasks()` (Nexus, Synapse, Aurora, Insight, Vector, Prism, Orbit, Argus).
- Solicitudes de escalabilidad: flujo SCALE (diagnóstico → optimización → carga).

## Relación con Llavia

Llavia ya demostró el patrón en `llavia-sprint-08` (`docs/rendimiento.md` del repo Llavia): índices, RCSI, caché de tablero, pool propio, workers y prueba de 500 concurrentes. La fábrica generaliza ese estándar para todas las apps siguientes.
