"""Casos de uso de Matrix: gestión de reglas, evaluación jerárquica, auditoría y analítica."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from src.agents.business_rules_agent import formula
from src.agents.business_rules_agent.agent import (
    ActionType,
    BusinessRule,
    Decision,
    RuleEngine,
    RuleEvaluationResult,
    RuleStatus,
    ScopeLevel,
    build_rule,
    calculation_pairs,
)
from src.agents.business_rules_agent.repository import EvaluationRecord, RulesRepository, STATUS_TO_DB
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError

VERSION = "1.0.0"
RULE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,100}$")
MAX_AUDIT_PAGE = 500
MAX_SCENARIOS = 50

SCOPES_FROM_API = {"global": ScopeLevel.GLOBAL, "linea_negocio": ScopeLevel.BUSINESS_LINE, "empresa": ScopeLevel.COMPANY}
STATUS_FROM_API = {"activa": RuleStatus.ACTIVE, "inactiva": RuleStatus.INACTIVE, "archivada": RuleStatus.ARCHIVED, "prueba": RuleStatus.TESTING}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def rule_view(rule: BusinessRule) -> Dict[str, Any]:
    return {
        "id_regla": rule.rule_id,
        "nombre": rule.name,
        "descripcion": rule.description,
        "nivel_alcance": rule.scope.value,
        "linea_negocio": rule.business_line,
        "id_empresa": rule.empresa_id,
        "estado": STATUS_TO_DB[rule.status],
        "prioridad": rule.priority,
        "fecha_creacion": rule.created_at or None,
        "modificada_por": rule.created_by,
        "condiciones": [
            {"campo": c.field, "operador": c.operator.value, "valor": c.value, "operador_logico": c.logical_operator}
            for c in rule.conditions
        ],
        "acciones": [{"tipo": a.type.value, "detalles": a.details, "critica": a.critical} for a in rule.actions],
    }


def _result_view(rule: BusinessRule, result: RuleEvaluationResult) -> Dict[str, Any]:
    return {
        "id_regla": rule.rule_id,
        "nombre": rule.name,
        "prioridad": rule.priority,
        "condiciones_cumplidas": result.matched,
        "decision": result.decision.value,
        "valores_calculados": result.calculated_values,
        "acciones_ejecutadas": result.actions_executed,
        "errores": result.errors,
    }


class RulesService:
    def __init__(self, repository: RulesRepository, clock: Callable[[], datetime] = _utcnow) -> None:
        self._repo = repository
        self._engine = RuleEngine()
        self._now = clock

    def ping(self) -> None:
        self._repo.ping()

    # ================================================================ validación

    def _parse(self, rule_id: str, data: Dict[str, Any]) -> BusinessRule:
        if not RULE_ID.match(rule_id or ""):
            raise InvalidInputError("id_regla solo admite letras, números, '_' y '-' (máx. 100)")
        nombre = (data.get("nombre") or "").strip()
        if not nombre or len(nombre) > 255:
            raise InvalidInputError("nombre es obligatorio (máx. 255 caracteres)")
        scope = SCOPES_FROM_API.get(data.get("nivel_alcance", "global"))
        if scope is None:
            raise InvalidInputError("nivel_alcance debe ser global, linea_negocio o empresa")
        status = STATUS_FROM_API.get(data.get("estado", "activa"))
        if status is None:
            raise InvalidInputError("estado debe ser activa, inactiva, archivada o prueba")
        linea, empresa = data.get("linea_negocio"), data.get("id_empresa")
        if scope == ScopeLevel.BUSINESS_LINE and not linea:
            raise InvalidInputError("Una regla de alcance linea_negocio requiere linea_negocio")
        if scope == ScopeLevel.COMPANY and empresa is None:
            raise InvalidInputError("Una regla de alcance empresa requiere id_empresa")
        if not data.get("acciones"):
            raise InvalidInputError("La regla necesita al menos una acción")
        try:
            rule = build_rule({
                "rule_id": rule_id,
                "name": nombre,
                "description": data.get("descripcion") or "",
                "empresa_id": empresa if scope == ScopeLevel.COMPANY else None,
                "scope": scope.value,
                "business_line": linea if scope == ScopeLevel.BUSINESS_LINE else None,
                "priority": data.get("prioridad", 50),
                "status": status.value,
                "conditions": [
                    {"field": c.get("campo"), "operator": c.get("operador", "eq"), "value": c.get("valor"),
                     "logical_operator": c.get("operador_logico", "AND")}
                    for c in data.get("condiciones", [])
                ],
                "actions": [
                    {"type": a.get("tipo"), "details": a.get("detalles") or {}, "critical": a.get("critica", False)}
                    for a in data["acciones"]
                ],
            })
        except (ValueError, TypeError) as e:
            raise InvalidInputError(f"Definición de regla inválida: {e}") from None
        for c in rule.conditions:
            if not c.field:
                raise InvalidInputError("Cada condición necesita un campo")
            if c.logical_operator not in ("AND", "OR"):
                raise InvalidInputError("operador_logico debe ser AND u OR")
        for a in rule.actions:
            if a.type == ActionType.CALCULATE:
                pairs = calculation_pairs(a.details)
                if not pairs or any(not name for name, _ in pairs):
                    raise InvalidInputError("Una acción calculate necesita {'variable': 'fórmula'}")
                for name, expression in pairs:
                    try:
                        formula.parse(expression)
                    except formula.FormulaError as e:
                        raise InvalidInputError(f"Fórmula de '{name}': {e}") from None
        return rule

    def _get(self, rule_id: str) -> BusinessRule:
        rule = self._repo.get_rule(rule_id)
        if rule is None:
            raise NotFoundError(f"Regla no encontrada: {rule_id}")
        return rule

    # ================================================================ gestión

    def list_rules(self, nivel_alcance: Optional[str] = None, id_empresa: Optional[int] = None,
                   linea_negocio: Optional[str] = None, estado: Optional[str] = None) -> Dict[str, Any]:
        if nivel_alcance is not None and nivel_alcance not in SCOPES_FROM_API:
            raise InvalidInputError("nivel_alcance debe ser global, linea_negocio o empresa")
        if estado is not None and estado not in STATUS_FROM_API:
            raise InvalidInputError("estado debe ser activa, inactiva, archivada o prueba")
        rules = self._repo.list_rules(nivel_alcance, id_empresa, linea_negocio, STATUS_FROM_API.get(estado) if estado else None)
        return {"total": len(rules), "reglas": [rule_view(r) for r in rules]}

    def get_rule(self, rule_id: str) -> Dict[str, Any]:
        return rule_view(self._get(rule_id))

    def active_rules(self, id_empresa: Optional[int] = None) -> List[BusinessRule]:
        rules = self._repo.list_rules(status=RuleStatus.ACTIVE)
        if id_empresa is None:
            return rules
        return [r for r in rules if r.scope != ScopeLevel.COMPANY or r.empresa_id == id_empresa]

    def create_rule(self, data: Dict[str, Any], actor: str) -> Dict[str, Any]:
        rule = self._parse(data.get("id_regla", ""), data)
        if not self._repo.create_rule(rule, actor, self._now()):
            raise ConflictError(f"Ya existe una regla con id {rule.rule_id}")
        return rule_view(self._get(rule.rule_id))

    def update_rule(self, rule_id: str, data: Dict[str, Any], actor: str) -> Dict[str, Any]:
        self._get(rule_id)
        rule = self._parse(rule_id, data)
        if not self._repo.update_rule(rule, actor, self._now()):
            raise NotFoundError(f"Regla no encontrada: {rule_id}")
        return rule_view(self._get(rule_id))

    def archive_rule(self, rule_id: str, actor: str) -> Dict[str, Any]:
        self._get(rule_id)
        self._repo.set_status(rule_id, RuleStatus.ARCHIVED, actor, self._now())
        return {"id_regla": rule_id, "estado": STATUS_TO_DB[RuleStatus.ARCHIVED]}

    # ================================================================ evaluación

    @staticmethod
    def _context(contexto: Dict[str, Any], id_empresa: Optional[int], linea_negocio: Optional[str]) -> Dict[str, Any]:
        context = dict(contexto)
        if id_empresa is not None:
            context.setdefault("id_empresa", id_empresa)
        if linea_negocio is not None:
            context.setdefault("linea_negocio", linea_negocio)
        return context

    def _run(self, rule: BusinessRule, context: Dict[str, Any], id_empresa: Optional[int],
             linea_negocio: Optional[str], actor: Optional[str]) -> RuleEvaluationResult:
        started = time.perf_counter()
        result = self._engine.evaluate_rule(rule, context)
        if actor is not None:
            self._repo.record_evaluation(EvaluationRecord(
                id_regla=rule.rule_id,
                nivel_alcance=rule.scope.value,
                linea_negocio=linea_negocio,
                id_empresa=id_empresa,
                condiciones_cumplidas=result.matched,
                decision=result.decision.value,
                valores_calculados=result.calculated_values,
                evaluada_por=actor,
                tiempo_ejecucion_ms=(time.perf_counter() - started) * 1000,
                fecha=self._now(),
            ))
        return result

    def evaluate_rule(self, rule_id: str, contexto: Dict[str, Any], actor: str,
                      id_empresa: Optional[int] = None, linea_negocio: Optional[str] = None) -> Dict[str, Any]:
        rule = self._get(rule_id)
        if rule.status != RuleStatus.ACTIVE:
            raise ConflictError(f"La regla {rule_id} no está activa ({STATUS_TO_DB[rule.status]})")
        result = self._run(rule, self._context(contexto, id_empresa, linea_negocio), id_empresa, linea_negocio, actor)
        return _result_view(rule, result)

    def evaluate_applicable(self, contexto: Dict[str, Any], actor: str,
                            id_empresa: Optional[int] = None, linea_negocio: Optional[str] = None) -> Dict[str, Any]:
        """Evalúa todas las reglas activas que aplican (global, línea de negocio y empresa) por prioridad."""
        context = self._context(contexto, id_empresa, linea_negocio)
        rules = [r for r in self._repo.list_rules(status=RuleStatus.ACTIVE) if r.applies_to(id_empresa, linea_negocio)]
        evaluated, values, notifications, blocks = [], {}, [], []
        for rule in rules:
            result = self._run(rule, context, id_empresa, linea_negocio, actor)
            evaluated.append(_result_view(rule, result))
            if not result.matched:
                continue
            for name, value in result.calculated_values.items():
                values.setdefault(name, value)
            for action in result.actions_executed:
                if action["type"] == ActionType.NOTIFY.value:
                    notifications.append({"id_regla": rule.rule_id, **action})
                elif action["type"] == ActionType.BLOCK.value:
                    blocks.append({"id_regla": rule.rule_id, "motivo": action["reason"]})
        matched = [e["id_regla"] for e in evaluated if e["condiciones_cumplidas"]]
        decision = Decision.BLOCKED if blocks else Decision.ALLOWED if matched else Decision.NOT_APPLICABLE
        return {
            "decision": decision.value,
            "reglas_evaluadas": len(evaluated),
            "reglas_cumplidas": matched,
            "bloqueos": blocks,
            "notificaciones": notifications,
            "valores_calculados": values,
            "detalle": evaluated,
        }

    def test_rule(self, rule_id: str, escenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Prueba una regla contra escenarios sin registrar auditoría; 'esperado' puede ser bool (cumple) o una decisión."""
        rule = self._get(rule_id)
        if not escenarios or len(escenarios) > MAX_SCENARIOS:
            raise InvalidInputError(f"Envía entre 1 y {MAX_SCENARIOS} escenarios")
        outcomes = []
        for index, escenario in enumerate(escenarios, start=1):
            context = self._context(escenario.get("contexto") or {}, escenario.get("id_empresa"), escenario.get("linea_negocio"))
            result = self._run(rule, context, None, None, actor=None)
            expected = escenario.get("esperado")
            if expected is None:
                passed = None
            elif isinstance(expected, bool):
                passed = result.matched == expected
            else:
                passed = result.decision.value == expected
            outcomes.append({"escenario": index, **_result_view(rule, result), "esperado": expected, "aprobado": passed})
        checked = [o for o in outcomes if o["aprobado"] is not None]
        return {
            "id_regla": rule_id,
            "total": len(outcomes),
            "verificados": len(checked),
            "aprobados": sum(1 for o in checked if o["aprobado"]),
            "escenarios": outcomes,
        }

    # ================================================================ auditoría y analítica

    def audit(self, id_regla: Optional[str] = None, dias: int = 30, limite: int = 100) -> Dict[str, Any]:
        dias = max(1, min(dias, 365))
        limite = max(1, min(limite, MAX_AUDIT_PAGE))
        records = self._repo.list_evaluations(id_regla, self._now() - timedelta(days=dias), limite)
        return {
            "id_regla": id_regla,
            "dias": dias,
            "total": len(records),
            "registros": [
                {
                    "id_auditoria": r.id_auditoria,
                    "id_regla": r.id_regla,
                    "fecha": r.fecha.isoformat() + "Z" if r.fecha else None,
                    "condiciones_cumplidas": r.condiciones_cumplidas,
                    "decision": r.decision,
                    "valores_calculados": r.valores_calculados,
                    "id_empresa": r.id_empresa,
                    "linea_negocio": r.linea_negocio,
                    "evaluada_por": r.evaluada_por,
                    "tiempo_ejecucion_ms": r.tiempo_ejecucion_ms,
                }
                for r in records
            ],
        }

    def evaluation_records(self, id_regla: Optional[str] = None, dias: int = 30, limite: int = 10_000) -> List[EvaluationRecord]:
        since = self._now() - timedelta(days=max(1, min(dias, 365)))
        return self._repo.list_evaluations(id_regla, since, max(1, min(limite, 100_000)))

    def analytics(self, dias: int = 30) -> Dict[str, Any]:
        dias = max(1, min(dias, 365))
        records = self._repo.list_evaluations(None, self._now() - timedelta(days=dias), 100_000)
        per_rule: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"evaluaciones": 0, "cumplidas": 0, "decisiones": defaultdict(int), "tiempo_total_ms": 0.0})
        for r in records:
            stats = per_rule[r.id_regla]
            stats["evaluaciones"] += 1
            stats["cumplidas"] += int(r.condiciones_cumplidas)
            stats["decisiones"][r.decision] += 1
            stats["tiempo_total_ms"] += r.tiempo_ejecucion_ms
        reglas = [
            {
                "id_regla": rule_id,
                "evaluaciones": s["evaluaciones"],
                "cumplidas": s["cumplidas"],
                "tasa_cumplimiento_porcentaje": round(100 * s["cumplidas"] / s["evaluaciones"], 2),
                "decisiones": dict(s["decisiones"]),
                "tiempo_promedio_ms": round(s["tiempo_total_ms"] / s["evaluaciones"], 3),
            }
            for rule_id, s in sorted(per_rule.items(), key=lambda item: -item[1]["evaluaciones"])
        ]
        active = {r.rule_id for r in self._repo.list_rules(status=RuleStatus.ACTIVE)}
        return {
            "dias": dias,
            "reglas_activas": len(active),
            "evaluaciones": len(records),
            "bloqueos": sum(1 for r in records if r.decision == Decision.BLOCKED.value),
            "reglas_activas_sin_uso": sorted(active - set(per_rule)),
            "por_regla": reglas,
        }
