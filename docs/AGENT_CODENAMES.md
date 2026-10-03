# Codenames de agentes AFP (Kinetix Studio)

Identidad pública del proyecto. Las clases legacy se mantienen en código por compatibilidad.

| Codename | Legacy (clase) | Rol |
|----------|------------------|-----|
| **Nexus** | DatabaseAgent | El núcleo de conexión de datos. |
| **Synapse** | APIsAgent | Los impulsos que conectan con el exterior. |
| **Matrix** | BusinessRulesAgent | El motor que procesa las reglas del negocio. |
| **Insight** | ReportingAgent | El encargado de reflejar las métricas y reportes. |
| **Prism** | QAAgent | El guardián que analiza y asegura la calidad. |
| **Orbit** | GitDeploymentAgent | El que pone la aplicación en órbita (producción). |
| **Vector** | DevelopmentAgent | El taller principal donde se moldea el código. |
| **Genesis** | CustomAIAgent | Genera código y soluciones AI automáticamente. |
| **Aurora** | InterfaceDesignAgent | Diseña sistemas UX/UI, componentes y accesibilidad multiplataforma. |
| **Cortex** | OrchestratorAgent | El cerebro que interpreta cada solicitud, pregunta lo necesario y coordina a los demás agentes. |
| **Sentinel** | SecurityAgent | El guardián que autentica, autoriza y audita cada acceso. |
| **Argus** | MonitoringAgent | El vigilante de los cien ojos que mide, alerta y reporta la salud de la plataforma. |

Fuente de verdad en código: `src/agents/agent_catalog.py`.

## Cortex: cómo orquesta

Cortex es la puerta de entrada de la fábrica. No construye nada por sí mismo:

1. **Clasifica** la solicitud: `nueva_aplicacion`, `escalabilidad`, `mejora` o `correccion`. Si la descripción es ambigua, lo primero que hace es preguntarlo.
2. **Mide la complejidad** (`baja`, `media`, `alta`) según las áreas detectadas (datos, integraciones, reglas, reportes, interfaz, IA, seguridad, monitoreo) y señales como multiempresa, alto volumen o normativas. Toda aplicación nueva incluye a Sentinel y Argus; toda solicitud de escalabilidad incluye a Argus.
3. **Pregunta** lo que falta. A mayor complejidad, más preguntas: una corrección simple pide pasos para reproducir, resultado esperado y severidad; una aplicación nueva compleja pregunta además por multiempresa, normativas, disponibilidad y presupuesto. `"no aplica"` es una respuesta válida.
4. **Propone un plan** solo cuando no quedan preguntas: tareas asignadas a cada agente, con dependencias (por ejemplo Nexus → Matrix → Synapse → Vector → Prism → Orbit).
5. **Espera aprobación humana.** Hasta que alguien aprueba, las tareas quedan en `pendiente_aprobacion`; después pasan a `lista_para_delegar`.

API: `/api/v1/cortex` (`POST /requests`, `POST /requests/{id}/answers`, `POST /requests/{id}/approve`, `GET /requests`, `GET /requests/{id}`, `GET /info`).

## Sentinel: seguridad

Código: `src/agents/security_agent/` · API: `/api/v1/sentinel` · Esquema: `SENTINEL_SCHEMA_SPANISH.sql` + `SENTINEL_SCHEMA_PHASE2.sql`.

- **Inicio de sesión en dos pasos con MFA.** `POST /autenticar` entrega la sesión solo si el usuario no tiene MFA. Con MFA devuelve una `ficha_mfa` de 5 minutos que no sirve como token; la sesión se obtiene en `POST /autenticar-mfa` con esa ficha y el código TOTP. Cada código se acepta una sola vez.
- **Sesiones cortas.** Token de acceso de 15 minutos y token de refresco de 7 días que rota en cada `POST /refrescar`. Reutilizar un refresco ya usado cierra todas las sesiones del usuario. `POST /cerrar-sesion` revoca el token actual.
- **Bloqueo por intentos.** 5 fallos de contraseña o de código MFA en 15 minutos bloquean la cuenta (429 con `Retry-After`). Solo cuentan los fallos, el contador vive en `bitacora_auditoria` (sobrevive reinicios y varias instancias) y se reinicia con un inicio de sesión exitoso. Además hay un límite por IP en los endpoints públicos.
- **Gestión del MFA con reautenticación.** `POST /configurar-mfa` no puede pisar un MFA activo; `POST /deshabilitar-mfa` exige contraseña y código vigente.
- **RBAC sobre las tablas existentes.** `GET /permisos`, `POST /autorizar`, `POST /roles/asignar` (requiere `roles:asignar`), `POST /permisos/otorgar` (requiere `permisos:otorgar`), siempre dentro de la misma empresa.
- **Cumplimiento.** `GET /auditoria` y `GET /reporte-cumplimiento` (requieren `auditoria:ver`): inicios de sesión, fallos, bloqueos, reutilización de tokens, adopción de MFA y hallazgos.
- **Para otros agentes.** `require_user` y `require_permission("recurso:accion")` en `src/agents/security_agent/dependencies.py`. Con `KINETIX_REQUIRE_AUTH=true`, los agentes legacy y Cortex exigen token de Sentinel.

Pendiente de fases siguientes: OAuth2/SAML, cifrado y bóveda de secretos, dispositivos de confianza.

## Argus: monitoreo

Código: `src/agents/monitoring_agent/` · API: `/api/v1/argus` (todo requiere `monitoreo:ver` salvo `GET /salud`).

- **Métricas reales.** Un middleware registra cada petición (agente, ruta, código, latencia). `GET /metricas` las expone en formato Prometheus (también acepta `ARGUS_SCRAPE_TOKEN` para un servidor Prometheus); `GET /metricas/json` las resume.
- **Salud de cada agente.** Sondas en proceso al endpoint de cada agente del catálogo cada `ARGUS_PROBE_INTERVAL_SECONDS` (30 s por defecto): `activo`, `lento`, `caido` o `no_desplegado`. `GET /agentes` y `GET /agentes/{codename}`.
- **Recursos del host** con psutil: `GET /sistema/recursos`.
- **Alertas** que se abren mientras la condición se cumple y se resuelven solas: latencia alta, tasa de errores 5xx alta, agente caído, CPU, memoria y disco. `POST /alertas/{id}/reconocer` requiere `alertas:reconocer`.
- **Reportes** de rendimiento (p95/p99 por agente y endpoints más lentos) y de disponibilidad contra el SLA (`ARGUS_SLA_OBJETIVO`, 99.9 por defecto).
- **Tiempo real:** WebSocket `/api/v1/argus/ws/metricas-vivo?token=...`.

Los datos viven en memoria desde el arranque (24 h); para histórico largo, un servidor Prometheus debe raspar `/metricas`.
