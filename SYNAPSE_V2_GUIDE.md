# SYNAPSE v2.0 - APIsAgent Integration Guide

**Status:** ✅ READY FOR DEPLOYMENT  
**Version:** 5.0.0  
**Endpoints:** 6 fully implemented

---

## 📋 SYNAPSE v2.0 ENDPOINTS

### 1. GET `/api/v1/synapse/info`
Agent metadata and capabilities
```json
{
  "id": "synapse",
  "name": "APIsAgent v2.0",
  "status": "active",
  "endpoints": 6,
  "capabilities": {
    "api_integration": true,
    "request_orchestration": true,
    "authentication": true,
    "rate_limiting": true,
    "response_caching": true,
    "error_handling": true
  }
}
```

### 2. POST `/api/v1/synapse/connect-api`
Register and connect an external API
```
Query Params:
- api_name: string (e.g., "github_api")
- base_url: string (e.g., "https://api.github.com")
- auth_type: string (none, basic, bearer, api_key)
- credentials: string (optional)

Response:
{
  "status": "success",
  "api_name": "github_api",
  "connection_id": "conn_github_api_...",
  "connected_at": "2026-09-28T..."
}
```

### 3. POST `/api/v1/synapse/call-api`
Execute an HTTP call to a registered API
```
Query Params:
- api_name: string (registered API name)
- endpoint: string (e.g., "/repos/user/repo")
- method: string (GET, POST, PUT, DELETE, PATCH)
- data: string (JSON data for POST/PUT)

Response:
{
  "status": "success",
  "api_name": "github_api",
  "endpoint": "/repos",
  "method": "GET",
  "http_status": 200,
  "response_time_ms": 245.32,
  "cached": false
}
```

### 4. GET `/api/v1/synapse/registered-apis`
List all registered APIs
```json
{
  "status": "success",
  "total": 4,
  "connected": 3,
  "apis": [
    {
      "name": "github_api",
      "base_url": "https://api.github.com",
      "auth_type": "bearer",
      "status": "connected"
    },
    ...
  ]
}
```

### 5. POST `/api/v1/synapse/test-connection`
Test connection to a registered API
```
Query Params:
- api_name: string
- endpoint: string (default: "/")

Response:
{
  "status": "completed",
  "api_name": "github_api",
  "connection_ok": true,
  "http_status": 200,
  "response_time_ms": 87.33,
  "message": "Conexión exitosa"
}
```

### 6. GET `/api/v1/synapse/api-logs`
Get logs of API calls
```
Query Params:
- api_name: string (optional filter)
- limit: int (default: 10)

Response:
{
  "status": "success",
  "total_logs": 3,
  "logs": [
    {
      "id": "log_001",
      "api_name": "github_api",
      "endpoint": "/repos",
      "method": "GET",
      "status": 200,
      "response_time_ms": 245.32
    },
    ...
  ]
}
```

### 7. GET `/api/v1/synapse/api-health`
Health status of all registered APIs
```json
{
  "status": "completed",
  "total_apis": 4,
  "healthy": 2,
  "degraded": 1,
  "unhealthy": 1,
  "apis": [
    {
      "api_name": "github_api",
      "status": "healthy",
      "uptime_percent": 99.95,
      "avg_response_time_ms": 245.5
    },
    ...
  ]
}
```

---

## 🔌 USE CASES

### 1. Connect GitHub API
```bash
POST /api/v1/synapse/connect-api
- api_name: github_api
- base_url: https://api.github.com
- auth_type: bearer
- credentials: ghp_xxxxxxxxxxxx
```

### 2. Fetch User Repos
```bash
POST /api/v1/synapse/call-api
- api_name: github_api
- endpoint: /user/repos
- method: GET
```

### 3. Monitor API Health
```bash
GET /api/v1/synapse/api-health
Response: Health status of all connected APIs
```

### 4. View Call Logs
```bash
GET /api/v1/synapse/api-logs?api_name=github_api&limit=20
Response: Last 20 calls to GitHub API
```

---

## 🔒 SECURITY

- ✅ URL validation (must start with http:// or https://)
- ✅ API name validation (regex: `^[a-zA-Z_][a-zA-Z0-9_]*$`)
- ✅ HTTP method validation (allowed: GET, POST, PUT, DELETE, PATCH)
- ✅ Endpoint validation (must start with /)
- ✅ Auth type validation (none, basic, bearer, api_key)
- ✅ Response caching to reduce API calls
- ✅ Rate limiting built-in
- ✅ Error handling with meaningful messages

---

## 📊 COMPARISON: NEXUS vs SYNAPSE

| Feature | NEXUS | SYNAPSE |
|---------|-------|---------|
| Focus | Database Operations | API Integration |
| Endpoints | 7 | 6 |
| Main Function | CRUD + Stored Procedures | HTTP Calls + Orchestration |
| Security | SQL Injection Prevention | URL + Auth Validation |
| Caching | N/A | Response Cache |
| Rate Limiting | N/A | Built-in |

---

## 🚀 DEPLOYMENT

### File
`main_scalable_NEXUS_SYNAPSE.py` (504 lines)

### Installation
```powershell
Copy-Item "main_scalable_NEXUS_SYNAPSE.py" "src\api\main_scalable.py" -Force
uvicorn src.api.main_scalable:app --reload
```

### Verification
```
http://127.0.0.1:8000/docs
```

You should see:
- **NEXUS v2.0** - 7 endpoints
- **SYNAPSE v2.0** - 6 endpoints
- **Health** - 3 endpoints
- **Metrics** - 4 endpoints
- **System** - 2 endpoints
- **Total: 22 endpoints**

---

## 📈 PROGRESS

| Agent | Endpoints | Status |
|-------|-----------|--------|
| NEXUS | 7/7 | ✅ Complete |
| SYNAPSE | 6/6 | ✅ Complete |
| MATRIX | 0/8 | ⏳ Pending |
| INSIGHT | 0/8 | ⏳ Pending |
| PRISM | 0/8 | ⏳ Pending |
| ORBIT | 0/8 | ⏳ Pending |
| VECTOR | 0/8 | ⏳ Pending |
| GENESIS | 0/6 | ⏳ Pending |

**Total: 22/58 endpoints (38%)**

---

## 🎯 NEXT AGENT

**MATRIX (BusinessRulesAgent) - 8 endpoints**
- Validate business rules
- Check constraints
- Apply conditions
- Audit decisions
- Cache rules
- Export/Import rules
- Rule testing
- Analytics

---

**Ready for integration!** 🚀
