# 🔐 SENTINEL v1.0 — SECURITY & AUTHENTICATION AGENT

**KINETIX Studio Integration Agent #10**  
**Status:** Specification Ready  
**Version:** 1.0.0  
**Endpoints:** 28 total (Phase 1: 14)  
**Timeline:** 2-3 weeks implementation

---

## 📋 TABLE OF CONTENTS

1. [Architecture Overview](#architecture-overview)
2. [Authentication Flows](#authentication-flows)
3. [API Endpoints (Phase 1)](#api-endpoints-phase-1)
4. [Database Schema](#database-schema)
5. [Integration with Existing Agents](#integration-with-existing-agents)
6. [Security Considerations](#security-considerations)
7. [Implementation Guide](#implementation-guide)

---

## 🏗️ ARCHITECTURE OVERVIEW

### SENTINEL Core Components

```
┌──────────────────────────────────────────────────────┐
│                   SENTINEL AGENT                     │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌─ AUTHENTICATION (6 endpoints)                    │
│  │  ├─ OAuth2 / SAML / OIDC / JWT                  │
│  │  ├─ Username/Password (bcrypt)                   │
│  │  ├─ 2FA/MFA                                     │
│  │  ├─ Token Management                            │
│  │  ├─ Session Management                          │
│  │  └─ Social Login                                │
│  │                                                  │
│  ├─ AUTHORIZATION (4 endpoints)                    │
│  │  ├─ RBAC (Role-Based Access Control)           │
│  │  ├─ ABAC (Attribute-Based Access Control)      │
│  │  ├─ Permission Management                       │
│  │  └─ Resource Access Control                     │
│  │                                                  │
│  ├─ ENCRYPTION & SECRETS (2 endpoints)            │
│  │  ├─ Encryption at-rest (AES-256)               │
│  │  └─ Secrets Management (HashiCorp Vault)       │
│  │                                                  │
│  └─ AUDIT & COMPLIANCE (2 endpoints)              │
│     ├─ Audit Logging                              │
│     └─ Compliance Tracking (GDPR, HIPAA, SOX)    │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Request Flow with SENTINEL

```
CLIENT REQUEST
    ↓
SENTINEL validates authentication
    ├─ Check token signature
    ├─ Verify expiration
    ├─ Extract claims (user_id, tenant_id, roles)
    └─ Audit log entry
    ↓
CONTEXT enriched
    ├─ user_context = {user_id, tenant_id, roles, permissions}
    └─ request_id for tracing
    ↓
NEXUS/SYNAPSE/MATRIX receive secure context
    ├─ NEXUS: Apply RLS (WHERE tenant_id = context.tenant_id)
    ├─ SYNAPSE: Use token for API calls
    ├─ MATRIX: Check permissions before applying rules
    └─ Automatic request filtering
    ↓
AUDIT LOG recorded
    ├─ user_id, action, resource, timestamp
    ├─ IP address, user-agent
    ├─ success/failure
    └─ Stored in immutable audit table
    ↓
CLIENT RESPONSE (with audit trail)
```

---

## 🔑 AUTHENTICATION FLOWS

### Flow 1: OAuth2 + JWT (Recommended)

```
┌─────────────────────────────────────────────────────┐
│             OAUTH2 + JWT AUTHENTICATION             │
├─────────────────────────────────────────────────────┤
│                                                     │
│  CLIENT                 SENTINEL                   │
│    │                       │                       │
│    ├─ POST /authenticate  │                       │
│    │   ├─ client_id       │                       │
│    │   └─ client_secret   │                       │
│    │                       ├─ Validate client    │
│    │                       ├─ Check credentials  │
│    │  ← 200 OK            │                      │
│    │    ├─ access_token (JWT)                    │
│    │    ├─ expires_in: 3600                      │
│    │    ├─ refresh_token                         │
│    │    └─ token_type: "Bearer"                  │
│    │                                             │
│    ├─ GET /protected                             │
│    │   Headers: {"Authorization": "Bearer <token>"}
│    │                       │                     │
│    │                       ├─ Verify JWT        │
│    │                       ├─ Extract claims    │
│    │  ← Protected resource │                    │
│    │                                            │
└─────────────────────────────────────────────────────┘
```

**JWT Claims Structure:**

```json
{
  "sub": "user_123",                    // Subject (user ID)
  "tenant_id": "imvesa",                // Tenant
  "roles": ["admin", "finance_manager"],// Roles
  "permissions": [                      // Permissions
    "view_sales",
    "edit_prices",
    "approve_orders"
  ],
  "iat": 1695981600,                    // Issued at
  "exp": 1695985200,                    // Expires in 1 hour
  "iss": "kinetix-sentinel",            // Issuer
  "aud": "kinetix-studio"               // Audience
}
```

### Flow 2: SAML 2.0 (Enterprise SSO)

```
CLIENT (SP)                SENTINEL                  IdP (Okta/Azure AD)
   │                          │                           │
   ├─ AuthnRequest ──────────→│                           │
   │                          ├─ Redirect ───────────────→│
   │                          │                           │
   │                          │←─ SAML Assertion ─────────┤
   │←─ SAML Response ─────────┤                           │
   │   ├─ ValidateAssertion                              │
   │   ├─ Extract attributes                             │
   │   └─ Issue JWT token                                │
```

### Flow 3: 2FA/MFA (Multifactor)

```
┌─────────────────────────────────────────────────────┐
│           2FA/MFA AUTHENTICATION FLOW               │
├─────────────────────────────────────────────────────┤
│                                                     │
│  STEP 1: Username/Password                         │
│  POST /authenticate                                │
│  ├─ username: "giovanny@imvesa.com"               │
│  └─ password: "secure_password"                   │
│  Response: "Waiting for 2FA code"                 │
│                                                    │
│  STEP 2: Enter 2FA Code                           │
│  POST /authenticate/verify-2fa                    │
│  ├─ username: "giovanny@imvesa.com"              │
│  ├─ auth_code: "123456"  (from TOTP app)         │
│  └─ or sms_code: "654321" (from SMS)             │
│  Response:                                        │
│  {                                                │
│    "access_token": "eyJhbGci...",                │
│    "expires_in": 3600,                           │
│    "mfa_verified": true                          │
│  }                                               │
│                                                  │
│  METHODS SUPPORTED:                              │
│  ├─ TOTP (Google Authenticator, Authy)          │
│  ├─ SMS (Twilio)                                │
│  ├─ Email                                       │
│  ├─ FIDO2 (Hardware keys - YubiKey)             │
│  └─ Backup codes (print & store)                │
│                                                  │
└─────────────────────────────────────────────────────┘
```

---

## 📡 API ENDPOINTS (Phase 1)

### 1. AUTHENTICATION ENDPOINTS (6)

#### 1.1 POST /api/v1/sentinel/authenticate

**Standard Username/Password Authentication**

```http
POST /api/v1/sentinel/authenticate
Content-Type: application/json

{
  "username": "giovanny@imvesa.com",
  "password": "secure_password",
  "tenant_id": "imvesa"
}
```

**Response (200 OK):**

```json
{
  "status": "success",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "refresh_eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": "user_123",
    "username": "giovanny@imvesa.com",
    "tenant_id": "imvesa",
    "roles": ["admin"],
    "permissions": ["*"]
  },
  "requires_2fa": false
}
```

**Validations:**
- Username must be email format
- Password must be >= 12 characters (in DB)
- tenant_id must exist in database
- Account must not be locked (3 failed attempts)

#### 1.2 POST /api/v1/sentinel/authenticate/verify-2fa

**Verify 2FA Code**

```http
POST /api/v1/sentinel/authenticate/verify-2fa
Content-Type: application/json

{
  "username": "giovanny@imvesa.com",
  "auth_code": "123456",
  "method": "totp"
}
```

**Response (200 OK):**

```json
{
  "status": "success",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "mfa_verified": true,
  "mfa_method": "totp"
}
```

**Methods Supported:**
- `totp` — Time-based OTP (Google Authenticator)
- `sms` — SMS code sent to phone
- `email` — Email code sent to email
- `fido2` — Hardware key (YubiKey)
- `backup` — Backup codes (one-time use)

#### 1.3 POST /api/v1/sentinel/authenticate/oauth2

**OAuth2 Authorization Code Flow**

```http
POST /api/v1/sentinel/authenticate/oauth2
Content-Type: application/json

{
  "grant_type": "authorization_code",
  "code": "authorization_code_from_provider",
  "client_id": "kinetix_studio",
  "client_secret": "client_secret_here",
  "redirect_uri": "https://kinetix.imvesa.com/callback",
  "provider": "google"
}
```

**Response (200 OK):**

```json
{
  "status": "success",
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "user": {
    "id": "user_google_123",
    "email": "giovanny@gmail.com",
    "tenant_id": "imvesa",
    "roles": ["developer"],
    "oauth_provider": "google"
  }
}
```

**Supported Providers:**
- Google
- GitHub
- Microsoft
- Apple
- LinkedIn
- Custom OIDC

#### 1.4 POST /api/v1/sentinel/authenticate/saml

**SAML 2.0 Authentication**

```http
POST /api/v1/sentinel/authenticate/saml
Content-Type: application/x-www-form-urlencoded

SAMLResponse=PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4...&RelayState=ac420de71e84
```

**Response (200 OK):**

```json
{
  "status": "success",
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "user": {
    "id": "user_saml_123",
    "email": "giovanny@imvesa.com",
    "tenant_id": "imvesa",
    "roles": ["admin"],
    "saml_name_id": "user@imvesa.com"
  }
}
```

#### 1.5 POST /api/v1/sentinel/refresh-token

**Refresh Access Token**

```http
POST /api/v1/sentinel/refresh-token
Content-Type: application/json

{
  "refresh_token": "refresh_eyJhbGciOiJIUzI1NiIs...",
  "grant_type": "refresh_token"
}
```

**Response (200 OK):**

```json
{
  "status": "success",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

#### 1.6 POST /api/v1/sentinel/logout

**Invalidate Token**

```http
POST /api/v1/sentinel/logout
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "revoke_all_sessions": false
}
```

**Response (200 OK):**

```json
{
  "status": "success",
  "message": "Successfully logged out",
  "sessions_revoked": 1
}
```

**Parameters:**
- `revoke_all_sessions: true` — Logout from all devices
- `revoke_all_sessions: false` — Logout current session only

---

### 2. AUTHORIZATION ENDPOINTS (4)

#### 2.1 POST /api/v1/sentinel/authorize

**Check if User Has Permission**

```http
POST /api/v1/sentinel/authorize
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "resource": "sales_orders",
  "action": "edit",
  "resource_id": "order_123"
}
```

**Response (200 OK):**

```json
{
  "status": "success",
  "authorized": true,
  "permission": "edit_sales_orders",
  "reason": "User has admin role",
  "attributes": {
    "tenant_id_match": true,
    "resource_owner": false,
    "role_allows": true
  }
}
```

**Response (403 Forbidden):**

```json
{
  "status": "error",
  "authorized": false,
  "reason": "User does not have permission to edit sales_orders",
  "required_permission": "edit_sales_orders",
  "user_permissions": ["view_sales_orders", "create_sales_orders"]
}
```

#### 2.2 GET /api/v1/sentinel/permissions

**Get User's Permissions**

```http
GET /api/v1/sentinel/permissions
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

**Response (200 OK):**

```json
{
  "status": "success",
  "user_id": "user_123",
  "tenant_id": "imvesa",
  "roles": ["admin", "finance_manager"],
  "permissions": [
    {
      "resource": "sales_orders",
      "actions": ["view", "create", "edit", "delete", "approve"]
    },
    {
      "resource": "products",
      "actions": ["view", "create", "edit"]
    },
    {
      "resource": "reports",
      "actions": ["view", "export"]
    },
    {
      "resource": "settings",
      "actions": ["view", "edit"]
    }
  ],
  "total_permissions": 18
}
```

#### 2.3 POST /api/v1/sentinel/roles/assign

**Assign Role to User**

```http
POST /api/v1/sentinel/roles/assign
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "user_id": "user_456",
  "role_name": "finance_manager",
  "tenant_id": "imvesa",
  "duration_days": null
}
```

**Response (200 OK):**

```json
{
  "status": "success",
  "user_id": "user_456",
  "role": "finance_manager",
  "tenant_id": "imvesa",
  "assigned_by": "user_123",
  "assigned_at": "2026-09-29T14:30:00Z",
  "expires_at": null
}
```

#### 2.4 POST /api/v1/sentinel/permissions/grant

**Grant Specific Permission**

```http
POST /api/v1/sentinel/permissions/grant
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "user_id": "user_456",
  "resource": "reports",
  "action": "export",
  "tenant_id": "imvesa"
}
```

**Response (200 OK):**

```json
{
  "status": "success",
  "permission_granted": "export_reports",
  "user_id": "user_456",
  "tenant_id": "imvesa",
  "granted_by": "user_123",
  "granted_at": "2026-09-29T14:30:00Z"
}
```

---

### 3. ENCRYPTION & SECRETS ENDPOINTS (2)

#### 3.1 POST /api/v1/sentinel/encrypt

**Encrypt Sensitive Data**

```http
POST /api/v1/sentinel/encrypt
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "data": "customer_credit_card_4111_1111_1111_1111",
  "encryption_key": "default",
  "field_type": "pii"
}
```

**Response (200 OK):**

```json
{
  "status": "success",
  "encrypted_data": "U2FsdGVkX1+...",
  "encryption_algorithm": "AES-256-GCM",
  "key_version": 1,
  "field_type": "pii"
}
```

#### 3.2 POST /api/v1/sentinel/secrets/store

**Store API Key/Secret Securely**

```http
POST /api/v1/sentinel/secrets/store
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "secret_name": "stripe_api_key",
  "secret_value": "sk_live_51234567890abcdef",
  "environment": "production",
  "tenant_id": "imvesa"
}
```

**Response (200 OK):**

```json
{
  "status": "success",
  "secret_id": "secret_123",
  "secret_name": "stripe_api_key",
  "environment": "production",
  "stored_at": "2026-09-29T14:30:00Z",
  "rotation_needed": false
}
```

---

### 4. AUDIT & COMPLIANCE ENDPOINTS (2)

#### 4.1 GET /api/v1/sentinel/audit-log

**Query Audit Log**

```http
GET /api/v1/sentinel/audit-log?
  user_id=user_123&
  action=edit_sales_order&
  start_date=2026-09-01&
  end_date=2026-09-29&
  limit=100
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

**Response (200 OK):**

```json
{
  "status": "success",
  "total_records": 1250,
  "page": 1,
  "records": [
    {
      "audit_id": "audit_123456",
      "timestamp": "2026-09-29T14:30:00Z",
      "user_id": "user_123",
      "tenant_id": "imvesa",
      "action": "edit_sales_order",
      "resource": "sales_orders",
      "resource_id": "order_456",
      "result": "success",
      "ip_address": "192.168.1.100",
      "user_agent": "Mozilla/5.0...",
      "changes": {
        "old_value": {"status": "pending"},
        "new_value": {"status": "approved"}
      }
    }
  ]
}
```

#### 4.2 GET /api/v1/sentinel/compliance-report

**Generate Compliance Report**

```http
GET /api/v1/sentinel/compliance-report?
  standard=gdpr&
  tenant_id=imvesa&
  start_date=2026-09-01&
  end_date=2026-09-29
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

**Response (200 OK):**

```json
{
  "status": "success",
  "report_id": "compliance_report_123",
  "standard": "gdpr",
  "tenant_id": "imvesa",
  "period": {
    "start": "2026-09-01",
    "end": "2026-09-29"
  },
  "compliance_checks": {
    "data_retention": {
      "status": "compliant",
      "records_deleted": 5000,
      "retention_policy": "1 year",
      "audit_trail": "immutable"
    },
    "user_rights": {
      "status": "compliant",
      "data_access_requests": 12,
      "requests_fulfilled": 12,
      "avg_fulfillment_time_days": 5
    },
    "encryption": {
      "status": "compliant",
      "encrypted_fields": 450000,
      "encryption_algorithm": "AES-256",
      "key_rotation_schedule": "quarterly"
    },
    "audit_logging": {
      "status": "compliant",
      "total_events_logged": 1250000,
      "log_retention_years": 7,
      "immutable_storage": true
    }
  },
  "overall_compliance": "100%",
  "issues": [],
  "recommendations": []
}
```

---

## 💾 DATABASE SCHEMA

### Users Table

```sql
CREATE TABLE usuarios (
    id NVARCHAR(50) PRIMARY KEY,
    tenant_id NVARCHAR(50) NOT NULL,
    username NVARCHAR(255) UNIQUE NOT NULL,
    email NVARCHAR(255) UNIQUE NOT NULL,
    password_hash NVARCHAR(MAX) NOT NULL,  -- bcrypt hash
    password_salt NVARCHAR(MAX),
    first_name NVARCHAR(100),
    last_name NVARCHAR(100),
    status NVARCHAR(20) DEFAULT 'active',  -- active, inactive, locked
    created_at DATETIME DEFAULT GETDATE(),
    updated_at DATETIME,
    last_login DATETIME,
    login_attempts INT DEFAULT 0,
    locked_until DATETIME NULL,
    mfa_enabled BIT DEFAULT 0,
    mfa_method NVARCHAR(50),  -- totp, sms, email, fido2
    mfa_secret NVARCHAR(MAX),  -- Encrypted
    phone_number NVARCHAR(20),
    phone_verified BIT DEFAULT 0,
    email_verified BIT DEFAULT 0,
    password_expires_at DATETIME,
    requires_password_change BIT DEFAULT 0,
    CONSTRAINT fk_usuarios_tenant FOREIGN KEY (tenant_id) REFERENCES empresas(id)
);

CREATE INDEX idx_usuarios_tenant ON usuarios(tenant_id);
CREATE INDEX idx_usuarios_email ON usuarios(email);
```

### Roles Table

```sql
CREATE TABLE roles (
    id NVARCHAR(50) PRIMARY KEY,
    tenant_id NVARCHAR(50) NOT NULL,
    role_name NVARCHAR(100) NOT NULL,
    description NVARCHAR(MAX),
    is_system_role BIT DEFAULT 0,  -- Cannot be deleted
    created_at DATETIME DEFAULT GETDATE(),
    updated_at DATETIME,
    CONSTRAINT fk_roles_tenant FOREIGN KEY (tenant_id) REFERENCES empresas(id),
    CONSTRAINT uq_role_name UNIQUE (tenant_id, role_name)
);

-- Pre-defined roles
INSERT INTO roles VALUES ('sys_admin', 'system', 'System Admin', 'Full system access', 1, GETDATE(), NULL);
INSERT INTO roles VALUES ('tenant_admin', 'system', 'Tenant Admin', 'Tenant-level admin', 1, GETDATE(), NULL);
INSERT INTO roles VALUES ('user', 'system', 'User', 'Basic user', 1, GETDATE(), NULL);
```

### User_Roles Table (Junction)

```sql
CREATE TABLE usuario_roles (
    id INT PRIMARY KEY IDENTITY,
    usuario_id NVARCHAR(50) NOT NULL,
    role_id NVARCHAR(50) NOT NULL,
    tenant_id NVARCHAR(50) NOT NULL,
    assigned_at DATETIME DEFAULT GETDATE(),
    assigned_by NVARCHAR(50),
    expires_at DATETIME NULL,
    CONSTRAINT fk_usuario_roles_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    CONSTRAINT fk_usuario_roles_role FOREIGN KEY (role_id) REFERENCES roles(id),
    CONSTRAINT fk_usuario_roles_tenant FOREIGN KEY (tenant_id) REFERENCES empresas(id)
);
```

### Permissions Table

```sql
CREATE TABLE permissions (
    id NVARCHAR(50) PRIMARY KEY,
    resource NVARCHAR(100) NOT NULL,
    action NVARCHAR(100) NOT NULL,
    description NVARCHAR(MAX),
    CONSTRAINT uq_permission UNIQUE (resource, action)
);

-- Pre-defined permissions
INSERT INTO permissions VALUES ('perm_sales_view', 'sales_orders', 'view', 'View sales orders');
INSERT INTO permissions VALUES ('perm_sales_create', 'sales_orders', 'create', 'Create sales orders');
INSERT INTO permissions VALUES ('perm_sales_edit', 'sales_orders', 'edit', 'Edit sales orders');
INSERT INTO permissions VALUES ('perm_sales_approve', 'sales_orders', 'approve', 'Approve sales orders');
```

### Role_Permissions Table (Junction)

```sql
CREATE TABLE role_permissions (
    id INT PRIMARY KEY IDENTITY,
    role_id NVARCHAR(50) NOT NULL,
    permission_id NVARCHAR(50) NOT NULL,
    CONSTRAINT fk_role_perm_role FOREIGN KEY (role_id) REFERENCES roles(id),
    CONSTRAINT fk_role_perm_perm FOREIGN KEY (permission_id) REFERENCES permissions(id)
);
```

### Tokens Table (For revocation & tracking)

```sql
CREATE TABLE tokens (
    id NVARCHAR(50) PRIMARY KEY,
    usuario_id NVARCHAR(50) NOT NULL,
    tenant_id NVARCHAR(50) NOT NULL,
    token_hash NVARCHAR(MAX) NOT NULL,
    token_type NVARCHAR(50),  -- access, refresh, reset_password
    issued_at DATETIME DEFAULT GETDATE(),
    expires_at DATETIME NOT NULL,
    revoked_at DATETIME NULL,
    last_used_at DATETIME,
    ip_address NVARCHAR(50),
    user_agent NVARCHAR(MAX),
    CONSTRAINT fk_tokens_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    CONSTRAINT fk_tokens_tenant FOREIGN KEY (tenant_id) REFERENCES empresas(id)
);

CREATE INDEX idx_tokens_usuario ON tokens(usuario_id);
CREATE INDEX idx_tokens_expires ON tokens(expires_at);
```

### Audit Log Table (Immutable)

```sql
CREATE TABLE audit_log (
    id BIGINT PRIMARY KEY IDENTITY,
    audit_timestamp DATETIME DEFAULT GETDATE() NOT NULL,
    usuario_id NVARCHAR(50),
    tenant_id NVARCHAR(50) NOT NULL,
    action NVARCHAR(255) NOT NULL,
    resource NVARCHAR(255),
    resource_id NVARCHAR(255),
    old_value NVARCHAR(MAX),
    new_value NVARCHAR(MAX),
    result NVARCHAR(50),  -- success, failure, denied
    error_message NVARCHAR(MAX),
    ip_address NVARCHAR(50),
    user_agent NVARCHAR(MAX),
    request_id NVARCHAR(100),
    changes_json NVARCHAR(MAX),
    
    -- IMMUTABLE: These indexes enforce fast querying but no modification
    CONSTRAINT fk_audit_tenant FOREIGN KEY (tenant_id) REFERENCES empresas(id)
);

-- Indexes for compliance queries
CREATE NONCLUSTERED INDEX idx_audit_usuario ON audit_log(usuario_id, audit_timestamp DESC);
CREATE NONCLUSTERED INDEX idx_audit_tenant ON audit_log(tenant_id, audit_timestamp DESC);
CREATE NONCLUSTERED INDEX idx_audit_action ON audit_log(action, audit_timestamp DESC);
CREATE NONCLUSTERED INDEX idx_audit_timestamp ON audit_log(audit_timestamp DESC);

-- NO UPDATE/DELETE allowed on audit_log (application-level enforcement)
```

### MFA Devices Table

```sql
CREATE TABLE mfa_devices (
    id NVARCHAR(50) PRIMARY KEY,
    usuario_id NVARCHAR(50) NOT NULL,
    device_type NVARCHAR(50),  -- totp, sms, email, fido2
    device_name NVARCHAR(100),
    device_secret NVARCHAR(MAX),  -- Encrypted
    public_key NVARCHAR(MAX),  -- For FIDO2
    verified BIT DEFAULT 0,
    verified_at DATETIME,
    created_at DATETIME DEFAULT GETDATE(),
    last_used_at DATETIME,
    backup_codes_generated BIT DEFAULT 0,
    CONSTRAINT fk_mfa_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);
```

---

## 🔗 INTEGRATION WITH EXISTING AGENTS

### SENTINEL ↔ NEXUS Integration

```python
# NEXUS receives secure context from SENTINEL
# Every NEXUS request automatically filters by tenant_id

@nexus.post("/crud")
async def crud(
    table_name: str,
    operation: str,
    data: Optional[str] = None,
    authorization: str = Header(...)  # Bearer token
):
    # 1. SENTINEL validates token
    user_context = await sentinel.validate_token(authorization)
    # Returns: {user_id, tenant_id, permissions}
    
    # 2. Check permission
    if not user_context.has_permission(f"{operation}_{table_name}"):
        return {"status": "error", "reason": "Permission denied"}
    
    # 3. Build query with automatic RLS
    query = f"""
        SELECT * FROM {table_name}
        WHERE tenant_id = '{user_context.tenant_id}'
    """
    if operation == "UPDATE":
        query += f" AND user_has_permission('{user_context.user_id}', '{table_name}')"
    
    # 4. Execute with automatic audit
    result = await nexus.execute(query)
    
    # 5. Audit log entry (automatic)
    await sentinel.audit_log({
        "user_id": user_context.user_id,
        "action": operation,
        "resource": table_name,
        "result": "success" if result else "failure"
    })
    
    return result
```

### SENTINEL ↔ SYNAPSE Integration

```python
# SYNAPSE uses SENTINEL token for API calls

@synapse.post("/call-api")
async def call_api(
    api_name: str,
    endpoint: str,
    authorization: str = Header(...)  # Bearer token from user
):
    # 1. Get user context from SENTINEL
    user_context = await sentinel.validate_token(authorization)
    
    # 2. Get API credentials from SENTINEL secrets
    api_credentials = await sentinel.get_secret(f"api_{api_name}_credentials")
    
    # 3. Make HTTP call with credentials + user token
    headers = {
        "Authorization": f"Bearer {api_credentials.token}",
        "X-User-ID": user_context.user_id,
        "X-Tenant-ID": user_context.tenant_id
    }
    
    response = await httpx.get(
        f"https://{api_name}.com{endpoint}",
        headers=headers
    )
    
    # 4. Audit the API call
    await sentinel.audit_log({
        "user_id": user_context.user_id,
        "action": "call_external_api",
        "resource": api_name,
        "endpoint": endpoint,
        "status_code": response.status_code
    })
    
    return response.json()
```

### SENTINEL ↔ MATRIX Integration

```python
# MATRIX checks permissions before applying rules

@matrix.post("/apply-rule")
async def apply_rule(
    rule_id: str,
    data: str,
    authorization: str = Header(...)
):
    # 1. Get user context
    user_context = await sentinel.validate_token(authorization)
    
    # 2. Load rule
    rule = await matrix.get_rule(rule_id)
    
    # 3. Check if user can apply this rule
    if not user_context.has_permission(f"apply_rule_{rule.category}"):
        return {"status": "error", "reason": "Permission denied"}
    
    # 4. Apply rule
    result = await matrix.apply_rule(rule, data)
    
    # 5. Audit the rule application
    await sentinel.audit_log({
        "user_id": user_context.user_id,
        "action": "apply_business_rule",
        "resource": f"rule_{rule_id}",
        "data": data,
        "result": result
    })
    
    return result
```

---

## 🔒 SECURITY CONSIDERATIONS

### Password Hashing

```python
# Use bcrypt with cost factor 12
import bcrypt

password = "user_password"
salt = bcrypt.gensalt(rounds=12)
password_hash = bcrypt.hashpw(password.encode(), salt)

# Verify on login
if bcrypt.checkpw(password.encode(), stored_hash):
    # Password correct
```

### JWT Secrets Management

```python
# Store JWT secret in environment variable (never in code)
JWT_SECRET = os.getenv("JWT_SECRET")  # Load from Vault/Env

# Rotate secrets every 90 days
# Keep old secrets for 30 days to allow token validation during rotation
```

### SQL Injection Prevention

```python
# ALWAYS use parameterized queries

# ❌ WRONG
query = f"SELECT * FROM users WHERE id = {user_id}"

# ✅ CORRECT
query = "SELECT * FROM users WHERE id = @user_id"
params = {"@user_id": user_id}
await db.execute(query, params)
```

### Rate Limiting on Authentication

```python
# Prevent brute force attacks

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = 900  # 15 minutes

@sentinel.post("/authenticate")
async def authenticate(username: str, password: str):
    user = await get_user(username)
    
    # Check if locked
    if user.locked_until and user.locked_until > now():
        return {"status": "error", "message": "Account locked"}
    
    # Verify password
    if not verify_password(password, user.password_hash):
        user.login_attempts += 1
        if user.login_attempts >= MAX_LOGIN_ATTEMPTS:
            user.locked_until = now() + timedelta(seconds=LOCKOUT_DURATION)
        await save_user(user)
        return {"status": "error", "message": "Invalid credentials"}
    
    # Successful login
    user.login_attempts = 0
    user.locked_until = None
    user.last_login = now()
    await save_user(user)
    
    return {"status": "success", "access_token": token}
```

### Encryption at Rest

```python
# Sensitive fields encrypted in database

from cryptography.fernet import Fernet

cipher = Fernet(os.getenv("ENCRYPTION_KEY"))

# Encrypt before storing
encrypted_ssn = cipher.encrypt(b"123-45-6789")
await db.execute("UPDATE users SET ssn = @ssn", {"@ssn": encrypted_ssn})

# Decrypt when reading
user = await db.fetch("SELECT ssn FROM users WHERE id = @id")
decrypted_ssn = cipher.decrypt(user['ssn']).decode()
```

### CORS & CSRF Protection

```python
# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://kinetix.imvesa.com"],  # Specific, not "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"]
)

# CSRF token validation
@app.post("/api/v1/sentinel/logout")
async def logout(request: Request):
    csrf_token = request.headers.get("X-CSRF-Token")
    if not validate_csrf_token(csrf_token):
        return {"status": "error", "message": "CSRF token invalid"}
```

---

## 🚀 IMPLEMENTATION GUIDE

### Phase 1: Core Authentication (Week 1)

**Tasks:**
1. Create database schema (users, roles, tokens, audit_log)
2. Implement password hashing (bcrypt)
3. Implement JWT token generation/validation
4. Create `/authenticate` endpoint
5. Create `/refresh-token` endpoint
6. Create `/logout` endpoint
7. Add rate limiting to authentication
8. Add audit logging for all auth events

**Testing:**
```bash
# Test basic auth
curl -X POST http://localhost:8000/api/v1/sentinel/authenticate \
  -H "Content-Type: application/json" \
  -d '{"username": "test@imvesa.com", "password": "secure_password"}'

# Should return: access_token, expires_in, token_type
```

### Phase 2: Authorization & RBAC (Week 2)

**Tasks:**
1. Create roles table with pre-defined roles
2. Create permissions table with pre-defined permissions
3. Create role_permissions junction table
4. Implement `/authorize` endpoint
5. Implement `/permissions` endpoint
6. Implement `/roles/assign` endpoint
7. Implement `/permissions/grant` endpoint
8. Add authorization checks to existing agents (NEXUS, MATRIX, etc)

**Integration Points:**
- NEXUS: Add WHERE tenant_id filter + permission check
- MATRIX: Add permission check before applying rules
- SYNAPSE: Add permission check before calling APIs

### Phase 3: 2FA & Advanced Auth (Week 3)

**Tasks:**
1. Implement TOTP (Time-based OTP)
2. Implement SMS 2FA (Twilio integration)
3. Implement Email 2FA
4. Implement FIDO2 (hardware keys)
5. Create `/authenticate/verify-2fa` endpoint
6. Add 2FA enrollment flow
7. Add backup codes generation
8. Add 2FA device management

### Phase 4: Encryption & Secrets (Post Phase 1)

**Tasks:**
1. Implement field-level encryption (AES-256)
2. Integrate HashiCorp Vault for secrets
3. Create `/encrypt` endpoint
4. Create `/secrets/store` endpoint
5. Add key rotation automation

### Phase 5: Compliance & Audit (Post Phase 1)

**Tasks:**
1. Implement immutable audit logging
2. Create `/audit-log` endpoint
3. Create `/compliance-report` endpoint
4. Add GDPR data retention policy
5. Add SOX compliance tracking

---

## 📊 PHASE 1 SUMMARY

**Timeline:** 2 weeks  
**Endpoints:** 6 (Authentication only)

```
SENTINEL v1.0 (Phase 1):
├─ POST /authenticate              ✅
├─ POST /authenticate/verify-2fa   ✅
├─ POST /authenticate/oauth2       ✅
├─ POST /authenticate/saml         ✅
├─ POST /refresh-token             ✅
└─ POST /logout                    ✅

Integration:
├─ NEXUS: RLS filtering by tenant_id
├─ MATRIX: Permission checks
├─ SYNAPSE: Token-based API calls
└─ ORBIT: Deployment credentials
```

**Result:** Apps can authenticate users securely  
**Dependencies:** Blocking for PROMETHEUS (needs to monitor auth events)

---

**Next Document:** SENTINEL v1.0 Implementation Code (Python + FastAPI)
