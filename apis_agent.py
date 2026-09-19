"""
APIs Agent - Generador automático de endpoints CRUD
Genera y valida endpoints REST a partir de esquemas de tabla
Soporta CRUD, filtrado, paginación, relaciones foráneas
"""

import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import hashlib
from abc import ABC

from base_agent import BaseAgent, AgentStatus, BaseAgentInput, BaseAgentOutput


# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================

class HTTPMethod(str, Enum):
    """HTTP Methods soportados"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class OperationType(str, Enum):
    """Operaciones que genera el APIs Agent"""
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LIST = "LIST"
    FILTER = "FILTER"


@dataclass
class PathParameter:
    """Parámetro de ruta en endpoint"""
    name: str
    type: str  # int, string, uuid
    description: str
    required: bool = True


@dataclass
class QueryParameter:
    """Parámetro de query en endpoint"""
    name: str
    type: str  # string, int, float, boolean
    description: str
    required: bool = False
    default: Optional[Any] = None


@dataclass
class RequestBody:
    """Schema del body de request"""
    schema_name: str
    fields: Dict[str, str]  # field_name -> type
    required_fields: List[str]
    example: Dict[str, Any]


@dataclass
class ResponseSchema:
    """Schema de respuesta"""
    status_code: int
    schema: Dict[str, Any]
    description: str
    example: Dict[str, Any]


@dataclass
class APIEndpoint:
    """Especificación completa de un endpoint"""
    path: str
    method: HTTPMethod
    operation_type: OperationType
    summary: str
    description: str
    tags: List[str]
    path_parameters: List[PathParameter] = field(default_factory=list)
    query_parameters: List[QueryParameter] = field(default_factory=list)
    request_body: Optional[RequestBody] = None
    responses: List[ResponseSchema] = field(default_factory=list)
    requires_auth: bool = True
    rate_limit: Optional[int] = None  # requests per minute
    cache_ttl: Optional[int] = None  # seconds


@dataclass
class APIEndpointInput(BaseAgentInput):
    """Input para APIs Agent"""
    request_id: str
    table_name: str
    table_columns: Dict[str, str]  # column_name -> type
    primary_key: str
    foreign_keys: List[Tuple[str, str, str]] = field(default_factory=list)  # (column, ref_table, ref_column)
    description: str = ""


@dataclass
class APIEndpointOutput(BaseAgentOutput):
    """Output del APIs Agent"""
    request_id: str
    status: AgentStatus
    data: Dict[str, Any] = field(default_factory=dict)
    endpoints_generated: int = 0
    endpoints: List[APIEndpoint] = field(default_factory=list)
    openapi_spec: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ============================================================================
# ENDPOINT GENERATOR
# ============================================================================

class EndpointGenerator:
    """Genera especificaciones de endpoints CRUD"""
    
    def __init__(self, table_name: str, primary_key: str, columns: Dict[str, str]):
        self.table_name = table_name
        self.primary_key = primary_key
        self.columns = columns
        self.endpoints: List[APIEndpoint] = []
    
    def generate_crud_endpoints(self) -> List[APIEndpoint]:
        """Genera los 5 endpoints CRUD estándar"""
        endpoints = [
            self._generate_create(),
            self._generate_read(),
            self._generate_list(),
            self._generate_update(),
            self._generate_delete(),
        ]
        self.endpoints = endpoints
        return endpoints
    
    def _generate_create(self) -> APIEndpoint:
        """POST /api/v1/{table_name} - Crear registro"""
        # Campos requeridos (excluyendo PK que es auto-incremental)
        required_fields = [col for col in self.columns.keys() if col != self.primary_key]
        
        # Schema de request
        request_schema = {col: self.columns[col] for col in required_fields}
        example = self._generate_example(request_schema, is_create=True)
        
        return APIEndpoint(
            path=f"/api/v1/{self.table_name.lower()}",
            method=HTTPMethod.POST,
            operation_type=OperationType.CREATE,
            summary=f"Create new {self.table_name}",
            description=f"Create a new {self.table_name.lower()} record",
            tags=[self.table_name.lower()],
            request_body=RequestBody(
                schema_name=self.table_name,
                fields=request_schema,
                required_fields=required_fields,
                example=example
            ),
            responses=[
                ResponseSchema(
                    status_code=201,
                    schema={"id": "int", "data": "object"},
                    description="Record created successfully",
                    example={"id": 1, "data": example}
                ),
                ResponseSchema(
                    status_code=400,
                    schema={"error": "string"},
                    description="Validation error",
                    example={"error": "Invalid input"}
                )
            ]
        )
    
    def _generate_read(self) -> APIEndpoint:
        """GET /api/v1/{table_name}/{id} - Leer un registro"""
        pk_type = self.columns.get(self.primary_key, "int")
        
        return APIEndpoint(
            path=f"/api/v1/{self.table_name.lower()}/{{id}}",
            method=HTTPMethod.GET,
            operation_type=OperationType.READ,
            summary=f"Get {self.table_name} by ID",
            description=f"Retrieve a single {self.table_name.lower()} record by ID",
            tags=[self.table_name.lower()],
            path_parameters=[
                PathParameter(
                    name="id",
                    type=pk_type,
                    description=f"{self.primary_key} of the {self.table_name.lower()}"
                )
            ],
            responses=[
                ResponseSchema(
                    status_code=200,
                    schema=self.columns,
                    description="Record found",
                    example=self._generate_example(self.columns)
                ),
                ResponseSchema(
                    status_code=404,
                    schema={"error": "string"},
                    description="Record not found",
                    example={"error": "Not found"}
                )
            ]
        )
    
    def _generate_list(self) -> APIEndpoint:
        """GET /api/v1/{table_name} - Listar registros con paginación"""
        return APIEndpoint(
            path=f"/api/v1/{self.table_name.lower()}",
            method=HTTPMethod.GET,
            operation_type=OperationType.LIST,
            summary=f"List {self.table_name} records",
            description=f"Retrieve paginated list of {self.table_name.lower()} records",
            tags=[self.table_name.lower()],
            query_parameters=[
                QueryParameter(
                    name="page",
                    type="int",
                    description="Page number (1-indexed)",
                    required=False,
                    default=1
                ),
                QueryParameter(
                    name="page_size",
                    type="int",
                    description="Records per page (1-100)",
                    required=False,
                    default=20
                ),
                QueryParameter(
                    name="sort_by",
                    type="string",
                    description="Column to sort by",
                    required=False
                ),
                QueryParameter(
                    name="sort_order",
                    type="string",
                    description="ASC or DESC",
                    required=False,
                    default="ASC"
                )
            ],
            responses=[
                ResponseSchema(
                    status_code=200,
                    schema={
                        "data": "array",
                        "total": "int",
                        "page": "int",
                        "page_size": "int"
                    },
                    description="List retrieved successfully",
                    example={
                        "data": [self._generate_example(self.columns)],
                        "total": 100,
                        "page": 1,
                        "page_size": 20
                    }
                )
            ]
        )
    
    def _generate_update(self) -> APIEndpoint:
        """PUT /api/v1/{table_name}/{id} - Actualizar registro"""
        pk_type = self.columns.get(self.primary_key, "int")
        
        # Todos los campos son opcionales en update
        update_schema = {col: self.columns[col] for col in self.columns.keys() if col != self.primary_key}
        
        return APIEndpoint(
            path=f"/api/v1/{self.table_name.lower()}/{{id}}",
            method=HTTPMethod.PUT,
            operation_type=OperationType.UPDATE,
            summary=f"Update {self.table_name}",
            description=f"Update an existing {self.table_name.lower()} record",
            tags=[self.table_name.lower()],
            path_parameters=[
                PathParameter(
                    name="id",
                    type=pk_type,
                    description=f"{self.primary_key} of the {self.table_name.lower()}"
                )
            ],
            request_body=RequestBody(
                schema_name=f"{self.table_name}Update",
                fields=update_schema,
                required_fields=[],  # Todos opcionales
                example=self._generate_example(update_schema, is_create=False)
            ),
            responses=[
                ResponseSchema(
                    status_code=200,
                    schema=self.columns,
                    description="Record updated successfully",
                    example=self._generate_example(self.columns)
                ),
                ResponseSchema(
                    status_code=404,
                    schema={"error": "string"},
                    description="Record not found",
                    example={"error": "Not found"}
                )
            ]
        )
    
    def _generate_delete(self) -> APIEndpoint:
        """DELETE /api/v1/{table_name}/{id} - Eliminar registro"""
        pk_type = self.columns.get(self.primary_key, "int")
        
        return APIEndpoint(
            path=f"/api/v1/{self.table_name.lower()}/{{id}}",
            method=HTTPMethod.DELETE,
            operation_type=OperationType.DELETE,
            summary=f"Delete {self.table_name}",
            description=f"Delete a {self.table_name.lower()} record",
            tags=[self.table_name.lower()],
            path_parameters=[
                PathParameter(
                    name="id",
                    type=pk_type,
                    description=f"{self.primary_key} of the {self.table_name.lower()}"
                )
            ],
            responses=[
                ResponseSchema(
                    status_code=204,
                    schema={},
                    description="Record deleted successfully",
                    example={}
                ),
                ResponseSchema(
                    status_code=404,
                    schema={"error": "string"},
                    description="Record not found",
                    example={"error": "Not found"}
                )
            ]
        )
    
    def _generate_example(self, schema: Dict[str, str], is_create: bool = True) -> Dict[str, Any]:
        """Genera un ejemplo de registro basado en tipos de columna"""
        example = {}
        for col, col_type in schema.items():
            if col == self.primary_key and is_create:
                continue
            
            col_type_lower = col_type.lower()
            if "int" in col_type_lower:
                example[col] = 1
            elif "varchar" in col_type_lower or "text" in col_type_lower:
                example[col] = "sample value"
            elif "decimal" in col_type_lower or "numeric" in col_type_lower:
                example[col] = 10.50
            elif "bool" in col_type_lower:
                example[col] = True
            elif "date" in col_type_lower:
                example[col] = "2026-09-12"
            elif "time" in col_type_lower:
                example[col] = "10:30:00"
            else:
                example[col] = "value"
        
        return example


# ============================================================================
# SCHEMA VALIDATOR
# ============================================================================

class SchemaValidator:
    """Valida esquemas de requests contra especificaciones"""
    
    VALID_TYPES = {"int", "varchar", "text", "decimal", "boolean", "date", "timestamp"}
    
    def __init__(self, columns: Dict[str, str]):
        self.columns = columns
        self.errors: List[str] = []
    
    def validate_column_types(self) -> bool:
        """Valida que todos los tipos de columna sean válidos"""
        self.errors = []
        for col, col_type in self.columns.items():
            if not any(valid in col_type.lower() for valid in self.VALID_TYPES):
                self.errors.append(f"Invalid column type for {col}: {col_type}")
        return len(self.errors) == 0
    
    def validate_request(self, request_data: Dict[str, Any], required_fields: List[str]) -> Tuple[bool, List[str]]:
        """Valida un request contra los campos requeridos"""
        errors = []
        
        # Validar campos requeridos
        for field in required_fields:
            if field not in request_data:
                errors.append(f"Missing required field: {field}")
        
        # Validar tipos de datos
        for field, value in request_data.items():
            if field not in self.columns:
                errors.append(f"Unknown field: {field}")
                continue
            
            col_type = self.columns[field].lower()
            if not self._validate_type(value, col_type):
                errors.append(f"Invalid type for {field}: expected {col_type}, got {type(value).__name__}")
        
        return len(errors) == 0, errors
    
    def _validate_type(self, value: Any, col_type: str) -> bool:
        """Valida que un valor corresponda al tipo de columna"""
        if value is None:
            return True
        
        if "int" in col_type:
            return isinstance(value, int) and not isinstance(value, bool)
        elif "varchar" in col_type or "text" in col_type:
            return isinstance(value, str)
        elif "decimal" in col_type or "numeric" in col_type:
            return isinstance(value, (int, float))
        elif "bool" in col_type:
            return isinstance(value, bool)
        elif "date" in col_type or "time" in col_type:
            return isinstance(value, str)
        
        return True


# ============================================================================
# OPENAPI SPEC GENERATOR
# ============================================================================

class OpenAPISpecGenerator:
    """Genera especificación OpenAPI 3.0 para los endpoints"""
    
    def __init__(self, title: str, version: str = "1.0.0"):
        self.title = title
        self.version = version
    
    def generate_spec(self, endpoints: List[APIEndpoint]) -> Dict[str, Any]:
        """Genera especificación OpenAPI completa"""
        paths = self._generate_paths(endpoints)
        
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": f"Auto-generated API documentation for {self.title}"
            },
            "servers": [
                {"url": "http://localhost:8000", "description": "Development"},
                {"url": "https://api.example.com", "description": "Production"}
            ],
            "paths": paths,
            "components": {
                "securitySchemes": {
                    "bearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT"
                    }
                }
            },
            "security": [{"bearerAuth": []}]
        }
        
        return spec
    
    def _generate_paths(self, endpoints: List[APIEndpoint]) -> Dict[str, Any]:
        """Genera la sección paths del OpenAPI"""
        paths = {}
        
        for endpoint in endpoints:
            if endpoint.path not in paths:
                paths[endpoint.path] = {}
            
            method_lower = endpoint.method.value.lower()
            paths[endpoint.path][method_lower] = self._endpoint_to_openapi(endpoint)
        
        return paths
    
    def _endpoint_to_openapi(self, endpoint: APIEndpoint) -> Dict[str, Any]:
        """Convierte un APIEndpoint a formato OpenAPI"""
        operation = {
            "summary": endpoint.summary,
            "description": endpoint.description,
            "tags": endpoint.tags,
            "operationId": f"{endpoint.operation_type.value.lower()}_{endpoint.path.replace('/', '_')}",
        }
        
        # Path parameters
        if endpoint.path_parameters:
            operation["parameters"] = [
                {
                    "name": param.name,
                    "in": "path",
                    "required": param.required,
                    "description": param.description,
                    "schema": {"type": param.type}
                }
                for param in endpoint.path_parameters
            ]
        
        # Query parameters
        if endpoint.query_parameters:
            if "parameters" not in operation:
                operation["parameters"] = []
            
            operation["parameters"].extend([
                {
                    "name": param.name,
                    "in": "query",
                    "required": param.required,
                    "description": param.description,
                    "schema": {
                        "type": param.type,
                        "default": param.default
                    }
                }
                for param in endpoint.query_parameters
            ])
        
        # Request body
        if endpoint.request_body:
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": endpoint.request_body.fields,
                        "example": endpoint.request_body.example
                    }
                }
            }
        
        # Responses
        if endpoint.responses:
            operation["responses"] = {
                str(resp.status_code): {
                    "description": resp.description,
                    "content": {
                        "application/json": {
                            "schema": resp.schema,
                            "example": resp.example
                        }
                    }
                }
                for resp in endpoint.responses
            }
        
        return operation


# ============================================================================
# APIS AGENT
# ============================================================================

class APIsAgent(BaseAgent):
    """Agent que genera automáticamente endpoints CRUD a partir de esquemas"""
    
    def __init__(self):
        super().__init__(
            agent_name="APIsAgent",
            version="1.0.0",
            description="Generador automático de endpoints REST CRUD"
        )
    
    async def execute(self, input_data: APIEndpointInput) -> APIEndpointOutput:
        """
        Genera endpoints CRUD completos para una tabla
        
        Args:
            input_data: APIEndpointInput con configuración de tabla
        
        Returns:
            APIEndpointOutput con endpoints generados y especificación OpenAPI
        """
        start_time = datetime.utcnow()
        
        try:
            # Validar input
            is_valid, validation_errors = self.validate_input(input_data)
            if not is_valid:
                return APIEndpointOutput(
                    request_id=input_data.request_id,
                    status=AgentStatus.FAILED,
                    error=f"Validation failed: {', '.join(validation_errors)}",
                    execution_time_ms=self._get_execution_time_ms(start_time)
                )
            
            # Generar endpoints
            generator = EndpointGenerator(
                table_name=input_data.table_name,
                primary_key=input_data.primary_key,
                columns=input_data.table_columns
            )
            endpoints = generator.generate_crud_endpoints()
            
            # Validar esquemas
            validator = SchemaValidator(input_data.table_columns)
            if not validator.validate_column_types():
                return APIEndpointOutput(
                    request_id=input_data.request_id,
                    status=AgentStatus.FAILED,
                    error=f"Schema validation failed: {', '.join(validator.errors)}",
                    execution_time_ms=self._get_execution_time_ms(start_time)
                )
            
            # Generar OpenAPI spec
            openapi_gen = OpenAPISpecGenerator(
                title=f"{input_data.table_name} API",
                version="1.0.0"
            )
            openapi_spec = openapi_gen.generate_spec(endpoints)
            
            # Generar hash de endpoints
            endpoints_hash = self._generate_endpoints_hash(endpoints)
            
            # Emitir evento
            await self._emit_event(
                event_type="ENDPOINTS_GENERATED",
                data={
                    "table_name": input_data.table_name,
                    "endpoints_count": len(endpoints),
                    "hash": endpoints_hash
                }
            )
            
            execution_time = self._get_execution_time_ms(start_time)
            
            return APIEndpointOutput(
                request_id=input_data.request_id,
                status=AgentStatus.COMPLETED,
                data={
                    "table_name": input_data.table_name,
                    "endpoints_count": len(endpoints),
                    "endpoints_hash": endpoints_hash,
                    "generated_at": datetime.utcnow().isoformat()
                },
                endpoints_generated=len(endpoints),
                endpoints=endpoints,
                openapi_spec=openapi_spec,
                execution_time_ms=execution_time
            )
        
        except Exception as e:
            self.logger.error(f"APIsAgent execution failed: {str(e)}", exc_info=True)
            return APIEndpointOutput(
                request_id=input_data.request_id,
                status=AgentStatus.FAILED,
                error=str(e),
                execution_time_ms=self._get_execution_time_ms(start_time)
            )
    
    def validate_input(self, input_data: APIEndpointInput) -> Tuple[bool, List[str]]:
        """Valida que el input sea correcto"""
        errors = []
        
        if not input_data.request_id:
            errors.append("request_id is required")
        if not input_data.table_name:
            errors.append("table_name is required")
        if not input_data.table_columns:
            errors.append("table_columns is required")
        if not input_data.primary_key:
            errors.append("primary_key is required")
        if input_data.primary_key not in input_data.table_columns:
            errors.append(f"primary_key '{input_data.primary_key}' not found in table_columns")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def _generate_endpoints_hash(endpoints: List[APIEndpoint]) -> str:
        """Genera un hash único para el conjunto de endpoints"""
        endpoint_str = json.dumps(
            [f"{ep.path}:{ep.method.value}" for ep in endpoints],
            sort_keys=True
        )
        return hashlib.sha256(endpoint_str.encode()).hexdigest()[:16]
    
    @staticmethod
    def _get_execution_time_ms(start_time: datetime) -> float:
        """Calcula tiempo de ejecución en ms"""
        return (datetime.utcnow() - start_time).total_seconds() * 1000
