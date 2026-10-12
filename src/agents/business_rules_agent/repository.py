"""Persistencia de reglas de Matrix: contrato, implementación en memoria y SQL Server (tablas reglas_negocio y relacionadas)."""

from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.agents.business_rules_agent.agent import (
    ActionType,
    BusinessRule,
    Condition,
    OperatorType,
    RuleAction,
    RuleStatus,
    ScopeLevel,
)
from src.agents.sqlserver import SqlServerClient, afectadas, ejecutar

STATUS_TO_DB = {
    RuleStatus.ACTIVE: "activa",
    RuleStatus.INACTIVE: "inactiva",
    RuleStatus.ARCHIVED: "archivada",
    RuleStatus.TESTING: "prueba",
}
STATUS_FROM_DB = {v: k for k, v in STATUS_TO_DB.items()}


@dataclass(frozen=True)
class EvaluationRecord:
    id_regla: str
    nivel_alcance: str
    linea_negocio: Optional[str]
    id_empresa: Optional[int]
    condiciones_cumplidas: bool
    decision: str
    valores_calculados: Dict[str, Any]
    evaluada_por: str
    tiempo_ejecucion_ms: float
    fecha: datetime
    id_auditoria: Optional[int] = None


class RulesRepository(ABC):
    @abstractmethod
    def list_rules(self, scope: Optional[str] = None, empresa_id: Optional[int] = None,
                   business_line: Optional[str] = None, status: Optional[RuleStatus] = None) -> List[BusinessRule]: ...

    @abstractmethod
    def get_rule(self, rule_id: str) -> Optional[BusinessRule]: ...

    @abstractmethod
    def create_rule(self, rule: BusinessRule, actor: str, now: datetime) -> bool:
        """False si ya existe una regla con ese id."""

    @abstractmethod
    def update_rule(self, rule: BusinessRule, actor: str, now: datetime) -> bool: ...

    @abstractmethod
    def set_status(self, rule_id: str, status: RuleStatus, actor: str, now: datetime) -> bool: ...

    @abstractmethod
    def record_evaluation(self, record: EvaluationRecord) -> None: ...

    @abstractmethod
    def list_evaluations(self, rule_id: Optional[str], since: datetime, limit: int) -> List[EvaluationRecord]: ...

    @abstractmethod
    def ping(self) -> None: ...


def _matches_filters(rule: BusinessRule, scope: Optional[str], empresa_id: Optional[int],
                     business_line: Optional[str], status: Optional[RuleStatus]) -> bool:
    return (
        (scope is None or rule.scope.value == scope)
        and (empresa_id is None or rule.empresa_id == empresa_id)
        and (business_line is None or rule.business_line == business_line)
        and (status is None or rule.status == status)
    )


def _sort_key(rule: BusinessRule) -> Tuple[int, str]:
    return (-rule.priority, rule.rule_id)


class InMemoryRulesRepository(RulesRepository):
    def __init__(self) -> None:
        self._rules: Dict[str, BusinessRule] = {}
        self._evaluations: List[EvaluationRecord] = []
        self._lock = threading.Lock()

    def list_rules(self, scope=None, empresa_id=None, business_line=None, status=None) -> List[BusinessRule]:
        rules = [r for r in self._rules.values() if _matches_filters(r, scope, empresa_id, business_line, status)]
        return sorted(rules, key=_sort_key)

    def get_rule(self, rule_id: str) -> Optional[BusinessRule]:
        return self._rules.get(rule_id)

    def create_rule(self, rule: BusinessRule, actor: str, now: datetime) -> bool:
        with self._lock:
            if rule.rule_id in self._rules:
                return False
            self._rules[rule.rule_id] = replace(rule, created_by=actor, created_at=now.isoformat())
            return True

    def update_rule(self, rule: BusinessRule, actor: str, now: datetime) -> bool:
        with self._lock:
            current = self._rules.get(rule.rule_id)
            if current is None:
                return False
            self._rules[rule.rule_id] = replace(rule, created_by=current.created_by, created_at=current.created_at)
            return True

    def set_status(self, rule_id: str, status: RuleStatus, actor: str, now: datetime) -> bool:
        with self._lock:
            current = self._rules.get(rule_id)
            if current is None:
                return False
            self._rules[rule_id] = replace(current, status=status)
            return True

    def record_evaluation(self, record: EvaluationRecord) -> None:
        with self._lock:
            self._evaluations.append(replace(record, id_auditoria=len(self._evaluations) + 1))

    def list_evaluations(self, rule_id: Optional[str], since: datetime, limit: int) -> List[EvaluationRecord]:
        found = [e for e in self._evaluations if e.fecha >= since and (rule_id is None or e.id_regla == rule_id)]
        return list(reversed(found))[:limit]

    def ping(self) -> None:
        return None


# ============================================================================ SQL Server

def _encode_value(value: Any) -> Optional[str]:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _encode_details(details: Dict[str, Any]) -> Optional[str]:
    if not details:
        return None
    if set(details) == {"mensaje"}:
        return str(details["mensaje"])
    return json.dumps(details, ensure_ascii=False)


def _decode_details(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {"mensaje": raw}
    return parsed if isinstance(parsed, dict) else {"mensaje": raw}


class SqlServerRulesRepository(RulesRepository):
    """Persistencia sobre los procedimientos del esquema matrix de la base kinetix."""

    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def ping(self) -> None:
        self._db.ping()

    @staticmethod
    def _load(cur, **filtros: Any) -> List[BusinessRule]:
        rows = ejecutar(cur, "matrix.regla_listar", **filtros).fetchall()
        cur.nextset()
        conditions: Dict[str, List[Condition]] = {}
        for rule_id, campo, operador, valor, logico in cur.fetchall():
            conditions.setdefault(rule_id, []).append(
                Condition(campo, OperatorType(operador), valor, (logico or "AND").upper())
            )
        cur.nextset()
        actions: Dict[str, List[RuleAction]] = {}
        for rule_id, tipo, detalles, critica in cur.fetchall():
            actions.setdefault(rule_id, []).append(RuleAction(ActionType(tipo), _decode_details(detalles), bool(critica)))
        return [
            BusinessRule(
                rule_id=row[0],
                name=row[1],
                description=row[2] or "",
                empresa_id=row[5],
                conditions=conditions.get(row[0], []),
                actions=actions.get(row[0], []),
                status=STATUS_FROM_DB.get(row[6] or "activa", RuleStatus.INACTIVE),
                created_at=row[8].isoformat() if row[8] else "",
                created_by=row[9] or "system",
                scope=ScopeLevel(row[3]),
                business_line=row[4],
                priority=row[7] if row[7] is not None else 0,
            )
            for row in rows
        ]

    def list_rules(self, scope=None, empresa_id=None, business_line=None, status=None) -> List[BusinessRule]:
        with self._db.cursor() as cur:
            return self._load(cur, nivel_alcance=scope, id_empresa=empresa_id, linea_negocio=business_line,
                              estado=STATUS_TO_DB[status] if status is not None else None)

    def get_rule(self, rule_id: str) -> Optional[BusinessRule]:
        with self._db.cursor() as cur:
            rules = self._load(cur, id_regla=rule_id)
        return rules[0] if rules else None

    @staticmethod
    def _insert_children(cur, rule: BusinessRule) -> None:
        for orden, c in enumerate(rule.conditions, start=1):
            ejecutar(cur, "matrix.condicion_insertar", id_regla=rule.rule_id, campo=c.field, operador=c.operator.value,
                     valor=_encode_value(c.value), orden=orden, operador_logico=c.logical_operator)
        for orden, a in enumerate(rule.actions, start=1):
            ejecutar(cur, "matrix.accion_insertar", id_regla=rule.rule_id, tipo_accion=a.type.value,
                     detalles=_encode_details(a.details), orden=orden, es_critica=a.critical)

    @staticmethod
    def _rule_values(rule: BusinessRule, actor: str, now: datetime) -> Dict[str, Any]:
        return dict(id_regla=rule.rule_id, nombre=rule.name, descripcion=rule.description, nivel_alcance=rule.scope.value,
                    linea_negocio=rule.business_line, id_empresa=rule.empresa_id, estado=STATUS_TO_DB[rule.status],
                    prioridad=rule.priority, ahora=now, actor=actor)

    def create_rule(self, rule: BusinessRule, actor: str, now: datetime) -> bool:
        with self._db.cursor(commit=True) as cur:
            if afectadas(ejecutar(cur, "matrix.regla_insertar", **self._rule_values(rule, actor, now))) != 1:
                return False
            self._insert_children(cur, rule)
            return True

    def update_rule(self, rule: BusinessRule, actor: str, now: datetime) -> bool:
        with self._db.cursor(commit=True) as cur:
            if afectadas(ejecutar(cur, "matrix.regla_actualizar", **self._rule_values(rule, actor, now))) != 1:
                return False
            self._insert_children(cur, rule)
            return True

    def set_status(self, rule_id: str, status: RuleStatus, actor: str, now: datetime) -> bool:
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "matrix.regla_cambiar_estado", id_regla=rule_id, estado=STATUS_TO_DB[status],
                                      ahora=now, actor=actor)) == 1

    def record_evaluation(self, record: EvaluationRecord) -> None:
        with self._db.cursor(commit=True) as cur:
            ejecutar(cur, "matrix.evaluacion_insertar", id_regla=record.id_regla, nivel_alcance=record.nivel_alcance,
                     linea_negocio=record.linea_negocio, id_empresa=record.id_empresa,
                     condiciones_cumplidas=record.condiciones_cumplidas, decision=record.decision,
                     valores_calculados=json.dumps(record.valores_calculados, ensure_ascii=False, default=str),
                     fecha=record.fecha, evaluada_por=record.evaluada_por[:100],
                     tiempo_ejecucion_ms=round(record.tiempo_ejecucion_ms, 2))

    def list_evaluations(self, rule_id: Optional[str], since: datetime, limit: int) -> List[EvaluationRecord]:
        with self._db.cursor() as cur:
            rows = ejecutar(cur, "matrix.evaluacion_listar", id_regla=rule_id, desde=since, limite=limit).fetchall()
        records = []
        for r in rows:
            try:
                valores = json.loads(r[7]) if r[7] else {}
            except ValueError:
                valores = {}
            records.append(EvaluationRecord(
                id_regla=r[1], nivel_alcance=r[2] or "", linea_negocio=r[3], id_empresa=r[4],
                condiciones_cumplidas=bool(r[5]), decision=r[6] or "", valores_calculados=valores if isinstance(valores, dict) else {},
                evaluada_por=r[8] or "", tiempo_ejecucion_ms=float(r[9] or 0), fecha=r[10], id_auditoria=r[0],
            ))
        return records
