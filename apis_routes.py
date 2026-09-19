"""
FastAPI Routes for APIs Agent
Endpoints para generar y consultar especificaciones de API
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from datetime import datetime
import asyncio

from agents.apis_agent.agent import (
    APIsAgent,
    APIEndpointInput,
    APIEndpointOutput,
    AgentStatus
)


logger = logging.getLogger(__name__)

# Crear router
router = APIRouter(
    prefix="/api/v1/apis",
    tags=["APIs Agent"]
)

# Cache de generaciones anteriores
_generation_cache: Dict[str, APIEndpointOutput] = {}

# Instancia global del agente
_apis_agent = APIsAgent()


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
        
        # Crear input
        input_data = APIEndpointInput(
            request_id=request_id,
            table_name=table_name,
            table_columns=table_columns,
            primary_key=primary_key,
            description=description or ""
        )
        
        # Ejecutar agente
        output = await _apis_agent.execute(input_data)
        
        if output.status == AgentStatus.FAILED:
            raise HTTPException(
                status_code=400,
                detail=f"API generation failed: {output.error}"
            )
        
        # Cachear resultado
        _generation_cache[request_id] = output
        
        # Preparar respuesta
        endpoints_summary = [
            {
                "path": ep.path,
                "method": ep.method.value,
                "operation": ep.operation_type.value,
                "summary": ep.summary
            }
            for ep in output.endpoints
        ]
        
        return {
            "request_id": output.request_id,
            "status": output.status.value,
            "data": {
                "table_name": output.data.get("table_name"),
                "endpoints_count": output.endpoints_generated,
                "endpoints_hash": output.data.get("endpoints_hash"),
                "generated_at": output.created_at
            },
            "endpoints": endpoints_summary,
            "execution_time_ms": output.execution_time_ms
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
async def get_endpoints(
    request_id: str,
) -> Dict[str, Any]:
    """
    Retrieve the full specification of generated endpoints
    
    Example response:
    ```json
    {
        "request_id": "gen_001",
        "endpoints": [
            {
                "path": "/api/v1/clientes",
                "method": "POST",
                "operation": "CREATE",
                "summary": "Create new cliente",
                "request_body": {
                    "fields": {...},
                    "required_fields": [...]
                },
                "responses": [...]
            }
        ]
    }
    ```
    """
    try:
        if request_id not in _generation_cache:
            raise HTTPException(
                status_code=404,
                detail=f"No generation found for request_id: {request_id}"
            )
        
        output = _generation_cache[request_id]
        
        # Convertir endpoints a dict
        endpoints_detail = [
            {
                "path": ep.path,
                "method": ep.method.value,
                "operation": ep.operation_type.value,
                "summary": ep.summary,
                "description": ep.description,
                "tags": ep.tags,
                "path_parameters": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "description": p.description,
                        "required": p.required
                    }
                    for p in ep.path_parameters
                ],
                "query_parameters": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "description": p.description,
                        "required": p.required,
                        "default": p.default
                    }
                    for p in ep.query_parameters
                ],
                "request_body": {
                    "schema_name": ep.request_body.schema_name,
                    "fields": ep.request_body.fields,
                    "required_fields": ep.request_body.required_fields,
                    "example": ep.request_body.example
                } if ep.request_body else None,
                "responses": [
                    {
                        "status_code": r.status_code,
                        "description": r.description,
                        "schema": r.schema,
                        "example": r.example
                    }
                    for r in ep.responses
                ]
            }
            for ep in output.endpoints
        ]
        
        return {
            "request_id": output.request_id,
            "status": output.status.value,
            "endpoints_count": output.endpoints_generated,
            "endpoints": endpoints_detail,
            "execution_time_ms": output.execution_time_ms
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving endpoints: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


@router.get(
    "/openapi/{request_id}",
    response_model=Dict[str, Any],
    summary="Get OpenAPI Specification",
    description="Retrieve OpenAPI 3.0 specification for generated endpoints"
)
async def get_openapi_spec(
    request_id: str,
) -> Dict[str, Any]:
    """
    Get complete OpenAPI 3.0 specification
    
    The returned spec can be used with Swagger UI, Redoc, or integrated into documentation
    """
    try:
        if request_id not in _generation_cache:
            raise HTTPException(
                status_code=404,
                detail=f"No generation found for request_id: {request_id}"
            )
        
        output = _generation_cache[request_id]
        
        return {
            "request_id": output.request_id,
            "openapi_spec": output.openapi_spec
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving OpenAPI spec: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


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
    
    Checks:
    - Primary key exists in columns
    - All column types are supported
    - No reserved column names
    """
    try:
        # Validar PK existe
        if primary_key not in table_columns:
            return {
                "valid": False,
                "errors": [f"Primary key '{primary_key}' not found in columns"]
            }
        
        # Validar tipos soportados
        from agents.apis_agent.agent import SchemaValidator
        
        validator = SchemaValidator(table_columns)
        is_valid = validator.validate_column_types()
        
        return {
            "valid": is_valid,
            "errors": validator.errors,
            "columns_count": len(table_columns),
            "primary_key": primary_key
        }
    
    except Exception as e:
        logger.error(f"Error validating schema: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


@router.get(
    "/status",
    response_model=Dict[str, Any],
    summary="API Agent Status",
    description="Check if the APIs Agent is operational"
)
async def agent_status() -> Dict[str, Any]:
    """
    Check the status of the APIs Agent
    """
    return {
        "agent_name": _apis_agent.agent_name,
        "version": _apis_agent.version,
        "status": "operational",
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
        "status": "healthy",
        "service": "APIsAgent",
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def clear_cache():
    """Limpia el cache de generaciones"""
    global _generation_cache
    _generation_cache.clear()


def get_cache_stats() -> Dict[str, Any]:
    """Obtiene estadísticas del cache"""
    return {
        "cached_items": len(_generation_cache),
        "cache_keys": list(_generation_cache.keys())
    }
