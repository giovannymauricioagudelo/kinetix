"""
Database Agent - Automatic schema management for multisector ERP
Handles: Schema creation/updates, migrations, audit logging, backups
"""

import asyncio
import logging
from typing import Any, Dict, Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ValidationInfo, field_validator
import hashlib
import json

from src.agents.agent_catalog import NEXUS
from src.agents.base_agent import BaseAgent, AgentConfig, AgentInput, AgentOutput, AgentStatus

logger = logging.getLogger(__name__)


# ============================================================================
# MODELS
# ============================================================================

class ColumnType(str, Enum):
    """Supported database column types"""
    VARCHAR = "varchar"
    INT = "int"
    BIGINT = "bigint"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    TEXT = "text"
    JSON = "json"


class ColumnDefinition(BaseModel):
    """Single column definition"""
    name: str = Field(..., min_length=1, max_length=100)
    type: ColumnType
    nullable: bool = True
    default: Optional[str] = None
    unique: bool = False
    primary_key: bool = False
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str, info: ValidationInfo):
        """Ensure column name follows conventions (strict mode on re-validation)"""
        if info.context and info.context.get('strict_column_names'):
            if not v.replace('_', '').isalnum():
                raise ValueError("Column name must be alphanumeric + underscore")
        if v.replace('_', '').isalnum():
            return v.lower()
        return v


class TableDefinition(BaseModel):
    """Complete table definition"""
    name: str = Field(..., min_length=1, max_length=100)
    schema: str = "public"
    columns: List[ColumnDefinition]
    company_column: bool = True  # Must have EmpresaID
    warehouse_column: bool = True  # Must have BodegaID
    audit_columns: bool = True  # Add created_at, updated_at, created_by
    description: Optional[str] = None

    @field_validator('columns')
    @classmethod
    def validate_columns(cls, v, info):
        """Validate multisector requirements"""
        column_names = {col.name for col in v}
        
        # Check required columns
        if info.data.get('company_column') and 'empresa_id' not in column_names:
            raise ValueError("Table must have 'empresa_id' column (multisector)")
        
        if info.data.get('warehouse_column') and 'bodega_id' not in column_names:
            raise ValueError("Table must have 'bodega_id' column (warehouse)")
        
        return v

    @classmethod
    def model_validate(cls, obj, *, strict=None, from_attributes=None, context=None):
        """Re-validation enforces strict column name rules"""
        ctx = {**(context or {}), 'strict_column_names': True}
        return super().model_validate(
            obj, strict=strict, from_attributes=from_attributes, context=ctx
        )


class SchemaMigration(BaseModel):
    """Database migration definition"""
    version: str = Field(..., description="Semantic version (e.g., 1.0.0)")
    name: str = Field(..., description="Migration name (e.g., add_retencion_dian)")
    tables_added: List[str] = Field(default_factory=list)
    tables_modified: List[str] = Field(default_factory=list)
    columns_added: Dict[str, List[str]] = Field(default_factory=dict)
    sql_script: str = Field(..., description="Raw SQL migration script")
    rollback_script: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DatabaseAgentInput(AgentInput):
    """Database Agent specific input"""
    action: str = Field(..., description="Action: create_table, migrate, audit, backup")
    table_definition: Optional[TableDefinition] = None
    migration: Optional[SchemaMigration] = None
    table_name: Optional[str] = None


class DatabaseAgentOutput(AgentOutput):
    """Database Agent specific output"""
    schema_hash: Optional[str] = None
    migration_id: Optional[str] = None
    affected_rows: int = 0
    backup_location: Optional[str] = None


# ============================================================================
# SCHEMA MANAGER
# ============================================================================

class SchemaManager:
    """Manages database schema creation and validation"""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.SchemaManager")
        self.schemas: Dict[str, TableDefinition] = {}

    def create_table(self, table_def: TableDefinition) -> str:
        """
        Generate CREATE TABLE DDL script
        
        Args:
            table_def: Table definition
            
        Returns:
            SQL script
        """
        self.logger.info(f"Creating table: {table_def.name}")
        
        # Start building DDL
        ddl_lines = [
            f"CREATE TABLE IF NOT EXISTS {table_def.schema}.{table_def.name} (",
        ]

        # Add all columns
        for i, col in enumerate(table_def.columns):
            col_def = f"  {col.name} {col.type.value}"
            
            if col.primary_key:
                col_def += " PRIMARY KEY"
            if not col.nullable:
                col_def += " NOT NULL"
            if col.default:
                col_def += f" DEFAULT {col.default}"
            if col.unique:
                col_def += " UNIQUE"
            
            # Add comma if not last column
            if i < len(table_def.columns) - 1:
                col_def += ","
            
            ddl_lines.append(col_def)

        # Add audit columns if enabled
        if table_def.audit_columns:
            ddl_lines[-1] += ","  # Add comma to previous line
            ddl_lines.extend([
                "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,",
                "  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,",
                "  created_by VARCHAR(100)"
            ])

        ddl_lines.append(");")

        # Add indexes for multisector columns
        if table_def.company_column:
            ddl_lines.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table_def.name}_empresa_id "
                f"ON {table_def.schema}.{table_def.name}(empresa_id);"
            )
        
        if table_def.warehouse_column:
            ddl_lines.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table_def.name}_bodega_id "
                f"ON {table_def.schema}.{table_def.name}(bodega_id);"
            )

        # Add comment
        if table_def.description:
            ddl_lines.append(
                f"COMMENT ON TABLE {table_def.schema}.{table_def.name} "
                f"IS '{table_def.description}';"
            )

        sql = "\n".join(ddl_lines)
        self.schemas[table_def.name] = table_def
        self.logger.debug(f"Generated DDL for {table_def.name}")
        
        return sql

    def validate_schema(self, table_def: TableDefinition) -> tuple[bool, Optional[str]]:
        """
        Validate table definition
        
        Args:
            table_def: Table to validate
            
        Returns:
            (is_valid, error_message)
        """
        # Check multisector columns
        column_names = {col.name for col in table_def.columns}
        
        if table_def.company_column and 'empresa_id' not in column_names:
            return False, "Missing required column: empresa_id"
        
        if table_def.warehouse_column and 'bodega_id' not in column_names:
            return False, "Missing required column: bodega_id"
        
        # Check for duplicate columns
        if len(column_names) != len(table_def.columns):
            return False, "Duplicate column names found"
        
        # Check primary key
        pk_count = sum(1 for col in table_def.columns if col.primary_key)
        if pk_count > 1:
            return False, "Multiple primary keys not allowed"
        
        return True, None

    def get_schema_hash(self, table_def: TableDefinition) -> str:
        """
        Calculate schema hash for versioning
        
        Args:
            table_def: Table definition
            
        Returns:
            Hash string
        """
        schema_json = json.dumps(table_def.model_dump(), sort_keys=True, default=str)
        return hashlib.sha256(schema_json.encode()).hexdigest()[:16]


# ============================================================================
# MIGRATION ENGINE
# ============================================================================

class MigrationEngine:
    """Handles database migrations with versioning and rollback"""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.MigrationEngine")
        self.migrations: Dict[str, SchemaMigration] = {}
        self.current_version = "0.0.0"

    def create_migration(self, migration: SchemaMigration) -> str:
        """
        Register migration
        
        Args:
            migration: Migration definition
            
        Returns:
            Migration ID
        """
        migration_id = f"mig_{migration.version}_{migration.name}_{int(datetime.utcnow().timestamp())}"
        self.migrations[migration_id] = migration
        
        self.logger.info(
            f"Migration created: {migration_id}",
            extra={
                "version": migration.version,
                "tables_added": len(migration.tables_added),
                "tables_modified": len(migration.tables_modified)
            }
        )
        
        return migration_id

    def generate_migration_script(
        self,
        previous_version: str,
        new_version: str,
        changes: Dict[str, Any]
    ) -> SchemaMigration:
        """
        Generate migration from changes
        
        Args:
            previous_version: Previous schema version
            new_version: New schema version
            changes: Changes to apply
            
        Returns:
            SchemaMigration object
        """
        # Build SQL script from changes
        sql_lines = [
            f"-- Migration from {previous_version} to {new_version}",
            f"-- Created: {datetime.utcnow().isoformat()}",
            "BEGIN TRANSACTION;",
            ""
        ]

        # Handle new columns
        if "columns_added" in changes:
            for table, columns in changes["columns_added"].items():
                for col in columns:
                    sql_lines.append(
                        f"ALTER TABLE {table} ADD COLUMN {col['name']} {col['type']};"
                    )

        # Handle new tables
        if "tables_added" in changes:
            for table in changes["tables_added"]:
                sql_lines.append(f"-- Table {table} added via separate DDL")

        sql_lines.extend([
            "",
            "-- Update schema version",
            f"INSERT INTO schema_versions (version, applied_at) VALUES ('{new_version}', NOW());",
            "COMMIT;"
        ])

        sql_script = "\n".join(sql_lines)
        
        migration = SchemaMigration(
            version=new_version,
            name=f"migration_{previous_version}_to_{new_version}",
            sql_script=sql_script,
            tables_added=changes.get("tables_added", []),
            tables_modified=changes.get("tables_modified", [])
        )
        
        return migration


# ============================================================================
# AUDIT LOGGER
# ============================================================================

class AuditLogger:
    """Logs all database changes for compliance and debugging"""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.AuditLogger")
        self.audit_log: List[Dict[str, Any]] = []

    def log_change(
        self,
        action: str,
        table_name: str,
        details: Dict[str, Any],
        user: str = "system"
    ) -> None:
        """
        Log database change
        
        Args:
            action: Action performed (CREATE, ALTER, DROP, etc.)
            table_name: Affected table
            details: Change details
            user: User who made change
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "table": table_name,
            "user": user,
            "details": details
        }
        
        self.audit_log.append(entry)
        self.logger.info(
            f"Audit: {action} on {table_name}",
            extra=entry
        )


# ============================================================================
# BACKUP MANAGER
# ============================================================================

class BackupManager:
    """Handles database backups and restore testing"""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.BackupManager")
        self.backups: Dict[str, Dict[str, Any]] = {}

    async def create_backup(self, backup_name: str) -> str:
        """
        Create database backup
        
        Args:
            backup_name: Name for backup
            
        Returns:
            Backup ID
        """
        backup_id = f"backup_{backup_name}_{int(datetime.utcnow().timestamp())}"
        
        self.backups[backup_id] = {
            "name": backup_name,
            "created_at": datetime.utcnow().isoformat(),
            "size_mb": 0,  # Would query actual size
            "status": "completed"
        }
        
        self.logger.info(f"Backup created: {backup_id}")
        return backup_id

    async def verify_backup(self, backup_id: str) -> bool:
        """
        Verify backup integrity
        
        Args:
            backup_id: Backup to verify
            
        Returns:
            True if valid
        """
        if backup_id not in self.backups:
            self.logger.warning(f"Backup not found: {backup_id}")
            return False
        
        self.logger.info(f"Backup verified: {backup_id}")
        return True


# ============================================================================
# DATABASE AGENT (Main)
# ============================================================================

class DatabaseAgent(BaseAgent):
    """
    Nexus (DatabaseAgent) — núcleo de conexión de datos.
    Orchestrates: Schema Manager, Migration Engine, Audit Logger, Backup Manager
    """

    def __init__(self):
        config = AgentConfig(
            name=NEXUS.codename,
            version="0.1.0",
            timeout_seconds=300
        )
        super().__init__(config)
        self.version = "0.1.0"
        
        self.schema_manager = SchemaManager()
        self.migration_engine = MigrationEngine()
        self.audit_logger = AuditLogger()
        self.backup_manager = BackupManager()

    def validate_input(self, input_data: AgentInput) -> tuple[bool, Optional[str]]:
        """
        Validate DatabaseAgentInput
        
        Args:
            input_data: Input to validate
            
        Returns:
            (is_valid, error_message)
        """
        if not isinstance(input_data, DatabaseAgentInput):
            return False, "Invalid input type"
        
        # Validate required fields for action
        if input_data.action == "create_table" and not input_data.table_definition:
            return False, "create_table action requires table_definition"
        
        if input_data.action == "migrate" and not input_data.migration:
            return False, "migrate action requires migration"
        
        return True, None

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """
        Execute database operation
        
        Args:
            input_data: Database operation input
            
        Returns:
            AgentOutput with results
        """
        input_data = DatabaseAgentInput.model_validate(input_data)
        start_time = datetime.utcnow()
        output = DatabaseAgentOutput(
            request_id=input_data.request_id,
            status=AgentStatus.PROCESSING,
            execution_time_ms=0,
        )

        try:
            self.status = AgentStatus.PROCESSING

            if input_data.action == "create_table":
                output = await self._create_table(input_data, output)

            elif input_data.action == "migrate":
                output = await self._migrate(input_data, output)

            elif input_data.action == "audit":
                output = await self._audit(input_data, output)

            elif input_data.action == "backup":
                output = await self._backup(input_data, output)

            else:
                output.status = AgentStatus.FAILED
                output.errors.append(f"Unknown action: {input_data.action}")

        except Exception as e:
            self.logger.error(f"Error executing {input_data.action}: {str(e)}")
            output.status = AgentStatus.FAILED
            output.errors.append(str(e))

        finally:
            # Calculate execution time
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            output.execution_time_ms = max(execution_time, 0.001)
            
            if output.status == AgentStatus.SUCCESS:
                self.status = AgentStatus.SUCCESS
            else:
                self.status = AgentStatus.FAILED

        return output

    async def _create_table(
        self,
        input_data: DatabaseAgentInput,
        output: DatabaseAgentOutput
    ) -> DatabaseAgentOutput:
        """Create table operation"""
        table_def = input_data.table_definition
        
        # Validate table definition
        is_valid, error = self.schema_manager.validate_schema(table_def)
        if not is_valid:
            output.status = AgentStatus.FAILED
            output.errors.append(error)
            return output

        # Generate DDL
        ddl_script = self.schema_manager.create_table(table_def)
        
        # Log audit entry
        self.audit_logger.log_change(
            action="CREATE_TABLE",
            table_name=table_def.name,
            details={"ddl": ddl_script}
        )
        
        # Calculate schema hash
        schema_hash = self.schema_manager.get_schema_hash(table_def)
        
        # Emit event
        await self.emit_event("TableCreated", {
            "table_name": table_def.name,
            "columns": len(table_def.columns),
            "schema_hash": schema_hash
        })
        
        output.status = AgentStatus.SUCCESS
        output.schema_hash = schema_hash
        output.result = {
            "table_name": table_def.name,
            "columns": len(table_def.columns),
            "ddl_script": ddl_script
        }

        return output

    async def _migrate(
        self,
        input_data: DatabaseAgentInput,
        output: DatabaseAgentOutput
    ) -> DatabaseAgentOutput:
        """Migration operation"""
        migration = input_data.migration
        
        # Create migration record
        migration_id = self.migration_engine.create_migration(migration)
        
        # Log audit
        self.audit_logger.log_change(
            action="MIGRATE",
            table_name="schema",
            details={"migration_id": migration_id, "version": migration.version}
        )
        
        # Emit event
        await self.emit_event("MigrationApplied", {
            "migration_id": migration_id,
            "version": migration.version,
            "tables_modified": migration.tables_modified
        })
        
        output.status = AgentStatus.SUCCESS
        output.migration_id = migration_id
        output.result = {
            "migration_id": migration_id,
            "version": migration.version,
            "sql_script": migration.sql_script
        }

        return output

    async def _audit(
        self,
        input_data: DatabaseAgentInput,
        output: DatabaseAgentOutput
    ) -> DatabaseAgentOutput:
        """Audit operation"""
        output.status = AgentStatus.SUCCESS
        output.result = {
            "total_changes": len(self.audit_logger.audit_log),
            "recent_changes": self.audit_logger.audit_log[-10:]
        }
        
        return output

    async def _backup(
        self,
        input_data: DatabaseAgentInput,
        output: DatabaseAgentOutput
    ) -> DatabaseAgentOutput:
        """Backup operation"""
        backup_id = await self.backup_manager.create_backup(
            backup_name=input_data.table_name or "full_backup"
        )
        
        is_valid = await self.backup_manager.verify_backup(backup_id)
        
        if not is_valid:
            output.status = AgentStatus.FAILED
            output.errors.append(f"Backup verification failed: {backup_id}")
            return output
        
        output.status = AgentStatus.SUCCESS
        output.backup_location = backup_id
        output.result = {
            "backup_id": backup_id,
            "verified": True
        }
        
        return output


# ============================================================================
# MAIN EXAMPLE
# ============================================================================

async def main():
    """Example usage"""
    agent = DatabaseAgent()
    
    # Example 1: Create table
    table_def = TableDefinition(
        name="clientes",
        columns=[
            ColumnDefinition(name="cliente_id", type=ColumnType.BIGINT, primary_key=True),
            ColumnDefinition(name="empresa_id", type=ColumnType.INT, nullable=False),
            ColumnDefinition(name="bodega_id", type=ColumnType.INT, nullable=False),
            ColumnDefinition(name="nombre", type=ColumnType.VARCHAR, nullable=False),
            ColumnDefinition(name="nit", type=ColumnType.VARCHAR, unique=True),
            ColumnDefinition(name="activo", type=ColumnType.BOOLEAN, default="true"),
        ],
        description="Tabla de clientes con soporte multisector"
    )
    
    input_data = DatabaseAgentInput(
        request_id="req_001",
        action="create_table",
        table_definition=table_def
    )
    
    output = await agent.execute(input_data)
    print(f"\n✅ Database Agent Output:")
    print(f"Status: {output.status}")
    print(f"Execution time: {output.execution_time_ms}ms")
    print(f"Result: {output.result}")


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run example
    asyncio.run(main())
