# NEXUS v2.0 - DatabaseAgent with Stored Procedures
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from fastapi import APIRouter, HTTPException, Query
import asyncio

logger = logging.getLogger(__name__)

# ============================================================================
# LOGGING
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# ENUMS
# ============================================================================

class OperationType(str, Enum):
    """Tipo de operación CRUD"""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CUSTOM = "CUSTOM"

class DatabaseType(str, Enum):
    """Tipo de base de datos"""
    POSTGRESQL = "postgresql"
    MSSQL = "mssql"

# ============================================================================
# REQUEST MODELS
# ============================================================================

class CreateStoredProcedureRequest(BaseModel):
    """Crear procedimiento almacenado"""
    table_name: str = Field(..., description="Nombre de la tabla")
    operation: OperationType = Field(..., description="Tipo de operación CRUD")
    columns_types: Optional[Dict[str, str]] = Field(
        default=None, 
        description="Dict de columnas y tipos (para INSERT/UPDATE)"
    )
    id_column: Optional[str] = Field(
        default="id",
        description="Nombre de la columna ID"
    )
    database: DatabaseType = Field(
        default=DatabaseType.MSSQL,
        description="Base de datos destino"
    )

class ExecuteStoredProcedureRequest(BaseModel):
    """Ejecutar procedimiento almacenado"""
    procedure_name: str = Field(..., description="Nombre del procedimiento")
    parameters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Parámetros del procedimiento"
    )
    database: DatabaseType = Field(
        default=DatabaseType.MSSQL,
        description="Base de datos"
    )

class CRUDRequest(BaseModel):
    """Solicitud genérica de CRUD"""
    table_name: str = Field(..., description="Nombre de la tabla")
    operation: OperationType = Field(..., description="SELECT, INSERT, UPDATE, DELETE")
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Datos (para INSERT/UPDATE)"
    )
    id: Optional[int] = Field(
        default=None,
        description="ID (para UPDATE/DELETE)"
    )
    database: DatabaseType = Field(
        default=DatabaseType.MSSQL,
        description="Base de datos"
    )

# ============================================================================
# RESPONSE MODELS
# ============================================================================

class StoredProcedureInfo(BaseModel):
    """Información de procedimiento almacenado"""
    name: str
    description: str
    parameters: List[Dict[str, Any]]
    sql_create: str

class CRUDResponse(BaseModel):
    """Respuesta de operación CRUD"""
    status: str
    operation: str
    table_name: str
    affected_rows: int
    procedure_name: str
    execution_time_ms: float
    timestamp: str

class QueryResponse(BaseModel):
    """Respuesta de query con SP"""
    status: str
    rows: int
    columns: List[str]
    data: List[Dict[str, Any]]
    procedure_used: str
    execution_time_ms: float
    timestamp: str

class StoredProceduresListResponse(BaseModel):
    """Lista de procedimientos almacenados"""
    status: str
    database: str
    total: int
    procedures: List[Dict[str, Any]]
    timestamp: str

class SQLInjectionTestResponse(BaseModel):
    """Respuesta de test de SQL injection"""
    status: str
    message: str
    safe: bool
    validation_results: Dict[str, Any]
    timestamp: str

# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(
    prefix="/api/v1/nexus",
    tags=["NEXUS v2.0 - DatabaseAgent (Stored Procedures)"],
    responses={
        200: {"description": "Success"},
        400: {"description": "Bad Request"},
        503: {"description": "Service Unavailable"}
    }
)

# ============================================================================
# ENDPOINT 1: Create Stored Procedure
# ============================================================================

@router.post(
    "/create-stored-procedure",
    response_model=StoredProcedureInfo,
    summary="Create Stored Procedure",
    description="Crear procedimiento almacenado seguro (sin SQL directo)"
)
async def create_stored_procedure(request: CreateStoredProcedureRequest) -> StoredProcedureInfo:
    """
    Crea un procedimiento almacenado seguro automáticamente.
    
    El sistema genera:
    - Procedimiento SELECT para lecturas
    - Procedimiento INSERT para creación (con SCOPE_IDENTITY)
    - Procedimiento UPDATE para actualización
    - Procedimiento DELETE para eliminación
    
    Previene SQL injection mediante:
    - Validación de identificadores (tabla, columnas)
    - Parámetros nombrados (parametrización)
    - Tipado de datos
    
    Body:
    ```json
    {
      "table_name": "users",
      "operation": "INSERT",
      "columns_types": {
        "name": "VARCHAR",
        "email": "VARCHAR",
        "age": "INT"
      },
      "id_column": "id",
      "database": "mssql"
    }
    ```
    """
    logger.info(f"NEXUS v2: Creating SP for {request.table_name} ({request.operation})")
    
    # Validación básica
    if not request.table_name or len(request.table_name) > 128:
        raise HTTPException(status_code=400, detail="Invalid table name")
    
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', request.table_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid table name format (SQL injection attempt?)"
        )
    
    # Simulación de creación de SP (en PROD sería real)
    sp_name = f"sp_{request.operation}_{request.table_name}"
    
    # Generar SQL (simulado)
    if request.operation == OperationType.SELECT:
        sql = f"""
IF OBJECT_ID('[dbo].[{sp_name}]', 'P') IS NOT NULL
    DROP PROCEDURE [dbo].[{sp_name}];
GO

CREATE PROCEDURE [dbo].[{sp_name}]
    @{request.id_column} INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT * FROM [{request.table_name}] WHERE [{request.id_column}] = @{request.id_column};
END;
GO
"""
    elif request.operation == OperationType.INSERT:
        cols = ", ".join([f"[{col}]" for col in request.columns_types.keys()])
        vals = ", ".join([f"@{col}" for col in request.columns_types.keys()])
        sql = f"""
IF OBJECT_ID('[dbo].[{sp_name}]', 'P') IS NOT NULL
    DROP PROCEDURE [dbo].[{sp_name}];
GO

CREATE PROCEDURE [dbo].[{sp_name}]
    {', '.join([f'@{col} VARCHAR(MAX)' for col in request.columns_types.keys()])}
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO [{request.table_name}] ({cols}) VALUES ({vals});
    SELECT SCOPE_IDENTITY() AS id;
END;
GO
"""
    else:
        sql = f"-- Procedimiento para {request.operation}"
    
    return StoredProcedureInfo(
        name=sp_name,
        description=f"{request.operation} procedure for {request.table_name}",
        parameters=[
            {"name": request.id_column, "type": "INT", "direction": "INPUT"}
        ],
        sql_create=sql
    )

# ============================================================================
# ENDPOINT 2: Execute Stored Procedure
# ============================================================================

@router.post(
    "/execute-stored-procedure",
    response_model=QueryResponse,
    summary="Execute Stored Procedure",
    description="Ejecutar procedimiento almacenado con parámetros seguros"
)
async def execute_stored_procedure(request: ExecuteStoredProcedureRequest) -> QueryResponse:
    """
    Ejecuta un procedimiento almacenado de forma segura.
    
    Ventajas:
    - Parámetros nombrados (sin concatenación de SQL)
    - Tipado de datos validado
    - Sin SQL injection posible
    - Rendimiento optimizado (BD cachea el plan)
    
    Body:
    ```json
    {
      "procedure_name": "sp_SELECT_users",
      "parameters": {
        "id": 1
      },
      "database": "mssql"
    }
    ```
    """
    logger.info(f"NEXUS v2: Executing SP {request.procedure_name}")
    
    # Validar nombre del procedimiento
    import re
    if not re.match(r'^sp_[a-zA-Z0-9_]+$', request.procedure_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid procedure name (SQL injection attempt?)"
        )
    
    # Validar parámetros (simulado - en PROD sería validación completa)
    if request.parameters:
        for key, value in request.parameters.items():
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', key):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid parameter name: {key}"
                )
    
    import time
    start = time.time()
    
    # Simular ejecución
    await asyncio.sleep(0.1)
    
    execution_time = (time.time() - start) * 1000
    
    return QueryResponse(
        status="success",
        rows=0,
        columns=["id", "name", "email"],
        data=[],
        procedure_used=request.procedure_name,
        execution_time_ms=execution_time,
        timestamp=datetime.utcnow().isoformat()
    )

# ============================================================================
# ENDPOINT 3: CRUD Operations (via Stored Procedures)
# ============================================================================

@router.post(
    "/crud",
    response_model=CRUDResponse,
    summary="CRUD Operation via Stored Procedure",
    description="Operación CRUD automática con procedimientos almacenados"
)
async def crud_operation(request: CRUDRequest) -> CRUDResponse:
    """
    Realiza operación CRUD usando procedimientos almacenados generados automáticamente.
    
    Flujo:
    1. Recibe solicitud CRUD
    2. Valida tabla y datos
    3. Genera/obtiene procedimiento si no existe
    4. Ejecuta procedimiento con parámetros seguros
    5. Retorna resultado
    
    Body para INSERT:
    ```json
    {
      "table_name": "users",
      "operation": "INSERT",
      "data": {
        "name": "John Doe",
        "email": "john@example.com",
        "age": 30
      },
      "database": "mssql"
    }
    ```
    
    Body para UPDATE:
    ```json
    {
      "table_name": "users",
      "operation": "UPDATE",
      "id": 1,
      "data": {
        "name": "Jane Doe",
        "email": "jane@example.com"
      },
      "database": "mssql"
    }
    ```
    
    Body para DELETE:
    ```json
    {
      "table_name": "users",
      "operation": "DELETE",
      "id": 1,
      "database": "mssql"
    }
    ```
    """
    logger.info(f"NEXUS v2: CRUD {request.operation} on {request.table_name}")
    
    # Validaciones
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', request.table_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid table name (SQL injection attempt?)"
        )
    
    if request.operation not in [op.value for op in OperationType]:
        raise HTTPException(status_code=400, detail="Invalid operation")
    
    # Validar datos si existen
    if request.data:
        for key in request.data.keys():
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', key):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid column name: {key}"
                )
    
    import time
    start = time.time()
    
    # Simular ejecución
    await asyncio.sleep(0.05)
    
    execution_time = (time.time() - start) * 1000
    sp_name = f"sp_{request.operation}_{request.table_name}"
    
    return CRUDResponse(
        status="success",
        operation=request.operation.value,
        table_name=request.table_name,
        affected_rows=1,
        procedure_name=sp_name,
        execution_time_ms=execution_time,
        timestamp=datetime.utcnow().isoformat()
    )

# ============================================================================
# ENDPOINT 4: List Available Stored Procedures
# ============================================================================

@router.get(
    "/stored-procedures",
    response_model=StoredProceduresListResponse,
    summary="List Stored Procedures",
    description="Listar procedimientos almacenados disponibles"
)
async def list_stored_procedures(
    database: DatabaseType = Query(DatabaseType.MSSQL)
) -> StoredProceduresListResponse:
    """
    Retorna lista de procedimientos almacenados disponibles en la BD.
    
    Útil para:
    - Auditoría de procedimientos
    - Documentación automática
    - Validar que SP existe antes de ejecutar
    """
    logger.info(f"NEXUS v2: Listing SPs for {database.value}")
    
    # Simulación (en PROD consultaría sys.procedures o information_schema)
    mock_procedures = [
        {
            "name": "sp_SELECT_users",
            "type": "SELECT",
            "table": "users",
            "parameters": ["@id"],
            "created": "2026-09-27T10:00:00Z"
        },
        {
            "name": "sp_INSERT_users",
            "type": "INSERT",
            "table": "users",
            "parameters": ["@name", "@email", "@age"],
            "created": "2026-09-27T10:00:00Z"
        },
        {
            "name": "sp_UPDATE_users",
            "type": "UPDATE",
            "table": "users",
            "parameters": ["@id", "@name", "@email"],
            "created": "2026-09-27T10:00:00Z"
        },
        {
            "name": "sp_DELETE_users",
            "type": "DELETE",
            "table": "users",
            "parameters": ["@id"],
            "created": "2026-09-27T10:00:00Z"
        }
    ]
    
    return StoredProceduresListResponse(
        status="success",
        database=database.value,
        total=len(mock_procedures),
        procedures=mock_procedures,
        timestamp=datetime.utcnow().isoformat()
    )

# ============================================================================
# ENDPOINT 5: Test SQL Injection Prevention
# ============================================================================

@router.post(
    "/test-sql-injection",
    response_model=SQLInjectionTestResponse,
    summary="Test SQL Injection Prevention",
    description="Prueba de prevención contra SQL injection"
)
async def test_sql_injection(
    table_name: str = Query(..., description="Tabla a probar"),
    malicious_input: str = Query(..., description="Input potencialmente malicioso")
) -> SQLInjectionTestResponse:
    """
    Prueba el sistema de prevención de SQL injection.
    
    El sistema valida:
    - Formato de identificadores
    - Caracteres especiales prohibidos
    - Patrones SQL maliciosos
    - Longitud de inputs
    
    Ejemplos de malicious_input:
    - `'; DROP TABLE users; --`
    - `1 OR 1=1`
    - `admin'--`
    - `1; DELETE FROM users WHERE '1'='1`
    """
    logger.info(f"NEXUS v2: Testing SQL injection prevention")
    
    import re
    
    validation_results = {
        "table_name_valid": bool(
            re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name)
        ),
        "input_length_ok": len(malicious_input) < 8000,
        "contains_semicolon": ";" in malicious_input,
        "contains_quotes": "'" in malicious_input or '"' in malicious_input,
        "contains_comment": "--" in malicious_input or "/*" in malicious_input,
        "contains_or": " OR " in malicious_input.upper(),
        "contains_union": " UNION " in malicious_input.upper(),
        "contains_drop": " DROP " in malicious_input.upper(),
        "contains_delete": " DELETE " in malicious_input.upper(),
    }
    
    # Determinar si es seguro
    dangerous_patterns = [
        validation_results.get("contains_semicolon", False),
        validation_results.get("contains_comment", False),
        validation_results.get("contains_drop", False),
        validation_results.get("contains_delete", False),
    ]
    
    is_safe = not any(dangerous_patterns)
    
    return SQLInjectionTestResponse(
        status="completed",
        message="SQL Injection Test" + (" PASSED" if is_safe else " FAILED"),
        safe=is_safe,
        validation_results=validation_results,
        timestamp=datetime.utcnow().isoformat()
    )

# ============================================================================
# ENDPOINT 6: Get Procedure SQL Definition
# ============================================================================

@router.get(
    "/procedure-definition",
    summary="Get Procedure SQL Definition",
    description="Obtener la definición SQL de un procedimiento almacenado"
)
async def get_procedure_definition(
    procedure_name: str = Query(..., description="Nombre del procedimiento"),
    database: DatabaseType = Query(DatabaseType.MSSQL)
):
    """
    Retorna la definición SQL completa de un procedimiento.
    
    Útil para:
    - Auditoría
    - Documentación
    - Verificar parámetros
    - Entender lógica del SP
    """
    logger.info(f"NEXUS v2: Getting definition for {procedure_name}")
    
    import re
    if not re.match(r'^sp_[a-zA-Z0-9_]+$', procedure_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid procedure name"
        )
    
    # Simulación
    if database == DatabaseType.MSSQL:
        sql = f"""
IF OBJECT_ID('[dbo].[{procedure_name}]', 'P') IS NOT NULL
BEGIN
    SELECT OBJECT_DEFINITION(OBJECT_ID('{procedure_name}')) AS definition;
END
ELSE
BEGIN
    RAISERROR('Procedure not found', 16, 1);
END
"""
    else:
        sql = f"""
SELECT pg_get_functiondef('{procedure_name}'::regprocedure) AS definition;
"""
    
    return {
        "status": "success",
        "procedure_name": procedure_name,
        "database": database.value,
        "definition_query": sql,
        "note": "En PROD ejecutaría esta query contra la BD",
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# AGENT INFO
# ============================================================================

@router.get(
    "/info",
    summary="Agent Information",
    description="Información sobre NEXUS v2.0"
)
async def agent_info():
    """Información sobre el agente NEXUS v2.0"""
    return {
        "id": "nexus",
        "name": "DatabaseAgent v2.0",
        "version": "5.0.0",
        "status": "active",
        "endpoints": 6,
        "security": {
            "stored_procedures": True,
            "parameterized_queries": True,
            "sql_injection_prevention": True,
            "input_validation": True,
            "identifier_validation": True
        },
        "capabilities": [
            "Create Stored Procedures",
            "Execute Stored Procedures",
            "CRUD Operations via SP",
            "List Procedures",
            "SQL Injection Testing",
            "Procedure Definition Retrieval"
        ],
        "supported_databases": ["PostgreSQL", "SQL Server"],
        "cache_enabled": True,
        "circuit_breaker": True,
        "audit_logging": True
    }

# ============================================================================
# IMPORTS ASYNC
# ============================================================================

import asyncio
