# Business Rules Agent - Setup Guide

## 📁 Estructura de Carpetas

```
src/
├── agents/
│   ├── business_rules_agent/          ← NUEVA
│   │   ├── __init__.py               (vacío)
│   │   └── agent.py                  (business_rules_agent.py → copiar aquí)
│   ├── database_agent/
│   │   ├── __init__.py
│   │   └── database_agent.py
│   └── apis_agent/
│       ├── __init__.py
│       └── agent.py
│
├── api/
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── apis.py
│   │   └── business_rules.py         ← NUEVA (copiar aquí)
│   └── main.py                       (actualizar imports y routers)
│
└── tests/
    └── unit/
        └── test_business_rules_agent.py  ← NUEVA (copiar aquí)
```

---

## 📝 Pasos de Integración

### 1. Crear carpeta del agente

```bash
mkdir src/agents/business_rules_agent
touch src/agents/business_rules_agent/__init__.py
```

### 2. Copiar archivos

```bash
# Desde /mnt/user-data/outputs/
cp business_rules_agent.py src/agents/business_rules_agent/agent.py
cp business_rules.py src/api/routes/business_rules.py
cp test_business_rules_agent.py tests/unit/test_business_rules_agent.py
```

### 3. Actualizar main.py

Agregar import y router:

```python
# En src/api/main.py - línea de imports

# ✅ AGREGAR:
from src.api.routes import business_rules

# ✅ En app.include_router() section:
app.include_router(database.router)
app.include_router(apis.router)
app.include_router(business_rules.router)  # ← AGREGAR ESTA LÍNEA
```

### 4. Actualizar __init__.py del agente

```python
# src/agents/business_rules_agent/__init__.py

from .agent import (
    BusinessRulesAgent,
    BusinessRule,
    RuleEngine,
    Condition,
    RuleAction,
    RuleStatus,
    OperatorType,
    ActionType,
    RuleEvaluationResult,
)

__all__ = [
    "BusinessRulesAgent",
    "BusinessRule",
    "RuleEngine",
    "Condition",
    "RuleAction",
    "RuleStatus",
    "OperatorType",
    "ActionType",
    "RuleEvaluationResult",
]
```

### 5. Ejecutar la app

```powershell
# PowerShell
.\venv\Scripts\Activate.ps1
python run.py

# O
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

### 6. Verificar en Swagger

Ir a: http://localhost:8000/docs

Deben aparecer bajo `Business Rules Agent`:
- ✅ POST `/api/v1/rules/create`
- ✅ POST `/api/v1/rules/evaluate`
- ✅ GET `/api/v1/rules/list`
- ✅ PUT `/api/v1/rules/{rule_id}`
- ✅ DELETE `/api/v1/rules/{rule_id}`
- ✅ GET `/api/v1/rules/audit`
- ✅ GET `/api/v1/rules/status`
- ✅ GET `/api/v1/rules/health`

---

## 🧪 Ejecutar Tests

```bash
# Todos los tests
pytest tests/unit/test_business_rules_agent.py -v

# Tests específicos
pytest tests/unit/test_business_rules_agent.py::TestRuleCreation -v
pytest tests/unit/test_business_rules_agent.py::TestRuleEvaluation -v

# Con cobertura
pytest tests/unit/test_business_rules_agent.py --cov=src.agents.business_rules_agent
```

---

## 📋 Ejemplos de Uso

### Crear regla de retención ISR

```bash
curl -X POST "http://localhost:8000/api/v1/rules/create" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_id": "retencion_isr_001",
    "name": "ISR Retención 2.5%",
    "description": "Retención sobre facturas HND >= 1000",
    "empresa_id": 100,
    "conditions": [
      {
        "field": "tipo_documento",
        "operator": "eq",
        "value": "factura"
      },
      {
        "field": "empresa_id",
        "operator": "eq",
        "value": 100
      },
      {
        "field": "monto",
        "operator": "gte",
        "value": 1000
      }
    ],
    "actions": [
      {
        "type": "calculate",
        "details": {
          "var": "retencion_isr",
          "formula": "monto * 0.025"
        }
      },
      {
        "type": "set_field",
        "details": {
          "field": "estado",
          "value": "pendiente_retencion"
        }
      },
      {
        "type": "notify",
        "details": {
          "target": "contabilidad",
          "message": "Retención ISR aplicada"
        }
      }
    ]
  }'
```

### Evaluar regla contra contexto

```bash
curl -X POST "http://localhost:8000/api/v1/rules/evaluate" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_id": "retencion_isr_001",
    "context": {
      "tipo_documento": "factura",
      "empresa_id": 100,
      "monto": 5000,
      "cliente_id": 523
    }
  }'
```

Response:
```json
{
  "status": "success",
  "rule_id": "retencion_isr_001",
  "data": {
    "rule_id": "retencion_isr_001",
    "matched": true,
    "context": {...},
    "decisions": [
      "Calculated retencion_isr=125.0",
      "Set estado=pendiente_retencion",
      "Notification to contabilidad: Retención ISR aplicada"
    ],
    "calculated_values": {
      "retencion_isr": 125.0,
      "estado": "pendiente_retencion"
    },
    "evaluated_at": "2026-09-18T..."
  }
}
```

### Listar reglas por empresa

```bash
curl "http://localhost:8000/api/v1/rules/list?empresa_id=100"
```

### Ver historial de evaluaciones

```bash
curl "http://localhost:8000/api/v1/rules/audit?rule_id=retencion_isr_001&limit=50"
```

### Ver estado del agente

```bash
curl "http://localhost:8000/api/v1/rules/status"
```

Response:
```json
{
  "agent_name": "BusinessRulesAgent",
  "version": "0.1.0",
  "status": "operational",
  "rules_loaded": 1,
  "timestamp": "2026-09-18T..."
}
```

---

## 🎯 Reglas Pre-configuradas para DMS Advance

### Plantilla: Retención ISR

```json
{
  "rule_id": "retencion_isr_hnd",
  "name": "Retención ISR - HND",
  "empresa_id": 100,
  "conditions": [
    {"field": "tipo_documento", "operator": "eq", "value": "factura"},
    {"field": "monto", "operator": "gte", "value": 1000}
  ],
  "actions": [
    {
      "type": "calculate",
      "details": {"var": "retencion_isr", "formula": "monto * 0.025"}
    }
  ]
}
```

### Plantilla: Retención Fuente

```json
{
  "rule_id": "retencion_fuente",
  "name": "Retención Fuente - 3%",
  "empresa_id": 100,
  "conditions": [
    {"field": "tipo_documento", "operator": "in", "value": ["factura", "nota_credito"]},
    {"field": "monto", "operator": "gte", "value": 100}
  ],
  "actions": [
    {
      "type": "calculate",
      "details": {"var": "retencion_fuente", "formula": "monto * 0.03"}
    }
  ]
}
```

### Plantilla: Límite de Crédito

```json
{
  "rule_id": "credit_limit_imvesa",
  "name": "Credit Limit Check - Imvesa",
  "empresa_id": 101,
  "conditions": [
    {"field": "saldo_disponible", "operator": "lt", "value": 0},
    {"field": "tipo_cliente", "operator": "eq", "value": "credito"}
  ],
  "actions": [
    {
      "type": "block",
      "details": {"reason": "Límite de crédito excedido"}
    },
    {
      "type": "notify",
      "details": {"target": "cartera", "message": "Cliente excedió límite de crédito"}
    }
  ]
}
```

### Plantilla: Validación de Bodega

```json
{
  "rule_id": "bodega_validation",
  "name": "Bodega Valid Check",
  "empresa_id": 100,
  "conditions": [
    {"field": "bodega_id", "operator": "in", "value": [1, 2, 3, 4]}
  ],
  "actions": [
    {
      "type": "allow"
    }
  ]
}
```

---

## 🔍 Operadores Soportados

| Operador | Descripción | Ejemplo |
|----------|-------------|---------|
| `eq` | Igual | `{"field": "empresa_id", "operator": "eq", "value": 100}` |
| `neq` | No igual | `{"field": "estado", "operator": "neq", "value": "cancelado"}` |
| `gt` | Mayor que | `{"field": "monto", "operator": "gt", "value": 1000}` |
| `gte` | Mayor o igual | `{"field": "monto", "operator": "gte", "value": 1000}` |
| `lt` | Menor que | `{"field": "monto", "operator": "lt", "value": 100}` |
| `lte` | Menor o igual | `{"field": "saldo", "operator": "lte", "value": 500}` |
| `in` | En lista | `{"field": "bodega_id", "operator": "in", "value": [1, 2, 3]}` |
| `not_in` | No en lista | `{"field": "estado", "operator": "not_in", "value": ["cancelado"]}` |
| `contains` | Contiene | `{"field": "nombre", "operator": "contains", "value": "HND"}` |

---

## 🎬 Tipos de Acciones

| Tipo | Descripción | Ejemplo |
|------|-------------|---------|
| `calculate` | Calcula variable | `{"type": "calculate", "details": {"var": "retencion", "formula": "monto * 0.025"}}` |
| `set_field` | Asigna valor | `{"type": "set_field", "details": {"field": "estado", "value": "pendiente"}}` |
| `block` | Bloquea operación | `{"type": "block", "details": {"reason": "Límite excedido"}}` |
| `allow` | Permite operación | `{"type": "allow"}` |
| `notify` | Notifica | `{"type": "notify", "details": {"target": "admin", "message": "..."}}` |
| `log` | Registra en auditoría | `{"type": "log", "details": {"message": "..."}}` |

---

## ✅ Checklist de Integración

- [ ] Crear carpeta `src/agents/business_rules_agent/`
- [ ] Copiar `business_rules_agent.py` como `agent.py`
- [ ] Copiar `business_rules.py` a routes
- [ ] Copiar tests a `tests/unit/`
- [ ] Actualizar `src/api/main.py` con import y router
- [ ] Crear `__init__.py` en business_rules_agent
- [ ] Ejecutar app y verificar Swagger
- [ ] Ejecutar tests
- [ ] Crear reglas iniciales (retenciones, límites)
- [ ] Documentar reglas en Wiki

---

## 📚 Próximos Pasos (Semana 4-5)

1. **Integración con Database Agent**
   - Guardar/cargar reglas desde PostgreSQL
   - Caché de reglas en memoria

2. **Integración con APIs Agent**
   - Generar endpoints dinámicos basados en reglas
   - Validación automática en CRUD

3. **UI Dashboard**
   - Crear/editar reglas desde UI
   - Visualizar auditoría
   - Testear reglas en sandbox

4. **Reglas DMS Advance Reales**
   - Retenciones (ISR, fuente, IVA)
   - Límites de crédito por cliente/empresa
   - Descuentos condicionales
   - Precios por segmento

---

## ❓ Troubleshooting

### Error: `ModuleNotFoundError: No module named 'business_rules_agent'`

**Solución:** Ejecutar desde raíz del proyecto con venv activo

```bash
cd D:\Desarrollo\kinetix-studio
.\venv\Scripts\Activate.ps1
python run.py
```

### Error: `No attribute 'business_rules' in routes`

**Solución:** Verificar que `src/api/main.py` tiene:

```python
from src.api.routes import business_rules
app.include_router(business_rules.router)
```

### Test falla con `NameError: name 'Condition' is not defined`

**Solución:** Verificar imports en `test_business_rules_agent.py`

```python
from src.agents.business_rules_agent.agent import Condition, RuleAction, ...
```

---

## 📞 Soporte

Para preguntas o issues:
- Revisa `/mnt/transcripts/` para historial de sesiones
- Consulta la especificación en `/mnt/user-data/outputs/API-SPECIFICATION.md`
- Ejecuta tests para validar setup
