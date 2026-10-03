"""
Detección de conflictos entre reglas activas de Matrix (Prism): pares que pueden dispararse juntos
(alcances solapados y condiciones compatibles) y cuyas acciones se contradicen o se pisan.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Dict, List, Optional, Set

from src.agents.business_rules_agent.agent import (
    ActionType,
    BusinessRule,
    Condition,
    OperatorType,
    RuleStatus,
    ScopeLevel,
    calculation_pairs,
)


def scopes_overlap(a: BusinessRule, b: BusinessRule) -> bool:
    if a.scope == b.scope == ScopeLevel.BUSINESS_LINE:
        return a.business_line == b.business_line
    if a.scope == b.scope == ScopeLevel.COMPANY:
        return a.empresa_id == b.empresa_id
    return True


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _values(value: Any) -> Set[str]:
    if isinstance(value, (list, tuple, set)):
        return {str(v) for v in value}
    return {v.strip() for v in str(value).split(",")} if value is not None else set()


@dataclass
class _Domain:
    low: float = -math.inf
    low_strict: bool = False
    high: float = math.inf
    high_strict: bool = False
    allowed: Optional[Set[str]] = None
    excluded: Set[str] = field(default_factory=set)

    def restrict(self, condition: Condition) -> None:
        op, number = condition.operator, _number(condition.value)
        if op in (OperatorType.GT, OperatorType.GTE) and number is not None:
            strict = op == OperatorType.GT
            if number > self.low or (number == self.low and strict):
                self.low, self.low_strict = number, strict
        elif op in (OperatorType.LT, OperatorType.LTE) and number is not None:
            strict = op == OperatorType.LT
            if number < self.high or (number == self.high and strict):
                self.high, self.high_strict = number, strict
        elif op in (OperatorType.EQ, OperatorType.IN):
            values = {str(condition.value)} if op == OperatorType.EQ else _values(condition.value)
            self.allowed = values if self.allowed is None else self.allowed & values
        elif op in (OperatorType.NEQ, OperatorType.NOT_IN):
            self.excluded |= {str(condition.value)} if op == OperatorType.NEQ else _values(condition.value)

    def _in_range(self, value: str) -> bool:
        number = _number(value)
        if number is None:
            return math.isinf(self.low) and math.isinf(self.high)
        above = number > self.low or (number == self.low and not self.low_strict)
        below = number < self.high or (number == self.high and not self.high_strict)
        return above and below

    def feasible(self) -> bool:
        if self.low > self.high or (self.low == self.high and (self.low_strict or self.high_strict)):
            return False
        if self.allowed is not None:
            return any(v not in self.excluded and self._in_range(v) for v in self.allowed)
        return True


def conditions_compatible(a: BusinessRule, b: BusinessRule) -> bool:
    """False solo si es seguro que ambas reglas no pueden cumplirse a la vez (condiciones AND contradictorias)."""
    conditions = [*a.conditions, *b.conditions]
    if any(c.logical_operator.upper() == "OR" for c in conditions[1:]):
        return True
    domains: Dict[str, _Domain] = {}
    for condition in conditions:
        domains.setdefault(condition.field, _Domain()).restrict(condition)
    return all(d.feasible() for d in domains.values())


def _effects(rule: BusinessRule) -> Dict[str, Any]:
    sets: Dict[str, Any] = {}
    calcs: Set[str] = set()
    for action in rule.actions:
        details = action.details or {}
        if action.type == ActionType.SET_FIELD:
            sets.update({details["field"]: details.get("value")} if "field" in details else dict(details))
        elif action.type == ActionType.CALCULATE:
            calcs |= {name for name, _ in calculation_pairs(details) if name}
    kinds = {a.type for a in rule.actions}
    return {"sets": sets, "calcs": calcs, "blocks": ActionType.BLOCK in kinds, "allows": ActionType.ALLOW in kinds}


def _signature(rule: BusinessRule) -> tuple:
    return (
        rule.scope, rule.business_line, rule.empresa_id,
        tuple(sorted((c.field, c.operator.value, str(c.value), c.logical_operator) for c in rule.conditions)),
        tuple(sorted((a.type.value, str(sorted((a.details or {}).items()))) for a in rule.actions)),
    )


def _winner(a: BusinessRule, b: BusinessRule) -> str:
    if a.priority == b.priority:
        return "misma prioridad: el resultado depende del orden por id; define prioridades distintas"
    first = a if a.priority > b.priority else b
    return f"se evalúa primero {first.rule_id} (prioridad {first.priority})"


def find_conflicts(rules: List[BusinessRule]) -> Dict[str, Any]:
    active = [r for r in rules if r.status == RuleStatus.ACTIVE]
    conflicts: List[Dict[str, Any]] = []

    def add(a: BusinessRule, b: BusinessRule, kind: str, severity: str, detail: str) -> None:
        conflicts.append({"regla_a": a.rule_id, "regla_b": b.rule_id, "tipo": kind, "severidad": severity,
                          "detalle": detail, "resolucion": _winner(a, b)})

    for a, b in combinations(active, 2):
        if not scopes_overlap(a, b) or not conditions_compatible(a, b):
            continue
        if _signature(a) == _signature(b):
            add(a, b, "reglas_duplicadas", "media", "Mismas condiciones y acciones en alcances que se solapan")
            continue
        ea, eb = _effects(a), _effects(b)
        if (ea["blocks"] and eb["allows"]) or (ea["allows"] and eb["blocks"]):
            add(a, b, "bloquear_y_permitir", "alta", "Una regla bloquea y la otra permite la misma operación")
        for name in sorted(set(ea["sets"]) & set(eb["sets"])):
            if ea["sets"][name] != eb["sets"][name]:
                add(a, b, "asignacion_contradictoria", "alta",
                    f"{name}: {ea['sets'][name]!r} frente a {eb['sets'][name]!r}")
        for name in sorted(ea["calcs"] & eb["calcs"]):
            add(a, b, "calculo_sobrescrito", "media", f"Ambas calculan {name}; una sobrescribe a la otra")
    by_severity = {s: sum(1 for c in conflicts if c["severidad"] == s) for s in ("alta", "media")}
    return {"reglas_activas": len(active), "pares_revisados": len(active) * (len(active) - 1) // 2,
            "total": len(conflicts), "por_severidad": by_severity, "conflictos": conflicts}
