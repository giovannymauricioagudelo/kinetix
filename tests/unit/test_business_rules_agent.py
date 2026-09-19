"""
Unit tests for Business Rules Agent
Tests para evaluación de reglas, acciones y auditoría
"""

import pytest
from datetime import datetime

# ============================================================================
# IMPORTS CON FALLBACK
# ============================================================================

try:
    from src.agents.business_rules_agent.agent import (
        BusinessRulesAgent,
        BusinessRule,
        RuleAction,
        Condition,
        RuleStatus,
        OperatorType,
        ActionType,
        RuleEngine
    )
except ImportError:
    try:
        from agents.business_rules_agent.agent import (
            BusinessRulesAgent,
            BusinessRule,
            RuleAction,
            Condition,
            RuleStatus,
            OperatorType,
            ActionType,
            RuleEngine
        )
    except ImportError:
        pytest.skip("BusinessRulesAgent not available", allow_module_level=True)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def agent():
    """Instancia del agente para pruebas"""
    return BusinessRulesAgent()


@pytest.fixture
def sample_rule_dict():
    """Diccionario de regla de ejemplo (retención ISR)"""
    return {
        "rule_id": "test_retencion_isr_001",
        "name": "ISR Retención Test",
        "description": "Test rule for ISR retention",
        "empresa_id": 100,
        "status": "active",
        "created_by": "test_user",
        "conditions": [
            {
                "field": "tipo_documento",
                "operator": "eq",
                "value": "factura"
            },
            {
                "field": "empresa_id",
                "operator": "eq",
                "value": 100
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
            },
            {
                "type": "set_field",
                "details": {
                    "field": "estado",
                    "value": "pendiente_retencion"
                }
            }
        ]
    }


@pytest.fixture
def sample_context():
    """Contexto de ejemplo para evaluación"""
    return {
        "tipo_documento": "factura",
        "empresa_id": 100,
        "monto": 5000,
        "cliente_id": 523,
        "bodega_id": 1
    }


# ============================================================================
# TESTS: RULE CREATION
# ============================================================================

class TestRuleCreation:
    """Tests para creación de reglas"""
    
    def test_create_rule_success(self, agent, sample_rule_dict):
        """Crear regla exitosamente"""
        rule = agent.create_rule(sample_rule_dict)
        
        assert rule.rule_id == "test_retencion_isr_001"
        assert rule.name == "ISR Retención Test"
        assert rule.empresa_id == 100
        assert len(rule.conditions) == 3
        assert len(rule.actions) == 2
        assert rule.status == RuleStatus.ACTIVE
    
    def test_rule_stored_in_agent(self, agent, sample_rule_dict):
        """Regla almacenada en el agente"""
        agent.create_rule(sample_rule_dict)
        
        stored_rule = agent.get_rule("test_retencion_isr_001")
        assert stored_rule is not None
        assert stored_rule.rule_id == "test_retencion_isr_001"
    
    def test_list_rules(self, agent, sample_rule_dict):
        """Listar todas las reglas"""
        agent.create_rule(sample_rule_dict)
        
        all_rules = agent.list_rules()
        assert len(all_rules) == 1
        assert all_rules[0].rule_id == "test_retencion_isr_001"
    
    def test_list_rules_filtered_by_empresa(self, agent, sample_rule_dict):
        """Listar reglas filtradas por empresa"""
        agent.create_rule(sample_rule_dict)
        
        # Buscar empresa 100
        rules_100 = agent.list_rules(empresa_id=100)
        assert len(rules_100) == 1
        
        # Buscar empresa 999 (no existe)
        rules_999 = agent.list_rules(empresa_id=999)
        assert len(rules_999) == 0


# ============================================================================
# TESTS: RULE EVALUATION
# ============================================================================

class TestRuleEvaluation:
    """Tests para evaluación de reglas"""
    
    def test_condition_evaluation_eq(self):
        """Test operador EQ"""
        cond = Condition(field="tipo_documento", operator=OperatorType.EQ, value="factura")
        
        assert cond.evaluate({"tipo_documento": "factura"}) is True
        assert cond.evaluate({"tipo_documento": "nota_credito"}) is False
    
    def test_condition_evaluation_gte(self):
        """Test operador GTE (mayor o igual)"""
        cond = Condition(field="monto", operator=OperatorType.GTE, value=1000)
        
        assert cond.evaluate({"monto": 5000}) is True
        assert cond.evaluate({"monto": 1000}) is True
        assert cond.evaluate({"monto": 500}) is False
    
    def test_condition_evaluation_in(self):
        """Test operador IN"""
        cond = Condition(field="estado", operator=OperatorType.IN, value=["activo", "pendiente"])
        
        assert cond.evaluate({"estado": "activo"}) is True
        assert cond.evaluate({"estado": "pendiente"}) is True
        assert cond.evaluate({"estado": "cancelado"}) is False
    
    def test_rule_evaluation_all_conditions_met(self, agent, sample_rule_dict, sample_context):
        """Evaluación cuando TODAS las condiciones se cumplen"""
        agent.create_rule(sample_rule_dict)
        
        result = agent.evaluate("test_retencion_isr_001", sample_context)
        
        assert result.matched is True
        assert len(result.actions_executed) > 0
        assert "retencion_isr" in result.calculated_values
        assert result.calculated_values["retencion_isr"] == 125.0  # 5000 * 0.025
    
    def test_rule_evaluation_condition_not_met(self, agent, sample_rule_dict):
        """Evaluación cuando condición NO se cumple"""
        agent.create_rule(sample_rule_dict)
        
        # Contexto con monto menor al requerido
        context = {
            "tipo_documento": "factura",
            "empresa_id": 100,
            "monto": 500  # < 1000
        }
        
        result = agent.evaluate("test_retencion_isr_001", context)
        
        assert result.matched is False
        assert len(result.actions_executed) == 0
        assert len(result.calculated_values) == 0
    
    def test_rule_not_found(self, agent):
        """Evaluación de regla que no existe"""
        context = {"monto": 5000}
        
        result = agent.evaluate("non_existent_rule", context)
        
        assert result.matched is False
        assert result.rule_id == "non_existent_rule"


# ============================================================================
# TESTS: ACTIONS
# ============================================================================

class TestActions:
    """Tests para ejecución de acciones"""
    
    def test_action_calculate(self):
        """Test acción CALCULATE"""
        engine = RuleEngine()
        action = RuleAction(
            type=ActionType.CALCULATE,
            details={
                "var": "retencion",
                "formula": "monto * 0.025"
            }
        )
        
        from dataclasses import dataclass
        
        @dataclass
        class MockResult:
            calculated_values = {}
            decisions = []
        
        context = {"monto": 4000}
        result = MockResult()
        
        action_result = engine._execute_action(action, context, result)
        
        assert action_result is not None
        assert action_result["type"] == "calculate"
        assert action_result["var"] == "retencion"
        assert action_result["value"] == 100.0  # 4000 * 0.025
    
    def test_action_set_field(self):
        """Test acción SET_FIELD"""
        engine = RuleEngine()
        action = RuleAction(
            type=ActionType.SET_FIELD,
            details={
                "field": "status",
                "value": "blocked"
            }
        )
        
        from dataclasses import dataclass
        
        @dataclass
        class MockResult:
            calculated_values = {}
            decisions = []
        
        context = {}
        result = MockResult()
        
        action_result = engine._execute_action(action, context, result)
        
        assert action_result is not None
        assert action_result["type"] == "set_field"
        assert action_result["field"] == "status"
        assert action_result["value"] == "blocked"
    
    def test_action_block(self):
        """Test acción BLOCK"""
        engine = RuleEngine()
        action = RuleAction(
            type=ActionType.BLOCK,
            details={"reason": "Límite de crédito excedido"}
        )
        
        from dataclasses import dataclass
        
        @dataclass
        class MockResult:
            calculated_values = {}
            decisions = []
        
        context = {}
        result = MockResult()
        
        action_result = engine._execute_action(action, context, result)
        
        assert action_result is not None
        assert action_result["type"] == "block"
        assert action_result["reason"] == "Límite de crédito excedido"


# ============================================================================
# TESTS: AUDIT LOG
# ============================================================================

class TestAuditLog:
    """Tests para auditoría"""
    
    def test_execution_log_recorded(self, agent, sample_rule_dict, sample_context):
        """Cada evaluación se registra en el log"""
        agent.create_rule(sample_rule_dict)
        
        assert len(agent.execution_log) == 0
        
        agent.evaluate("test_retencion_isr_001", sample_context)
        
        assert len(agent.execution_log) == 1
    
    def test_multiple_evaluations_logged(self, agent, sample_rule_dict):
        """Múltiples evaluaciones se registran"""
        agent.create_rule(sample_rule_dict)
        
        context_1 = {"tipo_documento": "factura", "empresa_id": 100, "monto": 5000}
        context_2 = {"tipo_documento": "factura", "empresa_id": 100, "monto": 500}
        
        agent.evaluate("test_retencion_isr_001", context_1)
        agent.evaluate("test_retencion_isr_001", context_2)
        
        assert len(agent.execution_log) == 2
        
        # Primera evaluación debe cumplir
        assert agent.execution_log[0].matched is True
        
        # Segunda evaluación NO debe cumplir
        assert agent.execution_log[1].matched is False
    
    def test_get_execution_log(self, agent, sample_rule_dict, sample_context):
        """Obtener historial de ejecución"""
        agent.create_rule(sample_rule_dict)
        agent.evaluate("test_retencion_isr_001", sample_context)
        
        log = agent.get_execution_log(rule_id="test_retencion_isr_001")
        
        assert len(log) == 1
        assert log[0].rule_id == "test_retencion_isr_001"
        assert log[0].matched is True


# ============================================================================
# TESTS: INTEGRATION
# ============================================================================

class TestIntegration:
    """Tests de integración - casos reales"""
    
    def test_retention_rule_workflow(self, agent):
        """Workflow completo: crear regla, evaluar, auditar"""
        # 1. Crear regla de retención
        rule_dict = {
            "rule_id": "retencion_isr",
            "name": "Retención ISR 2.5%",
            "description": "Retención sobre facturas >= 1000",
            "empresa_id": 100,
            "conditions": [
                {"field": "monto", "operator": "gte", "value": 1000}
            ],
            "actions": [
                {
                    "type": "calculate",
                    "details": {"var": "retencion", "formula": "monto * 0.025"}
                }
            ]
        }
        
        agent.create_rule(rule_dict)
        
        # 2. Evaluar contra múltiples contextos
        results = []
        for monto in [500, 1000, 5000, 10000]:
            result = agent.evaluate("retencion_isr", {"monto": monto})
            results.append(result)
        
        # 3. Verificar resultados
        assert results[0].matched is False  # 500 < 1000
        assert results[1].matched is True   # 1000 >= 1000
        assert results[2].matched is True   # 5000 >= 1000
        assert results[3].matched is True   # 10000 >= 1000
        
        # 4. Verificar auditoría
        log = agent.get_execution_log()
        assert len(log) == 4
        
        # Verificar cálculos
        assert results[1].calculated_values.get("retencion") == 25.0    # 1000 * 0.025
        assert results[2].calculated_values.get("retencion") == 125.0   # 5000 * 0.025
        assert results[3].calculated_values.get("retencion") == 250.0   # 10000 * 0.025
    
    def test_credit_limit_rule_workflow(self, agent):
        """Workflow de límite de crédito"""
        rule_dict = {
            "rule_id": "credit_limit_check",
            "name": "Check Credit Limit",
            "description": "Block if exceeds limit",
            "empresa_id": 100,
            "conditions": [
                {"field": "saldo_disponible", "operator": "lt", "value": 0}
            ],
            "actions": [
                {
                    "type": "block",
                    "details": {"reason": "Credit limit exceeded"}
                }
            ]
        }
        
        agent.create_rule(rule_dict)
        
        # Cliente con saldo disponible
        result1 = agent.evaluate("credit_limit_check", {"saldo_disponible": 5000})
        assert result1.matched is False
        
        # Cliente sin saldo disponible
        result2 = agent.evaluate("credit_limit_check", {"saldo_disponible": -1000})
        assert result2.matched is True


# ============================================================================
# TEST SUITE RUNNER
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
