# MATRIX v2.0 - BusinessRulesAgent Integration Guide

**Status:** ✅ READY FOR DEPLOYMENT  
**Version:** 5.0.0  
**Endpoints:** 8 fully implemented  
**Rule Types:** simple, compound, conditional, temporal

---

## 📋 MATRIX v2.0 ENDPOINTS

### 1. GET `/api/v1/matrix/info`
Agent metadata and capabilities
```json
{
  "id": "matrix",
  "name": "BusinessRulesAgent v2.0",
  "status": "active",
  "endpoints": 8,
  "capabilities": {
    "rule_creation": true,
    "rule_validation": true,
    "rule_execution": true,
    "constraint_checking": true,
    "audit_trail": true,
    "analytics": true,
    "testing": true
  },
  "supported_rule_types": ["simple", "compound", "conditional", "temporal"]
}
```

### 2. POST `/api/v1/matrix/create-rule`
Create a new business rule
```
Query Params:
- rule_name: string (e.g., "discount_over_100")
- rule_type: string (simple, compound, conditional, temporal)
- description: string (optional)
- condition: string (e.g., "amount > 100")
- action: string (e.g., "apply_10_percent_discount")

Response:
{
  "status": "success",
  "rule_id": "rule_discount_over_100_1234567890",
  "rule_name": "discount_over_100",
  "rule_type": "simple",
  "status": "created",
  "enabled": true,
  "created_at": "2026-09-28T11:00:00Z",
  "version": "1.0.0"
}
```

### 3. POST `/api/v1/matrix/validate-rule`
Validate a rule against constraints
```
Query Params:
- rule_id: string
- test_data: string (optional - JSON with test data)

Response:
{
  "status": "success",
  "rule_id": "rule_discount_over_100_...",
  "is_valid": true,
  "validation_checks": {
    "syntax_valid": true,
    "constraints_met": true,
    "dependencies_resolved": true,
    "conflicts_detected": false,
    "warnings": []
  },
  "message": "Rule validation PASSED"
}
```

### 4. POST `/api/v1/matrix/apply-rule`
Apply a rule to specific data
```
Query Params:
- rule_id: string
- data: string (JSON with data to process)
- context: string (optional - execution context)

Response:
{
  "status": "success",
  "rule_id": "rule_discount_over_100_...",
  "execution_result": "rule_applied",
  "data_processed": 1,
  "conditions_met": true,
  "action_executed": true,
  "affected_records": 1,
  "execution_time_ms": 45.67
}
```

### 5. GET `/api/v1/matrix/rules`
List all available business rules
```
Query Params:
- rule_type: string (optional - filter by type)
- enabled_only: boolean (default: true)
- limit: int (default: 50)

Response:
{
  "status": "success",
  "total": 4,
  "rule_type_filter": null,
  "enabled_only": true,
  "rules": [
    {
      "rule_id": "rule_discount_1",
      "rule_name": "discount_over_100",
      "rule_type": "simple",
      "enabled": true,
      "created_at": "2026-09-28T08:00:00Z",
      "execution_count": 245
    },
    ...
  ]
}
```

### 6. POST `/api/v1/matrix/test-rule`
Test a rule with multiple scenarios
```
Query Params:
- rule_id: string
- test_scenarios: string (optional - JSON with test cases)

Response:
{
  "status": "completed",
  "rule_id": "rule_discount_over_100_...",
  "total_scenarios": 5,
  "passed": 5,
  "failed": 0,
  "success_rate": "100.0%",
  "test_results": [
    {"scenario": "scenario_1", "result": "PASS"},
    ...
  ]
}
```

### 7. POST `/api/v1/matrix/audit-decision`
Record audit trail of rule decisions
```
Query Params:
- rule_id: string
- data_id: string
- decision: string (accepted, rejected, escalated, manual_review)
- reason: string (optional)

Response:
{
  "status": "success",
  "audit_id": "audit_rule_..._1234567890",
  "rule_id": "rule_discount_over_100_...",
  "data_id": "order_12345",
  "decision": "accepted",
  "reason": "Discount criteria met",
  "user": "system",
  "audited_at": "2026-09-28T11:00:00Z",
  "is_archived": false
}
```

### 8. GET `/api/v1/matrix/analytics`
Get rule execution and effectiveness analytics
```
Query Params:
- rule_id: string (optional - filter by specific rule)
- time_period: string (24h, 7d, 30d, 90d - default: 24h)

Response:
{
  "status": "success",
  "time_period": "24h",
  "total_rules_analyzed": 3,
  "total_executions": 1537,
  "average_success_rate": "99.2%",
  "rules": [
    {
      "rule_id": "rule_discount_over_100_...",
      "rule_name": "discount_over_100",
      "execution_count": 245,
      "success_rate": 98.5,
      "avg_execution_time_ms": 12.5,
      "decisions": {
        "accepted": 240,
        "rejected": 5,
        "escalated": 0
      }
    },
    ...
  ]
}
```

---

## 🎯 RULE TYPES

### 1. Simple Rules
Single condition → action
```
Condition: amount > 100
Action: apply_10_percent_discount
```

### 2. Compound Rules
Multiple conditions (AND/OR) → action
```
Condition: quantity > 50 AND total_weight > 1000
Action: require_warehouse_approval
```

### 3. Conditional Rules
If-then-else logic
```
Condition: payment_method == 'card' ? validate_cvv : validate_account
Action: process_payment
```

### 4. Temporal Rules
Time-based conditions
```
Condition: current_month IN (11,12) AND product_category == 'gift'
Action: apply_holiday_markup
```

---

## 💡 USE CASES

### UC1: Discount Rule
```bash
POST /api/v1/matrix/create-rule
- rule_name: discount_over_100
- rule_type: simple
- condition: amount > 100
- action: apply_10_percent_discount

# Apply the rule
POST /api/v1/matrix/apply-rule
- rule_id: rule_discount_over_100_...
- data: {"order_id": "12345", "amount": 150}

# Expected result: Discount applied (150 * 0.9 = 135)
```

### UC2: Bulk Order Approval
```bash
POST /api/v1/matrix/create-rule
- rule_name: bulk_order_check
- rule_type: compound
- condition: quantity > 50 AND total_weight > 1000
- action: require_warehouse_approval

# Apply to bulk order
POST /api/v1/matrix/apply-rule
- rule_id: rule_bulk_order_check_...
- data: {"order_id": "54321", "quantity": 75, "total_weight": 1200}

# Result: Escalated for warehouse approval
```

### UC3: Payment Validation
```bash
POST /api/v1/matrix/create-rule
- rule_name: payment_validation
- rule_type: conditional
- condition: payment_method == 'card' ? validate_cvv : validate_account
- action: process_payment

# Apply to payment
POST /api/v1/matrix/apply-rule
- rule_id: rule_payment_validation_...
- data: {"payment_method": "card", "amount": 299.99}

# Result: CVV validation required
```

### UC4: View Rule Effectiveness
```bash
GET /api/v1/matrix/analytics?rule_id=rule_discount_over_100_...&time_period=7d

# Response shows:
# - 245 executions in last 7 days
# - 98.5% success rate
# - Avg execution time: 12.5ms
# - Business impact: $15,200.50 in discounts
```

---

## 🔒 SECURITY

### Input Validation
```
✅ Rule name regex     → ^[a-zA-Z_][a-zA-Z0-9_]*$
✅ Rule type check     → simple, compound, conditional, temporal only
✅ Rule ID validation  → must start with "rule_"
✅ Decision validation → accepted, rejected, escalated, manual_review
✅ Data ID validation  → ^[a-zA-Z_][a-zA-Z0-9_]*$
✅ Minimum lengths     → condition >= 5 chars, action >= 5 chars
```

### Features
- ✅ Complete audit trail for all decisions
- ✅ Conflict detection between rules
- ✅ Constraint validation
- ✅ Dependency resolution checking
- ✅ Test execution without side effects

---

## 📊 COMPARISON: NEXUS vs SYNAPSE vs MATRIX

| Feature | NEXUS | SYNAPSE | MATRIX |
|---------|-------|---------|--------|
| Focus | Database | APIs | Business Rules |
| Endpoints | 7 | 6 | 8 |
| Primary Function | CRUD + SPs | HTTP Calls | Rule Engine |
| Validation | SQL Injection | URL + Auth | Constraints |
| Output | Query Results | API Response | Rule Decision |
| Audit | SP Execution | API Logs | Rule Decisions |

---

## 🚀 DEPLOYMENT

### File
`main_scalable_NEXUS_SYNAPSE_MATRIX.py` (574 lines)

### Installation
```powershell
Copy-Item "main_scalable_NEXUS_SYNAPSE_MATRIX.py" "src\api\main_scalable.py" -Force
uvicorn src.api.main_scalable:app --reload
```

### Verification
```
http://127.0.0.1:8000/docs

You should see:
- NEXUS v2.0: 7 endpoints
- SYNAPSE v2.0: 6 endpoints
- MATRIX v2.0: 8 endpoints
- Health: 3 endpoints
- Metrics: 4 endpoints
- System: 2 endpoints
- Total: 30 endpoints
```

---

## 📈 PROGRESS

| Agent | Endpoints | Status |
|-------|-----------|--------|
| NEXUS | 7/7 | ✅ Complete |
| SYNAPSE | 6/6 | ✅ Complete |
| MATRIX | 8/8 | ✅ Complete |
| INSIGHT | 0/8 | ⏳ Pending |
| PRISM | 0/8 | ⏳ Pending |
| ORBIT | 0/8 | ⏳ Pending |
| VECTOR | 0/8 | ⏳ Pending |
| GENESIS | 0/6 | ⏳ Pending |

**Total: 30/58 endpoints (52%)**

---

## 🎯 NEXT AGENT

**INSIGHT (ReportingAgent) - 8 endpoints**
- Generate reports (PDF, Excel, JSON)
- Data aggregation & summarization
- Custom report builder
- Scheduled delivery
- Report caching

---

**Ready for integration!** 🚀
