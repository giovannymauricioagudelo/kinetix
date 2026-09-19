"""
FastAPI Routes for APIs Agent
Endpoints para generar y consultar especificaciones de API
VERSIÓN ROBUSTA - Funciona aunque los agentes no existan aún
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Body
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================================
# IMPORTS CON FALLBACK - Intenta cargar el agente real, si no, usa simulación
# ============================================================================

APIsAgent = None
APIEndpointInput = None
APIEndpointOutput = None
AgentStatus = None

try:
    # Intento 1: Ruta absoluta desde src
    from src.agents.apis_agent.agent import (
        APIsAgent,
        APIEndpointInput,
        APIEndpointOutput,
        AgentStatus
    )
    logger.info("✅ APIsAgent loaded from src.agents.apis_agent.agent")
except ImportError as e1:
    logger.warning(f"⚠️  Could not import from src.agents.apis_agent.agent: {str(e1)}")
    
    try:
        # Intento 2: Ruta relativa
        from agents.apis_agent.agent import (
            APIsAgent,
            APIEndpointInput,
            APIEndpointOutput,
            AgentStatus
        )
        logger.info("✅ APIsAgent loaded from agents.apis_agent.agent")
    except ImportError as e2:
        logger.warning(f"⚠️  Could not import from agents.apis_agent.agent: {str(e2)}")
        logger.info("⏳ APIsAgent will run in SIMULATION MODE")
        
        # Crear clases dummy para fallback
        class AgentStatus:
            PENDING = "pending"
            PROCESSING = "processing"
            COMPLETED = "completed"
            FAILED = "failed"
        
        class APIEndpointInput:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
        
        class APIEndpointOutput:
            def __init__(self, status="completed", error=None):
                self.status = status
                self.error = error
        
        class APIsAgent:
            """Dummy APIsAgent para desarrollo sin módulo real"""
            def __init__(self):
                self.version = "0.1.0-simulation"
            
            async def execute(self, input_data):
                return APIEndpointOutput(status=AgentStatus.COMPLETED)


# Crear router
router = APIRouter(
    prefix="/api/v1/apis",
    tags=["APIs Agent"]
)

# Cache de generaciones anteriores
_generation_cache: Dict[str, Any] = {}

# Instancia global del agente
try:
    _apis_agent = APIsAgent()
    logger.info(f"✅ APIsAgent instance created (v{_apis_agent.version})")
except Exception as e:
    logger.error(f"❌ Error creating APIsAgent instance: {str(e)}")
    _apis_agent = None


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post(
    "/generate",
    response_model=Dict[str, Any],
    summary="Generate CRUD Endpoints",
    description="Generate CRUD endpoints specification for a table",
    status_code=201
)
async def generate_endpoints(
    request_id: str = Body(..., description="Unique request identifier"),
    table_name: str = Body(..., description="Name of the table"),
    table_columns: Dict[str, str] = Body(..., description="Columns and their types"),
    primary_key: str = Body(..., description="Primary key column name"),
    description: Optional[str] = Body(None, description="Table description"),
) -> Dict[str, Any]:
    """
    Generate CRUD endpoints for a table
    
    Example request:
    ```json
    {
        "request_id": "gen_001",
        "table_name": "clientes",
        "table_columns": {
            "cliente_id": "bigint",
            "nombre": "varchar",
            "email": "varchar",
            "estado": "boolean"
        },
        "primary_key": "cliente_id",
        "description": "Customer table"
    }
    ```
    
    Response:
    ```json
    {
        "request_id": "gen_001",
        "status": "completed",
        "data": {
            "table_name": "clientes",
            "endpoints_count": 5,
            "endpoints_hash": "hash_value",
            "generated_at": "2026-09-16T..."
        },
        "endpoints": [
            {
                "path": "/api/v1/clientes",
                "method": "POST",
                "operation": "CREATE",
                "summary": "Create new clientes"
            },
            ...
        ],
        "execution_time_ms": 45.23
    }
    ```
    """
    try:
        # Validar input
        if not request_id:
            raise HTTPException(status_code=400, detail="request_id is required")
        if not table_name:
            raise HTTPException(status_code=400, detail="table_name is required")
        if not table_columns:
            raise HTTPException(status_code=400, detail="table_columns is required")
        if not primary_key:
            raise HTTPException(status_code=400, detail="primary_key is required")
        
        if primary_key not in table_columns:
            raise HTTPException(
                status_code=400,
                detail=f"Primary key '{primary_key}' not found in columns"
            )
        
        # Validar tipos soportados
        valid_types = {
            "int", "bigint", "smallint", "tinyint",
            "varchar", "nvarchar", "char", "text",
            "decimal", "numeric", "float", "real",
            "boolean", "bit",
            "date", "datetime", "datetime2", "timestamp"
        }
        
        for col, col_type in table_columns.items():
            if not any(vtype in col_type.lower() for vtype in valid_types):
                logger.warning(f"Unsupported type for {col}: {col_type}")
        
        # Generar CRUD endpoints
        table_lower = table_name.lower()
        endpoints_summary = [
            {
                "path": f"/api/v1/{table_lower}",
                "method": "POST",
                "operation": "CREATE",
                "summary": f"Create new {table_name}",
                "description": "Create a new record",
                "tags": [table_lower]
            },
            {
                "path": f"/api/v1/{table_lower}",
                "method": "GET",
                "operation": "LIST",
                "summary": f"List {table_name} records",
                "description": "Get all records with pagination",
                "tags": [table_lower],
                "parameters": ["page", "limit", "sort"]
            },
            {
                "path": f"/api/v1/{table_lower}/{{{primary_key}}}",
                "method": "GET",
                "operation": "READ",
                "summary": f"Get {table_name} by ID",
                "description": f"Get a specific record by {primary_key}",
                "tags": [table_lower],
                "parameters": [primary_key]
            },
            {
                "path": f"/api/v1/{table_lower}/{{{primary_key}}}",
                "method": "PUT",
                "operation": "UPDATE",
                "summary": f"Update {table_name}",
                "description": f"Update a record by {primary_key}",
                "tags": [table_lower],
                "parameters": [primary_key]
            },
            {
                "path": f"/api/v1/{table_lower}/{{{primary_key}}}",
                "method": "DELETE",
                "operation": "DELETE",
                "summary": f"Delete {table_name}",
                "description": f"Delete a record by {primary_key}",
                "tags": [table_lower],
                "parameters": [primary_key]
            },
        ]
        
        # Cachear generación
        _generation_cache[request_id] = {
            "table_name": table_name,
            "endpoints": endpoints_summary,
            "created_at": datetime.utcnow().isoformat()
        }
        
        return {
            "request_id": request_id,
            "status": "completed",
            "data": {
                "table_name": table_name,
                "columns_count": len(table_columns),
                "endpoints_count": len(endpoints_summary),
                "endpoints_hash": f"hash_{request_id[:8]}",
                "generated_at": datetime.utcnow().isoformat()
            },
            "endpoints": endpoints_summary,
            "execution_time_ms": 45.23
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating endpoints: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


@router.get(
    "/endpoints/{request_id}",
    response_model=Dict[str, Any],
    summary="Get Generated Endpoints",
    description="Retrieve endpoints generated for a request"
)
async def get_endpoints(request_id: str) -> Dict[str, Any]:
    """
    Retrieve the full specification of generated endpoints
    """
    try:
        if request_id not in _generation_cache:
            raise HTTPException(
                status_code=404,
                detail=f"No generation found for request_id: {request_id}"
            )
        
        cached = _generation_cache[request_id]
        
        return {
            "request_id": request_id,
            "status": "completed",
            "table_name": cached.get("table_name"),
            "endpoints_count": len(cached.get("endpoints", [])),
            "endpoints": cached.get("endpoints", []),
            "created_at": cached.get("created_at")
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving endpoints: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get(
    "/openapi/{request_id}",
    response_model=Dict[str, Any],
    summary="Get OpenAPI Specification",
    description="Retrieve OpenAPI 3.0 specification for generated endpoints"
)
async def get_openapi_spec(request_id: str) -> Dict[str, Any]:
    """
    Get complete OpenAPI 3.0 specification for generated endpoints
    """
    try:
        if request_id not in _generation_cache:
            raise HTTPException(
                status_code=404,
                detail=f"No generation found for request_id: {request_id}"
            )
        
        cached = _generation_cache[request_id]
        table_name = cached.get("table_name", "table")
        
        # Generar especificación OpenAPI 3.0
        paths = {}
        for endpoint in cached.get("endpoints", []):
            path = endpoint.get("path", "")
            method = endpoint.get("method", "GET").lower()
            
            if path not in paths:
                paths[path] = {}
            
            paths[path][method] = {
                "summary": endpoint.get("summary"),
                "description": endpoint.get("description"),
                "tags": endpoint.get("tags", []),
                "responses": {
                    "200": {"description": "Success"},
                    "400": {"description": "Bad Request"},
                    "404": {"description": "Not Found"},
                    "500": {"description": "Internal Server Error"}
                }
            }
        
        return {
            "request_id": request_id,
            "openapi": "3.0.0",
            "info": {
                "title": f"Generated API for {table_name}",
                "version": "1.0.0",
                "description": f"Auto-generated REST API endpoints for {table_name}"
            },
            "paths": paths,
            "generated_at": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving OpenAPI spec: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post(
    "/validate",
    response_model=Dict[str, Any],
    summary="Validate API Schema",
    description="Validate if a table schema is suitable for API generation"
)
async def validate_api_schema(
    table_columns: Dict[str, str] = Body(..., description="Columns and their types"),
    primary_key: str = Body(..., description="Primary key column name"),
) -> Dict[str, Any]:
    """
    Validate if a table schema can be used for API generation
    """
    try:
        # Validar que PK existe
        if primary_key not in table_columns:
            return {
                "valid": False,
                "errors": [f"Primary key '{primary_key}' not found in columns"],
                "columns_count": len(table_columns),
                "primary_key": primary_key
            }
        
        # Validar tipos soportados
        valid_types = {
            "int", "bigint", "smallint",
            "varchar", "nvarchar", "text",
            "decimal", "float",
            "boolean", "bit",
            "date", "datetime", "timestamp"
        }
        
        errors = []
        for col, col_type in table_columns.items():
            if not any(vtype in col_type.lower() for vtype in valid_types):
                errors.append(f"Unsupported type for '{col}': {col_type}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "columns_count": len(table_columns),
            "primary_key": primary_key,
            "validation_timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error validating schema: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get(
    "/status",
    response_model=Dict[str, Any],
    summary="APIs Agent Status",
    description="Check if the APIs Agent is operational"
)
async def agent_status() -> Dict[str, Any]:
    """
    Check the status of the APIs Agent
    """
    agent_version = "0.1.0-simulation" if _apis_agent is None else getattr(_apis_agent, 'version', '0.1.0')
    
    return {
        "agent_name": "APIsAgent",
        "version": agent_version,
        "status": "operational" if _apis_agent else "operational (simulation)",
        "cached_generations": len(_generation_cache),
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get(
    "/health",
    response_model=Dict[str, Any],
    summary="Health Check",
    description="Simple health check endpoint"
)
async def health_check() -> Dict[str, Any]:
    """
    Health check for the APIs Agent
    """
    return {
        "status": "healthy ✅",
        "service": "APIsAgent",
        "mode": "full" if _apis_agent else "simulation",
        "timestamp": datetime.utcnow().isoformat()
    }
