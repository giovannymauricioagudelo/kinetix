"""
src/utils/stored_procedures_manager.py
StoredProcedureManager - Gestor empresarial de procedimientos almacenados
Prevención de SQL injection, validación de parámetros, CRUD seguro
"""

import logging
import re
from typing import Optional, Dict, List, Any, Tuple
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ============================================================================
# ENUMS
# ============================================================================

class DataType(str, Enum):
    """Tipos de datos SQL soportados"""
    INT = "INT"
    BIGINT = "BIGINT"
    VARCHAR = "VARCHAR"
    NVARCHAR = "NVARCHAR"
    DATETIME = "DATETIME"
    DATETIME2 = "DATETIME2"
    DECIMAL = "DECIMAL"
    BIT = "BIT"
    TEXT = "TEXT"
    UUID = "UNIQUEIDENTIFIER"

class ParameterType(str, Enum):
    """Tipo de parámetro del procedimiento"""
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    RETURN = "RETURN"

class SQLDialect(str, Enum):
    """Dialecto SQL soportado"""
    MSSQL = "mssql"
    POSTGRESQL = "postgresql"

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class StoredProcedureParameter:
    """Definición de parámetro de procedimiento almacenado"""
    name: str
    data_type: DataType
    param_type: ParameterType = ParameterType.INPUT
    size: Optional[int] = None
    required: bool = True
    
    def to_sql_mssql(self) -> str:
        """Genera SQL de declaración del parámetro para SQL Server"""
        type_def = self.data_type.value
        if self.size and self.data_type in [DataType.VARCHAR, DataType.NVARCHAR]:
            type_def += f"({self.size})"
        
        direction = self.param_type.value
        
        if direction == "OUTPUT":
            return f"    @{self.name} {type_def} OUTPUT"
        elif direction == "RETURN":
            return f"    @{self.name} {type_def} OUTPUT"
        else:
            return f"    @{self.name} {type_def}"
    
    def to_sql_postgresql(self) -> str:
        """Genera SQL de declaración del parámetro para PostgreSQL"""
        type_map = {
            DataType.INT: "INTEGER",
            DataType.BIGINT: "BIGINT",
            DataType.VARCHAR: "VARCHAR",
            DataType.NVARCHAR: "VARCHAR",
            DataType.DATETIME: "TIMESTAMP",
            DataType.DATETIME2: "TIMESTAMP",
            DataType.DECIMAL: "DECIMAL",
            DataType.BIT: "BOOLEAN",
            DataType.TEXT: "TEXT",
            DataType.UUID: "UUID",
        }
        
        pg_type = type_map.get(self.data_type, "VARCHAR")
        
        if self.size and self.data_type in [DataType.VARCHAR, DataType.NVARCHAR]:
            pg_type += f"({self.size})"
        
        direction_map = {
            ParameterType.INPUT: "IN",
            ParameterType.OUTPUT: "OUT",
            ParameterType.RETURN: "INOUT"
        }
        direction = direction_map.get(self.param_type, "IN")
        
        return f"    {self.name} {direction} {pg_type}"

@dataclass
class StoredProcedure:
    """Definición de procedimiento almacenado"""
    name: str
    description: str
    parameters: List[StoredProcedureParameter]
    body: str
    dialect: SQLDialect = SQLDialect.MSSQL
    
    def validate(self) -> Tuple[bool, str]:
        """Valida que el procedimiento sea válido"""
        # Validar nombre
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', self.name):
            return False, f"Invalid procedure name: {self.name}"
        
        # Validar parámetros
        param_names = set()
        for param in self.parameters:
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', param.name):
                return False, f"Invalid parameter name: {param.name}"
            
            if param.name in param_names:
                return False, f"Duplicate parameter: {param.name}"
            
            param_names.add(param.name)
        
        return True, ""
    
    def generate_mssql(self) -> str:
        """Genera SQL para crear procedimiento en SQL Server"""
        valid, error = self.validate()
        if not valid:
            raise ValueError(error)
        
        params_sql = ""
        if self.parameters:
            params = [p.to_sql_mssql() for p in self.parameters]
            params_sql = ",\n".join(params)
        
        sql = f"""
IF OBJECT_ID('[dbo].[{self.name}]', 'P') IS NOT NULL
    DROP PROCEDURE [dbo].[{self.name}];
GO

CREATE PROCEDURE [dbo].[{self.name}]
{params_sql}
AS
BEGIN
    SET NOCOUNT ON;
    
{self.body}
    
END;
GO
"""
        return sql
    
    def generate_postgresql(self) -> str:
        """Genera SQL para crear procedimiento en PostgreSQL (function)"""
        valid, error = self.validate()
        if not valid:
            raise ValueError(error)
        
        params_sql = ""
        if self.parameters:
            params = [p.to_sql_postgresql() for p in self.parameters]
            params_sql = ", ".join(params)
        
        sql = f"""
DROP FUNCTION IF EXISTS {self.name}({params_sql});

CREATE OR REPLACE FUNCTION {self.name}(
{params_sql}
) RETURNS TABLE AS $$
BEGIN
{self.body}
END;
$$ LANGUAGE plpgsql;
"""
        return sql

# ============================================================================
# STORED PROCEDURE MANAGER
# ============================================================================

class StoredProcedureManager:
    """Gestor empresarial de procedimientos almacenados"""
    
    def __init__(self, dialect: SQLDialect = SQLDialect.MSSQL):
        self.dialect = dialect
        self.procedures: Dict[str, StoredProcedure] = {}
    
    # ========================================================================
    # CRUD PROCEDURE GENERATORS
    # ========================================================================
    
    def create_select_procedure(
        self,
        table_name: str,
        id_column: str,
        columns: Optional[List[str]] = None,
        where_clause: Optional[str] = None
    ) -> StoredProcedure:
        """
        Crea procedimiento SELECT seguro
        
        Args:
            table_name: Nombre de la tabla
            id_column: Nombre de la columna ID
            columns: Columnas a seleccionar (None = todas)
            where_clause: Cláusula WHERE adicional
        """
        if columns is None:
            columns = ["*"]
        
        self._validate_identifier(table_name)
        self._validate_identifier(id_column)
        for col in columns:
            if col != "*":
                self._validate_identifier(col)
        
        columns_sql = ", ".join(columns)
        
        # Construir cuerpo del procedimiento
        if where_clause:
            body = f"    SELECT {columns_sql}\n    FROM [{table_name}]\n    WHERE {where_clause};"
            param = StoredProcedureParameter(
                name=id_column,
                data_type=DataType.INT,
                param_type=ParameterType.INPUT,
                required=True
            )
        else:
            body = f"    SELECT {columns_sql}\n    FROM [{table_name}];"
            param = None
        
        params = [param] if param else []
        
        sp = StoredProcedure(
            name=f"sp_Select_{table_name}",
            description=f"Selecciona datos de {table_name}",
            parameters=params,
            body=body,
            dialect=self.dialect
        )
        
        self.procedures[sp.name] = sp
        return sp
    
    def create_insert_procedure(
        self,
        table_name: str,
        columns_types: Dict[str, DataType]
    ) -> StoredProcedure:
        """
        Crea procedimiento INSERT seguro
        
        Args:
            table_name: Nombre de la tabla
            columns_types: Dict de {nombre_columna: tipo_datos}
        """
        self._validate_identifier(table_name)
        
        # Validar columnas
        for col in columns_types.keys():
            self._validate_identifier(col)
        
        # Crear parámetros
        parameters = [
            StoredProcedureParameter(
                name=col,
                data_type=data_type,
                param_type=ParameterType.INPUT,
                required=True
            )
            for col, data_type in columns_types.items()
        ]
        
        # Construir SQL
        columns_list = ", ".join([f"[{col}]" for col in columns_types.keys()])
        values_list = ", ".join([f"@{col}" for col in columns_types.keys()])
        
        body = f"""    INSERT INTO [{table_name}] ({columns_list})
    VALUES ({values_list});
    SELECT SCOPE_IDENTITY() AS id;"""
        
        sp = StoredProcedure(
            name=f"sp_Insert_{table_name}",
            description=f"Inserta registro en {table_name}",
            parameters=parameters,
            body=body,
            dialect=self.dialect
        )
        
        self.procedures[sp.name] = sp
        return sp
    
    def create_update_procedure(
        self,
        table_name: str,
        id_column: str,
        columns_types: Dict[str, DataType]
    ) -> StoredProcedure:
        """
        Crea procedimiento UPDATE seguro
        
        Args:
            table_name: Nombre de la tabla
            id_column: Nombre de la columna ID (clave primaria)
            columns_types: Dict de columnas a actualizar
        """
        self._validate_identifier(table_name)
        self._validate_identifier(id_column)
        
        for col in columns_types.keys():
            self._validate_identifier(col)
        
        # Crear parámetros (ID + columnas)
        parameters = [
            StoredProcedureParameter(
                name=id_column,
                data_type=DataType.INT,
                param_type=ParameterType.INPUT,
                required=True
            )
        ]
        
        parameters.extend([
            StoredProcedureParameter(
                name=col,
                data_type=data_type,
                param_type=ParameterType.INPUT,
                required=True
            )
            for col, data_type in columns_types.items()
        ])
        
        # Construir SQL
        set_clause = ", ".join([f"[{col}] = @{col}" for col in columns_types.keys()])
        
        body = f"""    UPDATE [{table_name}]
    SET {set_clause}
    WHERE [{id_column}] = @{id_column};
    SELECT @@ROWCOUNT AS affected_rows;"""
        
        sp = StoredProcedure(
            name=f"sp_Update_{table_name}",
            description=f"Actualiza registro en {table_name}",
            parameters=parameters,
            body=body,
            dialect=self.dialect
        )
        
        self.procedures[sp.name] = sp
        return sp
    
    def create_delete_procedure(
        self,
        table_name: str,
        id_column: str
    ) -> StoredProcedure:
        """
        Crea procedimiento DELETE seguro
        
        Args:
            table_name: Nombre de la tabla
            id_column: Nombre de la columna ID
        """
        self._validate_identifier(table_name)
        self._validate_identifier(id_column)
        
        parameters = [
            StoredProcedureParameter(
                name=id_column,
                data_type=DataType.INT,
                param_type=ParameterType.INPUT,
                required=True
            )
        ]
        
        body = f"""    DELETE FROM [{table_name}]
    WHERE [{id_column}] = @{id_column};
    SELECT @@ROWCOUNT AS affected_rows;"""
        
        sp = StoredProcedure(
            name=f"sp_Delete_{table_name}",
            description=f"Elimina registro de {table_name}",
            parameters=parameters,
            body=body,
            dialect=self.dialect
        )
        
        self.procedures[sp.name] = sp
        return sp
    
    # ========================================================================
    # VALIDACIÓN Y SEGURIDAD
    # ========================================================================
    
    def _validate_identifier(self, identifier: str) -> None:
        """
        Valida que un identificador sea seguro (previene SQL injection)
        
        Raises:
            ValueError si el identificador no es válido
        """
        if not identifier or len(identifier) > 128:
            raise ValueError(f"Invalid identifier: {identifier}")
        
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
            raise ValueError(f"Invalid identifier format: {identifier}")
    
    def validate_parameter_value(
        self,
        value: Any,
        param_type: DataType
    ) -> Tuple[bool, str]:
        """
        Valida que un valor sea seguro para el tipo de dato
        """
        if value is None:
            return True, ""
        
        # Validación por tipo
        if param_type == DataType.INT:
            try:
                int(value)
                return True, ""
            except (ValueError, TypeError):
                return False, f"Invalid INT value: {value}"
        
        elif param_type in [DataType.VARCHAR, DataType.NVARCHAR]:
            if isinstance(value, str) and len(value) > 8000:
                return False, f"String too long: {len(value)} > 8000"
            return True, ""
        
        elif param_type == DataType.DATETIME:
            try:
                from datetime import datetime
                if isinstance(value, str):
                    datetime.fromisoformat(value)
                return True, ""
            except:
                return False, f"Invalid DATETIME value: {value}"
        
        return True, ""
    
    # ========================================================================
    # UTILIDADES
    # ========================================================================
    
    def get_procedure(self, name: str) -> Optional[StoredProcedure]:
        """Obtiene un procedimiento almacenado por nombre"""
        return self.procedures.get(name)
    
    def list_procedures(self) -> List[str]:
        """Lista todos los procedimientos definidos"""
        return list(self.procedures.keys())
    
    def get_create_sql(self, procedure_name: str) -> str:
        """Obtiene el SQL para crear un procedimiento"""
        sp = self.procedures.get(procedure_name)
        if not sp:
            raise ValueError(f"Procedure not found: {procedure_name}")
        
        if self.dialect == SQLDialect.MSSQL:
            return sp.generate_mssql()
        else:
            return sp.generate_postgresql()
    
    def get_execution_sql(
        self,
        procedure_name: str,
        parameters: Dict[str, Any]
    ) -> str:
        """
        Genera SQL seguro para ejecutar un procedimiento con parámetros
        """
        sp = self.procedures.get(procedure_name)
        if not sp:
            raise ValueError(f"Procedure not found: {procedure_name}")
        
        # Validar parámetros
        for param in sp.parameters:
            if param.name not in parameters and param.required:
                raise ValueError(f"Missing required parameter: {param.name}")
            
            if param.name in parameters:
                valid, error = self.validate_parameter_value(
                    parameters[param.name],
                    param.data_type
                )
                if not valid:
                    raise ValueError(error)
        
        # Generar SQL de ejecución
        if self.dialect == SQLDialect.MSSQL:
            param_sql = ", ".join([
                f"@{param.name}=@{param.name}"
                for param in sp.parameters
            ])
            return f"EXEC [dbo].[{procedure_name}] {param_sql};"
        else:
            param_sql = ", ".join([
                f"@{param.name}:=@{param.name}"
                for param in sp.parameters
            ])
            return f"SELECT * FROM {procedure_name}({param_sql});"

# ============================================================================
# PRE-DEFINED PROCEDURES FOR COMMON OPERATIONS
# ============================================================================

class CommonStoredProcedures:
    """Procedimientos almacenados comunes reutilizables"""
    
    @staticmethod
    def create_pagination_procedure(
        table_name: str,
        order_by_column: str
    ) -> StoredProcedure:
        """Crea procedimiento con paginación segura"""
        
        parameters = [
            StoredProcedureParameter(
                name="pageNumber",
                data_type=DataType.INT,
                param_type=ParameterType.INPUT,
                required=True
            ),
            StoredProcedureParameter(
                name="pageSize",
                data_type=DataType.INT,
                data_type=DataType.INT,
                param_type=ParameterType.INPUT,
                required=True
            )
        ]
        
        body = f"""    DECLARE @offset INT = (@pageNumber - 1) * @pageSize;
    SELECT *
    FROM [{table_name}]
    ORDER BY [{order_by_column}]
    OFFSET @offset ROWS
    FETCH NEXT @pageSize ROWS ONLY;"""
        
        return StoredProcedure(
            name=f"sp_Paginate_{table_name}",
            description=f"Paginación segura en {table_name}",
            parameters=parameters,
            body=body
        )
    
    @staticmethod
    def create_search_procedure(
        table_name: str,
        search_columns: List[str]
    ) -> StoredProcedure:
        """Crea procedimiento de búsqueda segura"""
        
        # Validar columnas
        for col in search_columns:
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col):
                raise ValueError(f"Invalid column: {col}")
        
        where_clauses = [f"[{col}] LIKE CONCAT('%', @searchTerm, '%')" 
                        for col in search_columns]
        where_sql = " OR ".join(where_clauses)
        
        parameters = [
            StoredProcedureParameter(
                name="searchTerm",
                data_type=DataType.NVARCHAR,
                size=500,
                param_type=ParameterType.INPUT,
                required=True
            )
        ]
        
        body = f"""    SELECT *
    FROM [{table_name}]
    WHERE {where_sql};"""
        
        return StoredProcedure(
            name=f"sp_Search_{table_name}",
            description=f"Búsqueda segura en {table_name}",
            parameters=parameters,
            body=body
        )
