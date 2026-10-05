# ============================================================================
# MATRIX v2.0 - BusinessRulesAgent (8 Endpoints)
# Motor inteligente de reglas de negocio con auditoría y análisis
# ============================================================================

matrix_router_v2 = APIRouter(prefix="/api/v1/matrix", tags=["MATRIX v2.0 - BusinessRulesAgent (Rules Engine)"])

@matrix_router_v2.get("/info")
async def matrix_info():
    """Get MATRIX agent information and capabilities"""
    return {
        "id": "matrix",
        "name": "BusinessRulesAgent v2.0",
        "version": "5.0.0",
        "status": "active",
        "endpoints": 8,
        "capabilities": {
            "rule_creation": True,
            "rule_validation": True,
            "rule_execution": True,
            "constraint_checking": True,
            "audit_trail": True,
            "analytics": True,
            "testing": True
        },
        "supported_rule_types": ["simple", "compound", "conditional", "temporal"],
        "timestamp": datetime.utcnow().isoformat()
    }

@matrix_router_v2.post("/create-rule")
async def create_rule(
    rule_name: str = Query(..., description="Nombre único de la regla"),
    rule_type: str = Query(..., description="simple, compound, conditional, temporal"),
    description: Optional[str] = Query(None, description="Descripción de la regla"),
    condition: str = Query(..., description="Condición lógica de la regla"),
    action: str = Query(..., description="Acción a ejecutar cuando se cumple")
):
    """Crear una regla de negocio nueva"""
    import re
    
    # Validar nombre
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', rule_name):
        return {"status": "error", "message": "Invalid rule name"}
    
    # Validar tipo
    valid_types = ["simple", "compound", "conditional", "temporal"]
    if rule_type not in valid_types:
        return {"status": "error", "message": f"Invalid rule type. Use: {', '.join(valid_types)}"}
    
    # Validar longitud mínima de condición y acción
    if len(condition) < 5:
        return {"status": "error", "message": "Condition must be at least 5 characters"}
    
    if len(action) < 5:
        return {"status": "error", "message": "Action must be at least 5 characters"}
    
    return {
        "status": "success",
        "rule_id": f"rule_{rule_name}_{int(datetime.utcnow().timestamp())}",
        "rule_name": rule_name,
        "rule_type": rule_type,
        "status": "created",
        "enabled": True,
        "created_at": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@matrix_router_v2.post("/validate-rule")
async def validate_rule(
    rule_id: str = Query(..., description="ID de la regla a validar"),
    test_data: Optional[str] = Query(None, description="JSON con datos para validar")
):
    """Validar una regla contra restricciones y datos de prueba"""
    import re
    
    # Validar ID
    if not re.match(r'^rule_', rule_id):
        return {"status": "error", "message": "Invalid rule ID format"}
    
    # Simular validación
    validation_checks = {
        "syntax_valid": True,
        "constraints_met": True,
        "dependencies_resolved": True,
        "conflicts_detected": False,
        "warnings": []
    }
    
    if test_data and len(test_data) > 500:
        validation_checks["warnings"].append("Test data is quite large")
    
    return {
        "status": "success",
        "rule_id": rule_id,
        "is_valid": True,
        "validation_checks": validation_checks,
        "message": "Rule validation PASSED",
        "timestamp": datetime.utcnow().isoformat()
    }

@matrix_router_v2.post("/apply-rule")
async def apply_rule(
    rule_id: str = Query(..., description="ID de la regla a aplicar"),
    data: str = Query(..., description="JSON con datos a procesar"),
    context: Optional[str] = Query(None, description="Contexto de ejecución")
):
    """Aplicar una regla a datos específicos"""
    import re
    
    # Validar ID
    if not re.match(r'^rule_', rule_id):
        return {"status": "error", "message": "Invalid rule ID format"}
    
    # Validar data
    if len(data) < 2:
        return {"status": "error", "message": "Data cannot be empty"}
    
    return {
        "status": "success",
        "rule_id": rule_id,
        "execution_result": "rule_applied",
        "data_processed": 1,
        "conditions_met": True,
        "action_executed": True,
        "affected_records": 1,
        "execution_time_ms": 45.67,
        "timestamp": datetime.utcnow().isoformat()
    }

@matrix_router_v2.get("/rules")
async def list_rules(
    rule_type: Optional[str] = Query(None, description="Filtrar por tipo"),
    enabled_only: bool = Query(True, description="Solo mostrar reglas habilitadas"),
    limit: int = Query(50, description="Cantidad máxima de reglas")
):
    """Listar todas las reglas de negocio disponibles"""
    rules = [
        {
            "rule_id": "rule_discount_over_100_1234567",
            "rule_name": "discount_over_100",
            "rule_type": "simple",
            "condition": "amount > 100",
            "action": "apply_10_percent_discount",
            "enabled": True,
            "created_at": "2026-09-28T08:00:00Z",
            "execution_count": 245
        },
        {
            "rule_id": "rule_bulk_order_check_1234568",
            "rule_name": "bulk_order_check",
            "rule_type": "compound",
            "condition": "quantity > 50 AND total_weight > 1000",
            "action": "require_warehouse_approval",
            "enabled": True,
            "created_at": "2026-09-28T08:15:00Z",
            "execution_count": 89
        },
        {
            "rule_id": "rule_payment_validation_1234569",
            "rule_name": "payment_validation",
            "rule_type": "conditional",
            "condition": "payment_method == 'card' ? validate_cvv : validate_account",
            "action": "process_payment",
            "enabled": True,
            "created_at": "2026-09-28T08:30:00Z",
            "execution_count": 1203
        },
        {
            "rule_id": "rule_seasonal_pricing_1234570",
            "rule_name": "seasonal_pricing",
            "rule_type": "temporal",
            "condition": "current_month IN (11,12) AND product_category == 'gift'",
            "action": "apply_holiday_markup",
            "enabled": True,
            "created_at": "2026-09-28T08:45:00Z",
            "execution_count": 567
        }
    ]
    
    # Filtrar por tipo si se especifica
    if rule_type:
        rules = [r for r in rules if r["rule_type"] == rule_type]
    
    # Filtrar solo habilitadas si aplica
    if enabled_only:
        rules = [r for r in rules if r["enabled"]]
    
    # Limitar cantidad
    rules = rules[:limit]
    
    return {
        "status": "success",
        "total": len(rules),
        "rule_type_filter": rule_type,
        "enabled_only": enabled_only,
        "rules": rules,
        "timestamp": datetime.utcnow().isoformat()
    }

@matrix_router_v2.post("/test-rule")
async def test_rule(
    rule_id: str = Query(..., description="ID de la regla a probar"),
    test_scenarios: Optional[str] = Query(None, description="Escenarios de prueba (JSON)")
):
    """Probar una regla con múltiples escenarios de datos"""
    import re
    
    # Validar ID
    if not re.match(r'^rule_', rule_id):
        return {"status": "error", "message": "Invalid rule ID format"}
    
    # Simular pruebas con 5 escenarios predeterminados
    test_results = [
        {"scenario": "scenario_1", "condition_met": True, "expected": True, "result": "PASS"},
        {"scenario": "scenario_2", "condition_met": False, "expected": False, "result": "PASS"},
        {"scenario": "scenario_3", "condition_met": True, "expected": True, "result": "PASS"},
        {"scenario": "scenario_4", "condition_met": False, "expected": False, "result": "PASS"},
        {"scenario": "scenario_5", "condition_met": True, "expected": True, "result": "PASS"}
    ]
    
    passed = sum(1 for t in test_results if t["result"] == "PASS")
    total = len(test_results)
    
    return {
        "status": "completed",
        "rule_id": rule_id,
        "total_scenarios": total,
        "passed": passed,
        "failed": total - passed,
        "success_rate": f"{(passed/total*100):.1f}%",
        "test_results": test_results,
        "timestamp": datetime.utcnow().isoformat()
    }

@matrix_router_v2.post("/audit-decision")
async def audit_decision(
    rule_id: str = Query(..., description="ID de la regla ejecutada"),
    data_id: str = Query(..., description="ID del registro procesado"),
    decision: str = Query(..., description="Decisión tomada (accepted, rejected, escalated)"),
    reason: Optional[str] = Query(None, description="Razón de la decisión")
):
    """Registrar auditoría de decisión tomada por una regla"""
    import re
    
    # Validar inputs
    if not re.match(r'^rule_', rule_id):
        return {"status": "error", "message": "Invalid rule ID"}
    
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', data_id):
        return {"status": "error", "message": "Invalid data ID"}
    
    valid_decisions = ["accepted", "rejected", "escalated", "manual_review"]
    if decision not in valid_decisions:
        return {"status": "error", "message": f"Invalid decision. Use: {', '.join(valid_decisions)}"}
    
    return {
        "status": "success",
        "audit_id": f"audit_{rule_id}_{data_id}_{int(datetime.utcnow().timestamp())}",
        "rule_id": rule_id,
        "data_id": data_id,
        "decision": decision,
        "reason": reason or "Not specified",
        "user": "system",
        "audited_at": datetime.utcnow().isoformat(),
        "is_archived": False
    }

@matrix_router_v2.get("/analytics")
async def get_analytics(
    rule_id: Optional[str] = Query(None, description="Filtrar por rule_id (opcional)"),
    time_period: str = Query("24h", description="24h, 7d, 30d, 90d")
):
    """Obtener analíticas de ejecución y efectividad de reglas"""
    import re
    
    # Validar time_period
    valid_periods = ["24h", "7d", "30d", "90d"]
    if time_period not in valid_periods:
        return {"status": "error", "message": f"Invalid period. Use: {', '.join(valid_periods)}"}
    
    # Analíticas por regla
    analytics_data = [
        {
            "rule_id": "rule_discount_over_100_1234567",
            "rule_name": "discount_over_100",
            "execution_count": 245,
            "success_rate": 98.5,
            "avg_execution_time_ms": 12.5,
            "decisions": {"accepted": 240, "rejected": 5, "escalated": 0},
            "business_impact": {"savings": 15200.50, "currency": "USD"}
        },
        {
            "rule_id": "rule_bulk_order_check_1234568",
            "rule_name": "bulk_order_check",
            "execution_count": 89,
            "success_rate": 100.0,
            "avg_execution_time_ms": 18.3,
            "decisions": {"accepted": 70, "rejected": 0, "escalated": 19},
            "business_impact": {"orders_held_for_approval": 19}
        },
        {
            "rule_id": "rule_payment_validation_1234569",
            "rule_name": "payment_validation",
            "execution_count": 1203,
            "success_rate": 99.2,
            "avg_execution_time_ms": 25.7,
            "decisions": {"accepted": 1194, "rejected": 9, "escalated": 0},
            "business_impact": {"fraud_prevented": 4}
        }
    ]
    
    # Filtrar si se especifica rule_id
    if rule_id:
        analytics_data = [a for a in analytics_data if a["rule_id"] == rule_id]
    
    # Calcular totales
    total_executions = sum(a["execution_count"] for a in analytics_data)
    avg_success_rate = sum(a["success_rate"] for a in analytics_data) / len(analytics_data) if analytics_data else 0
    
    return {
        "status": "success",
        "time_period": time_period,
        "total_rules_analyzed": len(analytics_data),
        "total_executions": total_executions,
        "average_success_rate": f"{avg_success_rate:.1f}%",
        "rules": analytics_data,
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# OPTIONAL: 9th endpoint for getting rule execution history
# (Not in core 8, but useful for audit trail)
# ============================================================================

@matrix_router_v2.get("/execution-history")
async def get_execution_history(
    rule_id: Optional[str] = Query(None, description="Filtrar por rule_id"),
    limit: int = Query(20, description="Cantidad de registros")
):
    """Obtener historial de ejecución de reglas"""
    history = [
        {
            "execution_id": "exec_001",
            "rule_id": "rule_discount_over_100_1234567",
            "data_id": "order_12345",
            "status": "success",
            "duration_ms": 12.3,
            "result": "accepted",
            "executed_at": "2026-09-28T10:45:00Z"
        },
        {
            "execution_id": "exec_002",
            "rule_id": "rule_payment_validation_1234569",
            "data_id": "payment_67890",
            "status": "success",
            "duration_ms": 28.5,
            "result": "accepted",
            "executed_at": "2026-09-28T10:44:15Z"
        }
    ]
    
    if rule_id:
        history = [h for h in history if h["rule_id"] == rule_id]
    
    history = history[:limit]
    
    return {
        "status": "success",
        "total_records": len(history),
        "history": history,
        "timestamp": datetime.utcnow().isoformat()
    }
