# PRISM v2.0 — QAAgent (Agent 5)
**Status:** ✅ LIVE | **Endpoints:** 8 | **Base URL:** `/api/v1/prism`

## Overview
QAAgent manages automated testing, quality assurance, test execution, and performance testing across all test types.

---

## Endpoints

### 1️⃣ GET `/info`
**Metadata and capabilities**
```json
{
  "id": "prism",
  "name": "QAAgent v2.0",
  "endpoints": 8,
  "status": "active",
  "test_types": ["unit", "integration", "e2e", "performance"]
}
```

### 2️⃣ POST `/create-test`
**Create a new test case**
- `test_name` (string): Alphanumeric + underscore (required)
- `test_type` (string): `unit`, `integration`, `e2e`, `performance`
- `description` (optional, string): Test purpose

**Response:**
```json
{
  "status": "success",
  "test_id": "test_user_login_123",
  "test_type": "integration",
  "created": "2026-09-28T11:00:00Z"
}
```

**Example:**
```powershell
$uri = "http://127.0.0.1:8000/api/v1/prism/create-test?" +
       "test_name=test_login_flow&test_type=e2e&description=Verify%20user%20login%20process"
Invoke-WebRequest -Uri $uri -Method POST
```

### 3️⃣ POST `/execute-test`
**Run a test with environment selection**
- `test_id` (string): Target test to execute
- `environment` (string): `dev`, `staging`, `prod`

**Response:**
```json
{
  "status": "success",
  "execution_id": "exec_test_user_login_123",
  "status": "passed",
  "duration_ms": 1523.4,
  "assertions_passed": 8,
  "assertions_failed": 0
}
```

### 4️⃣ GET `/test-results`
**List test execution results**
- `test_id` (optional, string): Filter by test
- `limit` (integer, default=50): Max results

**Response:**
```json
{
  "status": "success",
  "total": 10,
  "results": [
    {
      "execution_id": "exec_test_001",
      "test_id": "test_user_login_123",
      "status": "passed",
      "duration_ms": 1234.5,
      "timestamp": "2026-09-28T11:00:00Z",
      "environment": "staging"
    }
  ]
}
```

### 5️⃣ POST `/create-test-suite`
**Group tests into a suite**
- `suite_name` (string): Alphanumeric + underscore
- `tests` (string): Comma-separated test IDs

**Response:**
```json
{
  "status": "success",
  "suite_id": "suite_smoke_tests_123",
  "tests_added": 5,
  "created": "2026-09-28T11:05:00Z"
}
```

### 6️⃣ POST `/run-test-suite`
**Execute entire test suite with parallel option**
- `suite_id` (string): Target suite
- `parallel` (boolean): Run tests in parallel (default=false)

**Response:**
```json
{
  "status": "success",
  "execution_id": "suite_exec_123",
  "tests_run": 5,
  "passed": 5,
  "failed": 0,
  "skipped": 0,
  "duration_ms": 5234.2,
  "success_rate": "100.0%"
}
```

### 7️⃣ GET `/coverage`
**Code coverage metrics**
- `test_suite` (optional, string): Filter by suite

**Response:**
```json
{
  "status": "success",
  "overall_coverage": 87.5,
  "statements": 92.3,
  "branches": 81.4,
  "functions": 85.6,
  "lines": 89.2,
  "coverage_status": "acceptable"
}
```

### 8️⃣ POST `/performance-test`
**Run load/performance testing**
- `endpoint` (string): Target endpoint URL
- `requests_per_second` (integer): RPS load (min=1)
- `duration_seconds` (integer): Test duration (10-3600)

**Response:**
```json
{
  "status": "success",
  "test_id": "perf_123",
  "duration_seconds": 60,
  "total_requests": 6000,
  "avg_response_ms": 45.3,
  "min_response_ms": 12.1,
  "max_response_ms": 234.5,
  "p99_ms": 234.5,
  "errors": 2,
  "error_rate": "0.03%",
  "throughput_rps": 99.8
}
```

---

## Quality Test Types

| Type | Purpose | Duration | Environment |
|------|---------|----------|-------------|
| **unit** | Test individual functions | <1s | dev |
| **integration** | Test module interactions | 1-5s | staging |
| **e2e** | Test full user workflows | 5-30s | staging/prod |
| **performance** | Load and stress testing | 60-600s | staging |

---

## Security Rules
✅ Test name validation (alphanumeric + underscore)  
✅ Environment whitelist: dev, staging, prod only  
✅ RPS validation: 1+ requests per second  
✅ Duration validation: 10-3600 seconds  
✅ Test type validation: Only 4 allowed types  

---

## Error Handling
- Invalid test_type → `{"status": "error"}`
- RPS < 1 or > 10000 → `{"status": "error"}`
- Duration < 10 seconds → `{"status": "error"}`
- Invalid environment → `{"status": "error"}`
- Test not found → `{"status": "error"}`
