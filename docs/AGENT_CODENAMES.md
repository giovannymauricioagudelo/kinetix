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

## Agentes de plataforma: Aurora, Vector, Prism, Orbit e Insight

Los cinco siguen el mismo patrón que Nexus y Matrix: todo requiere token de Sentinel salvo `GET /salud`, las escrituras quedan en `bitacora_auditoria`, persisten en SQL Server (`PLATFORM_AGENTS_SCHEMA.sql`: tablas, permisos y asignación a `rol_admin`/`rol_auditor`) y aceptan `<AGENTE>_REPOSITORY=memory` para desarrollo y pruebas. Vector, Prism y Orbit trabajan sobre el repositorio git de `KINETIX_REPO_PATH` (la raíz del proyecto por defecto).

### Aurora: diseño UI/UX

Código: `src/agents/interface_design_agent/` · API: `/api/v1/aurora` · Permisos: `diseno:ver`, `diseno:gestionar` · Tablas: `aurora_sistemas`, `aurora_componentes`.

- **Sistemas de diseño por empresa** (`/sistemas`): paletas generadas (50–900) a partir de colores base, tipografía, espaciado, radios, sombras, breakpoints 320/768/1024 y temas claro/oscuro. Los tokens se versionan con control optimista (`PUT /sistemas/{id}/tokens` exige la versión leída; 409 si cambió).
- **Accesibilidad WCAG 2.1.** `POST /contraste` calcula la relación de contraste; `POST /sistemas/{id}/accesibilidad` audita todos los pares texto/fondo del sistema y, con `aplicar`, corrige los colores hasta cumplir AA o AAA. Los componentes (`PUT /sistemas/{id}/componentes`) se revisan contra criterios como etiquetas (1.3.1), foco (2.4.3/2.4.7) y trampas de teclado (2.1.2).
- **Exportación** (`GET /sistemas/{id}/exportar?formato=`): `css` (variables y `[data-theme="dark"]`), `scss`, `tailwind`, `json` (formato DTCG) y `android` (XML).
- **Layouts y pantallas.** `POST /sistemas/{id}/layout` (`grid`, `sidebar`, `stack`, con media queries) y `POST /sistemas/{id}/pantallas` (`login`, `dashboard`, `list`, `form`): HTML semántico y accesible, con todo el texto escapado.

### Vector: desarrollo

Código: `src/agents/development_agent/` · API: `/api/v1/vector` · Permisos: `codigo:ver`, `codigo:escribir` · Tabla: `vector_analisis`.

- **Análisis estático por AST** (`POST /analisis` sobre rutas del repositorio, `POST /analisis/codigo` sobre un fragmento): complejidad ciclomática, anidamiento, funciones largas o con muchos parámetros, `eval`/`exec`, `subprocess` con `shell=True`, SQL armado con f-strings, secretos en el código, `except` vacíos, peticiones HTTP sin timeout y docstrings faltantes. Devuelve una puntuación de 0 a 10; el historial queda en `GET /analisis`. Prism usa los hallazgos críticos en su compuerta.
- **Git de solo lectura:** `GET /ramas`, `GET /commits`, `GET /diff`.
- **Escritura controlada:** `POST /ramas` y `POST /commits` crean ramas `feature/`, `fix/`, `chore/` o `vector/` y commits con plumbing de git (sin checkout y sin tocar tu índice ni tu árbol de trabajo). `master` y `main` nunca se modifican; solo se escribe bajo `src`, `tests`, `scripts`, `docs` y `sql`; el mensaje termina con la marca `ddMMyyyy HH:MM:SS`.
- **Plantillas** (`POST /plantillas/vista-previa` y `/plantillas/aplicar`): a partir de un módulo, una entidad y sus campos genera repositorio (memoria + SQL Server), servicio, dependencias, rutas con permisos de Sentinel, pruebas y el DDL con PK CLUSTERED, y lo commitea en una rama.

### Prism: calidad

Código: `src/agents/qa_agent/` · API: `/api/v1/prism` · Permisos: `calidad:ver`, `calidad:ejecutar` · Tabla: `prism_ejecuciones`.

- **Pruebas reales.** `GET /pruebas` descubre las pruebas; `POST /ejecuciones` (202) lanza pytest en segundo plano, con cobertura opcional (JUnit + coverage JSON), una ejecución a la vez. `GET /ejecuciones` y `GET /ejecuciones/{id}` muestran el resultado, los fallos y los archivos con menos cobertura. Las ejecuciones que quedaron colgadas por un reinicio se marcan como `error` al arrancar.
- **Análisis estático:** `POST /analisis-estatico` corre flake8 con la configuración `.flake8` del proyecto.
- **Conflictos de reglas de Matrix:** `GET /reglas/conflictos` detecta reglas duplicadas, bloquear contra permitir, asignaciones contradictorias y cálculos sobrescritos entre reglas activas cuyos alcances y condiciones pueden coincidir.
- **Compuerta de calidad** (`GET /compuerta?referencia=`): aprueba un commit solo si tiene una suite completa aprobada con cobertura ≥ `PRISM_COBERTURA_MINIMA` (80 por defecto), se ejecutó con el árbol limpio y Vector no reporta hallazgos críticos. Orbit la consulta antes de cada despliegue.
- **Métricas:** `GET /metricas` (tasa de aprobación, cobertura actual, duración promedio y pruebas que más fallan).

### Orbit: despliegues

Código: `src/agents/git_deployment_agent/` · API: `/api/v1/orbit` · Permisos: `despliegues:ver`, `despliegues:ejecutar` · Tabla: `orbit_despliegues`.

- **Release** (`POST /despliegues`, entornos `staging` y `produccion`): el commit debe pasar la compuerta de Prism y estar integrado en `ORBIT_RELEASE_BRANCH` (master); producción exige además un despliegue exitoso del mismo commit en staging. Se crea un tag anotado `release/<entorno>/<AAAAMMDD-HHMMSS>` cuyo mensaje termina con la marca `ddMMyyyy HH:MM:SS`. Con `publicar_tag` se empuja a `origin`; si el push falla, el tag local se borra y el despliegue queda `fallido`.
- **Rechazos auditados:** si no se cumple una condición, el intento queda en el historial como `rechazado` y la API responde 409 con el detalle.
- **Reversión** (`POST /despliegues/reversion`): vuelve a desplegar el commit de un despliegue exitoso anterior (el previo al actual, o el indicado) con un tag nuevo; exige motivo.
- **Verificación:** `GET /despliegues/verificacion` comprueba que los tags de lo desplegado existan y apunten al commit registrado, y consulta el estado de GitHub.
- **GitHub Actions** (con `GITHUB_TOKEN`): `lanzar_workflow` dispara `ORBIT_GITHUB_WORKFLOW` sobre el tag publicado; `GET /github/workflows` y `GET /github/estado/{referencia}` muestran las ejecuciones y los checks.

### Insight: reportes

Código: `src/agents/reporting_agent/` · API: `/api/v1/insight` · Permisos: `reportes:ver`, `reportes:generar`, `reportes:programar` · Tablas: `insight_reportes`, `insight_programaciones`.

- **Catálogo cerrado** (`GET /catalogo`), nunca SQL libre: evaluaciones y estado de reglas (Matrix), auditoría de seguridad y accesos de usuarios (Sentinel, solo tu empresa y con `auditoria:ver`), rendimiento y disponibilidad (Argus), calidad de pruebas (Prism), despliegues (Orbit) y análisis de código (Vector). Los parámetros se validan contra el catálogo.
- **Generar y exportar:** `POST /reportes/generar` (con `guardar` queda en el historial de la empresa) y `POST /reportes/exportar?formato=csv|json`. El CSV lleva BOM para Excel y neutraliza celdas que empiezan con `=`, `+`, `-` o `@` (inyección de fórmulas).
- **Reportes guardados por empresa:** listar, ver, exportar y borrar; se purgan tras `INSIGHT_RETENCION_DIAS`.
- **Programaciones** diarias, semanales o mensuales a una hora UTC. Corren cada `INSIGHT_SCHEDULER_INTERVAL_SECONDS` con la identidad de quien las creó y vuelven a verificar `reportes:programar`; si se le retiró el permiso, la ejecución queda en error. Con varias instancias, cada ejecución se reclama de forma atómica para no duplicarse.
- **KPIs** (`GET /kpis`): resumen de reglas, API, calidad, despliegues y código. Si un agente no responde, su sección aparece como no disponible y el resto se entrega igual.

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
