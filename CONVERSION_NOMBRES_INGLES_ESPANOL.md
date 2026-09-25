# 📝 Conversión de Nombres: Inglés → Español

Mapeo completo de nombres de objetos SQL Server para el Motor de Reglas de Negocio.

---

## 📋 TABLAS

| Inglés | Español | Columnas Principales |
|--------|---------|----------------------|
| `business_rules` | `reglas_negocio` | `id_regla`, `nombre`, `nivel_alcance`, `prioridad` |
| `rule_conditions` | `condiciones_regla` | `id_condicion`, `campo`, `operador`, `valor` |
| `rule_actions` | `acciones_regla` | `id_accion`, `tipo_accion`, `detalles`, `orden_ejecucion` |
| `rule_audit_log` | `auditoria_evaluacion_reglas` | `id_auditoria`, `decision`, `condiciones_cumplidas` |
| `rule_evaluation_cache` | `cache_evaluacion_reglas` | `id_cache`, `hash_contexto`, `resultado_cache` |
| `rule_inheritance` | `herencia_reglas` | `id_herencia`, `id_regla_padre`, `id_regla_hija` |

---

## 🔧 STORED PROCEDURES

| Inglés | Español |
|--------|---------|
| `sp_create_business_rule` | `sp_crear_regla_negocio` |
| `sp_evaluate_rule_hierarchy` | `sp_evaluar_regla_jerarquica` |
| `sp_list_rules_by_scope` | `sp_listar_reglas_por_alcance` |
| `sp_get_audit_log` | `sp_obtener_auditoria` |
| `sp_update_business_rule` | `sp_actualizar_regla_negocio` |
| `sp_delete_business_rule` | `sp_eliminar_regla_negocio` |

---

## 📊 VISTAS

| Inglés | Español |
|--------|---------|
| `vw_rules_by_empresa` | `vw_reglas_por_empresa` |
| `vw_audit_summary` | `vw_resumen_auditoria` |
| `vw_active_rules_by_level` | `vw_reglas_activas_por_nivel` |

---

## 🔑 COLUMNAS - REGLAS_NEGOCIO

| Inglés | Español | Tipo | Notas |
|--------|---------|------|-------|
| `rule_id` | `id_regla` | NVARCHAR(50) | Primary Key |
| `rule_name` | `nombre` | NVARCHAR(255) | Nombre legible |
| `rule_description` | `descripcion` | NVARCHAR(MAX) | Descripción |
| `scope_level` | `nivel_alcance` | NVARCHAR(20) | 'global', 'linea_negocio', 'empresa' |
| `business_line` | `linea_negocio` | NVARCHAR(50) | RETAIL, AUTOMOTRIZ, etc |
| `company_id` | `id_empresa` | INT | De Advance ERP |
| `priority` | `prioridad` | INT | 1-100 |
| `allow_override` | `permite_override` | BIT | Booleano |
| `inherits_from` | `hereda_de` | NVARCHAR(MAX) | JSON array |
| `status` | `estado` | NVARCHAR(20) | activa, inactiva, prueba, archivada |
| `version` | `version` | INT | Control de versiones |
| `created_at` | `fecha_creacion` | DATETIME | Auditoría |
| `created_by` | `creada_por` | NVARCHAR(100) | Usuario |
| `updated_at` | `fecha_actualizacion` | DATETIME | Auditoría |
| `updated_by` | `actualizada_por` | NVARCHAR(100) | Usuario |

---

## 🎯 COLUMNAS - CONDICIONES_REGLA

| Inglés | Español | Tipo | Notas |
|--------|---------|------|-------|
| `condition_id` | `id_condicion` | INT | Auto-increment |
| `rule_id` | `id_regla` | NVARCHAR(50) | Foreign Key |
| `field_name` | `campo` | NVARCHAR(100) | Campo a evaluar |
| `operator` | `operador` | NVARCHAR(20) | eq, neq, gt, gte, lt, lte, en, no_en, contiene, regex |
| `field_value` | `valor` | NVARCHAR(MAX) | Valor de comparación |
| `evaluation_order` | `orden_evaluacion` | INT | Secuencia |
| `logical_operator` | `operador_logico` | NVARCHAR(10) | 'Y' (AND), 'O' (OR) |

---

## 🎬 COLUMNAS - ACCIONES_REGLA

| Inglés | Español | Tipo | Notas |
|--------|---------|------|-------|
| `action_id` | `id_accion` | INT | Auto-increment |
| `rule_id` | `id_regla` | NVARCHAR(50) | Foreign Key |
| `action_type` | `tipo_accion` | NVARCHAR(50) | calcular, asignar_campo, bloquear, permitir, notificar, registrar |
| `action_details` | `detalles` | NVARCHAR(MAX) | JSON con detalles |
| `execution_order` | `orden_ejecucion` | INT | Secuencia |
| `is_critical` | `es_critica` | BIT | ¿Si falla, falla la regla? |

---

## 📝 COLUMNAS - AUDITORIA_EVALUACION_REGLAS

| Inglés | Español | Tipo | Notas |
|--------|---------|------|-------|
| `audit_id` | `id_auditoria` | BIGINT | Primary Key |
| `rule_id` | `id_regla` | NVARCHAR(50) | Foreign Key |
| `scope_level` | `nivel_alcance` | NVARCHAR(20) | Global, línea, empresa |
| `business_line` | `linea_negocio` | NVARCHAR(50) | Contexto |
| `company_id` | `id_empresa` | INT | Contexto |
| `context_data` | `datos_contexto` | NVARCHAR(MAX) | JSON con contexto |
| `conditions_matched` | `condiciones_cumplidas` | BIT | Booleano |
| `actions_executed` | `acciones_ejecutadas` | NVARCHAR(MAX) | JSON array |
| `calculated_values` | `valores_calculados` | NVARCHAR(MAX) | JSON con resultados |
| `decision` | `decision` | NVARCHAR(MAX) | permitida, bloqueada, requiere_aprobacion |
| `decision_log` | `log_decisiones` | NVARCHAR(MAX) | JSON array |
| `evaluation_time` | `fecha_evaluacion` | DATETIME | Cuándo se evaluó |
| `evaluated_by` | `evaluada_por` | NVARCHAR(100) | Usuario/sistema |
| `execution_time_ms` | `tiempo_ejecucion_ms` | INT | Performance |

---

## 💾 COLUMNAS - CACHE_EVALUACION_REGLAS

| Inglés | Español | Tipo | Notas |
|--------|---------|------|-------|
| `cache_id` | `id_cache` | BIGINT | Primary Key |
| `rule_id` | `id_regla` | NVARCHAR(50) | Foreign Key |
| `context_hash` | `hash_contexto` | NVARCHAR(64) | SHA-256 |
| `cached_result` | `resultado_cache` | NVARCHAR(MAX) | JSON |
| `cached_at` | `fecha_cache` | DATETIME | Cuándo se cachó |
| `expires_at` | `fecha_expiracion` | DATETIME | TTL |

---

## 🔗 COLUMNAS - HERENCIA_REGLAS

| Inglés | Español | Tipo | Notas |
|--------|---------|------|-------|
| `inheritance_id` | `id_herencia` | INT | Primary Key |
| `parent_rule_id` | `id_regla_padre` | NVARCHAR(50) | Regla nivel superior |
| `child_rule_id` | `id_regla_hija` | NVARCHAR(50) | Regla nivel inferior |
| `override_priority` | `prioridad_override` | INT | Precedencia |

---

## 🔍 ÍNDICES

| Inglés | Español |
|--------|---------|
| `idx_business_rules_scope` | `idx_alcance` |
| `idx_business_rules_status` | `idx_estado` |
| `idx_business_rules_priority` | `idx_prioridad` |
| `idx_rule_conditions_rule` | `idx_id_regla` (conditions) |
| `idx_rule_actions_rule` | `idx_id_regla` (actions) |
| `idx_rule_audit_log_rule` | `idx_id_regla` (audit) |
| `idx_rule_audit_log_company` | `idx_id_empresa` |
| `idx_rule_audit_log_decision` | `idx_decision` |
| `idx_rule_evaluation_cache` | `idx_regla_contexto` |

---

## 🔌 PARÁMETROS DE STORED PROCEDURES

### `sp_crear_regla_negocio`

| Inglés | Español | Tipo |
|--------|---------|------|
| `@rule_id` | `@id_regla` | NVARCHAR(50) |
| `@rule_name` | `@nombre` | NVARCHAR(255) |
| `@rule_description` | `@descripcion` | NVARCHAR(MAX) |
| `@scope_level` | `@nivel_alcance` | NVARCHAR(20) |
| `@business_line` | `@linea_negocio` | NVARCHAR(50) |
| `@company_id` | `@id_empresa` | INT |
| `@priority` | `@prioridad` | INT |
| `@created_by` | `@creada_por` | NVARCHAR(100) |
| `@json_conditions` | `@json_condiciones` | NVARCHAR(MAX) |
| `@json_actions` | `@json_acciones` | NVARCHAR(MAX) |

### `sp_evaluar_regla_jerarquica`

| Inglés | Español | Tipo |
|--------|---------|------|
| `@rule_id` | `@id_regla` | NVARCHAR(50) |
| `@company_id` | `@id_empresa` | INT |
| `@business_line` | `@linea_negocio` | NVARCHAR(50) |
| `@json_context` | `@json_contexto` | NVARCHAR(MAX) |
| `@evaluated_by` | `@evaluada_por` | NVARCHAR(100) |

### `sp_listar_reglas_por_alcance`

| Inglés | Español | Tipo |
|--------|---------|------|
| `@scope_level` | `@nivel_alcance` | NVARCHAR(20) |
| `@business_line` | `@linea_negocio` | NVARCHAR(50) |
| `@company_id` | `@id_empresa` | INT |
| `@status` | `@estado` | NVARCHAR(20) |

### `sp_obtener_auditoria`

| Inglés | Español | Tipo |
|--------|---------|------|
| `@rule_id` | `@id_regla` | NVARCHAR(50) |
| `@company_id` | `@id_empresa` | INT |
| `@days` | `@dias` | INT |
| `@limit` | `@limite` | INT |

---

## 🌐 OPERADORES (SIN CAMBIO)

Los operadores se usan en **español descriptivo** pero mantienen códigos internos:

| Código Interno | Español Descriptivo | Ejemplo |
|---|---|---|
| `eq` | Igual a | `operador = 'eq'`, `valor = 'VIP'` |
| `neq` | No igual a | `operador = 'neq'`, `valor = 'BLOQUEADO'` |
| `gt` | Mayor que | `operador = 'gt'`, `valor = '100'` |
| `gte` | Mayor o igual a | `operador = 'gte'`, `valor = '1000'` |
| `lt` | Menor que | `operador = 'lt'`, `valor = '50'` |
| `lte` | Menor o igual a | `operador = 'lte'`, `valor = '100000'` |
| `en` | En lista | `operador = 'en'`, `valor = 'factura,nota_credito'` |
| `no_en` | No en lista | `operador = 'no_en'`, `valor = 'bloqueado,cancelado'` |
| `contiene` | Contiene | `operador = 'contiene'`, `valor = 'CASAB'` |
| `regex` | Expresión regular | `operador = 'regex'`, `valor = '^[A-Z]{3}$'` |

---

## 🎯 TIPOS DE ACCIONES (SIN CAMBIO)

Los tipos de acciones se usan en **español descriptivo** pero mantienen códigos internos:

| Código Interno | Español Descriptivo | Ejemplo |
|---|---|---|
| `calcular` | Calcular valor | `tipo_accion = 'calcular'`, `detalles: {variable: "retencion", formula: "monto * 0.025"}` |
| `asignar_campo` | Asignar campo | `tipo_accion = 'asignar_campo'`, `detalles: {campo: "estado", valor: "descuento_aplicado"}` |
| `bloquear` | Bloquear operación | `tipo_accion = 'bloquear'`, `detalles: {razon: "Límite excedido"}` |
| `permitir` | Permitir operación | `tipo_accion = 'permitir'` |
| `notificar` | Enviar notificación | `tipo_accion = 'notificar'`, `detalles: {destino: "gerencia", mensaje: "..."}` |
| `registrar` | Registrar en log | `tipo_accion = 'registrar'`, `detalles: {mensaje: "..."}` |

---

## 📐 ESTADOS (SIN CAMBIO - Códigos Internos)

Los estados usan códigos internos en minúsculas:

| Código | Español | Descripción |
|--------|---------|-------------|
| `activa` | Activa | Regla evaluada en operaciones normales |
| `inactiva` | Inactiva | Regla deshabilitada temporalmente |
| `prueba` | Prueba | Regla en fase de testing |
| `archivada` | Archivada | Regla soft-deleted |

---

## 🔄 Migración de Código Existente

Si tienes código que usa los nombres en inglés, aquí está el mapeo para reemplazo global:

```python
# Script de búsqueda y reemplazo (Python)

replacements = {
    # Tablas
    'business_rules': 'reglas_negocio',
    'rule_conditions': 'condiciones_regla',
    'rule_actions': 'acciones_regla',
    'rule_audit_log': 'auditoria_evaluacion_reglas',
    'rule_evaluation_cache': 'cache_evaluacion_reglas',
    'rule_inheritance': 'herencia_reglas',
    
    # Stored Procedures
    'sp_create_business_rule': 'sp_crear_regla_negocio',
    'sp_evaluate_rule_hierarchy': 'sp_evaluar_regla_jerarquica',
    'sp_list_rules_by_scope': 'sp_listar_reglas_por_alcance',
    'sp_get_audit_log': 'sp_obtener_auditoria',
    'sp_update_business_rule': 'sp_actualizar_regla_negocio',
    'sp_delete_business_rule': 'sp_eliminar_regla_negocio',
    
    # Vistas
    'vw_rules_by_empresa': 'vw_reglas_por_empresa',
    'vw_audit_summary': 'vw_resumen_auditoria',
    'vw_active_rules_by_level': 'vw_reglas_activas_por_nivel',
}
```

---

## ✅ Checklist de Migración

- [ ] Reemplazar nombres de tablas en DDL
- [ ] Reemplazar nombres de SPs en DDL
- [ ] Reemplazar nombres de vistas en DDL
- [ ] Actualizar queries Python/FastAPI
- [ ] Actualizar documentación
- [ ] Probar SPs con datos de ejemplo
- [ ] Actualizar test unitarios
- [ ] Migrar datos existentes (si aplica)

---

Documento de referencia para el Motor de Reglas de Negocio en SQL Server 🗄️
