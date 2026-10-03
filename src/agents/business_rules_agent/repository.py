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
from src.agents.sqlserver import SqlServerClient

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
    _RULE_COLUMNS = (
        "r.id_regla, r.nombre, r.descripcion, r.nivel_alcance, r.linea_negocio, r.id_empresa, "
        "r.estado, r.prioridad, r.fecha_creacion, r.modificada_por"
    )

    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def ping(self) -> None:
        self._db.ping()

    def _load(self, cur, where: str, params: Tuple[Any, ...]) -> List[BusinessRule]:
        cur.execute(f"SELECT {self._RULE_COLUMNS} FROM dbo.reglas_negocio r {where} "
                    "ORDER BY COALESCE(r.prioridad, 0) DESC, r.id_regla", params)
        rows = cur.fetchall()
        if not rows:
            return []
        cur.execute(
            f"SELECT c.id_regla, c.campo, c.operador, c.valor, c.operador_logico FROM dbo.condiciones_regla c "
            f"JOIN dbo.reglas_negocio r ON r.id_regla = c.id_regla {where} ORDER BY c.id_regla, c.orden, c.id_condicion",
            params,
        )
        conditions: Dict[str, List[Condition]] = {}
        for rule_id, campo, operador, valor, logico in cur.fetchall():
            conditions.setdefault(rule_id, []).append(
                Condition(campo, OperatorType(operador), valor, (logico or "AND").upper())
            )
        cur.execute(
            f"SELECT a.id_regla, a.tipo_accion, a.detalles, a.es_critica FROM dbo.acciones_regla a "
            f"JOIN dbo.reglas_negocio r ON r.id_regla = a.id_regla {where} ORDER BY a.id_regla, a.orden, a.id_accion",
            params,
        )
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
        clauses, params = [], []
        for column, value in (("r.nivel_alcance", scope), ("r.id_empresa", empresa_id), ("r.linea_negocio", business_line)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if status is not None:
            clauses.append("COALESCE(r.estado, 'activa') = ?")
            params.append(STATUS_TO_DB[status])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._db.cursor() as cur:
            return self._load(cur, where, tuple(params))

    def get_rule(self, rule_id: str) -> Optional[BusinessRule]:
        with self._db.cursor() as cur:
            rules = self._load(cur, "WHERE r.id_regla = ?", (rule_id,))
        return rules[0] if rules else None

    def _insert_children(self, cur, rule: BusinessRule) -> None:
        for orden, c in enumerate(rule.conditions, start=1):
            cur.execute(
                "INSERT INTO dbo.condiciones_regla (id_regla, campo, operador, valor, orden, operador_logico) VALUES (?, ?, ?, ?, ?, ?)",
                (rule.rule_id, c.field, c.operator.value, _encode_value(c.value), orden, c.logical_operator),
            )
        for orden, a in enumerate(rule.actions, start=1):
            cur.execute(
                "INSERT INTO dbo.acciones_regla (id_regla, tipo_accion, detalles, orden, es_critica) VALUES (?, ?, ?, ?, ?)",
                (rule.rule_id, a.type.value, _encode_details(a.details), orden, a.critical),
            )

    def create_rule(self, rule: BusinessRule, actor: str, now: datetime) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO dbo.reglas_negocio (id_regla, nombre, descripcion, nivel_alcance, linea_negocio, id_empresa, "
                "estado, prioridad, fecha_creacion, fecha_modificacion, modificada_por) "
                "SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? "
                "WHERE NOT EXISTS (SELECT 1 FROM dbo.reglas_negocio WITH (UPDLOCK, HOLDLOCK) WHERE id_regla = ?)",
                (rule.rule_id, rule.name, rule.description, rule.scope.value, rule.business_line, rule.empresa_id,
                 STATUS_TO_DB[rule.status], rule.priority, now, now, actor, rule.rule_id),
            )
            if cur.rowcount != 1:
                return False
            self._insert_children(cur, rule)
            return True

    def update_rule(self, rule: BusinessRule, actor: str, now: datetime) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.reglas_negocio SET nombre = ?, descripcion = ?, nivel_alcance = ?, linea_negocio = ?, "
                "id_empresa = ?, estado = ?, prioridad = ?, fecha_modificacion = ?, modificada_por = ? WHERE id_regla = ?",
                (rule.name, rule.description, rule.scope.value, rule.business_line, rule.empresa_id,
                 STATUS_TO_DB[rule.status], rule.priority, now, actor, rule.rule_id),
            )
            if cur.rowcount != 1:
                return False
            cur.execute("DELETE FROM dbo.condiciones_regla WHERE id_regla = ?", (rule.rule_id,))
            cur.execute("DELETE FROM dbo.acciones_regla WHERE id_regla = ?", (rule.rule_id,))
            self._insert_children(cur, rule)
            return True

    def set_status(self, rule_id: str, status: RuleStatus, actor: str, now: datetime) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.reglas_negocio SET estado = ?, fecha_modificacion = ?, modificada_por = ? WHERE id_regla = ?",
                (STATUS_TO_DB[status], now, actor, rule_id),
            )
            return cur.rowcount == 1

    def record_evaluation(self, record: EvaluationRecord) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO dbo.auditoria_evaluacion_reglas (id_regla, nivel_alcance, linea_negocio, id_empresa, "
                "condiciones_cumplidas, decision, valores_calculados, fecha_evaluacion, evaluada_por, tiempo_ejecucion_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record.id_regla, record.nivel_alcance, record.linea_negocio, record.id_empresa,
                 record.condiciones_cumplidas, record.decision,
                 json.dumps(record.valores_calculados, ensure_ascii=False, default=str),
                 record.fecha, record.evaluada_por[:100], round(record.tiempo_ejecucion_ms, 2)),
            )

    def list_evaluations(self, rule_id: Optional[str], since: datetime, limit: int) -> List[EvaluationRecord]:
        sql = (
            "SELECT TOP (?) id_auditoria, id_regla, nivel_alcance, linea_negocio, id_empresa, condiciones_cumplidas, "
            "decision, valores_calculados, evaluada_por, tiempo_ejecucion_ms, fecha_evaluacion "
            "FROM dbo.auditoria_evaluacion_reglas WHERE fecha_evaluacion >= ?"
        )
        params: List[Any] = [limit, since]
        if rule_id is not None:
            sql += " AND id_regla = ?"
            params.append(rule_id)
        with self._db.cursor() as cur:
            cur.execute(sql + " ORDER BY id_auditoria DESC", tuple(params))
            rows = cur.fetchall()
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
