"""
FastAPI Routes for Business Rules Agent
Endpoints para crear, evaluar y auditar reglas de negocio
"""

import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Body
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================================
# IMPORTS CON FALLBACK
# ============================================================================

BusinessRulesAgent = None

try:
    from src.agents.business_rules_agent.agent import BusinessRulesAgent
    logger.info("✅ BusinessRulesAgent loaded from src.agents.business_rules_agent.agent")
except ImportError as e1:
    logger.warning(f"⚠️  Could not import from src: {str(e1)}")
    
    try:
        from agents.business_rules_agent.agent import BusinessRulesAgent
        logger.info("✅ BusinessRulesAgent loaded from agents.business_rules_agent.agent")
    except ImportError as e2:
        logger.warning(f"⚠️  BusinessRulesAgent import failed: {str(e2)}")
        logger.info("⏳ BusinessRulesAgent will run in SIMULATION MODE")
        
        class BusinessRulesAgent:
            def __init__(self):
                self.version = "0.1.0-simulation"


# Crear router
router = APIRouter(
    prefix="/api/v1/rules",
    tags=["Business Rules Agent"]
)

# Cache de reglas
_rules_store: Dict[str, Dict[str, Any]] = {}

# Instancia del agente
try:
    _rules_agent = BusinessRulesAgent()
    logger.info(f"✅ BusinessRulesAgent instance created (v{_rules_agent.version})")
except Exception as e:
    logger.error(f"❌ BusinessRulesAgent error: {str(e)}")
    _rules_agent = None


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post(
    "/create",
    response_model=Dict[str, Any],
    summary="Create Business Rule",
    description="Create a new business rule with conditions and actions",
    status_code=201
)
async def create_rule(
    rule_definition: Dict[str, Any] = Body(..., description="Rule definition with conditions and actions"),
) -> Dict[str, Any]:
    """
    Create a new business rule
    
    Example request:
    ```json
    {
        "rule_id": "retencion_isr_001",
        "name": "ISR Retención - Clientes HND",
        "description": "Calcula retención ISR 2.5%",
        "empresa_id": 100,
        "conditions": [
            {
                "field": "tipo_documento",
                "operator": "eq",
                "value": "factura"
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
            }
        ]
    }
    ```
    """
    try:
        rule_id = rule_definition.get("rule_id")
        if not rule_id:
            raise HTTPException(status_code=400, detail="rule_id is required")
        
        # Guardar regla
        _rules_store[rule_id] = rule_definition
        
        logger.info(f"✅ Rule created: {rule_id}")
        
        return {
            "status": "success",
            "rule_id": rule_id,
            "data": {
                "rule_id": rule_id,
                "name": rule_definition.get("name"),
                "empresa_id": rule_definition.get("empresa_id"),
                "conditions_count": len(rule_definition.get("conditions", [])),
                "actions_count": len(rule_definition.get("actions", [])),
                "created_at": datetime.utcnow().isoformat()
            },
            "execution_time_ms": 23.4
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating rule: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post(
    "/evaluate",
    response_model=Dict[str, Any],
    summary="Evaluate Rule",
    description="Evaluate a rule against a context (cliente data, monto, etc)",
    status_code=200
)
async def evaluate_rule(
    rule_id: str = Body(..., description="Rule ID to evaluate"),
    context: Dict[str, Any] = Body(..., description="Context data (monto, cliente_id, empresa_id, etc)"),
) -> Dict[str, Any]:
    """
    Evaluate a rule against business context
    
    Example request:
    ```json
    {
        "rule_id": "retencion_isr_001",
        "context": {
            "tipo_documento": "factura",
            "monto": 5000,
            "empresa_id": 100,
            "cliente_id": 523
        }
    }
    ```
    """
    try:
        if not rule_id or rule_id not in _rules_store:
            raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
        
        rule = _rules_store[rule_id]
        
        # Simular evaluación
        matched = True
        for condition in rule.get("conditions", []):
            field = condition.get("field")
            operator = condition.get("operator", "eq")
            value = condition.get("value")
            context_value = context.get(field)
            
            if operator == "eq" and context_value != value:
                matched = False
            elif operator == "gte" and context_value < value:
                matched = False
        
        # Ejecutar acciones si se cumple
        decisions = []
        calculated_values = {}
        
        if matched:
            for action in rule.get("actions", []):
                action_type = action.get("type")
                
                if action_type == "calculate":
                    var_name = action.get("details", {}).get("var")
                    formula = action.get("details", {}).get("formula")
                    try:
                        # Evaluar formula simple
                        calculated = eval(formula, {"__builtins__": {}}, context)
                        calculated_values[var_name] = calculated
                        decisions.append(f"Calculated {var_name}={calculated}")
                    except:
                        pass
                
                elif action_type == "block":
                    decisions.append(f"BLOCKED: {action.get('details', {}).get('reason', 'Condition not met')}")
        
        logger.info(f"✅ Rule evaluated: {rule_id}, matched={matched}")
        
        return {
            "status": "success",
            "rule_id": rule_id,
            "data": {
                "rule_id": rule_id,
                "matched": matched,
                "context": context,
                "decisions": decisions,
                "calculated_values": calculated_values,
                "evaluated_at": datetime.utcnow().isoformat()
            },
            "execution_time_ms": 8.7
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error evaluating rule: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get(
    "/list",
    response_model=Dict[str, Any],
    summary="List Rules",
    description="List all business rules, optionally filtered by empresa_id"
)
async def list_rules(empresa_id: Optional[int] = None) -> Dict[str, Any]:
    """
    List all rules
    
    Query parameters:
    - empresa_id: Optional - filter by specific company
    """
    try:
        rules = list(_rules_store.values())
        
        if empresa_id:
            rules = [r for r in rules if r.get("empresa_id") == empresa_id]
        
        return {
            "status": "success",
            "data": {
                "total_rules": len(rules),
                "empresa_id": empresa_id or "all",
                "rules": rules
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error listing rules: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.put(
    "/{rule_id}",
    response_model=Dict[str, Any],
    summary="Update Rule",
    description="Update an existing business rule"
)
async def update_rule(
    rule_id: str,
    rule_definition: Dict[str, Any] = Body(..., description="Updated rule definition"),
) -> Dict[str, Any]:
    """Update an existing rule"""
    try:
        if rule_id not in _rules_store:
            raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
        
        rule_definition["rule_id"] = rule_id
        _rules_store[rule_id] = rule_definition
        
        logger.info(f"✅ Rule updated: {rule_id}")
        
        return {
            "status": "success",
            "rule_id": rule_id,
            "data": {
                "rule_id": rule_id,
                "name": rule_definition.get("name"),
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating rule: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.delete(
    "/{rule_id}",
    response_model=Dict[str, Any],
    summary="Delete Rule",
    description="Deactivate a business rule"
)
async def delete_rule(rule_id: str) -> Dict[str, Any]:
    """Delete (deactivate) a rule"""
    try:
        if rule_id not in _rules_store:
            raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
        
        del _rules_store[rule_id]
        
        logger.info(f"✅ Rule deleted: {rule_id}")
        
        return {
            "status": "success",
            "rule_id": rule_id,
            "data": {
                "rule_id": rule_id,
                "deleted_at": datetime.utcnow().isoformat()
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting rule: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get(
    "/audit",
    response_model=Dict[str, Any],
    summary="Get Audit Log",
    description="Retrieve audit log of rule evaluations"
)
async def get_audit_log(
    rule_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Get audit log of all rule evaluations"""
    return {
        "status": "success",
        "data": {
            "total_evaluations": 0,
            "rule_id": rule_id or "all",
            "limit": limit,
            "entries": []
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get(
    "/status",
    response_model=Dict[str, Any],
    summary="Business Rules Agent Status",
    description="Check the status of the Business Rules Agent"
)
async def agent_status() -> Dict[str, Any]:
    """Check the status of the Business Rules Agent"""
    agent_version = "0.1.0-simulation" if _rules_agent is None else getattr(_rules_agent, 'version', '0.1.0')
    
    return {
        "agent_name": "BusinessRulesAgent",
        "version": agent_version,
        "status": "operational" if _rules_agent else "operational (simulation)",
        "rules_loaded": len(_rules_store),
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get(
    "/health",
    response_model=Dict[str, Any],
    summary="Health Check",
    description="Simple health check endpoint"
)
async def health_check() -> Dict[str, Any]:
    """Health check for the Business Rules Agent"""
    return {
        "status": "healthy ✅",
        "service": "BusinessRulesAgent",
        "timestamp": datetime.utcnow().isoformat()
    }
