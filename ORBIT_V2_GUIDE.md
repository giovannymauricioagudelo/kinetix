# ORBIT v2.0 — GitDeploymentAgent (Agent 6)
**Status:** ✅ LIVE | **Endpoints:** 8 | **Base URL:** `/api/v1/orbit`

## Overview
GitDeploymentAgent manages CI/CD pipelines, git repository connections, automated deployments and rollback operations.

---

## Endpoints

### 1️⃣ GET `/info`
**Metadata and capabilities**
```json
{
  "id": "orbit",
  "name": "GitDeploymentAgent v2.0",
  "endpoints": 8,
  "status": "active",
  "vcs_providers": ["github", "gitlab", "bitbucket"]
}
```

### 2️⃣ POST `/connect-repository`
**Register a git repository for deployment**
- `repo_url` (string): HTTPS repository URL (required)
- `vcs_provider` (string): `github`, `gitlab`, `bitbucket`
- `credentials` (optional, string): API token or credentials ID

**Response:**
```json
{
  "status": "success",
  "connection_id": "conn_github_123",
  "repo_name": "kinetix-studio",
  "connected_at": "2026-09-28T11:30:00Z"
}
```

**Example:**
```powershell
$uri = "http://127.0.0.1:8000/api/v1/orbit/connect-repository?" +
       "repo_url=https://github.com/kinetix/studio&vcs_provider=github&credentials=ghp_XXXXX"
Invoke-WebRequest -Uri $uri -Method POST
```

### 3️⃣ GET `/repositories`
**List all connected repositories**
- `vcs_provider` (optional, string): Filter by provider
- `status` (string): `active`, `archived`, `all` (default=`active`)

**Response:**
```json
{
  "status": "success",
  "total": 3,
  "repos": [
    {
      "repo_id": "repo_001",
      "name": "kinetix-studio",
      "vcs": "github",
      "url": "https://github.com/kinetix/studio",
      "connected": true,
      "branches": 8,
      "last_commit": "2026-09-28T10:45:00Z"
    }
  ]
}
```

### 4️⃣ POST `/trigger-deployment`
**Trigger automated deployment to environment**
- `repository_id` (string): Target repository
- `branch` (string): Git branch (default=`main`)
- `environment` (string): `dev`, `staging`, `prod`

**Response:**
```json
{
  "status": "success",
  "deployment_id": "deploy_repo_001_123",
  "status": "in_progress",
  "branch": "main",
  "environment": "staging",
  "triggered_at": "2026-09-28T11:35:00Z",
  "eta_minutes": 5
}
```

### 5️⃣ GET `/deployment-history`
**List deployment history with status**
- `repository_id` (optional, string): Filter by repo
- `limit` (integer, default=20): Max results

**Response:**
```json
{
  "status": "success",
  "total": 15,
  "deployments": [
    {
      "deployment_id": "deploy_001",
      "repository_id": "repo_001",
      "branch": "main",
      "environment": "prod",
      "status": "success",
      "duration_seconds": 234,
      "deployed_by": "ci-bot",
      "timestamp": "2026-09-28T10:30:00Z",
      "commit_hash": "abc1234"
    }
  ]
}
```

### 6️⃣ POST `/rollback-deployment`
**Rollback to previous deployment**
- `deployment_id` (string): Current deployment ID
- `target_version` (string): Previous version/commit hash

**Response:**
```json
{
  "status": "success",
  "rollback_id": "rb_deploy_001",
  "status": "in_progress",
  "target": "abc1234",
  "from_version": "def5678",
  "eta_minutes": 3,
  "triggered_at": "2026-09-28T11:40:00Z"
}
```

### 7️⃣ GET `/ci-cd-status`
**Get current CI/CD pipeline status**
- `repository_id` (optional, string): Filter by repo

**Response:**
```json
{
  "status": "success",
  "pipelines": 3,
  "running": 1,
  "queued": 0,
  "failed": 0,
  "success": 47,
  "last_run": "2026-09-28T11:15:00Z",
  "workflows": [
    {
      "workflow_id": "workflow_001",
      "name": "Build & Test",
      "status": "running",
      "duration_minutes": 2,
      "branch": "main"
    }
  ]
}
```

### 8️⃣ GET `/deployment-logs`
**Retrieve deployment execution logs**
- `deployment_id` (string): Target deployment
- `limit` (integer, default=100): Max log lines

**Response:**
```json
{
  "status": "success",
  "deployment_id": "deploy_001",
  "log_entries": 45,
  "logs": [
    {
      "line": 1,
      "timestamp": "2026-09-28T10:30:01Z",
      "level": "INFO",
      "message": "Deployment started",
      "source": "system"
    },
    {
      "line": 2,
      "timestamp": "2026-09-28T10:30:15Z",
      "level": "INFO",
      "message": "Building Docker image...",
      "source": "docker"
    }
  ]
}
```

---

## VCS Provider Support

| Provider | Support | Auth | Features |
|----------|---------|------|----------|
| **GitHub** | ✅ Full | PAT/OAuth | Actions, Webhooks, Status Checks |
| **GitLab** | ✅ Full | PAT/OAuth | CI/CD Pipelines, Webhooks |
| **Bitbucket** | ✅ Full | App Password | Pipelines, PR Checks |

---

## Environment Deployment Workflow
```
dev → staging → prod
├─ Auto-deploy on commit
├─ Manual approval for prod
└─ Automatic rollback on failure
```

---

## Security Rules
✅ HTTPS URL validation (no HTTP)  
✅ VCS provider whitelist: github, gitlab, bitbucket  
✅ Environment whitelist: dev, staging, prod  
✅ Deployment ID format validation (starts with `deploy_`)  
✅ Credentials secured (never returned in logs)  

---

## Error Handling
- Invalid `vcs_provider` → `{"status": "error"}`
- HTTP URL provided → `{"status": "error"}`
- Invalid `environment` → `{"status": "error"}`
- Invalid `deployment_id` → `{"status": "error"}`
- Repository not found → `{"status": "error"}`
