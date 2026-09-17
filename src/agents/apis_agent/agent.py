"""
APIs Agent - Automatic REST API Generation
Genera endpoints CRUD automáticamente desde definiciones de tablas
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================

class AgentStatus(str, Enum):
    """Estados del agente"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class APIEndpointInput:
    """Input para generación de endpoints"""
    request_id: str
    table_name: str
    table_columns: Dict[str, str]
    primary_key: str
    description: str = ""
    
    def __post_init__(self):
        if not self.request_id:
            raise ValueError("request_id is required")
        if not self.table_name:
            raise ValueError("table_name is required")
        if not self.table_columns:
            raise ValueError("table_columns is required")
        if not self.primary_key:
            raise ValueError("primary_key is required")
        if self.primary_key not in self.table_columns:
            raise ValueError(f"Primary key '{self.primary_key}' not found in columns")


@dataclass
class Endpoint:
    """Especificación de un endpoint"""
    path: str
    method: str
    operation: str
    summary: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    parameters: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "method": self.method,
            "operation": self.operation,
            "summary": self.summary,
            "description": self.description,
            "tags": self.tags,
            "parameters": self.parameters
        }


@dataclass
class APIEndpointOutput:
    """Output de generación de endpoints"""
    status: AgentStatus
    request_id: str
    table_name: str
    endpoints: List[Endpoint] = field(default_factory=list)
    error: Optional[str] = None
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "request_id": self.request_id,
            "table_name": self.table_name,
            "endpoints_count": len(self.endpoints),
            "endpoints": [ep.to_dict() for ep in self.endpoints],
            "error": self.error,
            "generated_at": self.generated_at
        }


# ============================================================================
# APIS AGENT
# ============================================================================

class APIsAgent:
    """Agente para generar APIs REST automáticamente"""
    
    def __init__(self):
        self.name = "APIsAgent"
        self.version = "0.1.0"
        logger.info(f"✅ {self.name} v{self.version} initialized")
    
    async def execute(self, input_data: APIEndpointInput) -> APIEndpointOutput:
        """
        Ejecuta la generación de endpoints
        
        Args:
            input_data: Especificación de tabla y columnas
            
        Returns:
            APIEndpointOutput con endpoints generados
        """
        try:
            logger.info(f"Processing request {input_data.request_id} for table {input_data.table_name}")
            
            # Validar PK existe
            if input_data.primary_key not in input_data.table_columns:
                return APIEndpointOutput(
                    status=AgentStatus.FAILED,
                    request_id=input_data.request_id,
                    table_name=input_data.table_name,
                    error=f"Primary key '{input_data.primary_key}' not found in columns"
                )
            
            logger.info(f"✅ Schema validation passed")
            
            # Generar endpoints CRUD
            table_lower = input_data.table_name.lower()
            endpoints = []
            
            # 1. CREATE
            endpoints.append(Endpoint(
                path=f"/api/v1/{table_lower}",
                method="POST",
                operation="CREATE",
                summary=f"Create new {input_data.table_name}",
                description=f"Create a new {input_data.table_name} record",
                tags=[table_lower]
            ))
            
            # 2. LIST
            endpoints.append(Endpoint(
                path=f"/api/v1/{table_lower}",
                method="GET",
                operation="LIST",
                summary=f"List {input_data.table_name} records",
                description=f"Get all {input_data.table_name} records with pagination",
                tags=[table_lower],
                parameters=["page", "limit", "sort"]
            ))
            
            # 3. READ by ID
            endpoints.append(Endpoint(
                path=f"/api/v1/{table_lower}/{{{input_data.primary_key}}}",
                method="GET",
                operation="READ",
                summary=f"Get {input_data.table_name} by ID",
                description=f"Get a specific {input_data.table_name} record by {input_data.primary_key}",
                tags=[table_lower],
                parameters=[input_data.primary_key]
            ))
            
            # 4. UPDATE
            endpoints.append(Endpoint(
                path=f"/api/v1/{table_lower}/{{{input_data.primary_key}}}",
                method="PUT",
                operation="UPDATE",
                summary=f"Update {input_data.table_name}",
                description=f"Update a {input_data.table_name} record by {input_data.primary_key}",
                tags=[table_lower],
                parameters=[input_data.primary_key]
            ))
            
            # 5. DELETE
            endpoints.append(Endpoint(
                path=f"/api/v1/{table_lower}/{{{input_data.primary_key}}}",
                method="DELETE",
                operation="DELETE",
                summary=f"Delete {input_data.table_name}",
                description=f"Delete a {input_data.table_name} record by {input_data.primary_key}",
                tags=[table_lower],
                parameters=[input_data.primary_key]
            ))
            
            logger.info(f"✅ Generated {len(endpoints)} CRUD endpoints")
            
            output = APIEndpointOutput(
                status=AgentStatus.COMPLETED,
                request_id=input_data.request_id,
                table_name=input_data.table_name,
                endpoints=endpoints
            )
            
            logger.info(f"✅ Request {input_data.request_id} completed successfully")
            
            return output
            
        except Exception as e:
            logger.error(f"Error executing APIsAgent: {str(e)}", exc_info=True)
            return APIEndpointOutput(
                status=AgentStatus.FAILED,
                request_id=input_data.request_id,
                table_name=input_data.table_name,
                error=str(e)
            )
