"""
Unit tests for APIs Agent
Tests: Endpoint Generator, Schema Validator, OpenAPI Spec Generator
Cobertura: CRUD generation, validation, schema compatibility, OpenAPI spec
"""

import pytest
import asyncio
from datetime import datetime
from typing import Dict, List, Any

from agents.apis_agent.agent import (
    APIsAgent,
    APIEndpointInput,
    APIEndpointOutput,
    APIEndpoint,
    HTTPMethod,
    OperationType,
    PathParameter,
    QueryParameter,
    RequestBody,
    ResponseSchema,
    EndpointGenerator,
    SchemaValidator,
    OpenAPISpecGenerator,
    AgentStatus,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_table_columns() -> Dict[str, str]:
    """Columnas de tabla de ejemplo"""
    return {
        "cliente_id": "bigint",
        "empresa_id": "int",
        "bodega_id": "int",
        "nombre": "varchar",
        "email": "varchar",
        "estado": "boolean",
        "fecha_creacion": "timestamp",
        "saldo": "decimal"
    }


@pytest.fixture
def sample_api_input(sample_table_columns) -> APIEndpointInput:
    """Input de ejemplo para APIsAgent"""
    return APIEndpointInput(
        request_id="test_apis_001",
        table_name="clientes",
        table_columns=sample_table_columns,
        primary_key="cliente_id",
        description="Table de clientes"
    )


@pytest.fixture
def apis_agent() -> APIsAgent:
    """Instancia del APIsAgent"""
    return APIsAgent()


# ============================================================================
# TEST: ENDPOINT GENERATOR
# ============================================================================

class TestEndpointGenerator:
    """Tests para el generador de endpoints CRUD"""
    
    def test_generator_initialization(self, sample_table_columns):
        """Test: Inicialización del generador"""
        generator = EndpointGenerator(
            table_name="clientes",
            primary_key="cliente_id",
            columns=sample_table_columns
        )
        
        assert generator.table_name == "clientes"
        assert generator.primary_key == "cliente_id"
        assert len(generator.columns) == 8
    
    def test_generate_crud_endpoints_count(self, sample_table_columns):
        """Test: Genera exactamente 5 endpoints CRUD"""
        generator = EndpointGenerator(
            table_name="clientes",
            primary_key="cliente_id",
            columns=sample_table_columns
        )
        
        endpoints = generator.generate_crud_endpoints()
        
        assert len(endpoints) == 5
        assert len(generator.endpoints) == 5
    
    def test_generate_crud_endpoints_types(self, sample_table_columns):
        """Test: Tipos de operación CRUD correctos"""
        generator = EndpointGenerator(
            table_name="clientes",
            primary_key="cliente_id",
            columns=sample_table_columns
        )
        
        endpoints = generator.generate_crud_endpoints()
        operation_types = [ep.operation_type for ep in endpoints]
        
        assert OperationType.CREATE in operation_types
        assert OperationType.READ in operation_types
        assert OperationType.LIST in operation_types
        assert OperationType.UPDATE in operation_types
        assert OperationType.DELETE in operation_types
    
    def test_generate_create_endpoint(self, sample_table_columns):
        """Test: Endpoint CREATE tiene request body"""
        generator = EndpointGenerator(
            table_name="clientes",
            primary_key="cliente_id",
            columns=sample_table_columns
        )
        
        endpoints = generator.generate_crud_endpoints()
        create_ep = [ep for ep in endpoints if ep.operation_type == OperationType.CREATE][0]
        
        assert create_ep.method == HTTPMethod.POST
        assert create_ep.request_body is not None
        assert "cliente_id" not in create_ep.request_body.fields  # PK no en crear
        assert "nombre" in create_ep.request_body.fields
    
    def test_generate_read_endpoint(self, sample_table_columns):
        """Test: Endpoint READ tiene path parameter"""
        generator = EndpointGenerator(
            table_name="clientes",
            primary_key="cliente_id",
            columns=sample_table_columns
        )
        
        endpoints = generator.generate_crud_endpoints()
        read_ep = [ep for ep in endpoints if ep.operation_type == OperationType.READ][0]
        
        assert read_ep.method == HTTPMethod.GET
        assert len(read_ep.path_parameters) == 1
        assert read_ep.path_parameters[0].name == "id"
        assert "{id}" in read_ep.path
    
    def test_generate_list_endpoint_query_params(self, sample_table_columns):
        """Test: Endpoint LIST tiene query parameters de paginación"""
        generator = EndpointGenerator(
            table_name="clientes",
            primary_key="cliente_id",
            columns=sample_table_columns
        )
        
        endpoints = generator.generate_crud_endpoints()
        list_ep = [ep for ep in endpoints if ep.operation_type == OperationType.LIST][0]
        
        assert list_ep.method == HTTPMethod.GET
        query_names = [qp.name for qp in list_ep.query_parameters]
        assert "page" in query_names
        assert "page_size" in query_names
        assert "sort_by" in query_names
    
    def test_generate_update_endpoint(self, sample_table_columns):
        """Test: Endpoint UPDATE tiene path parameter y request body"""
        generator = EndpointGenerator(
            table_name="clientes",
            primary_key="cliente_id",
            columns=sample_table_columns
        )
        
        endpoints = generator.generate_crud_endpoints()
        update_ep = [ep for ep in endpoints if ep.operation_type == OperationType.UPDATE][0]
        
        assert update_ep.method == HTTPMethod.PUT
        assert len(update_ep.path_parameters) == 1
        assert update_ep.request_body is not None
    
    def test_generate_delete_endpoint(self, sample_table_columns):
        """Test: Endpoint DELETE tiene solo path parameter"""
        generator = EndpointGenerator(
            table_name="clientes",
            primary_key="cliente_id",
            columns=sample_table_columns
        )
        
        endpoints = generator.generate_crud_endpoints()
        delete_ep = [ep for ep in endpoints if ep.operation_type == OperationType.DELETE][0]
        
        assert delete_ep.method == HTTPMethod.DELETE
        assert len(delete_ep.path_parameters) == 1
        assert delete_ep.request_body is None
    
    def test_endpoint_paths_are_correct(self, sample_table_columns):
        """Test: Rutas de endpoints son correctas"""
        generator = EndpointGenerator(
            table_name="clientes",
            primary_key="cliente_id",
            columns=sample_table_columns
        )
        
        endpoints = generator.generate_crud_endpoints()
        
        paths = {ep.operation_type: ep.path for ep in endpoints}
        
        assert paths[OperationType.CREATE] == "/api/v1/clientes"
        assert paths[OperationType.READ] == "/api/v1/clientes/{id}"
        assert paths[OperationType.LIST] == "/api/v1/clientes"
        assert paths[OperationType.UPDATE] == "/api/v1/clientes/{id}"
        assert paths[OperationType.DELETE] == "/api/v1/clientes/{id}"
    
    def test_endpoint_responses_defined(self, sample_table_columns):
        """Test: Todos los endpoints tienen respuestas definidas"""
        generator = EndpointGenerator(
            table_name="clientes",
            primary_key="cliente_id",
            columns=sample_table_columns
        )
        
        endpoints = generator.generate_crud_endpoints()
        
        for endpoint in endpoints:
            assert len(endpoint.responses) > 0
            status_codes = [r.status_code for r in endpoint.responses]
            assert any(status in status_codes for status in [200, 201, 204, 400, 404])
    
    def test_generate_example_with_different_types(self, sample_table_columns):
        """Test: Generador de ejemplos maneja diferentes tipos"""
        generator = EndpointGenerator(
            table_name="clientes",
            primary_key="cliente_id",
            columns=sample_table_columns
        )
        
        example = generator._generate_example(sample_table_columns)
        
        assert isinstance(example["cliente_id"], int)
        assert isinstance(example["nombre"], str)
        assert isinstance(example["estado"], bool)
        assert isinstance(example["saldo"], (int, float))


# ============================================================================
# TEST: SCHEMA VALIDATOR
# ============================================================================

class TestSchemaValidator:
    """Tests para el validador de esquemas"""
    
    def test_validator_initialization(self, sample_table_columns):
        """Test: Inicialización del validador"""
        validator = SchemaValidator(sample_table_columns)
        
        assert validator.columns == sample_table_columns
        assert len(validator.errors) == 0
    
    def test_validate_valid_column_types(self, sample_table_columns):
        """Test: Valida tipos de columna válidos"""
        validator = SchemaValidator(sample_table_columns)
        
        is_valid = validator.validate_column_types()
        
        assert is_valid is True
        assert len(validator.errors) == 0
    
    def test_validate_invalid_column_type(self):
        """Test: Detecta tipos de columna inválidos"""
        invalid_columns = {
            "id": "bigint",
            "name": "unknowntype"
        }
        
        validator = SchemaValidator(invalid_columns)
        is_valid = validator.validate_column_types()
        
        assert is_valid is False
        assert len(validator.errors) > 0
    
    def test_validate_request_with_required_fields(self, sample_table_columns):
        """Test: Valida request con campos requeridos"""
        validator = SchemaValidator(sample_table_columns)
        
        request_data = {
            "nombre": "Juan",
            "email": "juan@example.com",
            "estado": True
        }
        required_fields = ["nombre", "email"]
        
        is_valid, errors = validator.validate_request(request_data, required_fields)
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_validate_request_missing_required_field(self, sample_table_columns):
        """Test: Detecta campos requeridos faltantes"""
        validator = SchemaValidator(sample_table_columns)
        
        request_data = {
            "email": "juan@example.com"
        }
        required_fields = ["nombre", "email"]
        
        is_valid, errors = validator.validate_request(request_data, required_fields)
        
        assert is_valid is False
        assert any("nombre" in error for error in errors)
    
    def test_validate_request_unknown_field(self, sample_table_columns):
        """Test: Detecta campos desconocidos"""
        validator = SchemaValidator(sample_table_columns)
        
        request_data = {
            "nombre": "Juan",
            "campo_inexistente": "valor"
        }
        required_fields = ["nombre"]
        
        is_valid, errors = validator.validate_request(request_data, required_fields)
        
        assert is_valid is False
        assert any("campo_inexistente" in error for error in errors)
    
    def test_validate_request_wrong_type(self, sample_table_columns):
        """Test: Detecta tipos de datos incorrectos"""
        validator = SchemaValidator(sample_table_columns)
        
        request_data = {
            "cliente_id": "not_an_int",  # Debería ser int
            "nombre": "Juan"
        }
        required_fields = ["nombre"]
        
        is_valid, errors = validator.validate_request(request_data, required_fields)
        
        assert is_valid is False
        assert any("cliente_id" in error for error in errors)
    
    def test_validate_request_null_values_accepted(self, sample_table_columns):
        """Test: Acepta valores null/None"""
        validator = SchemaValidator(sample_table_columns)
        
        request_data = {
            "nombre": "Juan",
            "email": None
        }
        required_fields = ["nombre"]
        
        is_valid, errors = validator.validate_request(request_data, required_fields)
        
        assert is_valid is True


# ============================================================================
# TEST: OPENAPI SPEC GENERATOR
# ============================================================================

class TestOpenAPISpecGenerator:
    """Tests para el generador de especificación OpenAPI"""
    
    def test_openapi_generator_initialization(self):
        """Test: Inicialización del generador OpenAPI"""
        generator = OpenAPISpecGenerator(title="Clientes API", version="1.0.0")
        
        assert generator.title == "Clientes API"
        assert generator.version == "1.0.0"
    
    def test_generate_openapi_spec_structure(self, sample_table_columns):
        """Test: Especificación OpenAPI tiene estructura correcta"""
        gen = EndpointGenerator("clientes", "cliente_id", sample_table_columns)
        endpoints = gen.generate_crud_endpoints()
        
        openapi_gen = OpenAPISpecGenerator(title="Clientes API")
        spec = openapi_gen.generate_spec(endpoints)
        
        assert spec["openapi"] == "3.0.0"
        assert "info" in spec
        assert "paths" in spec
        assert "components" in spec
        assert spec["info"]["title"] == "Clientes API"
    
    def test_generate_openapi_paths(self, sample_table_columns):
        """Test: OpenAPI paths tienen endpoints correctos"""
        gen = EndpointGenerator("clientes", "cliente_id", sample_table_columns)
        endpoints = gen.generate_crud_endpoints()
        
        openapi_gen = OpenAPISpecGenerator(title="Clientes API")
        spec = openapi_gen.generate_spec(endpoints)
        
        paths = spec["paths"]
        assert "/api/v1/clientes" in paths
        assert "/api/v1/clientes/{id}" in paths
    
    def test_openapi_paths_have_methods(self, sample_table_columns):
        """Test: Paths de OpenAPI tienen métodos HTTP correctos"""
        gen = EndpointGenerator("clientes", "cliente_id", sample_table_columns)
        endpoints = gen.generate_crud_endpoints()
        
        openapi_gen = OpenAPISpecGenerator(title="Clientes API")
        spec = openapi_gen.generate_spec(endpoints)
        
        paths = spec["paths"]
        
        # Path /clientes
        assert "post" in paths["/api/v1/clientes"]
        assert "get" in paths["/api/v1/clientes"]
        
        # Path /clientes/{id}
        assert "get" in paths["/api/v1/clientes/{id}"]
        assert "put" in paths["/api/v1/clientes/{id}"]
        assert "delete" in paths["/api/v1/clientes/{id}"]
    
    def test_openapi_operation_has_summary(self, sample_table_columns):
        """Test: Operaciones OpenAPI tienen summary"""
        gen = EndpointGenerator("clientes", "cliente_id", sample_table_columns)
        endpoints = gen.generate_crud_endpoints()
        
        openapi_gen = OpenAPISpecGenerator(title="Clientes API")
        spec = openapi_gen.generate_spec(endpoints)
        
        create_op = spec["paths"]["/api/v1/clientes"]["post"]
        assert "summary" in create_op
        assert "description" in create_op


# ============================================================================
# TEST: APIS AGENT
# ============================================================================

class TestAPIsAgent:
    """Tests para el APIsAgent principal"""
    
    def test_agent_initialization(self):
        """Test: Inicialización del agente"""
        agent = APIsAgent()
        
        assert agent.agent_name == "APIsAgent"
        assert agent.version == "1.0.0"
    
    @pytest.mark.asyncio
    async def test_agent_execute_success(self, apis_agent, sample_api_input):
        """Test: Ejecución exitosa del agente"""
        output = await apis_agent.execute(sample_api_input)
        
        assert output.request_id == sample_api_input.request_id
        assert output.status == AgentStatus.COMPLETED
        assert output.endpoints_generated == 5
        assert len(output.endpoints) == 5
        assert output.error is None
    
    @pytest.mark.asyncio
    async def test_agent_output_has_openapi_spec(self, apis_agent, sample_api_input):
        """Test: Output incluye especificación OpenAPI"""
        output = await apis_agent.execute(sample_api_input)
        
        assert output.openapi_spec is not None
        assert "openapi" in output.openapi_spec
        assert "paths" in output.openapi_spec
        assert "info" in output.openapi_spec
    
    @pytest.mark.asyncio
    async def test_agent_validate_input_missing_request_id(self):
        """Test: Detecta request_id faltante"""
        agent = APIsAgent()
        
        input_data = APIEndpointInput(
            request_id="",
            table_name="clientes",
            table_columns={"id": "int"},
            primary_key="id"
        )
        
        is_valid, errors = agent.validate_input(input_data)
        
        assert is_valid is False
        assert any("request_id" in error for error in errors)
    
    @pytest.mark.asyncio
    async def test_agent_validate_input_missing_table_name(self):
        """Test: Detecta table_name faltante"""
        agent = APIsAgent()
        
        input_data = APIEndpointInput(
            request_id="test_001",
            table_name="",
            table_columns={"id": "int"},
            primary_key="id"
        )
        
        is_valid, errors = agent.validate_input(input_data)
        
        assert is_valid is False
        assert any("table_name" in error for error in errors)
    
    @pytest.mark.asyncio
    async def test_agent_validate_input_primary_key_not_in_columns(self):
        """Test: Detecta PK no en columnas"""
        agent = APIsAgent()
        
        input_data = APIEndpointInput(
            request_id="test_001",
            table_name="clientes",
            table_columns={"name": "varchar"},
            primary_key="id"  # No existe en columnas
        )
        
        is_valid, errors = agent.validate_input(input_data)
        
        assert is_valid is False
        assert any("primary_key" in error for error in errors)
    
    @pytest.mark.asyncio
    async def test_agent_execution_time_tracked(self, apis_agent, sample_api_input):
        """Test: Tiempo de ejecución es registrado"""
        output = await apis_agent.execute(sample_api_input)
        
        assert output.execution_time_ms > 0
        assert output.execution_time_ms < 5000  # Menos de 5 segundos
    
    @pytest.mark.asyncio
    async def test_agent_generates_unique_hash(self, apis_agent, sample_api_input):
        """Test: Genera hash único para endpoints"""
        output = await apis_agent.execute(sample_api_input)
        
        assert "endpoints_hash" in output.data
        assert len(output.data["endpoints_hash"]) == 16
    
    @pytest.mark.asyncio
    async def test_agent_endpoints_have_tags(self, apis_agent, sample_api_input):
        """Test: Endpoints tienen tags para agrupación"""
        output = await apis_agent.execute(sample_api_input)
        
        for endpoint in output.endpoints:
            assert len(endpoint.tags) > 0
            assert "clientes" in endpoint.tags[0]


# ============================================================================
# TEST: INTEGRATION
# ============================================================================

class TestAPIsAgentIntegration:
    """Tests de integración del APIsAgent"""
    
    @pytest.mark.asyncio
    async def test_full_workflow_table_to_endpoints(self):
        """Test: Workflow completo de tabla a endpoints"""
        agent = APIsAgent()
        
        columns = {
            "usuario_id": "bigint",
            "nombre": "varchar",
            "email": "varchar",
            "activo": "boolean"
        }
        
        input_data = APIEndpointInput(
            request_id="test_workflow_001",
            table_name="usuarios",
            table_columns=columns,
            primary_key="usuario_id"
        )
        
        output = await agent.execute(input_data)
        
        # Validar resultado
        assert output.status == AgentStatus.COMPLETED
        assert output.endpoints_generated == 5
        
        # Validar OpenAPI
        assert output.openapi_spec["info"]["title"] == "usuarios API"
        assert "/api/v1/usuarios" in output.openapi_spec["paths"]
    
    @pytest.mark.asyncio
    async def test_multiple_executions_sequential(self, apis_agent):
        """Test: Múltiples ejecuciones secuenciales"""
        inputs = [
            APIEndpointInput(
                request_id=f"test_{i}",
                table_name=f"tabla_{i}",
                table_columns={"id": "int", "name": "varchar"},
                primary_key="id"
            )
            for i in range(3)
        ]
        
        outputs = []
        for input_data in inputs:
            output = await apis_agent.execute(input_data)
            outputs.append(output)
        
        assert len(outputs) == 3
        assert all(o.status == AgentStatus.COMPLETED for o in outputs)
        assert all(o.endpoints_generated == 5 for o in outputs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
