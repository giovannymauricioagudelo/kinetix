"""
Business Rules Agent Package
Motor de reglas de negocio declarativo para validaciones multisector
"""

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

__version__ = "0.1.0"
__author__ = "AFP Team"

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
