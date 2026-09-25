# 📋 ESPECIFICACIÓN DETALLADA DE AGENTES
## Fábrica de Aplicaciones Inteligente

**Versión:** 0.1  
**Fecha:** Septiembre 03, 2026

> **Identidad pública (codenames):** Nexus, Synapse, Matrix, Insight, Prism, Orbit, Vector.  
> Tabla completa y fuente de verdad en código: `docs/AGENT_CODENAMES.md` y `src/agents/agent_catalog.py`.

---

## ÍNDICE DE AGENTES

1. **Nexus** (Database Agent) - Gestión de esquemas y datos
2. **Synapse** (APIs Agent) - Generación de endpoints
3. **Matrix** (Business Rules Agent) - Lógica de negocio
4. **Insight** (Reporting Agent) - Reportería y visualización
5. **Prism** (QA Agent) - Control de calidad
6. **Orbit** (Git Deployment Agent) - Versionado y despliegue
7. **Vector** (Development Agent) - Desarrollo y PRs
8. **Custom AI Agents** - Agentes de negocio personalizados

---

## 1️⃣ DATABASE AGENT (DB-Agent)

### 1.1 Propósito
Crear, mantener y evolucionar esquemas de bases de datos multisector, aplicando normalizacion, optimización y auditoría.

### 1.2 Responsabilidades Clave
```
Inputs (Acepta):
├─ Definiciones de entidades (nombre, atributos, relaciones)
├─ Requisitos de multisector (Empresa, Bodega, Centro Costo)
├─ Estándares de normalización (3NF)
├─ Cambios solicitud (Agente Reglas, Agente APIs)
└─ Validaciones de integridad

Processing:
├─ Generar DDL (Create Table, Alter, Drop)
├─ Diseñar índices y constraints
├─ Aplicar particiones (si aplica)
├─ Gestionar migraciones versionadas
├─ Auditar cambios (quién, qué, cuándo, por qué)
└─ Validar impacto en aplicaciones existentes

Outputs (Produce):
├─ Script SQL versionado
├─ Diagrama ER actualizado
├─ Documentación de esquema
├─ Plan de migración
└─ Reporte de impacto
```

### 1.3 Interfaz de Entrada/Salida

**Evento de Entrada - Crear Tabla Multisector:**
```
{
  "agent_id": "db-agent",
  "trigger": "create_entity",
  "payload": {
    "entity_name": "Clientes",
    "multisector": ["Empresa", "Bodega"],
    "attributes": [
      {"name": "ClienteID", "type": "INT", "pk": true},
      {"name": "Nombre", "type": "NVARCHAR(200)", "required": true},
      {"name": "NIT", "type": "VARCHAR(20)", "unique": true},
      {"name": "Activo", "type": "BIT", "default": 1}
    ],
    "relationships": [
      {"foreign_entity": "Empresa", "cardinality": "N:1"}
    ]
  },
  "requested_by": "business-rules-agent",
  "timestamp": "2026-09-03T10:30:00Z"
}
```

**Evento de Salida - Schema Creado:**
```
{
  "agent_id": "db-agent",
  "event_type": "schema_created",
  "payload": {
    "entity": "Clientes",
    "ddl_script": "CREATE TABLE Clientes...",
    "version": "1.0.0",
    "migration_id": "mig_2026_09_001",
    "audit_trail": {
      "created_by": "db-agent",
      "created_at": "2026-09-03T10:30:15Z",
      "reason": "Nueva entidad: Gestión de Clientes"
    },
    "depends_on": ["Empresas", "Bodegas"],
    "impact_assessment": {
      "affected_views": [],
      "affected_procedures": [],
      "requires_data_migration": false
    }
  }
}
```

### 1.4 Reglas de Negocio del Agente
- ✅ Toda tabla multisector debe tener campos: EmpresaID, BodegaID, FechaCreacion, FechaModificacion, UsuarioModificacion
- ✅ Claves primarias siempre INT + IDENTITY(1,1)
- ✅ Relaciones N:1 requieren índices automáticos
- ✅ No permitir cambios que rompan aplicaciones en producción sin aprobación
- ✅ Auditar cada cambio DDL

### 1.5 Integraciones
```
⬅️  Recibe de:
    - Business Rules Agent (nuevas validaciones = nuevas columnas)
    - APIs Agent (cambios en tipos de datos)
    - QA Agent (validación de migraciones)

➡️  Envía a:
    - APIs Agent (notificación de schema actualizado)
    - Reporting Agent (nuevas fuentes de datos)
    - QA Agent (script de migración para testing)
```

### 1.6 Métricas de Éxito
- ✅ 100% de DDL generado sigue estándares SQL Server
- ✅ 0 errores de migración en producción
- ✅ Documentación de schema siempre al día
- ✅ Tiempo DDL → Validación < 5 minutos

---

## 2️⃣ APIS AGENT (API-Agent)

### 2.1 Propósito
Generar automáticamente endpoints RESTful, SOAP y documentación OpenAPI a partir de esquema de BD y reglas de negocio.

### 2.2 Responsabilidades Clave
```
Inputs:
├─ Schema de base de datos
├─ Reglas de negocio (validaciones, transformaciones)
├─ Requisitos de autenticación/autorización
├─ Especificaciones de versioning
└─ Rate limiting & throttling

Processing:
├─ Generar CRUD endpoints RESTful
├─ Aplicar validaciones de reglas de negocio
├─ Implementar paginación, filtros, búsqueda
├─ Definir autenticación (JWT, OAuth2)
├─ Generar documentación OpenAPI 3.0
├─ Crear tests de API
└─ Aplicar versionamiento (v1, v2, v3)

Outputs:
├─ Especificación OpenAPI (YAML/JSON)
├─ Colección Postman
├─ Código deployable (Framework agnóstico)
├─ Tests automáticos
└─ Documentación interactiva (Swagger UI)
```

### 2.3 Interfaz de Entrada/Salida

**Evento: Generar API para Entidad**
```
{
  "agent_id": "apis-agent",
  "trigger": "generate_api",
  "payload": {
    "entity": "Clientes",
    "operations": ["CREATE", "READ", "UPDATE", "DELETE", "LIST"],
    "authentication": "jwt",
    "rate_limit": "1000 req/hour",
    "pagination": {
      "default_page_size": 50,
      "max_page_size": 500
    },
    "filters": [
      {"field": "Estado", "type": "enum", "values": ["Activo", "Inactivo"]},
      {"field": "FechaCreacion", "type": "date_range"}
    ],
    "api_version": "v1",
    "documentation": true
  },
  "requested_by": "orchestrator",
  "timestamp": "2026-09-03T10:35:00Z"
}
```

**Evento: API Generada**
```
{
  "agent_id": "apis-agent",
  "event_type": "api_generated",
  "payload": {
    "entity": "Clientes",
    "endpoints": [
      {
        "method": "GET",
        "path": "/v1/clientes",
        "operation": "LIST",
        "description": "Listar clientes con filtros y paginación"
      },
      {
        "method": "POST",
        "path": "/v1/clientes",
        "operation": "CREATE",
        "description": "Crear nuevo cliente"
      },
      {
        "method": "GET",
        "path": "/v1/clientes/{id}",
        "operation": "READ",
        "description": "Obtener detalles de cliente"
      },
      {
        "method": "PUT",
        "path": "/v1/clientes/{id}",
        "operation": "UPDATE",
        "description": "Actualizar cliente"
      },
      {
        "method": "DELETE",
        "path": "/v1/clientes/{id}",
        "operation": "DELETE",
        "description": "Desactivar cliente"
      }
    ],
    "openapi_spec": "https://api.app.com/docs/openapi.json",
    "postman_collection": "clientes-v1.postman.json",
    "swagger_ui": "https://api.app.com/swagger",
    "deployment_artifact": "api-clientes-v1.zip",
    "tests_included": true
  }
}
```

### 2.4 Reglas de Negocio del Agente
- ✅ Toda API requiere autenticación (excepto health checks)
- ✅ Todas las respuestas incluyen status codes estándar (200, 201, 400, 401, 404, 500)
- ✅ Errores siguen RFC 7807 (Problem Details)
- ✅ Paginación siempre include: total, page, pageSize, hasMore
- ✅ Documentación OpenAPI genera automáticamente

### 2.5 Integraciones
```
⬅️  Recibe de:
    - Database Agent (cambios de schema)
    - Business Rules Agent (validaciones a aplicar)
    - QA Agent (requisitos de testing)

➡️  Envía a:
    - QA Agent (tests de API)
    - Git Deployment Agent (código)
    - Reporting Agent (datos para reportes)
```

### 2.6 Métricas de Éxito
- ✅ 100% de endpoints tienen documentación OpenAPI
- ✅ 0 datos sensibles en logs
- ✅ Latencia promedio < 200ms
- ✅ Uptime > 99.5%

---

## 3️⃣ BUSINESS RULES AGENT (Rules-Agent)

### 3.1 Propósito
Definir, versionar y ejecutar lógica de negocio en lenguaje declarativo (no código), propagando cambios automáticamente a APIs, BD y reportes.

### 3.2 Responsabilidades Clave
```
Inputs:
├─ Definiciones de reglas (IF-THEN-ELSE, fórmulas)
├─ Contexto multisector (Empresa, país, industria)
├─ Catálogos de valores (Tipos de clientes, estados)
├─ Configuraciones locales (Retenciones DIAN, IVA, etc.)
└─ Cambios de políticas

Processing:
├─ Compilar reglas a formato ejecutable
├─ Detectar conflictos y ciclos
├─ Aplicar reglas en orden correcto
├─ Registrar evaluaciones en auditoría
├─ Propagar cambios (API, BD, reportes)
└─ Versionar cada cambio

Outputs:
├─ Motor de reglas compiladas
├─ Documentación legible
├─ APIs de validación
├─ Auditoría de evaluaciones
└─ Notificaciones de cambios
```

### 3.3 Interfaz de Entrada/Salida

**Evento: Definir Regla de Negocio**
```
{
  "agent_id": "business-rules-agent",
  "trigger": "define_rule",
  "payload": {
    "rule_name": "Aplicar Retención DIAN",
    "rule_type": "validation",
    "entity": "Facturas",
    "sector": "general",
    "country": "CO",
    "description": "Calcular retención DIAN según tipo de proveedor",
    "conditions": [
      {
        "field": "ProveedorTipo",
        "operator": "IN",
        "values": ["Persona Jurídica", "Persona Natural"]
      },
      {
        "field": "ValorFactura",
        "operator": ">",
        "value": 600000
      }
    ],
    "actions": [
      {
        "action": "calculate",
        "formula": "ValorFactura * (TasaRetención / 100)",
        "assign_to": "MontoRetención"
      },
      {
        "action": "validate",
        "condition": "MontoRetención > 0"
      },
      {
        "action": "create_field",
        "field_name": "FechaRetención",
        "value": "GETDATE()"
      }
    ],
    "version": "1.0.0",
    "effective_date": "2026-09-03"
  },
  "requested_by": "finance-team",
  "timestamp": "2026-09-03T10:40:00Z"
}
```

**Evento: Regla Definida y Propagada**
```
{
  "agent_id": "business-rules-agent",
  "event_type": "rule_deployed",
  "payload": {
    "rule_id": "rule_dian_retention_1",
    "rule_name": "Aplicar Retención DIAN",
    "version": "1.0.0",
    "status": "active",
    "deployed_at": "2026-09-03T10:41:00Z",
    "propagation": {
      "database_agent": {
        "status": "completed",
        "action": "Agregó columnas MontoRetención, FechaRetención"
      },
      "apis_agent": {
        "status": "in_progress",
        "action": "Actualizando endpoints /facturas"
      },
      "reporting_agent": {
        "status": "queued",
        "action": "Agregará columnas a reporte de retenciones"
      },
      "qa_agent": {
        "status": "queued",
        "action": "Creando tests para validar regla"
      }
    },
    "audit_trail": {
      "created_by": "finance-team",
      "reviewed_by": "compliance-officer",
      "approval_timestamp": "2026-09-03T10:40:30Z"
    }
  }
}
```

### 3.4 Reglas de Negocio del Agente
- ✅ Toda regla requiere revisión/aprobación antes de producción
- ✅ Cambios se propagan automáticamente a todos los agentes
- ✅ Versiones anteriores siempre reversibles (rollback)
- ✅ Auditoría de cada evaluación de regla
- ✅ Documentación en lenguaje de negocio (no técnico)

### 3.5 Integraciones
```
⬅️  Recibe de:
    - Usuarios/Configuradores de negocio
    - QA Agent (feedback de tests)

➡️  Envía a:
    - Database Agent (nuevas columnas)
    - APIs Agent (validaciones)
    - Reporting Agent (nuevas métricas)
    - QA Agent (tests automáticos)
    - Orchestrator (notificación de propagación)
```

### 3.6 Métricas de Éxito
- ✅ 0 conflictos de reglas sin resolver
- ✅ 100% de cambios auditados
- ✅ Propagación completa < 10 minutos
- ✅ Documentación de regla comprensible por no-técnicos

---

## 4️⃣ REPORTING AGENT (Report-Agent)

### 4.1 Propósito
Diseñador visual de reportes que genera desde simples listados a reportes complejos con códigos de barras, QR, gráficos, exportación multi-formato.

### 4.2 Responsabilidades Clave
```
Inputs:
├─ Definiciones visuales de reportes (drag-and-drop)
├─ Fuentes de datos (queries, stored procedures)
├─ Parámetros de filtro
├─ Reglas de negocio (para cálculos en reportes)
├─ Formatos de salida (PDF, Excel, HTML, XML)
└─ Códigos de barras, QR, imágenes

Processing:
├─ Renderizar report visualmente
├─ Aplicar filtros y agrupaciones
├─ Calcular métricas/KPIs
├─ Generar códigos de barras/QR
├─ Exportar a múltiples formatos
├─ Cachear reportes generados
├─ Programar generación (nightly, weekly)
└─ Integrar con BI (Power BI, Tableau)

Outputs:
├─ Archivo generado (PDF, Excel, HTML)
├─ URL para visualizar en browser
├─ Metadata del reporte (fecha, usuario, parámetros)
├─ Notificación de disponibilidad
└─ Link de descarga/compartir
```

### 4.3 Interfaz de Entrada/Salida

**Evento: Crear Reporte Visual**
```
{
  "agent_id": "reporting-agent",
  "trigger": "create_report_visual",
  "payload": {
    "report_name": "Estado de Resultados Trimestral",
    "report_type": "financial",
    "data_source": "stored_procedure",
    "data_source_name": "sp_EstadoResultados",
    "parameters": [
      {"name": "empresa_id", "type": "int", "required": true},
      {"name": "start_date", "type": "date", "required": true},
      {"name": "end_date", "type": "date", "required": true}
    ],
    "layout": {
      "header": {
        "logo": "company_logo.png",
        "title": "Estado de Resultados - {empresa_name}",
        "subtitle": "{start_date} a {end_date}"
      },
      "sections": [
        {
          "type": "table",
          "title": "Ingresos",
          "columns": ["Concepto", "Valor", "% del Total"],
          "data_mapping": {
            "Concepto": "concepto",
            "Valor": "monto",
            "% del Total": "porcentaje"
          },
          "totals_row": true
        },
        {
          "type": "chart",
          "chart_type": "pie",
          "title": "Distribución de Ingresos",
          "data_field": "concepto"
        }
      ],
      "footer": {
        "page_number": true,
        "print_date": true,
        "generated_by": "Fábrica de Reportes"
      }
    },
    "export_formats": ["pdf", "excel", "html"],
    "additional_features": {
      "barcode": false,
      "digital_signature": true,
      "watermark": "CONFIDENCIAL"
    }
  },
  "requested_by": "accounting-team",
  "timestamp": "2026-09-03T11:00:00Z"
}
```

**Evento: Reporte Generado**
```
{
  "agent_id": "reporting-agent",
  "event_type": "report_generated",
  "payload": {
    "report_id": "rpt_ero_q3_2026",
    "report_name": "Estado de Resultados Trimestral",
    "generation_timestamp": "2026-09-03T11:05:00Z",
    "generation_time_ms": 2340,
    "parameters_used": {
      "empresa_id": 1,
      "start_date": "2026-07-01",
      "end_date": "2026-09-03"
    },
    "output_files": {
      "pdf": {
        "url": "https://reports.app.com/files/rpt_ero_q3_2026.pdf",
        "size_kb": 524,
        "pages": 3
      },
      "excel": {
        "url": "https://reports.app.com/files/rpt_ero_q3_2026.xlsx",
        "size_kb": 45
      },
      "html": {
        "url": "https://reports.app.com/viewer/rpt_ero_q3_2026.html",
        "interactive": true
      }
    },
    "cache_key": "rpt_ero_q3_2026_20260903_1",
    "cache_ttl_hours": 24,
    "share_link": "https://reports.app.com/share/xyz123abc",
    "share_link_expires_at": "2026-09-10T11:05:00Z"
  }
}
```

### 4.4 Reglas de Negocio del Agente
- ✅ Reportes generados se cachean 24 horas (configurable)
- ✅ PDFs siempre en formato PDF/A-1 (archivable)
- ✅ Accesibilidad WCAG 2.1 AA mínimo
- ✅ Auditoría de quién accedió a qué reporte
- ✅ Códigos de barras/QR generados con estándares EAN/QR ISO

### 4.5 Integraciones
```
⬅️  Recibe de:
    - Database Agent (datos para reportes)
    - Business Rules Agent (cálculos/métricas)
    - QA Agent (validaciones de datos)

➡️  Envía a:
    - Usuarios finales (archivos generados)
    - Orchestrator (notificación de disponibilidad)
    - BI Platforms (Power BI, Tableau)
```

### 4.6 Métricas de Éxito
- ✅ Generación de reporte < 5 segundos
- ✅ 100% de reportes con auditoría de acceso
- ✅ 0 errores en PDF/Excel generados
- ✅ Accesibilidad validada (WCAG 2.1)

---

## 5️⃣ QA AGENT (QA-Agent)

### 5.1 Propósito
Orquestar pruebas automáticas (unitarias, integración, E2E, seguridad, performance) y bloquear despliegues si se incumple calidad mínima.

### 5.2 Responsabilidades Clave
```
Inputs:
├─ Cambios propuestos (DB, API, Reglas)
├─ Casos de test (manuales + automáticos)
├─ Criterios de calidad (cobertura, performance)
├─ Requisitos de seguridad (OWASP)
└─ Baseline de performance

Processing:
├─ Ejecutar pruebas automáticas
├─ Análisis estático de código
├─ Validación de seguridad
├─ Medición de performance
├─ Coverage analysis
├─ Comparar con baseline
├─ Generar reportes
└─ Notificar resultado

Outputs:
├─ Reporte de tests (pass/fail)
├─ Cobertura de código (%)
├─ Vulnerabilidades encontradas
├─ Performance metrics
├─ Go/No-Go decision
└─ Notificación de bloqueos
```

### 5.3 Interfaz de Entrada/Salida

**Evento: Ejecutar Suite de Tests**
```
{
  "agent_id": "qa-agent",
  "trigger": "run_test_suite",
  "payload": {
    "change_id": "change_2026_09_001",
    "change_type": "database_schema_change",
    "entity_affected": "Clientes",
    "test_suites": [
      {
        "suite_name": "Unit Tests",
        "test_count": 45,
        "priority": "critical"
      },
      {
        "suite_name": "Integration Tests",
        "test_count": 28,
        "priority": "high"
      },
      {
        "suite_name": "Security Tests",
        "test_count": 12,
        "priority": "critical"
      },
      {
        "suite_name": "Performance Tests",
        "test_count": 8,
        "priority": "high"
      }
    ],
    "quality_gates": {
      "min_code_coverage": 80,
      "max_critical_vulnerabilities": 0,
      "max_high_vulnerabilities": 2,
      "max_p95_latency_ms": 200,
      "min_pass_rate": 98
    },
    "requested_by": "api-agent",
    "timestamp": "2026-09-03T11:15:00Z"
  }
}
```

**Evento: Suite de Tests Completada**
```
{
  "agent_id": "qa-agent",
  "event_type": "test_suite_completed",
  "payload": {
    "change_id": "change_2026_09_001",
    "execution_timestamp": "2026-09-03T11:22:00Z",
    "execution_duration_seconds": 420,
    "overall_result": "PASS",
    "go_no_go": "GO",
    "results": {
      "unit_tests": {
        "passed": 45,
        "failed": 0,
        "skipped": 0,
        "pass_rate": 100
      },
      "integration_tests": {
        "passed": 28,
        "failed": 0,
        "skipped": 0,
        "pass_rate": 100
      },
      "security_tests": {
        "passed": 12,
        "failed": 0,
        "vulnerabilities": {
          "critical": 0,
          "high": 1,
          "medium": 3,
          "low": 2
        }
      },
      "performance_tests": {
        "p50_latency_ms": 45,
        "p95_latency_ms": 128,
        "p99_latency_ms": 195,
        "throughput_req_per_sec": 2500
      }
    },
    "code_coverage": {
      "overall": 84,
      "new_code": 92,
      "critical_path": 96
    },
    "blockers": [],
    "warnings": [
      "1 high severity vulnerability encontrada en dependencia 'lodash' - ver security report"
    ],
    "recommendations": [
      "Upgrading 'lodash' to v4.17.21 resolves the high vulnerability"
    ],
    "artifacts": {
      "test_report_html": "https://qa.app.com/reports/change_2026_09_001/index.html",
      "coverage_report": "https://qa.app.com/coverage/change_2026_09_001/index.html",
      "security_report": "https://qa.app.com/security/change_2026_09_001/report.pdf"
    },
    "approval_token": "approval_xyz123"
  }
}
```

### 5.4 Reglas de Negocio del Agente
- ✅ 0 tests críticos pueden fallar (bloquea despliegue)
- ✅ Mínimo 80% cobertura de código (target 85%+)
- ✅ 0 vulnerabilidades críticas/altas sin remediación
- ✅ P95 latencia no excede baseline + 10%
- ✅ Cada cambio requiere test automático asociado

### 5.5 Integraciones
```
⬅️  Recibe de:
    - Database Agent (cambios de schema)
    - APIs Agent (nuevos endpoints)
    - Business Rules Agent (nuevas reglas)
    - Reporting Agent (nuevos reportes)

➡️  Envía a:
    - Git Deployment Agent (approval_token para despliegue)
    - Orchestrator (bloqueo si QA falla)
    - Notificaciones (Slack, email)
```

### 5.6 Métricas de Éxito
- ✅ % de cambios que pasan QA primera vez (target: >95%)
- ✅ Promedio tiempo ejecución tests < 10 minutos
- ✅ 0 bugs en producción causados por falla de QA
- ✅ Cobertura promedio código > 80%

---

## 6️⃣ GIT DEPLOYMENT AGENT (Deploy-Git-Agent)

### 6.1 Propósito
Versionado automático en Git, generación de releases notes, y trigger de pipelines CI/CD.

### 6.2 Responsabilidades Clave
```
Inputs:
├─ Cambios validados (DB, API, Reglas, etc.)
├─ Aprobación de QA
├─ Versión semántica (major.minor.patch)
├─ Release notes
└─ Información de issue/ticket asociado

Processing:
├─ Crear rama feature (si no existe)
├─ Commit con mensaje convencional
├─ Crear Pull Request automático
├─ Merge a develop (requiere aprobación)
├─ Tag version en main
├─ Generar release notes
├─ Trigger de CI/CD pipeline
└─ Notificar equipos

Outputs:
├─ Commit creado
├─ Pull Request abierto
├─ Release notes generado
├─ Git tag creado
├─ CI/CD pipeline disparado
└─ Notificaciones enviadas
```

### 6.3 Interfaz de Entrada/Salida

**Evento: Desplegar Cambio a Git**
```
{
  "agent_id": "git-deployment-agent",
  "trigger": "deploy_to_git",
  "payload": {
    "change_id": "change_2026_09_001",
    "version": "1.2.0",
    "version_type": "minor",
    "title": "Nueva entidad Clientes y regla DIAN",
    "description": "Implementa gestión de clientes con retenciones DIAN",
    "components": [
      {
        "type": "database",
        "component": "Clientes",
        "action": "create_table"
      },
      {
        "type": "api",
        "component": "Clientes",
        "action": "create_endpoints"
      },
      {
        "type": "business_rule",
        "component": "Retención DIAN",
        "action": "create_rule"
      }
    ],
    "related_issues": ["ISSUE-456", "ISSUE-457"],
    "team_members": ["dev-lead@company.com", "qa-lead@company.com"],
    "branch_strategy": "git-flow",
    "target_branch": "develop",
    "requested_by": "orchestrator",
    "timestamp": "2026-09-03T11:30:00Z"
  }
}
```

**Evento: Cambio Desplegado a Git**
```
{
  "agent_id": "git-deployment-agent",
  "event_type": "git_deployment_completed",
  "payload": {
    "change_id": "change_2026_09_001",
    "version": "1.2.0",
    "deployment_timestamp": "2026-09-03T11:35:00Z",
    "git_artifacts": {
      "repository": "https://github.com/company/app-factory",
      "commit_hash": "abc123def456",
      "commit_url": "https://github.com/company/app-factory/commit/abc123def456",
      "pull_request": {
        "number": 245,
        "url": "https://github.com/company/app-factory/pull/245",
        "status": "merged"
      },
      "branch": "develop",
      "tag": "v1.2.0",
      "tag_url": "https://github.com/company/app-factory/releases/tag/v1.2.0"
    },
    "release_notes": {
      "title": "Release v1.2.0 - Gestión de Clientes",
      "content": "## Features\n- Nueva entidad Clientes...\n## Bug Fixes\n- ...\n## Breaking Changes\n- Ninguno",
      "url": "https://github.com/company/app-factory/releases/v1.2.0"
    },
    "ci_cd_pipeline": {
      "pipeline_id": "pipeline_xyz123",
      "pipeline_url": "https://azure-pipelines.company.com/...",
      "status": "queued"
    },
    "notifications": {
      "slack": "posted_to_#deployments",
      "email": "sent_to_team"
    },
    "next_step": "CI/CD pipeline will run now - check status in Azure Pipelines"
  }
}
```

### 6.4 Reglas de Negocio del Agente
- ✅ Commits siempre con convención: feat(), fix(), docs(), etc.
- ✅ PR automático requiere aprobación manual antes de merge
- ✅ Versionamiento semántico (major.minor.patch)
- ✅ Release notes auto-generadas desde commits y issues
- ✅ Tags en main siempre alineados con versión liberada

### 6.5 Integraciones
```
⬅️  Recibe de:
    - QA Agent (approval_token)
    - Orchestrator (cambios validados)

➡️  Envía a:
    - Development Agent (trigger despliegue infraestructura)
    - Slack/Teams (notificación de despliegue)
    - CI/CD Pipeline (trigger automático)
```

### 6.6 Métricas de Éxito
- ✅ 100% de cambios en Git con PR
- ✅ Release notes siempre completo y preciso
- ✅ Tiempo commit → PR < 2 minutos
- ✅ 0 conflictos sin resolver en merges

---

## 7️⃣ DEVELOPMENT AGENT (Dev-Agent)

### 7.1 Propósito
Desplegar código a ambientes (Dev, Staging, Prod) en cloud (Azure/AWS/GCP), con validación de salud y rollback automático.

### 7.2 Responsabilidades Clave
```
Inputs:
├─ Commit/Release de Git
├─ Configuración de ambiente
├─ Secrets (conexiones DB, API keys)
├─ Health check endpoints
└─ Rollback triggers

Processing:
├─ Pull código del repo
├─ Build artefactos
├─ Ejecutar migraciones DB (si aplica)
├─ Desplegar a infraestructura cloud
├─ Ejecutar health checks
├─ Validar deployment
├─ Registrar en auditoría
└─ Rollback si detecta anomalías

Outputs:
├─ Deployment completado
├─ Health status
├─ Logs de despliegue
├─ Notificación de éxito/falla
└─ Rollback (si aplica)
```

### 7.3 Interfaz de Entrada/Salida

**Evento: Desplegar a Infraestructura**
```
{
  "agent_id": "development-agent",
  "trigger": "deploy_to_infrastructure",
  "payload": {
    "deployment_id": "deploy_2026_09_001",
    "version": "1.2.0",
    "source": {
      "type": "git_release",
      "git_tag": "v1.2.0",
      "git_hash": "abc123def456"
    },
    "target_environment": "staging",
    "cloud_provider": "azure",
    "deployment_type": "blue_green",
    "components": [
      {
        "type": "database",
        "component": "Clientes",
        "action": "run_migration"
      },
      {
        "type": "api",
        "component": "app-api",
        "action": "deploy_container"
      },
      {
        "type": "reporting",
        "component": "reporting-service",
        "action": "deploy_service"
      }
    ],
    "health_checks": [
      {
        "endpoint": "https://api-staging.app.com/health",
        "expected_status": 200,
        "timeout_seconds": 10
      },
      {
        "query": "SELECT COUNT(*) FROM Clientes",
        "expected_rows": "> 0",
        "timeout_seconds": 5
      }
    ],
    "rollback_triggers": {
      "auto_rollback_if_health_fails": true,
      "auto_rollback_if_error_rate_exceeds": 5,
      "manual_rollback_token": "optional"
    },
    "requested_by": "git-deployment-agent",
    "timestamp": "2026-09-03T11:45:00Z"
  }
}
```

**Evento: Despliegue Completado**
```
{
  "agent_id": "development-agent",
  "event_type": "deployment_completed",
  "payload": {
    "deployment_id": "deploy_2026_09_001",
    "version": "1.2.0",
    "target_environment": "staging",
    "status": "SUCCESS",
    "deployment_timestamp": "2026-09-03T11:52:00Z",
    "deployment_duration_seconds": 420,
    "steps": {
      "database_migration": {
        "status": "completed",
        "duration_seconds": 45,
        "changes": "Created table Clientes"
      },
      "api_deployment": {
        "status": "completed",
        "duration_seconds": 180,
        "instances": 3,
        "all_healthy": true
      },
      "reporting_deployment": {
        "status": "completed",
        "duration_seconds": 60,
        "instances": 2,
        "all_healthy": true
      }
    },
    "health_checks": {
      "api_endpoint": {
        "status": "healthy",
        "response_time_ms": 45
      },
      "database_connectivity": {
        "status": "healthy",
        "row_count": 2450
      }
    },
    "metrics": {
      "cpu_usage_percent": 32,
      "memory_usage_percent": 64,
      "api_request_latency_p95_ms": 128,
      "error_rate_percent": 0.02
    },
    "next_step": "Ready for production deployment. Run smoke tests before proceeding.",
    "rollback_available_until": "2026-09-03T19:52:00Z"
  }
}
```

### 7.4 Reglas de Negocio del Agente
- ✅ Nunca desplegar sin pasar QA
- ✅ Despliegue azul-verde (zero-downtime)
- ✅ Health checks deben pasar antes de dar por exitoso
- ✅ Rollback disponible hasta 8 horas post-despliegue
- ✅ Toda acción desplegada es auditable

### 7.5 Integraciones
```
⬅️  Recibe de:
    - Git Deployment Agent (cambios lista para desplegar)
    - QA Agent (validación)

➡️  Envía a:
    - Monitoring/Observability (métricas)
    - Notificaciones (Slack, pagerduty)
    - Orchestrator (estado)
```

### 7.6 Métricas de Éxito
- ✅ Deployment exitoso > 99% de veces
- ✅ Tiempo despliegue < 30 minutos
- ✅ 0 rollbacks por errores de despliegue
- ✅ Downtime < 0 segundos (blue-green)

---

## 8️⃣ CUSTOM AI AGENTS

### 8.1 Propósito
Crear agentes especializados por dominio de negocio que orquesten agentes técnicos para resolver problemas específicos sin escribir código.

### 8.2 Ejemplos de Agentes Custom

**Ejemplo 1: Agente de Facturación**
```
Agente: Facturación
├─ Responsabilidades:
│  ├─ Crear facturas
│  ├─ Aplicar impuestos locales (IVA, retenciones)
│  ├─ Validar clientes
│  ├─ Generar comprobantes
│  └─ Enviar a autoridades fiscales
│
└─ Usa Agentes Técnicos:
   ├─ Business Rules Agent (retenciones DIAN)
   ├─ APIs Agent (crear factura vía API)
   ├─ Reporting Agent (generar PDF comprobante)
   ├─ Database Agent (guardar en BD)
   └─ Development Agent (enviar a servidor DIAN)
```

**Ejemplo 2: Agente de Cartera**
```
Agente: Gestión de Cartera
├─ Responsabilidades:
│  ├─ Rastrear pagos pendientes
│  ├─ Calcular intereses por mora
│  ├─ Generar notificaciones de cobro
│  ├─ Análisis de riesgo crediticio
│  └─ Reportería de antigüedad
│
└─ Usa Agentes Técnicos:
   ├─ Business Rules Agent (cálculo intereses)
   ├─ APIs Agent (consultar saldos)
   ├─ Reporting Agent (reporte antigüedad)
   ├─ Database Agent (actualizar status pagos)
   └─ Notificaciones (enviar recordatorios)
```

**Ejemplo 3: Agente de RRHH**
```
Agente: Gestión de Recursos Humanos
├─ Responsabilidades:
│  ├─ Administrar nóminas
│  ├─ Calcular retenciones
│  ├─ Gestionar vacaciones
│  ├─ Incapacidades
│  └─ Reportes fiscales
│
└─ Usa Agentes Técnicos:
   ├─ Business Rules Agent (fórmulas nómina)
   ├─ APIs Agent (integración RRHH)
   ├─ Reporting Agent (recibos de pago)
   ├─ Database Agent (registro empleados)
   └─ Development Agent (envío a payroll)
```

### 8.3 Cómo Crear un Agente Custom (No-Code)
```
1. Definir responsabilidades en lenguaje natural
2. Mapear a Agentes Técnicos disponibles
3. Definir flujo de orquestación (secuencial, paralelo)
4. Configurar triggers y notificaciones
5. Crear tests de validación
6. Publicar y versionar
```

### 8.4 Interfaz de Creación de Agente Custom
```
{
  "agent_type": "custom",
  "agent_name": "Facturación Electrónica",
  "domain": "finance",
  "description": "Orquestar creación de facturas con impuestos y envío a autoridades",
  "workflows": [
    {
      "workflow_id": "crear_factura_completa",
      "trigger": "invoice_requested",
      "steps": [
        {
          "step": 1,
          "agent": "business-rules-agent",
          "action": "validate_rules",
          "inputs": ["cliente_id", "items", "descuentos"]
        },
        {
          "step": 2,
          "agent": "database-agent",
          "action": "save_invoice",
          "inputs": ["invoice_data", "calculated_taxes"]
        },
        {
          "step": 3,
          "agent": "reporting-agent",
          "action": "generate_pdf",
          "inputs": ["invoice_id"]
        },
        {
          "step": 4,
          "agent": "apis-agent",
          "action": "send_to_authority",
          "inputs": ["invoice_xml", "digital_signature"]
        }
      ]
    }
  ]
}
```

---

## RESUMEN DE INTEGRACIONES

```
                    ┌──────────────┐
                    │  Orchestrator│
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
    ┌───▼────┐         ┌───▼────┐        ┌───▼────┐
    │   DB   │◄────────┤ Rules  │────────►│  API   │
    │ Agent  │         │ Agent  │        │ Agent  │
    └───┬────┘         └────────┘        └────┬───┘
        │                                      │
        │    ┌────────────────────────┐       │
        └───►│  Reporting Agent       │◄──────┘
             └────────┬───────────────┘
                      │
             ┌────────▼────────┐
             │    QA Agent     │
             └────────┬────────┘
                      │
             ┌────────▼─────────────┐
             │  Git Deploy Agent    │
             └────────┬─────────────┘
                      │
             ┌────────▼──────────────┐
             │  Development Agent    │
             └──────────────────────┘
                      ▲
                      │
            ┌─────────────────────┐
            │ Custom AI Agents    │
            │ (Facturación, RRHH) │
            └─────────────────────┘
```

---

## MÉTRICAS GLOBALES DE ÉXITO

| Métrica | Target |
|---------|--------|
| % Automatización de cambios | > 90% |
| Tiempo ciclo (idea → producción) | < 3 días |
| Defectos detectados por QA | > 95% |
| Disponibilidad de plataforma | > 99.5% |
| Cobertura de tests | > 85% |
| % Cambios sin incidentes | > 98% |
| MTTR (Mean Time To Recover) | < 15 min |

---

**Versión:** 0.1  
**Próxima Revisión:** 10/09/2026  
**Owner:** Equipo de Arquitectura
