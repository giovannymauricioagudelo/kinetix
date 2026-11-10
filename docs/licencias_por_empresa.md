# Licencias por empresa (plantilla fundamental)

Monetización base de toda aplicación generada por Kinetix: **asientos de usuario** y/o **módulos de funcionalidad**.

Regla operativa: `.cursor/rules/licencias-por-empresa.mdc`  
Plantilla Nexus: `src/agents/database_agent/license_template.py` (`licencias_por_empresa`)

## Qué incluye Nexus al registrar una app

1. Migración `permisos_por_empresa` (RBAC).
2. Migración `licencias_por_empresa`: tablas `plan_suscripcion`, `limite_plan`, `suscripcion` + procs `app.licencia_*`.

Apps anteriores: `POST /api/v1/nexus/aplicaciones/{id}/licencias`.

## Contrato para Vector / Synapse

| Capacidad | Procedimiento / helper |
| --- | --- |
| Resumen | `app.licencia_resumen` |
| Cupo de usuarios | `app.licencia_assert_asiento` (`@usados`, `@pendientes`) → 52102 |
| Módulo | `app.licencia_assert_modulo` (`@modulo`) → 52103 |
| Overrides | `app.licencia_personalizar` |

Tras `requiere(opcion, evento)`, las rutas de módulos de pago validan licencia. Las invitaciones de equipo validan asiento.

## Catálogo de permisos

`permission_template.catalogo_base()` incluye la opción `suscripcion` (`/suscripcion`) con eventos `acceder`, `consultar`, `actualizar`.

## Aurora

Pantalla tipo `licenses`: plan, asientos usados/cupo y módulos incluidos.

## Relación con Llavia

Llavia ya implementa el producto (`docs/licencias.md` en su repo). La fábrica generaliza el mismo modelo para que toda app nueva lo herede al registrarse.
