"""
Matrix (BusinessRulesAgent) — motor declarativo de reglas de negocio.
"""

from src.agents.agent_catalog import MATRIX
from src.agents.business_rules_agent import formula

import json
import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

MAX_REGEX_LENGTH = 200


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


class ScopeLevel(str, Enum):
    """Alcance jerárquico de una regla"""
    GLOBAL = "global"
    BUSINESS_LINE = "linea_negocio"
    COMPANY = "empresa"


class Decision(str, Enum):
    ALLOWED = "permitida"
    BLOCKED = "bloqueada"
    NOT_APPLICABLE = "no_aplica"


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _same(left: Any, right: Any) -> bool:
    """Igualdad tolerante: los valores guardados en la base llegan como texto ('5000', '2')."""
    a, b = _as_number(left), _as_number(right)
    if a is not None and b is not None:
        return a == b
    if isinstance(left, bool) or isinstance(right, bool):
        return str(left).lower() == str(right).lower()
    return left == right or str(left) == str(right)


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return parsed
            except ValueError:
                pass
        return [item.strip() for item in text.split(",")]
    return [value]


@dataclass
class Condition:
    """Una condición en una regla"""
    field: str
    operator: OperatorType
    value: Any
    logical_operator: str = "AND"

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evalúa la condición contra el contexto (un campo ausente nunca cumple)."""
        if self.field not in context or context[self.field] is None:
            return False
        actual = context[self.field]
        try:
            return bool(self._compare(actual))
        except (TypeError, re.error):
            return False

    def _compare(self, actual: Any) -> bool:
        op = self.operator
        if op == OperatorType.EQ:
            return _same(actual, self.value)
        if op == OperatorType.NEQ:
            return not _same(actual, self.value)
        if op in (OperatorType.GT, OperatorType.GTE, OperatorType.LT, OperatorType.LTE):
            a, b = _as_number(actual), _as_number(self.value)
            if a is None or b is None:
                a, b = actual, self.value
            return {
                OperatorType.GT: a > b,
                OperatorType.GTE: a >= b,
                OperatorType.LT: a < b,
                OperatorType.LTE: a <= b,
            }[op]
        if op == OperatorType.IN:
            return any(_same(actual, item) for item in _as_list(self.value))
        if op == OperatorType.NOT_IN:
            return not any(_same(actual, item) for item in _as_list(self.value))
        if op == OperatorType.CONTAINS:
            return str(self.value) in str(actual)
        if op == OperatorType.REGEX:
            pattern = str(self.value)
            return len(pattern) <= MAX_REGEX_LENGTH and re.search(pattern, str(actual)) is not None
        return False


@dataclass
class RuleAction:
    """Una acción a ejecutar si la regla se cumple"""
    type: ActionType
    details: Dict[str, Any] = field(default_factory=dict)
    critical: bool = False


@dataclass
class BusinessRule:
    """Definición de una regla de negocio"""
    rule_id: str
    name: str
    description: str
    empresa_id: Optional[int]
    conditions: List[Condition] = field(default_factory=list)
    actions: List[RuleAction] = field(default_factory=list)
    status: RuleStatus = RuleStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)
    scope: ScopeLevel = ScopeLevel.GLOBAL
    business_line: Optional[str] = None
    priority: int = 50

    def applies_to(self, empresa_id: Optional[int], business_line: Optional[str]) -> bool:
        """Jerarquía: global aplica siempre; línea de negocio y empresa solo si coinciden."""
        if self.scope == ScopeLevel.GLOBAL:
            return True
        if self.scope == ScopeLevel.BUSINESS_LINE:
            return business_line is not None and self.business_line == business_line
        return empresa_id is not None and self.empresa_id == empresa_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "empresa_id": self.empresa_id,
            "scope": self.scope.value,
            "business_line": self.business_line,
            "priority": self.priority,
            "conditions": [
                {
                    "field": c.field,
                    "operator": c.operator.value,
                    "value": c.value,
                    "logical_operator": c.logical_operator,
                }
                for c in self.conditions
            ],
            "actions": [
                {
                    "type": a.type.value,
                    "details": a.details,
                    "critical": a.critical,
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
    decision: Decision = Decision.NOT_APPLICABLE
    errors: List[str] = field(default_factory=list)


def build_rule(rule_dict: Dict[str, Any]) -> BusinessRule:
    """Construye una regla desde un dict JSON; lanza ValueError si un operador, acción o alcance no existe."""
    conditions = [
        Condition(
            field=c.get("field"),
            operator=OperatorType(c.get("operator", "eq")),
            value=c.get("value"),
            logical_operator=str(c.get("logical_operator", "AND")).upper(),
        )
        for c in rule_dict.get("conditions", [])
    ]
    actions = [
        RuleAction(
            type=ActionType(a.get("type", "log")),
            details={"mensaje": a["details"]} if isinstance(a.get("details"), str) else (a.get("details") or {}),
            critical=bool(a.get("critical", False)),
        )
        for a in rule_dict.get("actions", [])
    ]
    return BusinessRule(
        rule_id=rule_dict.get("rule_id"),
        name=rule_dict.get("name"),
        description=rule_dict.get("description", "") or "",
        empresa_id=rule_dict.get("empresa_id"),
        conditions=conditions,
        actions=actions,
        status=RuleStatus(rule_dict.get("status", "active")),
        created_by=rule_dict.get("created_by", "system"),
        metadata=rule_dict.get("metadata", {}),
        scope=ScopeLevel(rule_dict.get("scope", "global")),
        business_line=rule_dict.get("business_line"),
        priority=int(rule_dict.get("priority", 50)),
    )


def calculation_pairs(details: Dict[str, Any]) -> List[tuple]:
    """Acepta {"var": x, "formula": f} o el formato de la base {"x": "f", "y": "g"}."""
    if "formula" in details:
        return [(details.get("var"), details.get("formula"))]
    return [(name, expr) for name, expr in details.items() if isinstance(expr, str)]


def _message(details: Dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        if details.get(key):
            return str(details[key])
    return default


# ============================================================================
# RULE ENGINE
# ============================================================================

class RuleEngine:
    """Motor de evaluación de reglas"""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.RuleEngine")

    @staticmethod
    def conditions_met(conditions: List[Condition], context: Dict[str, Any]) -> bool:
        """Combina de izquierda a derecha con el operador lógico (AND/OR) de cada condición."""
        if not conditions:
            return True
        met = conditions[0].evaluate(context)
        for cond in conditions[1:]:
            if cond.logical_operator == "OR":
                met = met or cond.evaluate(context)
            else:
                met = met and cond.evaluate(context)
        return met

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

        result.matched = self.conditions_met(rule.conditions, context)

        if result.matched:
            result.decision = Decision.ALLOWED
            for action in rule.actions:
                action_result = self._execute_action(action, context, result)
                if action_result:
                    result.actions_executed.append(action_result)
                    if action_result["type"] == ActionType.BLOCK.value:
                        result.decision = Decision.BLOCKED

        return result

    def _execute_action(
        self,
        action: RuleAction,
        context: Dict[str, Any],
        result: RuleEvaluationResult
    ) -> Optional[Dict[str, Any]]:
        """Ejecuta una acción individual"""
        details = action.details or {}

        if action.type == ActionType.CALCULATE:
            values: Dict[str, Any] = {}
            for var_name, expression in calculation_pairs(details):
                try:
                    value = formula.evaluate(expression, {**context, **result.calculated_values})
                except formula.FormulaError as e:
                    self.logger.warning(f"Error calculating {var_name}: {e}")
                    if hasattr(result, "errors"):
                        result.errors.append(f"{var_name}: {e}")
                    continue
                result.calculated_values[var_name] = value
                result.decisions.append(f"Calculated {var_name}={value}")
                values[var_name] = value
            if not values:
                return None
            if len(values) == 1:
                var_name, value = next(iter(values.items()))
                return {"type": "calculate", "var": var_name, "value": value}
            return {"type": "calculate", "values": values}

        elif action.type == ActionType.SET_FIELD:
            assignments = {details["field"]: details.get("value")} if "field" in details else dict(details)
            for name, value in assignments.items():
                result.calculated_values[name] = value
                result.decisions.append(f"Set {name}={value}")
            if len(assignments) == 1:
                name, value = next(iter(assignments.items()))
                return {"type": "set_field", "field": name, "value": value}
            return {"type": "set_field", "values": assignments}

        elif action.type == ActionType.BLOCK:
            reason = _message(details, "reason", "mensaje", default="Regla bloqueó operación")
            result.decisions.append(f"BLOCKED: {reason}")
            return {"type": "block", "reason": reason, "critical": action.critical}

        elif action.type == ActionType.ALLOW:
            message = _message(details, "message", "mensaje", default="Operation allowed")
            result.decisions.append(message)
            return {"type": "allow", "message": message}

        elif action.type == ActionType.NOTIFY:
            target = details.get("target", "admin")
            message = _message(details, "message", "mensaje")
            result.decisions.append(f"Notification to {target}: {message}")
            return {"type": "notify", "target": target, "message": message, "critical": action.critical}

        elif action.type == ActionType.LOG:
            log_message = _message(details, "message", "mensaje")
            result.decisions.append(f"Logged: {log_message}")
            return {"type": "log", "message": log_message}

        return None


# ============================================================================
# BUSINESS RULES AGENT
# ============================================================================

class BusinessRulesAgent:
    """Agente para evaluar y gestionar reglas de negocio en memoria (la API usa RulesService)."""

    def __init__(self):
        self.name = MATRIX.codename
        self.version = "0.2.0"
        self.rule_engine = RuleEngine()
        self.rules_store: Dict[str, BusinessRule] = {}
        self.execution_log: List[RuleEvaluationResult] = []

        logger.info(f"✅ {self.name} v{self.version} initialized")

    def create_rule(self, rule_dict: Dict[str, Any]) -> BusinessRule:
        """Crea una nueva regla a partir de un dict JSON"""
        rule = build_rule(rule_dict)
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
