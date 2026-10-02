# 🔐 SENTINEL v1.0 — INTEGRATION GUIDE

**How SENTINEL Integrates with KINETIX Studio Agents**  
**Version:** 1.0.0  
**Status:** Ready for Implementation

---

## 📑 TABLE OF CONTENTS

1. [Architecture Overview](#architecture-overview)
2. [Integration with NEXUS (Database)](#integration-with-nexus-database)
3. [Integration with MATRIX (Business Rules)](#integration-with-matrix-business-rules)
4. [Integration with SYNAPSE (APIs)](#integration-with-synapse-apis)
5. [Integration with AURORA (Frontend)](#integration-with-aurora-frontend)
6. [Integration with VECTOR (Code Generation)](#integration-with-vector-code-generation)
7. [Integration with ORBIT (Deployment)](#integration-with-orbit-deployment)
8. [Integration with PRISM (QA)](#integration-with-prism-qa)
9. [Complete Request Flow](#complete-request-flow)
10. [Error Handling Strategy](#error-handling-strategy)

---

## 🏗️ ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────┐
│                     CLIENT REQUEST                         │
│                                                             │
│     curl -X POST /api/v1/nexus/crud \                      │
│       -H "Authorization: Bearer <token>"                   │
│       -H "Content-Type: application/json"                  │
│       -d '{"table":"sales_orders", "op":"SELECT"}'         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   SENTINEL VALIDATION                      │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  1. Extract JWT token from Authorization header    │  │
│  │  2. Validate JWT signature (HS256)                 │  │
│  │  3. Check token expiration                          │  │
│  │  4. Extract claims: user_id, tenant_id, roles      │  │
│  │  5. Create user_context object                     │  │
│  │  6. Log authentication event to audit_log          │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  Result: user_context = {                                 │
│    "user_id": "user_123",                                 │
│    "tenant_id": "imvesa",                                 │
│    "roles": ["admin"],                                    │
│    "permissions": ["*"]                                   │
│  }                                                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│               NEXUS PROCESSES REQUEST                       │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  1. Receive user_context from SENTINEL             │  │
│  │  2. Check permission (select_sales_orders)         │  │
│  │  3. Build query with automatic RLS:                │  │
│  │     SELECT * FROM sales_orders                     │  │
│  │     WHERE tenant_id = 'imvesa'  [AUTO from SENTINEL]│  │
│  │     AND user_has_permission(user_123, 'SELECT')    │  │
│  │  4. Execute secured query                          │  │
│  │  5. Return filtered results                        │  │
│  │  6. Log NEXUS operation to audit_log              │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  Result: data filtered by tenant + permissions            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                CLIENT RECEIVES RESPONSE                     │
│  - Only data user is authorized to see                     │
│  - Audit trail recorded in immutable log                   │
│  - Response time: ~50-100ms (cached)                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔗 INTEGRATION WITH NEXUS (DATABASE)

### 1. NEXUS receives JWT token from SENTINEL

**Flow:**

```python
# Client makes request to NEXUS with Bearer token
curl -X POST http://localhost:8000/api/v1/nexus/crud \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "sales_orders",
    "operation": "SELECT",
    "filters": {"status": "pending"}
  }'
```

### 2. NEXUS validates token with SENTINEL

```python
# In NEXUS endpoint
@nexus.post("/crud")
async def nexus_crud(
    table_name: str,
    operation: str,
    filters: Optional[Dict] = None,
    authorization: str = Header(...)  # Bearer token
):
    # STEP 1: Validate token with SENTINEL
    user_context = await sentinel.validate_token(authorization)
    if not user_context:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Result:
    # user_context = {
    #   "user_id": "user_123",
    #   "tenant_id": "imvesa",
    #   "roles": ["admin"],
    #   "permissions": ["select_sales_orders", "insert_sales_orders"]
    # }
    
    # STEP 2: Check permission
    required_permission = f"{operation.lower()}_{table_name}"
    if required_permission not in user_context["permissions"] and \
       "*" not in user_context["permissions"]:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # STEP 3: Build query with automatic RLS (Row-Level Security)
    query = f"SELECT * FROM {table_name}"
    
    # CRITICAL: Always filter by tenant_id
    query += f" WHERE tenant_id = '{user_context['tenant_id']}'"
    
    # Add user filters
    if filters:
        for key, value in filters.items():
            query += f" AND {key} = '{value}'"
    
    # STEP 4: Execute query
    try:
        result = await execute_sql(query)
    except Exception as e:
        # Log failure
        await sentinel.audit_log(
            user_id=user_context["user_id"],
            tenant_id=user_context["tenant_id"],
            action="nexus_crud",
            resource=table_name,
            result="failure",
            error=str(e)
        )
        raise
    
    # STEP 5: Log success to SENTINEL audit
    await sentinel.audit_log(
        user_id=user_context["user_id"],
        tenant_id=user_context["tenant_id"],
        action=operation,
        resource=table_name,
        result="success",
        changes={"filters": filters}
    )
    
    return {"status": "success", "data": result}
```

### 3. Key NEXUS+SENTINEL Integration Points

| Aspect | Implementation |
|--------|-----------------|
| **RLS (Row-Level Security)** | Always add `WHERE tenant_id = :tenant_id` |
| **Permission Check** | Before executing query, check `{operation}_{table}` permission |
| **Audit Logging** | Log every CRUD operation with user_id, action, result |
| **Error Handling** | Return 403 for permission denied, 401 for invalid token |
| **Connection Pool** | Use same DB connection pool, pass user_id for audit |

### 4. Example: Secure CRUD Operations

```python
# SELECT - Read data (only user's tenant + allowed rows)
@nexus.get("/select")
async def select_data(
    table_name: str,
    authorization: str = Header(...)
):
    user_context = await sentinel.validate_token(authorization)
    
    # Only user's own data
    query = f"""
        SELECT * FROM {table_name}
        WHERE tenant_id = '{user_context['tenant_id']}'
    """
    
    data = await execute_sql(query)
    await sentinel.audit_log(user_context, "SELECT", table_name, "success")
    return data

# INSERT - Create new record (auto-set tenant_id)
@nexus.post("/insert")
async def insert_data(
    table_name: str,
    data: Dict,
    authorization: str = Header(...)
):
    user_context = await sentinel.validate_token(authorization)
    
    # Check permission
    if f"insert_{table_name}" not in user_context["permissions"]:
        raise HTTPException(status_code=403)
    
    # Auto-set tenant_id and created_by
    data["tenant_id"] = user_context["tenant_id"]
    data["created_by"] = user_context["user_id"]
    data["created_at"] = datetime.utcnow()
    
    result = await insert_to_db(table_name, data)
    await sentinel.audit_log(user_context, "INSERT", table_name, "success")
    return result

# UPDATE - Modify record (only own tenant's records)
@nexus.put("/update")
async def update_data(
    table_name: str,
    record_id: str,
    updates: Dict,
    authorization: str = Header(...)
):
    user_context = await sentinel.validate_token(authorization)
    
    # Verify record belongs to user's tenant
    query = f"""
        SELECT id FROM {table_name}
        WHERE id = '{record_id}' AND tenant_id = '{user_context['tenant_id']}'
    """
    record = await fetch_one(query)
    
    if not record:
        raise HTTPException(status_code=404)
    
    updates["updated_by"] = user_context["user_id"]
    updates["updated_at"] = datetime.utcnow()
    
    result = await update_db(table_name, record_id, updates)
    await sentinel.audit_log(user_context, "UPDATE", table_name, "success")
    return result

# DELETE - Remove record (only own tenant's records)
@nexus.delete("/delete")
async def delete_data(
    table_name: str,
    record_id: str,
    authorization: str = Header(...)
):
    user_context = await sentinel.validate_token(authorization)
    
    # Check permission
    if f"delete_{table_name}" not in user_context["permissions"]:
        raise HTTPException(status_code=403)
    
    # Verify record belongs to user's tenant
    query = f"""
        SELECT id FROM {table_name}
        WHERE id = '{record_id}' AND tenant_id = '{user_context['tenant_id']}'
    """
    record = await fetch_one(query)
    
    if not record:
        raise HTTPException(status_code=404)
    
    # Soft delete (better for audit)
    result = await update_db(table_name, record_id, {
        "deleted_at": datetime.utcnow(),
        "deleted_by": user_context["user_id"]
    })
    
    await sentinel.audit_log(user_context, "DELETE", table_name, "success")
    return result
```

---

## 🔗 INTEGRATION WITH MATRIX (BUSINESS RULES)

### Flow: MATRIX applies rules only if user has permission

```python
@matrix.post("/apply-rule")
async def apply_business_rule(
    rule_id: str,
    data: Dict,
    authorization: str = Header(...)
):
    # STEP 1: Validate token
    user_context = await sentinel.validate_token(authorization)
    
    # STEP 2: Load rule
    rule = await matrix.get_rule(rule_id)
    
    # STEP 3: Check permission
    permission_required = f"apply_rule_{rule.category}"
    if permission_required not in user_context["permissions"] and \
       "*" not in user_context["permissions"]:
        await sentinel.audit_log(
            user_context, "apply_rule", rule_id, "failure"
        )
        raise HTTPException(status_code=403)
    
    # STEP 4: Audit entry for rule application
    audit_id = secrets.token_hex(8)
    
    # STEP 5: Apply rule (MATRIX evaluates business logic)
    result = await matrix.evaluate_rule(rule, data)
    
    # STEP 6: Audit the decision
    await sentinel.audit_log(
        user_id=user_context["user_id"],
        tenant_id=user_context["tenant_id"],
        action=f"apply_rule_{rule.type}",
        resource=f"rule_{rule_id}",
        result="success",
        changes={
            "input": data,
            "output": result,
            "audit_id": audit_id
        }
    )
    
    # STEP 7: Return result with audit trail
    return {
        "status": "success",
        "rule_id": rule_id,
        "result": result,
        "audit_id": audit_id
    }
```

### Example: Apply approval rule only if user is approver

```python
# Rule: If order > $10,000, requires manager approval
# User permission: "approve_orders_over_10k"

rule = {
    "id": "rule_approval_001",
    "type": "approval",
    "condition": "order.total > 10000",
    "action": "require_manager_approval",
    "required_role": "finance_manager"
}

# User with admin role: ✅ Can apply any rule
# User with finance_manager role: ✅ Can apply if has explicit permission
# User with sales_rep role: ❌ Cannot apply

# SENTINEL checks: "apply_rule_approval" in user.permissions
```

---

## 🔗 INTEGRATION WITH SYNAPSE (EXTERNAL APIs)

### Flow: SYNAPSE uses SENTINEL token for API calls

```python
@synapse.post("/call-api")
async def call_external_api(
    api_name: str,  # "stripe", "salesforce", "shopify", etc
    endpoint: str,  # "/v1/customers"
    method: str = "GET",
    payload: Optional[Dict] = None,
    authorization: str = Header(...)
):
    # STEP 1: Validate user token
    user_context = await sentinel.validate_token(authorization)
    
    # STEP 2: Check permission to call this API
    permission = f"call_api_{api_name}"
    if permission not in user_context["permissions"]:
        await sentinel.audit_log(
            user_context, "call_api", api_name, "failure"
        )
        raise HTTPException(status_code=403)
    
    # STEP 3: Get API credentials from SENTINEL secrets vault
    # In production: HashiCorp Vault / AWS Secrets Manager
    api_credentials = await sentinel.get_secret(
        secret_name=f"api_{api_name}_credentials",
        tenant_id=user_context["tenant_id"]
    )
    
    # Credentials example:
    # {
    #   "api_key": "sk_live_1234567890",
    #   "secret": "secret_key_1234",
    #   "access_token": "token_abc123",
    #   "endpoint_base": "https://api.stripe.com"
    # }
    
    # STEP 4: Make HTTP call with credentials
    headers = {
        "Authorization": f"Bearer {api_credentials.access_token}",
        "X-API-Key": api_credentials.api_key,
        "X-User-ID": user_context["user_id"],
        "X-Tenant-ID": user_context["tenant_id"],
        "X-Request-ID": str(uuid4())  # For tracing
    }
    
    try:
        response = await httpx.request(
            method=method,
            url=f"{api_credentials.endpoint_base}{endpoint}",
            headers=headers,
            json=payload,
            timeout=30.0
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        await sentinel.audit_log(
            user_context, "call_api", api_name, "failure",
            error=str(e)
        )
        raise
    
    # STEP 5: Log successful API call
    await sentinel.audit_log(
        user_id=user_context["user_id"],
        tenant_id=user_context["tenant_id"],
        action="call_external_api",
        resource=api_name,
        resource_id=endpoint,
        result="success",
        changes={
            "method": method,
            "status_code": response.status_code,
            "endpoint": endpoint
        }
    )
    
    return {
        "status": "success",
        "api": api_name,
        "endpoint": endpoint,
        "response": response.json()
    }
```

### SYNAPSE API Permissions Matrix

```
User Roles:
  - admin: call_api_*  (all APIs)
  - sales_manager: call_api_salesforce, call_api_stripe
  - inventory_manager: call_api_shopify, call_api_inventory_system
  - finance: call_api_accounting, call_api_payroll

Credentials stored per tenant:
  - imvesa/api_stripe_credentials ✅
  - imvesa/api_salesforce_credentials ✅
  - imvesa/api_shopify_credentials ✅
```

---

## 🔗 INTEGRATION WITH AURORA (FRONTEND)

### Flow: AURORA receives user context from SENTINEL

```javascript
// Client-side JavaScript (React/Vue/Angular)

// Step 1: Get token from SENTINEL
async function login(username, password) {
  const response = await fetch('/api/v1/sentinel/authenticate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: username,
      password: password,
      tenant_id: 'imvesa'
    })
  });
  
  const data = await response.json();
  
  if (response.ok) {
    // Store token
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    
    // Step 2: Initialize AURORA with user context
    initializeAuroraUI(data.user);
  }
}

// Step 2: AURORA uses token for all API calls
function makeSecureRequest(endpoint, options = {}) {
  const token = localStorage.getItem('access_token');
  
  return fetch(endpoint, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
}

// Step 3: AURORA renders UI based on user permissions
function renderSalesOrderForm(user) {
  const permissions = user.permissions;
  
  return (
    <div>
      {permissions.includes('create_sales_orders') && (
        <button onClick={createOrder}>Create Order</button>
      )}
      {permissions.includes('approve_orders') && (
        <button onClick={approveOrder}>Approve</button>
      )}
      {permissions.includes('delete_sales_orders') && (
        <button onClick={deleteOrder} className="danger">Delete</button>
      )}
    </div>
  );
}

// Step 4: Token refresh
async function refreshAccessToken() {
  const refreshToken = localStorage.getItem('refresh_token');
  
  const response = await fetch('/api/v1/sentinel/refresh-token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      refresh_token: refreshToken,
      grant_type: 'refresh_token'
    })
  });
  
  const data = await response.json();
  
  if (response.ok) {
    localStorage.setItem('access_token', data.access_token);
  } else {
    // Redirect to login
    window.location.href = '/login';
  }
}

// Step 5: Logout
async function logout() {
  const token = localStorage.getItem('access_token');
  
  await fetch('/api/v1/sentinel/logout', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
  
  window.location.href = '/login';
}
```

### AURORA Component Configuration with Permissions

```python
# In AURORA design system, permissions-aware components

components = {
    "SalesOrderForm": {
        "fields": [
            {"name": "customer_id", "required": True},
            {"name": "amount", "required": True},
            {
                "name": "approval_needed",
                "visible_if": "user.permissions.includes('request_approval')",
                "editable_if": "user.roles.includes('manager')"
            }
        ],
        "buttons": [
            {"label": "Create", "action": "create", "requires_permission": "create_sales_orders"},
            {"label": "Approve", "action": "approve", "requires_permission": "approve_orders"},
            {"label": "Delete", "action": "delete", "requires_permission": "delete_sales_orders"}
        ]
    },
    "DashboardWidget": {
        "visible_if": "user.roles.includes('admin') OR user.roles.includes('manager')",
        "data_endpoint": "/api/v1/nexus/select?table=dashboard_data"
    }
}
```

---

## 🔗 INTEGRATION WITH VECTOR (CODE GENERATION)

### Flow: VECTOR generates code with authentication checks

```python
@vector.post("/generate-code")
async def generate_secure_code(
    specification: str,  # Component spec
    authorization: str = Header(...)
):
    # STEP 1: Validate user token
    user_context = await sentinel.validate_token(authorization)
    
    # STEP 2: Check permission
    if "generate_code" not in user_context["permissions"]:
        raise HTTPException(status_code=403)
    
    # STEP 3: Parse specification
    spec = json.loads(specification)
    
    # STEP 4: Generate code WITH security headers
    generated_code = {
        "react_component": f"""
import React, {{useState}} from 'react';

export function {spec.component_name}() {{
  // SECURITY: Get token from localStorage
  const token = localStorage.getItem('access_token');
  
  // SECURITY: Make authenticated requests
  const handleSubmit = async (data) => {{
    const response = await fetch('/api/v1/nexus/insert', {{
      method: 'POST',
      headers: {{
        'Authorization': `Bearer ${{token}}`,
        'Content-Type': 'application/json'
      }},
      body: JSON.stringify({{
        table_name: '{spec.table}',
        data: data
      }})
    }});
    return response.json();
  }};
  
  return (
    <form onSubmit={{handleSubmit}}>
      {/* Form fields */}
    </form>
  );
}}
        """,
        "fastapi_endpoint": f"""
@app.post("/api/v1/{spec.path}")
async def {spec.endpoint_name}(
    data: dict,
    authorization: str = Header(...)
):
    # SECURITY: Validate token with SENTINEL
    user_context = await sentinel.validate_token(authorization)
    
    # SECURITY: Check permission
    if "{spec.permission}" not in user_context["permissions"]:
        raise HTTPException(status_code=403)
    
    # SECURITY: Auto-inject tenant_id and user_id
    data["tenant_id"] = user_context["tenant_id"]
    data["created_by"] = user_context["user_id"]
    
    # SECURITY: Audit log
    await sentinel.audit_log(
        user_context, "{spec.action}", "{spec.resource}", "success"
    )
    
    return {{"status": "success", "data": data}}
        """
    }
    
    # STEP 5: Log code generation
    await sentinel.audit_log(
        user_context, "generate_code", f"component_{spec.component_name}", "success"
    )
    
    return {
        "status": "success",
        "code": generated_code,
        "security_headers_included": True
    }
```

**Key Point:** VECTOR always injects:
- `Authorization: Bearer ${token}` header
- `user_context` validation
- `tenant_id` auto-injection
- Audit logging calls

---

## 🔗 INTEGRATION WITH ORBIT (DEPLOYMENT)

### Flow: ORBIT uses SENTINEL for deployment credentials

```python
@orbit.post("/deploy")
async def deploy_application(
    app_name: str,
    version: str,
    environment: str,  # dev, staging, production
    authorization: str = Header(...)
):
    # STEP 1: Validate user token
    user_context = await sentinel.validate_token(authorization)
    
    # STEP 2: Check deployment permission
    if f"deploy_to_{environment}" not in user_context["permissions"]:
        await sentinel.audit_log(
            user_context, "deploy", app_name, "failure"
        )
        raise HTTPException(status_code=403)
    
    # STEP 3: Production deployments require approval
    if environment == "production" and "approve_production_deploy" not in user_context["permissions"]:
        raise HTTPException(status_code=403, detail="Production deployments require explicit approval")
    
    # STEP 4: Get deployment credentials from SENTINEL
    deploy_creds = await sentinel.get_secret(
        secret_name=f"deploy_creds_{environment}",
        tenant_id=user_context["tenant_id"]
    )
    
    # STEP 5: Execute deployment
    try:
        result = await deploy_with_credentials(
            app_name=app_name,
            version=version,
            environment=environment,
            credentials=deploy_creds
        )
    except Exception as e:
        await sentinel.audit_log(
            user_context, "deploy", app_name, "failure", error=str(e)
        )
        raise
    
    # STEP 6: Audit deployment
    await sentinel.audit_log(
        user_id=user_context["user_id"],
        tenant_id=user_context["tenant_id"],
        action="deploy",
        resource=app_name,
        result="success",
        changes={
            "version": version,
            "environment": environment,
            "result": result
        }
    )
    
    return {
        "status": "success",
        "app": app_name,
        "version": version,
        "environment": environment,
        "result": result
    }
```

### Deployment Permissions Matrix

```
Production Deploy:
  - Requires: deploy_to_production + approve_production_deploy
  - Approvers: ONLY senior architects + CTO
  - Audit: Immutable log with timestamp, approver, version

Staging Deploy:
  - Requires: deploy_to_staging
  - Approvers: Tech leads, architects, senior devs
  - Audit: Full audit trail

Dev Deploy:
  - Requires: deploy_to_dev
  - Approvers: ANY developer
  - Audit: Logged but less critical
```

---

## 🔗 INTEGRATION WITH PRISM (QA)

### Flow: PRISM uses SENTINEL for test data access

```python
@prism.post("/run-tests")
async def run_qa_tests(
    test_suite: str,
    environment: str = "staging",
    authorization: str = Header(...)
):
    # STEP 1: Validate QA user token
    user_context = await sentinel.validate_token(authorization)
    
    # STEP 2: Check QA permission
    if "run_qa_tests" not in user_context["permissions"]:
        raise HTTPException(status_code=403)
    
    # STEP 3: Get test database credentials
    test_db_creds = await sentinel.get_secret(
        secret_name=f"test_db_creds_{environment}",
        tenant_id=user_context["tenant_id"]
    )
    
    # STEP 4: Run tests with user context
    results = await run_test_suite(
        test_suite=test_suite,
        environment=environment,
        db_credentials=test_db_creds,
        user_context=user_context
    )
    
    # STEP 5: Audit test execution
    await sentinel.audit_log(
        user_id=user_context["user_id"],
        tenant_id=user_context["tenant_id"],
        action="run_qa_tests",
        resource=test_suite,
        result="success",
        changes={
            "environment": environment,
            "tests_passed": results["passed"],
            "tests_failed": results["failed"]
        }
    )
    
    return {
        "status": "success",
        "test_suite": test_suite,
        "environment": environment,
        "results": results
    }
```

---

## 📊 COMPLETE REQUEST FLOW

### Example: User creates a sales order

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. CLIENT REQUEST (AURORA Frontend)                             │
└─────────────────────────────────────────────────────────────────┘
    POST /api/v1/nexus/crud
    Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
    Content-Type: application/json
    
    {
      "table_name": "sales_orders",
      "operation": "INSERT",
      "data": {
        "customer_id": "cust_123",
        "product_id": "prod_456",
        "quantity": 10,
        "unit_price": 99.99,
        "total": 999.90
      }
    }

        ↓ ↓ ↓

┌─────────────────────────────────────────────────────────────────┐
│ 2. SENTINEL VALIDATION                                          │
│    ✅ JWT signature valid (HS256)                              │
│    ✅ Token not expired (exp: 2026-09-29T16:30:00Z)           │
│    ✅ Extract claims:                                          │
│         - sub: "user_123"                                      │
│         - tenant_id: "imvesa"                                  │
│         - roles: ["sales_manager"]                             │
│         - permissions: [                                       │
│             "create_sales_orders",                             │
│             "view_sales_orders",                               │
│             "edit_sales_orders"                                │
│           ]                                                    │
│    ✅ Create user_context                                     │
│    ✅ Log auth event: "authenticate: success"                │
└─────────────────────────────────────────────────────────────────┘

        ↓ ↓ ↓

┌─────────────────────────────────────────────────────────────────┐
│ 3. NEXUS RECEIVES USER CONTEXT                                  │
│    user_context = {                                             │
│      "user_id": "user_123",                                    │
│      "tenant_id": "imvesa",                                    │
│      "roles": ["sales_manager"],                               │
│      "permissions": ["create_sales_orders", ...]               │
│    }                                                            │
│                                                                 │
│    ✅ Check permission: "create_sales_orders"                 │
│    ✅ Auto-inject tenant_id: "imvesa"                        │
│    ✅ Auto-inject created_by: "user_123"                     │
│    ✅ Build INSERT query:                                    │
│                                                                 │
│    INSERT INTO sales_orders (                                  │
│      customer_id, product_id, quantity, unit_price, total,     │
│      tenant_id, created_by, created_at, status                 │
│    ) VALUES (                                                  │
│      'cust_123', 'prod_456', 10, 99.99, 999.90,               │
│      'imvesa', 'user_123', NOW(), 'pending'                   │
│    )                                                            │
└─────────────────────────────────────────────────────────────────┘

        ↓ ↓ ↓

┌─────────────────────────────────────────────────────────────────┐
│ 4. EXECUTE SQL WITH AUTOMATIC RLS                               │
│    WHERE clause automatically filters by tenant_id             │
│    Column created_by automatically set to user_id             │
│    Status defaults to 'pending' (can be overridden by role)    │
│                                                                 │
│    ✅ Query executed successfully                             │
│    ✅ Result: order_id = "order_789"                         │
└─────────────────────────────────────────────────────────────────┘

        ↓ ↓ ↓

┌─────────────────────────────────────────────────────────────────┐
│ 5. CHECK BUSINESS RULES (MATRIX)                                │
│    Rule 1: If total > $1000, requires manager approval         │
│             ✅ User is sales_manager → Can apply               │
│                                                                 │
│    Rule 2: If customer_id = "special_customer", apply 10% disc  │
│             ✅ Applicable                                      │
│                                                                 │
│    ✅ Rules applied successfully                              │
└─────────────────────────────────────────────────────────────────┘

        ↓ ↓ ↓

┌─────────────────────────────────────────────────────────────────┐
│ 6. AUDIT LOGGING (SENTINEL)                                     │
│    Entry 1: authenticate - success                             │
│    Entry 2: nexus_insert - sales_orders - success              │
│    Entry 3: matrix_apply_rule - rule_total_check - success     │
│    Entry 4: matrix_apply_rule - rule_discount - success        │
│                                                                 │
│    All entries stored in IMMUTABLE audit_log table             │
│    ✅ 4 audit events recorded                                 │
└─────────────────────────────────────────────────────────────────┘

        ↓ ↓ ↓

┌─────────────────────────────────────────────────────────────────┐
│ 7. CLIENT RECEIVES RESPONSE (AURORA)                            │
│    HTTP 200 OK                                                  │
│    {                                                            │
│      "status": "success",                                       │
│      "order": {                                                 │
│        "id": "order_789",                                       │
│        "customer_id": "cust_123",                               │
│        "product_id": "prod_456",                                │
│        "quantity": 10,                                          │
│        "unit_price": 99.99,                                     │
│        "total": 999.90,                                         │
│        "discount": 100.00,  // From MATRIX rule                │
│        "status": "pending",                                     │
│        "created_by": "user_123",                                │
│        "created_at": "2026-09-29T14:30:00Z",                   │
│        "tenant_id": "imvesa"                                    │
│      },                                                         │
│      "audit_id": "audit_123456"                                │
│    }                                                            │
│                                                                 │
│    ✅ Response time: 45ms (cached)                            │
│    ✅ All security checks passed                              │
└─────────────────────────────────────────────────────────────────┘

        ↓ ↓ ↓

┌─────────────────────────────────────────────────────────────────┐
│ 8. COMPLIANCE VERIFICATION                                      │
│    ✅ RLS: Only imvesa tenant data visible                    │
│    ✅ Audit: All operations logged immutably                 │
│    ✅ Permission: User had create_sales_orders               │
│    ✅ GDPR: Audit trail shows who created order              │
│    ✅ SOX: Financial impact is tracked                        │
│    ✅ Data Encryption: Sensitive fields encrypted at rest    │
└─────────────────────────────────────────────────────────────────┘
```

---

## ⚠️ ERROR HANDLING STRATEGY

### 1. Authentication Errors

```python
# Error 401: Unauthorized
{
  "status": "error",
  "code": "UNAUTHORIZED",
  "message": "Invalid or expired token",
  "details": {
    "reason": "token_expired",
    "expires_at": "2026-09-29T14:30:00Z"
  }
}

# Action: Client should refresh token or redirect to login
# Audit: Logged with "unauthorized_access" event
```

### 2. Authorization Errors

```python
# Error 403: Forbidden
{
  "status": "error",
  "code": "FORBIDDEN",
  "message": "Permission denied",
  "details": {
    "reason": "insufficient_permissions",
    "required_permission": "create_sales_orders",
    "user_permissions": ["view_sales_orders", "edit_sales_orders"]
  }
}

# Action: Client should show "Not authorized" message
# Audit: Logged with "permission_denied" event
```

### 3. Rate Limiting (Brute Force Protection)

```python
# Error 429: Too Many Requests
{
  "status": "error",
  "code": "RATE_LIMIT_EXCEEDED",
  "message": "Too many authentication attempts",
  "details": {
    "retry_after": 900,  # 15 minutes in seconds
    "attempts": 5,
    "reset_at": "2026-09-29T14:45:00Z"
  }
}

# Action: Lock account for 15 minutes, then reset
# Audit: Logged with "brute_force_attempt" event
```

### 4. Token Refresh Error

```python
# Error 401: Refresh Token Expired
{
  "status": "error",
  "code": "REFRESH_TOKEN_EXPIRED",
  "message": "Refresh token has expired",
  "details": {
    "reason": "token_expired",
    "issued_at": "2026-09-21T10:00:00Z",
    "expired_at": "2026-09-28T10:00:00Z"
  }
}

# Action: Redirect to login screen
# Audit: Logged with "refresh_token_expired" event
```

### 5. Business Logic Error (from MATRIX)

```python
# Error 422: Rule Validation Failed
{
  "status": "error",
  "code": "RULE_VALIDATION_FAILED",
  "message": "Business rule validation failed",
  "details": {
    "rule_id": "rule_approval_001",
    "reason": "Order requires manager approval (> $10,000)",
    "user_role": "sales_rep",
    "required_role": "manager"
  }
}

# Action: Show message to user about what's needed
# Audit: Logged with "rule_validation_failed" event
```

---

## 🔄 TOKEN LIFECYCLE

```
┌──────────────────────────────────────────┐
│      USER AUTHENTICATION (SENTINEL)      │
└────────────────┬─────────────────────────┘
                 │
                 ▼
         ┌──────────────────┐
         │  Issue JWT Token │
         │  expires_in: 1h  │
         │  + Refresh Token │
         │  expires_in: 7d  │
         └────────┬─────────┘
                  │
                  ▼
    ┌─────────────────────────┐
    │  Client stores tokens   │
    │  Access: Memory         │
    │  Refresh: localStorage  │
    └────────────┬────────────┘
                 │
                 ▼
    ┌──────────────────────────────────────┐
    │  Make API Requests with Access Token │
    │  Header: Authorization: Bearer <token>
    └────────────┬─────────────────────────┘
                 │
            ┌────┴─────┐
            ▼          ▼
    ┌────────────┐  ┌──────────────────┐
    │   Valid    │  │  Expired (< 5m)  │
    │  Continue  │  │  Silently refresh│
    └────────────┘  │  New access token│
                    └──────────────────┘
                        │
                        ▼
                   ┌──────────────┐
                   │ Refresh Token│
                   │  Valid?      │
                   └──┬──────┬────┘
                      │      │
                    YES    NO
                      │      │
                      ▼      ▼
                   Issue   Redirect
                   New     to Login
                   Token
```

---

## 📋 IMPLEMENTATION CHECKLIST

### Phase 1: Core SENTINEL (Weeks 1-2)

- [ ] Create JWT token generation/validation
- [ ] Create authentication endpoint with bcrypt hashing
- [ ] Create token refresh endpoint
- [ ] Create audit logging table
- [ ] Create rate limiting (5 failed attempts → 15 min lockout)
- [ ] Create audit log table (immutable)
- [ ] Integrate SENTINEL with NEXUS (RLS filtering)
- [ ] Integrate SENTINEL with MATRIX (permission checks)
- [ ] Write comprehensive tests
- [ ] Deploy to staging

### Phase 2: Advanced Features (Weeks 3+)

- [ ] Implement 2FA (TOTP, SMS, Email, FIDO2)
- [ ] Implement OAuth2 flows
- [ ] Implement SAML 2.0
- [ ] Implement encryption at rest (AES-256)
- [ ] Implement secrets management (Vault)
- [ ] Create compliance reports (GDPR, HIPAA, SOX)
- [ ] Integrate with all 9 agents

---

**Next Document:** SENTINEL_INTEGRATION_EXAMPLES.md (Practical code examples)
