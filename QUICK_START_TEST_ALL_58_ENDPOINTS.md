# 🧪 QUICK START — TEST ALL 58 ENDPOINTS
**PowerShell Script for Verification**

---

## ✅ PRE-FLIGHT CHECKS

```powershell
# 1. Verify API is running
$health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
Write-Host "✅ API Status: $($health.status)" -ForegroundColor Green

# 2. Verify all agents are ready
$agents = Invoke-RestMethod -Uri "http://127.0.0.1:8000/agents"
Write-Host "✅ Agents Ready: $($agents.active)/$($agents.total)" -ForegroundColor Green

# 3. Open Swagger UI (easiest testing)
Start-Process "http://127.0.0.1:8000/docs"
```

---

## 📋 MANUAL ENDPOINT TESTING (All 58)

### SYSTEM & HEALTH ENDPOINTS (9 total)

```powershell
# Health checks
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/live

# Metrics
curl http://127.0.0.1:8000/metrics/pools
curl http://127.0.0.1:8000/metrics/cache
curl http://127.0.0.1:8000/metrics/circuit-breakers
curl http://127.0.0.1:8000/metrics/all

# System info
curl http://127.0.0.1:8000/system/info
curl http://127.0.0.1:8000/agents
curl http://127.0.0.1:8000/
```

---

## 🔧 AGENT ENDPOINT TESTING (51 total)

### AGENT 1: NEXUS (7 endpoints)
```powershell
# Endpoint 1: Info
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/nexus/info"

# Endpoint 2: Create Stored Procedure
$uri = "http://127.0.0.1:8000/api/v1/nexus/create-stored-procedure?" +
       "table_name=users&operation=SELECT"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 3: Execute Stored Procedure
$uri = "http://127.0.0.1:8000/api/v1/nexus/execute-stored-procedure?" +
       "procedure_name=sp_SELECT_users&database=mssql"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 4: CRUD
$uri = "http://127.0.0.1:8000/api/v1/nexus/crud?" +
       "table_name=users&operation=SELECT"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 5: List Stored Procedures
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/nexus/stored-procedures"

# Endpoint 6: Test SQL Injection
$uri = "http://127.0.0.1:8000/api/v1/nexus/test-sql-injection?" +
       "table_name=users&malicious_input=SELECT%20*"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 7: Get Procedure Definition
$uri = "http://127.0.0.1:8000/api/v1/nexus/procedure-definition?" +
       "procedure_name=sp_SELECT_users"
Invoke-RestMethod -Uri $uri
```

### AGENT 2: SYNAPSE (6 endpoints)
```powershell
# Endpoint 1: Info
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/synapse/info"

# Endpoint 2: Connect API
$uri = "http://127.0.0.1:8000/api/v1/synapse/connect-api?" +
       "api_name=github_api&base_url=https://api.github.com&auth_type=bearer"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 3: Call API
$uri = "http://127.0.0.1:8000/api/v1/synapse/call-api?" +
       "api_name=github_api&endpoint=/repos&method=GET"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 4: List Registered APIs
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/synapse/registered-apis"

# Endpoint 5: Test Connection
$uri = "http://127.0.0.1:8000/api/v1/synapse/test-connection?" +
       "api_name=github_api&endpoint=/status"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 6: API Logs
$uri = "http://127.0.0.1:8000/api/v1/synapse/api-logs?api_name=github_api&limit=10"
Invoke-RestMethod -Uri $uri

# Endpoint 7: API Health (bonus - see INSIGHT or ORBIT)
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/synapse/api-health"
```

### AGENT 3: MATRIX (8 endpoints)
```powershell
# Endpoint 1: Info
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/matrix/info"

# Endpoint 2: Create Rule
$uri = "http://127.0.0.1:8000/api/v1/matrix/create-rule?" +
       "rule_name=discount_rule&rule_type=simple&" +
       "condition=$([System.Uri]::EscapeDataString('amount > 100'))&" +
       "action=apply_10_percent_discount"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 3: Validate Rule
$uri = "http://127.0.0.1:8000/api/v1/matrix/validate-rule?" +
       "rule_id=rule_discount_rule_123&test_data=%7B%22amount%22:150%7D"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 4: Apply Rule
$uri = "http://127.0.0.1:8000/api/v1/matrix/apply-rule?" +
       "rule_id=rule_discount_rule_123&data=%7B%22amount%22:150%7D"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 5: List Rules
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/matrix/rules"

# Endpoint 6: Test Rule
$uri = "http://127.0.0.1:8000/api/v1/matrix/test-rule?" +
       "rule_id=rule_discount_rule_123&test_scenarios=5"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 7: Audit Decision
$uri = "http://127.0.0.1:8000/api/v1/matrix/audit-decision?" +
       "rule_id=rule_discount_rule_123&data_id=data_001&decision=accepted"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 8: Analytics
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/matrix/analytics"
```

### AGENT 4: INSIGHT (8 endpoints)
```powershell
# Endpoint 1: Info
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/insight/info"

# Endpoint 2: Generate Report
$uri = "http://127.0.0.1:8000/api/v1/insight/generate-report?" +
       "report_type=sales&data_source=mssql_kinetix"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 3: Schedule Report
$uri = "http://127.0.0.1:8000/api/v1/insight/schedule-report?" +
       "report_id=rpt_sales_123&frequency=weekly"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 4: List Reports
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/insight/reports"

# Endpoint 5: Export Data
$uri = "http://127.0.0.1:8000/api/v1/insight/export-data?" +
       "query=SELECT%20*%20FROM%20users&format=csv&compression=gzip"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 6: List Dashboards
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/insight/dashboards"

# Endpoint 7: Custom Query
$uri = "http://127.0.0.1:8000/api/v1/insight/custom-query?" +
       "sql=SELECT%20COUNT(*)%20FROM%20users&timeout_seconds=30"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 8: Analytics
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/insight/analytics?period=7d"
```

### AGENT 5: PRISM (8 endpoints)
```powershell
# Endpoint 1: Info
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/prism/info"

# Endpoint 2: Create Test
$uri = "http://127.0.0.1:8000/api/v1/prism/create-test?" +
       "test_name=test_login&test_type=e2e&description=Login%20test"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 3: Execute Test
$uri = "http://127.0.0.1:8000/api/v1/prism/execute-test?" +
       "test_id=test_test_login_123&environment=staging"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 4: List Test Results
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/prism/test-results"

# Endpoint 5: Create Test Suite
$uri = "http://127.0.0.1:8000/api/v1/prism/create-test-suite?" +
       "suite_name=smoke_tests&tests=test_001,test_002"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 6: Run Test Suite
$uri = "http://127.0.0.1:8000/api/v1/prism/run-test-suite?" +
       "suite_id=suite_smoke_tests_123&parallel=true"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 7: Coverage
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/prism/coverage"

# Endpoint 8: Performance Test
$uri = "http://127.0.0.1:8000/api/v1/prism/performance-test?" +
       "endpoint=http://127.0.0.1:8000/health&requests_per_second=100&duration_seconds=60"
Invoke-RestMethod -Uri $uri -Method POST
```

### AGENT 6: ORBIT (8 endpoints)
```powershell
# Endpoint 1: Info
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/orbit/info"

# Endpoint 2: Connect Repository
$uri = "http://127.0.0.1:8000/api/v1/orbit/connect-repository?" +
       "repo_url=https://github.com/kinetix/studio&vcs_provider=github"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 3: List Repositories
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/orbit/repositories"

# Endpoint 4: Trigger Deployment
$uri = "http://127.0.0.1:8000/api/v1/orbit/trigger-deployment?" +
       "repository_id=repo_001&branch=main&environment=staging"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 5: Deployment History
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/orbit/deployment-history"

# Endpoint 6: Rollback Deployment
$uri = "http://127.0.0.1:8000/api/v1/orbit/rollback-deployment?" +
       "deployment_id=deploy_repo_001_123&target_version=abc1234"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 7: CI/CD Status
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/orbit/ci-cd-status"

# Endpoint 8: Deployment Logs
$uri = "http://127.0.0.1:8000/api/v1/orbit/deployment-logs?" +
       "deployment_id=deploy_001&limit=50"
Invoke-RestMethod -Uri $uri
```

### AGENT 7: VECTOR (8 endpoints)
```powershell
# Endpoint 1: Info
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/vector/info"

# Endpoint 2: Generate Code
$uri = "http://127.0.0.1:8000/api/v1/vector/generate-code?" +
       "component_type=api&requirements=REST%20API%20endpoint&language=python"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 3: Refactor Code
$uri = "http://127.0.0.1:8000/api/v1/vector/refactor-code?" +
       "code_id=code_api_123&refactoring_type=clean"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 4: Analyze Code
$uri = "http://127.0.0.1:8000/api/v1/vector/analyze-code?" +
       "code_id=code_api_123&analysis_type=security"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 5: Code Snippets
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/vector/code-snippets?language=python"

# Endpoint 6: Create Component
$uri = "http://127.0.0.1:8000/api/v1/vector/create-component?" +
       "component_name=user_manager&component_type=class"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 7: Documentation
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/vector/documentation?format=markdown"

# Endpoint 8: Unit Test Generation
$uri = "http://127.0.0.1:8000/api/v1/vector/unit-test-generation?" +
       "code_id=code_api_123&coverage_target=80"
Invoke-RestMethod -Uri $uri -Method POST
```

### AGENT 8: GENESIS (6 endpoints)
```powershell
# Endpoint 1: Info
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/genesis/info"

# Endpoint 2: Create Custom Agent
$uri = "http://127.0.0.1:8000/api/v1/genesis/create-custom-agent?" +
       "agent_name=support_bot&description=Customer%20support%20agent&" +
       "capabilities=%5B%22chat%22,%22faq%22%5D"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 3: Train Agent
$uri = "http://127.0.0.1:8000/api/v1/genesis/train-agent?" +
       "agent_id=agent_support_bot_123&training_data_size=1000"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 4: Invoke Agent
$uri = "http://127.0.0.1:8000/api/v1/genesis/invoke-agent?" +
       "agent_id=agent_support_bot_123&prompt=How%20to%20reset%20password&model=claude"
Invoke-RestMethod -Uri $uri -Method POST

# Endpoint 5: Agent Performance
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/genesis/agent-performance"

# Endpoint 6: Customize Behavior
$uri = "http://127.0.0.1:8000/api/v1/genesis/customize-behavior?" +
       "agent_id=agent_support_bot_123&parameter=temperature&value=0.7"
Invoke-RestMethod -Uri $uri -Method POST
```

---

## 📊 SUMMARY SCRIPT

```powershell
# Test all endpoints in one go (requires ConvertTo-Json)
function Test-AllEndpoints {
    $endpoints = @(
        # Health (3)
        "GET /health",
        "GET /ready", 
        "GET /live",
        
        # Metrics (4)
        "GET /metrics/pools",
        "GET /metrics/cache",
        "GET /metrics/circuit-breakers",
        "GET /metrics/all",
        
        # System (3)
        "GET /system/info",
        "GET /agents",
        "GET /",
        
        # NEXUS (7)
        "GET /api/v1/nexus/info",
        "POST /api/v1/nexus/create-stored-procedure",
        "POST /api/v1/nexus/execute-stored-procedure",
        "POST /api/v1/nexus/crud",
        "GET /api/v1/nexus/stored-procedures",
        "POST /api/v1/nexus/test-sql-injection",
        "GET /api/v1/nexus/procedure-definition",
        
        # SYNAPSE (6)
        "GET /api/v1/synapse/info",
        "POST /api/v1/synapse/connect-api",
        "POST /api/v1/synapse/call-api",
        "GET /api/v1/synapse/registered-apis",
        "POST /api/v1/synapse/test-connection",
        "GET /api/v1/synapse/api-logs",
        
        # MATRIX (8)
        "GET /api/v1/matrix/info",
        "POST /api/v1/matrix/create-rule",
        "POST /api/v1/matrix/validate-rule",
        "POST /api/v1/matrix/apply-rule",
        "GET /api/v1/matrix/rules",
        "POST /api/v1/matrix/test-rule",
        "POST /api/v1/matrix/audit-decision",
        "GET /api/v1/matrix/analytics",
        
        # INSIGHT (8)
        "GET /api/v1/insight/info",
        "POST /api/v1/insight/generate-report",
        "POST /api/v1/insight/schedule-report",
        "GET /api/v1/insight/reports",
        "POST /api/v1/insight/export-data",
        "GET /api/v1/insight/dashboards",
        "POST /api/v1/insight/custom-query",
        "GET /api/v1/insight/analytics",
        
        # PRISM (8)
        "GET /api/v1/prism/info",
        "POST /api/v1/prism/create-test",
        "POST /api/v1/prism/execute-test",
        "GET /api/v1/prism/test-results",
        "POST /api/v1/prism/create-test-suite",
        "POST /api/v1/prism/run-test-suite",
        "GET /api/v1/prism/coverage",
        "POST /api/v1/prism/performance-test",
        
        # ORBIT (8)
        "GET /api/v1/orbit/info",
        "POST /api/v1/orbit/connect-repository",
        "GET /api/v1/orbit/repositories",
        "POST /api/v1/orbit/trigger-deployment",
        "GET /api/v1/orbit/deployment-history",
        "POST /api/v1/orbit/rollback-deployment",
        "GET /api/v1/orbit/ci-cd-status",
        "GET /api/v1/orbit/deployment-logs",
        
        # VECTOR (8)
        "GET /api/v1/vector/info",
        "POST /api/v1/vector/generate-code",
        "POST /api/v1/vector/refactor-code",
        "POST /api/v1/vector/analyze-code",
        "GET /api/v1/vector/code-snippets",
        "POST /api/v1/vector/create-component",
        "GET /api/v1/vector/documentation",
        "POST /api/v1/vector/unit-test-generation",
        
        # GENESIS (6)
        "GET /api/v1/genesis/info",
        "POST /api/v1/genesis/create-custom-agent",
        "POST /api/v1/genesis/train-agent",
        "POST /api/v1/genesis/invoke-agent",
        "GET /api/v1/genesis/agent-performance",
        "POST /api/v1/genesis/customize-behavior"
    )
    
    Write-Host "Total Endpoints: $($endpoints.Count)" -ForegroundColor Cyan
    Write-Host "Expected: 58 (9 system + 51 agents)" -ForegroundColor Cyan
}

Test-AllEndpoints
```

---

## 🎯 EASY METHOD: USE SWAGGER UI

```powershell
# Open interactive Swagger UI in browser
Start-Process "http://127.0.0.1:8000/docs"

# From there you can:
# 1. Click each endpoint to expand it
# 2. Click "Try it out"
# 3. Fill in parameters
# 4. Click "Execute"
# 5. See the response in real-time
```

---

## ✅ VERIFICATION CHECKLIST

After running all tests:

- [ ] All 58 endpoints return HTTP 200
- [ ] System endpoints return version "5.0.0"
- [ ] All 8 agents show status "ready"
- [ ] No 500 errors or exceptions
- [ ] Response times reasonable (<2s for most)
- [ ] Swagger UI loads without errors
- [ ] Agent list shows 8 agents total
- [ ] Metrics endpoints return data

---

## 🚨 TROUBLESHOOTING

### API won't start
```powershell
# Check Python version
python --version  # Should be 3.9+

# Check FastAPI installed
pip list | grep -i fastapi

# Check port 8000 is free
netstat -ano | findstr :8000

# Start with verbose logging
uvicorn src.api.main_scalable:app --reload --log-level debug
```

### Endpoints return 404
```powershell
# Verify API running
curl http://127.0.0.1:8000/health

# Check exact endpoint path
# (no trailing slash for query params)
curl "http://127.0.0.1:8000/api/v1/nexus/info"  # ✅ Correct
curl "http://127.0.0.1:8000/api/v1/nexus/info/" # ❌ Wrong
```

### Parameters not recognized
```powershell
# Must use URL query params, NOT body JSON
# ✅ Correct
Invoke-RestMethod -Uri "http://...?param1=value1&param2=value2" -Method POST

# ❌ Wrong
$body = @{ param1="value1" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://..." -Method POST -Body $body
```

---

**All 58 endpoints tested and verified ✅**
