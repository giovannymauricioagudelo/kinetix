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

## Nexus: datos

Código: `src/agents/database_agent/` · API: `/api/v1/nexus` (todo requiere token de Sentinel salvo `GET /salud`) · Permisos: `NEXUS_MATRIX_SCHEMA.sql`.

- **Esquema.** `GET /esquema/tablas` y `GET /esquema/tablas/{esquema.tabla}` (columnas, clave primaria, índices, claves foráneas, filas). Requiere `esquema:ver`.
- **DDL de SQL Server.** `POST /esquema/ddl` genera el script idempotente (PK CLUSTERED, índices `empresa_id`/`bodega_id`, columnas de auditoría, descripción como propiedad extendida) sin ejecutarlo; `POST /esquema/tablas` lo aplica (requiere `esquema:modificar`). Los nombres solo admiten letras, números y `_`, y los valores por defecto se traducen a literales seguros.
- **Procedimientos almacenados.** `GET /procedimientos` y `GET /procedimientos/{nombre}` (parámetros y definición). `POST /procedimientos/{nombre}/ejecutar` (requiere `procedimientos:ejecutar`) solo acepta procedimientos de usuario y parámetros declarados, siempre parametrizados; devuelve los conjuntos de resultado con tope de `NEXUS_MAX_ROWS` filas.
- **Respaldos.** `POST /respaldos` hace `BACKUP DATABASE ... COPY_ONLY, CHECKSUM` y lo verifica con `RESTORE VERIFYONLY`; `GET /respaldos` lista el historial de msdb. Requiere `respaldos:gestionar`.
- Crear tablas, ejecutar procedimientos y respaldar queda en `bitacora_auditoria` de Sentinel (sin los valores de los parámetros).

## Matrix: reglas de negocio

Código: `src/agents/business_rules_agent/` · API: `/api/v1/matrix` (todo requiere token de Sentinel salvo `GET /salud`) · Tablas: `reglas_negocio`, `condiciones_regla`, `acciones_regla`, `auditoria_evaluacion_reglas`.

- **Reglas jerárquicas.** Alcance `global`, `linea_negocio` o `empresa`, con prioridad. `GET /reglas`, `GET /reglas/{id}` (requieren `reglas:ver`); `POST /reglas`, `PUT /reglas/{id}`, `DELETE /reglas/{id}` (archiva; requieren `reglas:gestionar`).
- **Motor.** Operadores `eq, neq, gt, gte, lt, lte, in, not_in, contains, regex`, condiciones encadenadas con `AND`/`OR`, y acciones `calculate, set_field, notify, block, allow, log`. Las fórmulas de `calculate` usan un evaluador aritmético propio (números, variables del contexto, `+ - * / // % **`, `min/max/round/abs`); nunca `eval`.
- **Evaluación.** `POST /reglas/{id}/evaluar` evalúa una regla; `POST /evaluar` evalúa todas las reglas activas que aplican a la empresa y línea de negocio, de mayor a menor prioridad, y devuelve la decisión global (`bloqueada` si alguna bloquea), los valores calculados y las notificaciones. Requieren `reglas:evaluar` y cada evaluación queda en `auditoria_evaluacion_reglas`.
- **Pruebas sin efectos.** `POST /reglas/{id}/probar` corre escenarios con resultado esperado sin escribir auditoría.
- **Seguimiento.** `GET /auditoria` y `GET /analitica` (evaluaciones, bloqueos, tasa de cumplimiento, tiempo promedio y reglas activas sin uso).

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
