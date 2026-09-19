"""
FastAPI routes for Database Agent
Exposes database operations via REST API
"""

from fastapi import APIRouter, HTTPException, status, Depends
from typing import Optional, Dict, Any
import logging
from datetime import datetime
import uuid

from database_agent import (
    DatabaseAgent,
    DatabaseAgentInput,
    TableDefinition,
    SchemaMigration,
    AgentStatus
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/database", tags=["database"])

# Initialize agent (singleton)
_database_agent: Optional[DatabaseAgent] = None


def get_database_agent() -> DatabaseAgent:
    """Dependency: Get database agent instance"""
    global _database_agent
    if _database_agent is None:
        _database_agent = DatabaseAgent()
    return _database_agent


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class CreateTableRequest(DatabaseAgentInput):
    """Request to create a new table"""
    action: str = "create_table"
    table_definition: TableDefinition


class MigrateRequest(DatabaseAgentInput):
    """Request to apply migration"""
    action: str = "migrate"
    migration: SchemaMigration


class AuditRequest(DatabaseAgentInput):
    """Request audit log"""
    action: str = "audit"
    table_name: Optional[str] = None


class BackupRequest(DatabaseAgentInput):
    """Request database backup"""
    action: str = "backup"
    table_name: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: datetime
    version: str


# ============================================================================
# ROUTES
# ============================================================================

@router.post(
    "/tables",
    status_code=status.HTTP_201_CREATED,
    summary="Create new table",
    response_description="Table created successfully"
)
async def create_table(
    request: CreateTableRequest,
    agent: DatabaseAgent = Depends(get_database_agent)
):
    """
    Create a new table in the database.
    
    Automatically:
    - Validates multisector requirements (empresa_id, bodega_id)
    - Generates DDL script
    - Adds audit columns
    - Creates indexes
    - Logs change to audit trail
    
    Example:
    ```json
    {
      "request_id": "req_123",
      "table_definition": {
        "name": "clientes",
        "columns": [
          {
            "name": "cliente_id",
            "type": "bigint",
            "primary_key": true
          },
          {
            "name": "empresa_id",
            "type": "int",
            "nullable": false
          },
          {
            "name": "bodega_id",
            "type": "int",
            "nullable": false
          },
          {
            "name": "nombre",
            "type": "varchar",
            "nullable": false
          }
        ],
        "description": "Tabla de clientes"
      }
    }
    ```
    """
    try:
        # Ensure request_id is set
        if not request.request_id:
            request.request_id = str(uuid.uuid4())
        
        logger.info(f"Creating table: {request.table_definition.name}")
        
        # Execute agent
        output = await agent.execute(request)
        
        # Check if successful
        if output.status != AgentStatus.SUCCESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Table creation failed: {output.errors}"
            )
        
        logger.info(f"Table created successfully: {request.table_definition.name}")
        
        return {
            "request_id": output.request_id,
            "status": output.status,
            "data": {
                "table_name": request.table_definition.name,
                "columns": len(request.table_definition.columns),
                "schema_hash": output.schema_hash,
                "ddl_script": output.result.get("ddl_script"),
                "created_at": output.timestamp.isoformat()
            },
            "execution_time_ms": output.execution_time_ms
        }
        
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid table definition: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error creating table: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/migrations",
    status_code=status.HTTP_201_CREATED,
    summary="Apply database migration",
    response_description="Migration applied successfully"
)
async def apply_migration(
    request: MigrateRequest,
    agent: DatabaseAgent = Depends(get_database_agent)
):
    """
    Apply a database migration.
    
    Handles:
    - Schema updates
    - Column additions/modifications
    - New table creation
    - Automatic rollback capability
    - Semantic versioning
    
    Example:
    ```json
    {
      "request_id": "req_124",
      "migration": {
        "version": "1.0.1",
        "name": "add_retencion_dian",
        "tables_modified": ["facturas"],
        "sql_script": "ALTER TABLE facturas ADD COLUMN retencion_dian DECIMAL(10,2);",
        "rollback_script": "ALTER TABLE facturas DROP COLUMN retencion_dian;"
      }
    }
    ```
    """
    try:
        if not request.request_id:
            request.request_id = str(uuid.uuid4())
        
        logger.info(f"Applying migration: {request.migration.version}")
        
        output = await agent.execute(request)
        
        if output.status != AgentStatus.SUCCESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Migration failed: {output.errors}"
            )
        
        logger.info(f"Migration applied: {output.migration_id}")
        
        return {
            "request_id": output.request_id,
            "status": output.status,
            "data": {
                "migration_id": output.migration_id,
                "version": request.migration.version,
                "tables_modified": request.migration.tables_modified,
                "applied_at": output.timestamp.isoformat()
            },
            "execution_time_ms": output.execution_time_ms
        }
        
    except Exception as e:
        logger.error(f"Error applying migration: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/audit",
    summary="Get audit log",
    response_description="Audit log entries"
)
async def get_audit_log(
    table_name: Optional[str] = None,
    limit: int = 100,
    agent: DatabaseAgent = Depends(get_database_agent)
):
    """
    Retrieve database audit log.
    
    Shows all schema changes, who made them, and when.
    
    Query parameters:
    - table_name: Filter by table (optional)
    - limit: Max entries to return (default: 100)
    
    Example:
    ```
    GET /api/v1/database/audit?table_name=clientes&limit=50
    ```
    """
    try:
        request = AuditRequest(
            request_id=str(uuid.uuid4()),
            action="audit",
            table_name=table_name
        )
        
        output = await agent.execute(request)
        
        if output.status != AgentStatus.SUCCESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Audit failed"
            )
        
        # Filter by table if specified
        entries = output.result.get("recent_changes", [])
        
        if table_name:
            entries = [e for e in entries if e.get("table") == table_name]
        
        # Limit results
        entries = entries[-limit:]
        
        return {
            "total_entries": output.result.get("total_changes", 0),
            "returned": len(entries),
            "entries": entries,
            "timestamp": output.timestamp.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error retrieving audit log: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/backups",
    status_code=status.HTTP_201_CREATED,
    summary="Create database backup",
    response_description="Backup created successfully"
)
async def create_backup(
    request: BackupRequest,
    agent: DatabaseAgent = Depends(get_database_agent)
):
    """
    Create a database backup.
    
    - Full database backup
    - Automatic verification
    - Timestamped location
    
    Example:
    ```json
    {
      "request_id": "req_125",
      "action": "backup"
    }
    ```
    """
    try:
        if not request.request_id:
            request.request_id = str(uuid.uuid4())
        
        logger.info("Creating database backup")
        
        output = await agent.execute(request)
        
        if output.status != AgentStatus.SUCCESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Backup failed: {output.errors}"
            )
        
        logger.info(f"Backup created: {output.backup_location}")
        
        return {
            "request_id": output.request_id,
            "status": output.status,
            "data": {
                "backup_id": output.backup_location,
                "verified": output.result.get("verified", False),
                "created_at": output.timestamp.isoformat()
            },
            "execution_time_ms": output.execution_time_ms
        }
        
    except Exception as e:
        logger.error(f"Error creating backup: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/status",
    summary="Get database agent status",
    response_description="Agent status"
)
async def get_agent_status(
    agent: DatabaseAgent = Depends(get_database_agent)
):
    """
    Get current database agent status.
    
    Returns:
    - Agent name and version
    - Current status (idle, processing, success, failed)
    - Timestamp
    """
    return agent.get_status()


@router.get(
    "/health",
    summary="Health check",
    response_description="Service is healthy"
)
async def health_check(
    agent: DatabaseAgent = Depends(get_database_agent)
):
    """
    Health check endpoint for load balancers.
    
    Returns 200 OK if service is healthy.
    """
    agent_status = agent.get_status()
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": agent.config.version,
        "database_agent": agent_status
    }


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@router.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle validation errors"""
    logger.error(f"Validation error: {str(exc)}")
    return {
        "error": "validation_error",
        "detail": str(exc)
    }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

"""
USAGE EXAMPLES:

1. CREATE TABLE:
```bash
curl -X POST http://localhost:8000/api/v1/database/tables \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req_001",
    "table_definition": {
      "name": "clientes",
      "columns": [
        {"name": "cliente_id", "type": "bigint", "primary_key": true},
        {"name": "empresa_id", "type": "int", "nullable": false},
        {"name": "bodega_id", "type": "int", "nullable": false},
        {"name": "nombre", "type": "varchar", "nullable": false}
      ]
    }
  }'
```

2. APPLY MIGRATION:
```bash
curl -X POST http://localhost:8000/api/v1/database/migrations \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req_002",
    "migration": {
      "version": "1.0.1",
      "name": "add_email",
      "tables_modified": ["clientes"],
      "sql_script": "ALTER TABLE clientes ADD COLUMN email VARCHAR(100);"
    }
  }'
```

3. GET AUDIT LOG:
```bash
curl http://localhost:8000/api/v1/database/audit?limit=50
```

4. CREATE BACKUP:
```bash
curl -X POST http://localhost:8000/api/v1/database/backups \
  -H "Content-Type: application/json" \
  -d '{"request_id": "req_003"}'
```

5. HEALTH CHECK:
```bash
curl http://localhost:8000/api/v1/database/health
```
"""


# Include in main FastAPI app:
# from fastapi import FastAPI
# app = FastAPI()
# app.include_router(router)
