# 🚀 Guía Rápida: Kinetix Studio en Cursor

## Introducción

**Kinetix Studio** es una fábrica de aplicaciones agéntica que genera aplicaciones empresariales multiplataforma de forma automatizada. Este documento te guía para operarla en **Cursor IDE**.

---

## ¿Qué es Cursor?

Cursor es un IDE basado en VS Code con **integración profunda de IA**. Para Kinetix, lo usamos como:

- **Sistema central de coordinación** de 8 agentes especializados
- **Single source of truth** mediante archivos Composer compartidos
- **Orquestador determinista** sin APIs ocultas ni plataformas externas

---

## Estructura de Carpetas

```
kinetix-studio/
├── .cursorrules                    # 👈 CRÍTICO: Directivas de comportamiento de agentes
├── .cursor/
│   ├── agents/                     # Identidad de cada agente
│   │   ├── daedalus.md            # Orquestador
│   │   ├── aegis.md               # Reglas de negocio
│   │   ├── atlas.md               # Base de datos
│   │   ├── iris.md                # UI/UX
│   │   ├── hermes.md              # APIs
│   │   ├── hephaestus.md          # Desarrollo
│   │   ├── sentinel.md            # QA/Seguridad
│   │   └── chronos.md             # Documentación
│   ├── execution_state.json        # 👈 Estado compartido (RAM del enjambre)
│   ├── metrics.json                # Monitoreo en tiempo real
│   └── schemas/                    # Contratos JSON-Schema entre agentes
├── src/
│   ├── backend/                    # ASP.NET Core o Node.js
│   ├── frontend/                   # React/Vue micro-frontends
│   └── database/                   # SQL Server schemas
├── tests/                          # Suite de validación
├── docs/                           # Documentación generada
└── README.md                       # Punto de entrada
```

---

## Paso 1: Setup Inicial (15 minutos)

### 1.1 Clonar o crear repositorio
```bash
git clone <tu-repo-kinetix> kinetix-studio
cd kinetix-studio
```

### 1.2 Crear estructura `.cursor/`
```bash
mkdir -p .cursor/agents .cursor/schemas
touch .cursor/execution_state.json
touch .cursor/metrics.json
touch .cursorrules
```

### 1.3 Copiar `.cursorrules`
Coloca el archivo `.cursorrules` en la raíz del proyecto. Este archivo **automáticamente** carga los comportamientos de los 8 agentes.

### 1.4 Inicializar `execution_state.json`
```json
{
  "current_phase": "phase_1",
  "current_task_graph": [],
  "agents": {
    "daedalus": { "status": "idle", "input": {}, "output": {}, "last_updated": "2024-01-15T08:00:00Z" },
    "aegis": { "status": "idle", "input": {}, "output": {}, "last_updated": "2024-01-15T08:00:00Z" },
    "atlas": { "status": "idle", "input": {}, "output": {}, "last_updated": "2024-01-15T08:00:00Z" },
    "iris": { "status": "idle", "input": {}, "output": {}, "last_updated": "2024-01-15T08:00:00Z" },
    "hermes": { "status": "idle", "input": {}, "output": {}, "last_updated": "2024-01-15T08:00:00Z" },
    "hephaestus": { "status": "idle", "input": {}, "output": {}, "last_updated": "2024-01-15T08:00:00Z" },
    "sentinel": { "status": "idle", "input": {}, "output": {}, "last_updated": "2024-01-15T08:00:00Z" },
    "chronos": { "status": "idle", "input": {}, "output": {}, "last_updated": "2024-01-15T08:00:00Z" }
  },
  "global_metrics": {
    "total_tokens_consumed": 0,
    "total_tokens_budget": 500000,
    "current_phase_tokens": 0,
    "execution_start_time": "2024-01-15T08:00:00Z",
    "estimated_completion": "2024-04-15T08:00:00Z"
  },
  "circuit_breakers": {
    "active": false,
    "reason": "",
    "human_intervention_required": false
  },
  "errors": []
}
```

### 1.5 Abrir en Cursor
```bash
cursor .
```

Cursor automáticamente cargará `.cursorrules`. Verás que el IDE now "entiende" a los 8 agentes.

---

## Paso 2: Primer Requerimiento (Fase 1, Semana 1)

### Invocación en Cursor

Abre Cursor y haz este prompt:

```
Act as Daedalus (Chief Orchestrator).

REQUIREMENT:
"Build the core foundation for SICITA (appointment booking system for automotive workshops). 
Include: multi-tenant support, role-based access (admin, technician, customer), 
and real-time appointment availability."

CURRENT STATE:
- This is Phase 1 (Weeks 1-4)
- execution_state.json is initialized at .cursor/execution_state.json
- All agents are idle and ready

TASKS:
1. Read execution_state.json and analyze current state
2. Decompose this requirement into atomic subtasks
3. Assign each subtask to the correct agent (Aegis for rules, Atlas for DB, Iris for UI, etc.)
4. Define dependencies between subtasks
5. Create a deterministic task graph
6. Return OUTPUT in DAEDALUS_OUTPUT_FORMAT

OUTPUT MUST BE VALID JSON that can be merged into execution_state.json['current_task_graph']
```

### Daedalus responderá con:

```json
{
  "task_graph": [
    {
      "id": "aegis_phase1_01",
      "agent": "aegis",
      "description": "Define business rules for SICITA: multi-tenancy, roles, appointment constraints",
      "depends_on": [],
      "status": "pending",
      "estimated_tokens": 2000
    },
    {
      "id": "atlas_phase1_01",
      "agent": "atlas",
      "description": "Design database schema: companies, users, appointments, available slots",
      "depends_on": ["aegis_phase1_01"],
      "status": "pending",
      "estimated_tokens": 3000
    },
    ...
  ],
  "estimated_tokens": 15000,
  "execution_plan": "Aegis validates business rules → Atlas designs schema → Iris defines UI flows → ..."
}
```

### Paso 3: Copiar task_graph a execution_state.json

Copia el output de Daedalus directamente en `.cursor/execution_state.json`:

```json
{
  ...
  "current_task_graph": [
    { "id": "aegis_phase1_01", "agent": "aegis", ... },
    { "id": "atlas_phase1_01", "agent": "atlas", ... },
    ...
  ],
  ...
}
```

---

## Paso 4: Invocar Primer Agente (Aegis)

```
Act as Aegis (Business Rules Expert).

CURRENT TASK: aegis_phase1_01
"Define business rules for SICITA: multi-tenancy, roles, appointment constraints"

CONTEXT (from execution_state.json):
{
  "domain": "automotive_workshop",
  "business_rules_description": "Multi-tenant workshop appointment system with 3 roles (admin, technician, customer). 
                                 Constraints: appointments max 2 hours, must respect technician availability,
                                 one appointment per slot per technician.",
  "existing_rules": {}
}

TASKS:
1. Load automotive_workshop domain template
2. Translate abstract rules into concrete, executable rules
3. Check for internal conflicts
4. Generate list of exceptions

OUTPUT in AEGIS_OUTPUT_FORMAT
```

Aegis retornará:
```json
{
  "validated_rules": [
    { "id": "br_001", "domain": "automotive_workshop", "rule": "Each appointment must be <= 2 hours duration", "priority": "critical" },
    { "id": "br_002", "rule": "Each technician can have max 1 active appointment at a time", "priority": "critical" },
    { "id": "br_003", "rule": "Customer can book only if they have active company contract", "priority": "high" },
    ...
  ],
  "conflicts_detected": [],
  "exceptions_allowed": ["admin can override time constraints for emergency service"]
}
```

---

## Paso 5: Update execution_state.json

```bash
# En .cursor/execution_state.json, actualiza el estado de aegis:
{
  "agents": {
    "aegis": {
      "status": "complete",
      "input": { "domain": "automotive_workshop", ... },
      "output": { "validated_rules": [...], ... },
      "last_updated": "2024-01-15T10:30:00Z"
    }
  },
  "current_task_graph": [
    { "id": "aegis_phase1_01", "status": "complete" },  # ← MARCAR COMO COMPLETE
    { "id": "atlas_phase1_01", "status": "pending" },   # ← Ahora Atlas puede comenzar
    ...
  ]
}
```

---

## Paso 6: Continuar con Atlas, Iris, Hermes, ...

Repite el ciclo:

1. **Daedalus** identifica próxima tarea que tiene sus dependencias resueltas
2. Invoca el **agente correspondiente** (Atlas → Iris → Hermes → ...)
3. Agente ejecuta y retorna OUTPUT en su formato
4. Actualiza `execution_state.json` con status = "complete"
5. Vuelve al paso 1

---

## Monitoreo en Tiempo Real

Abre dos pestañas en Cursor:

**Pestaña 1: Ejecución**
```
Act as Daedalus: Check execution_state.json and report current progress:
- Which tasks are complete?
- Which agent should execute next?
- Total tokens consumed so far?
- Are we on budget?
```

**Pestaña 2: Observabilidad**
Abre `.cursor/metrics.json` y monitorea:
```json
{
  "phase": 1,
  "tokens_consumed": 15000,
  "tokens_budget": 500000,
  "tokens_remaining": 485000,
  "agent_executions": [
    { "agent": "daedalus", "count": 5, "avg_latency_ms": 3200, "tokens_per_call": 2000 },
    { "agent": "aegis", "count": 2, "avg_latency_ms": 4100, "tokens_per_call": 3000 },
    ...
  ],
  "circuit_breaker_activations": 0,
  "human_interventions": 0
}
```

---

## Circuito de Interrupción (Circuit Breaker)

Si algo falla:

```
Act as Daedalus: CIRCUIT BREAKER ACTIVATED.

execution_state.json shows:
{
  "circuit_breakers": {
    "active": true,
    "reason": "Sentinel detected 3 critical vulnerabilities in generated code",
    "human_intervention_required": true
  }
}

Analyze the problem and propose remediation steps.
```

Daedalus pausará el enjambre. Revisas el problema, haces ajustes manuales, y luego:

```
Act as Daedalus: RESUME EXECUTION after human intervention.

We fixed the vulnerabilities. Mark circuit_breaker.active = false and continue from 
where we left off.
```

---

## Roadmap: 16 Semanas

| Fase | Semanas | Hitos | Agentes Activos |
|------|---------|-------|-----------------|
| 1    | 1-4     | Setup .cursorrules, Daedalus + Aegis fundamentals | Daedalus, Aegis |
| 2    | 5-8     | Atlas (DB schema), Iris (Design system), business rules | Aegis, Atlas, Iris |
| 3    | 9-12    | Hermes (APIs), Sentinel (Tests), security hardening | Hermes, Sentinel |
| 4    | 13-16   | Hephaestus (Full-stack), Chronos (Docs), SICITA MVP | Hephaestus, Chronos |

---

## Trucos y Mejores Prácticas

### ✓ DO

- Mantén `execution_state.json` como fuente de verdad única
- Copiar/pegar outputs directamente del agente en el formato especificado
- Invocar agentes secuencialmente respetando dependencias (Daedalus lo valida)
- Monitorear tokens en `.cursor/metrics.json` cada 2-3 tareas
- Hacer un commit a Git después de cada tarea completada

### ✗ DON'T

- No improvises prompts sin referencia a AGENT_ROLE y AGENT_TASKS
- No ignores el circuit breaker (es tu red de seguridad)
- No crees tareas que violen las dependencias del task graph
- No uses modelos premium para tareas de bajo nivel (Daedalus maneja Model Cascading)
- No edites execution_state.json manualmente sin entender las consecuencias

---

## Troubleshooting

| Problema | Solución |
|----------|----------|
| Cursor no reconoce .cursorrules | Reinicia Cursor. Verifica que archivo esté en raíz del workspace |
| Agent output no coincide con formato esperado | Copia el texto literalmente en execution_state.json, o pide al agente generar JSON válido |
| Tokens se acaban rápido | Ejecuta `Act as Daedalus: Analyze token consumption and recommend optimizations` |
| Task queda en "pending" para siempre | Verifica que sus dependencias estén marcadas como "complete" |
| Circuit breaker se activa constantemente | Revisa errores en execution_state.json['errors']. Puede haber conflicto irresolvible |

---

## Próximos Pasos

1. **Ahora**: Configura tu repo con esta estructura
2. **Semana 1**: Invoca Daedalus con el requirement de SICITA Phase 1
3. **Semana 2-4**: Ejecuta la cadena de agentes (Aegis → Atlas → Iris)
4. **Semana 5+**: Continúa con Phase 2 (APIs) y Phase 3 (Implementación)

---

## Contacto & Soporte

Si execution_state.json se queda **stuck**:
- Abre la terminal en Cursor: `cat .cursor/execution_state.json` y copia el JSON
- Invoca Daedalus nuevamente: "EXECUTION STUCK. Here's the current state. What went wrong and how do we recover?"

---

**¡Bienvenido a Kinetix Studio en Cursor! 🚀**
