"""
Business Rules Agent - Declarative Rule Engine
Motor de reglas JSON para validaciones multisector DMS Advance
Soporta: retenciones, límites de crédito, validaciones de negocio, auditoría
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import hashlib

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================

class RuleStatus(str, Enum):
    """Estados de una regla"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    TESTING = "testing"


class OperatorType(str, Enum):
    """Operadores soportados"""
    EQ = "eq"              # igual
    NEQ = "neq"            # no igual
    GT = "gt"              # mayor que
    GTE = "gte"            # mayor o igual
    LT = "lt"              # menor que
    LTE = "lte"            # menor o igual
    IN = "in"              # en lista
    NOT_IN = "not_in"      # no en lista
    CONTAINS = "contains"  # contiene (strings)
    REGEX = "regex"        # expresión regular


class ActionType(str, Enum):
    """Tipos de acciones"""
    CALCULATE = "calculate"      # Calcular variable
    SET_FIELD = "set_field"      # Asignar campo
    NOTIFY = "notify"            # Notificar
    BLOCK = "block"              # Bloquear operación
    ALLOW = "allow"              # Permitir operación
    LOG = "log"                  # Registrar en auditoría


@dataclass
class Condition:
    """Una condición en una regla"""
    field: str
    operator: OperatorType
    value: Any
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evalúa la condición contra el contexto"""
        if field_value := context.get(self.field):
            if self.operator == OperatorType.EQ:
                return field_value == self.value
            elif self.operator == OperatorType.NEQ:
                return field_value != self.value
            elif self.operator == OperatorType.GT:
                return field_value > self.value
            elif self.operator == OperatorType.GTE:
                return field_value >= self.value
            elif self.operator == OperatorType.LT:
                return field_value < self.value
            elif self.operator == OperatorType.LTE:
                return field_value <= self.value
            elif self.operator == OperatorType.IN:
                return field_value in self.value
            elif self.operator == OperatorType.NOT_IN:
                return field_value not in self.value
            elif self.operator == OperatorType.CONTAINS:
                return self.value in str(field_value)
            else:
                return False
        return False


@dataclass
class RuleAction:
    """Una acción a ejecutar si la regla se cumple"""
    type: ActionType
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BusinessRule:
    """Definición de una regla de negocio"""
    rule_id: str
    name: str
    description: str
    empresa_id: int
    conditions: List[Condition] = field(default_factory=list)
    actions: List[RuleAction] = field(default_factory=list)
    status: RuleStatus = RuleStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "empresa_id": self.empresa_id,
            "conditions": [
                {
                    "field": c.field,
                    "operator": c.operator.value,
                    "value": c.value
                }
                for c in self.conditions
            ],
            "actions": [
                {
                    "type": a.type.value,
                    "details": a.details
                }
                for a in self.actions
            ],
            "status": self.status.value,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "metadata": self.metadata
        }


@dataclass
class RuleEvaluationResult:
    """Resultado de evaluar una regla"""
    rule_id: str
    matched: bool
    context_used: Dict[str, Any]
    actions_executed: List[Dict[str, Any]] = field(default_factory=list)
    calculated_values: Dict[str, Any] = field(default_factory=dict)
    decisions: List[str] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ============================================================================
# RULE ENGINE
# ============================================================================

class RuleEngine:
    """Motor de evaluación de reglas"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.RuleEngine")
    
    def evaluate_rule(
        self,
        rule: BusinessRule,
        context: Dict[str, Any]
    ) -> RuleEvaluationResult:
        """
        Evalúa una regla contra un contexto
        
        Args:
            rule: La regla a evaluar
            context: Datos del contexto (cliente, monto, empresa_id, etc)
        
        Returns:
            RuleEvaluationResult con resultado de la evaluación
        """
        result = RuleEvaluationResult(
            rule_id=rule.rule_id,
            matched=False,
            context_used=context.copy()
        )
        
        # Evaluar todas las condiciones (AND lógico)
        all_conditions_met = all(
            cond.evaluate(context)
            for cond in rule.conditions
        )
        
        result.matched = all_conditions_met
        
        if all_conditions_met:
            # Ejecutar acciones
            for action in rule.actions:
                action_result = self._execute_action(action, context, result)
                if action_result:
                    result.actions_executed.append(action_result)
        
        return result
    
    def _execute_action(
        self,
        action: RuleAction,
        context: Dict[str, Any],
        result: RuleEvaluationResult
    ) -> Optional[Dict[str, Any]]:
        """Ejecuta una acción individual"""
        
        if action.type == ActionType.CALCULATE:
            # Calcular variable usando formula
            var_name = action.details.get("var")
            formula = action.details.get("formula")
            
            try:
                # Evaluar formula (simple: monto * 0.025)
                calculated_value = eval(formula, {"__builtins__": {}}, context)
                result.calculated_values[var_name] = calculated_value
                result.decisions.append(f"Calculated {var_name}={calculated_value}")
                
                return {
                    "type": "calculate",
                    "var": var_name,
                    "value": calculated_value
                }
            except Exception as e:
                self.logger.error(f"Error calculating {var_name}: {str(e)}")
                return None
        
        elif action.type == ActionType.SET_FIELD:
            field_name = action.details.get("field")
            field_value = action.details.get("value")
            result.calculated_values[field_name] = field_value
            result.decisions.append(f"Set {field_name}={field_value}")
            
            return {
                "type": "set_field",
                "field": field_name,
                "value": field_value
            }
        
        elif action.type == ActionType.BLOCK:
            reason = action.details.get("reason", "Regla bloqueó operación")
            result.decisions.append(f"BLOCKED: {reason}")
            
            return {
                "type": "block",
                "reason": reason
            }
        
        elif action.type == ActionType.ALLOW:
            result.decisions.append("Operation allowed")
            
            return {
                "type": "allow"
            }
        
        elif action.type == ActionType.NOTIFY:
            target = action.details.get("target", "admin")
            message = action.details.get("message", "")
            result.decisions.append(f"Notification to {target}: {message}")
            
            return {
                "type": "notify",
                "target": target,
                "message": message
            }
        
        elif action.type == ActionType.LOG:
            log_message = action.details.get("message", "")
            result.decisions.append(f"Logged: {log_message}")
            
            return {
                "type": "log",
                "message": log_message
            }
        
        return None


# ============================================================================
# BUSINESS RULES AGENT
# ============================================================================

class BusinessRulesAgent:
    """Agente para evaluar y gestionar reglas de negocio"""
    
    def __init__(self):
        self.name = "BusinessRulesAgent"
        self.version = "0.1.0"
        self.rule_engine = RuleEngine()
        self.rules_store: Dict[str, BusinessRule] = {}
        self.execution_log: List[RuleEvaluationResult] = []
        
        logger.info(f"✅ {self.name} v{self.version} initialized")
    
    def create_rule(self, rule_dict: Dict[str, Any]) -> BusinessRule:
        """Crea una nueva regla a partir de un dict JSON"""
        
        # Parsear condiciones
        conditions = [
            Condition(
                field=c.get("field"),
                operator=OperatorType(c.get("operator", "eq")),
                value=c.get("value")
            )
            for c in rule_dict.get("conditions", [])
        ]
        
        # Parsear acciones
        actions = [
            RuleAction(
                type=ActionType(a.get("type", "log")),
                details=a.get("details", {})
            )
            for a in rule_dict.get("actions", [])
        ]
        
        rule = BusinessRule(
            rule_id=rule_dict.get("rule_id"),
            name=rule_dict.get("name"),
            description=rule_dict.get("description", ""),
            empresa_id=rule_dict.get("empresa_id", 0),
            conditions=conditions,
            actions=actions,
            status=RuleStatus(rule_dict.get("status", "active")),
            created_by=rule_dict.get("created_by", "system"),
            metadata=rule_dict.get("metadata", {})
        )
        
        self.rules_store[rule.rule_id] = rule
        logger.info(f"✅ Rule created: {rule.rule_id}")
        
        return rule
    
    def evaluate(
        self,
        rule_id: str,
        context: Dict[str, Any]
    ) -> RuleEvaluationResult:
        """Evalúa una regla específica contra un contexto"""
        
        if rule_id not in self.rules_store:
            logger.error(f"Rule not found: {rule_id}")
            return RuleEvaluationResult(
                rule_id=rule_id,
                matched=False,
                context_used=context,
                decisions=["Rule not found"]
            )
        
        rule = self.rules_store[rule_id]
        result = self.rule_engine.evaluate_rule(rule, context)
        
        # Guardar en log
        self.execution_log.append(result)
        
        logger.info(f"✅ Rule evaluated: {rule_id}, matched={result.matched}")
        
        return result
    
    def evaluate_all_rules(
        self,
        empresa_id: int,
        context: Dict[str, Any]
    ) -> List[RuleEvaluationResult]:
        """Evalúa todas las reglas activas para una empresa"""
        
        results = []
        for rule in self.rules_store.values():
            if rule.empresa_id == empresa_id and rule.status == RuleStatus.ACTIVE:
                result = self.evaluate(rule.rule_id, context)
                results.append(result)
        
        return results
    
    def get_rule(self, rule_id: str) -> Optional[BusinessRule]:
        """Obtiene una regla por ID"""
        return self.rules_store.get(rule_id)
    
    def list_rules(self, empresa_id: Optional[int] = None) -> List[BusinessRule]:
        """Lista todas las reglas, opcionalmente filtradas por empresa"""
        rules = list(self.rules_store.values())
        
        if empresa_id:
            rules = [r for r in rules if r.empresa_id == empresa_id]
        
        return rules
    
    def update_rule(self, rule_id: str, rule_dict: Dict[str, Any]) -> BusinessRule:
        """Actualiza una regla existente"""
        
        if rule_id not in self.rules_store:
            raise ValueError(f"Rule not found: {rule_id}")
        
        # Eliminar y recrear
        del self.rules_store[rule_id]
        rule_dict["rule_id"] = rule_id
        
        return self.create_rule(rule_dict)
    
    def delete_rule(self, rule_id: str) -> bool:
        """Desactiva una regla (soft delete)"""
        
        if rule_id not in self.rules_store:
            return False
        
        self.rules_store[rule_id].status = RuleStatus.INACTIVE
        logger.info(f"✅ Rule deactivated: {rule_id}")
        
        return True
    
    def get_execution_log(
        self,
        rule_id: Optional[str] = None,
        limit: int = 100
    ) -> List[RuleEvaluationResult]:
        """Obtiene historial de evaluaciones"""
        
        log = self.execution_log
        
        if rule_id:
            log = [r for r in log if r.rule_id == rule_id]
        
        return log[-limit:]
