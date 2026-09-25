"""
Unit tests for Nexus (DatabaseAgent)
Tests: Schema Manager, Migration Engine, Audit Logger, Backup Manager
"""

import pytest
import asyncio
from datetime import datetime
from src.agents.database_agent.database_agent import (
    DatabaseAgent,
    DatabaseAgentInput,
    DatabaseAgentOutput,
    TableDefinition,
    ColumnDefinition,
    ColumnType,
    SchemaMigration,
    SchemaManager,
    MigrationEngine,
    AuditLogger,
    BackupManager,
    AgentStatus,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def database_agent():
    """Fixture: Database Agent instance"""
    return DatabaseAgent()


@pytest.fixture
def sample_table():
    """Fixture: Sample table definition"""
    return TableDefinition(
        name="clientes",
        columns=[
            ColumnDefinition(
                name="cliente_id",
                type=ColumnType.BIGINT,
                primary_key=True
            ),
            ColumnDefinition(
                name="empresa_id",
                type=ColumnType.INT,
                nullable=False
            ),
            ColumnDefinition(
                name="bodega_id",
                type=ColumnType.INT,
                nullable=False
            ),
            ColumnDefinition(
                name="nombre",
                type=ColumnType.VARCHAR,
                nullable=False
            ),
            ColumnDefinition(
                name="nit",
                type=ColumnType.VARCHAR,
                unique=True
            ),
        ],
        description="Table de clientes"
    )


@pytest.fixture
def sample_migration():
    """Fixture: Sample migration"""
    return SchemaMigration(
        version="1.0.1",
        name="add_retencion_dian",
        tables_modified=["facturas"],
        sql_script="ALTER TABLE facturas ADD COLUMN retencion_dian DECIMAL(10,2);",
        rollback_script="ALTER TABLE facturas DROP COLUMN retencion_dian;"
    )


# ============================================================================
# SCHEMA MANAGER TESTS
# ============================================================================

class TestSchemaManager:
    """Tests for SchemaManager"""

    def test_create_table_generates_valid_ddl(self, sample_table):
        """Test that DDL generation includes all columns"""
        manager = SchemaManager()
        ddl = manager.create_table(sample_table)
        
        # Verify DDL contains all column names
        assert "cliente_id" in ddl
        assert "empresa_id" in ddl
        assert "bodega_id" in ddl
        assert "nombre" in ddl
        assert "nit" in ddl
        
        # Verify DDL contains key constraints
        assert "PRIMARY KEY" in ddl
        assert "NOT NULL" in ddl
        assert "UNIQUE" in ddl

    def test_create_table_includes_audit_columns(self, sample_table):
        """Test that audit columns are added when enabled"""
        sample_table.audit_columns = True
        manager = SchemaManager()
        ddl = manager.create_table(sample_table)
        
        assert "created_at" in ddl
        assert "updated_at" in ddl
        assert "created_by" in ddl

    def test_create_table_excludes_audit_columns(self, sample_table):
        """Test that audit columns are omitted when disabled"""
        sample_table.audit_columns = False
        manager = SchemaManager()
        ddl = manager.create_table(sample_table)
        
        # Check that common audit column patterns are NOT in DDL
        assert "created_at DATETIME" not in ddl

    def test_create_table_adds_indexes(self, sample_table):
        """Test that indexes are created for multisector columns"""
        manager = SchemaManager()
        ddl = manager.create_table(sample_table)
        
        assert "CREATE INDEX" in ddl
        assert "empresa_id" in ddl
        assert "bodega_id" in ddl

    def test_validate_schema_missing_empresa_id(self, sample_table):
        """Test validation fails without empresa_id"""
        sample_table.columns = [col for col in sample_table.columns if col.name != "empresa_id"]
        manager = SchemaManager()
        
        is_valid, error = manager.validate_schema(sample_table)
        assert not is_valid
        assert "empresa_id" in error

    def test_validate_schema_missing_bodega_id(self, sample_table):
        """Test validation fails without bodega_id"""
        sample_table.columns = [col for col in sample_table.columns if col.name != "bodega_id"]
        manager = SchemaManager()
        
        is_valid, error = manager.validate_schema(sample_table)
        assert not is_valid
        assert "bodega_id" in error

    def test_validate_schema_duplicate_columns(self, sample_table):
        """Test validation detects duplicate column names"""
        # Add duplicate
        sample_table.columns.append(
            ColumnDefinition(name="nombre", type=ColumnType.VARCHAR)
        )
        manager = SchemaManager()
        
        is_valid, error = manager.validate_schema(sample_table)
        assert not is_valid

    def test_validate_schema_valid(self, sample_table):
        """Test validation passes for valid schema"""
        manager = SchemaManager()
        is_valid, error = manager.validate_schema(sample_table)
        
        assert is_valid
        assert error is None

    def test_get_schema_hash_deterministic(self, sample_table):
        """Test that schema hash is deterministic"""
        manager = SchemaManager()
        
        hash1 = manager.get_schema_hash(sample_table)
        hash2 = manager.get_schema_hash(sample_table)
        
        assert hash1 == hash2
        assert len(hash1) == 16  # SHA256[:16]

    def test_get_schema_hash_changes_with_schema(self, sample_table):
        """Test that schema hash changes when schema changes"""
        manager = SchemaManager()
        
        hash1 = manager.get_schema_hash(sample_table)
        
        # Modify schema
        sample_table.columns.append(
            ColumnDefinition(name="email", type=ColumnType.VARCHAR)
        )
        
        hash2 = manager.get_schema_hash(sample_table)
        
        assert hash1 != hash2


# ============================================================================
# MIGRATION ENGINE TESTS
# ============================================================================

class TestMigrationEngine:
    """Tests for MigrationEngine"""

    def test_create_migration_generates_id(self, sample_migration):
        """Test that migration gets unique ID"""
        engine = MigrationEngine()
        
        migration_id = engine.create_migration(sample_migration)
        
        assert migration_id.startswith("mig_")
        assert sample_migration.version in migration_id

    def test_create_migration_stored(self, sample_migration):
        """Test that migration is stored in engine"""
        engine = MigrationEngine()
        
        migration_id = engine.create_migration(sample_migration)
        
        assert migration_id in engine.migrations
        assert engine.migrations[migration_id] == sample_migration

    def test_generate_migration_script(self):
        """Test migration script generation"""
        engine = MigrationEngine()
        
        changes = {
            "tables_added": ["new_table"],
            "tables_modified": ["existing_table"],
            "columns_added": {
                "existing_table": [
                    {"name": "retencion_dian", "type": "DECIMAL(10,2)"}
                ]
            }
        }
        
        migration = engine.generate_migration_script("1.0.0", "1.0.1", changes)
        
        assert migration.version == "1.0.1"
        assert "ALTER TABLE" in migration.sql_script
        assert "BEGIN TRANSACTION" in migration.sql_script
        assert "COMMIT" in migration.sql_script


# ============================================================================
# AUDIT LOGGER TESTS
# ============================================================================

class TestAuditLogger:
    """Tests for AuditLogger"""

    def test_log_change_records_entry(self):
        """Test that changes are logged"""
        logger = AuditLogger()
        
        logger.log_change(
            action="CREATE_TABLE",
            table_name="test_table",
            details={"columns": 5}
        )
        
        assert len(logger.audit_log) == 1
        assert logger.audit_log[0]["action"] == "CREATE_TABLE"
        assert logger.audit_log[0]["table"] == "test_table"

    def test_log_change_includes_timestamp(self):
        """Test that entries include timestamp"""
        logger = AuditLogger()
        
        before = datetime.utcnow()
        logger.log_change(
            action="ALTER_TABLE",
            table_name="test",
            details={}
        )
        after = datetime.utcnow()
        
        entry = logger.audit_log[0]
        timestamp = datetime.fromisoformat(entry["timestamp"])
        
        assert before <= timestamp <= after

    def test_log_change_includes_user(self):
        """Test that user is included in log"""
        logger = AuditLogger()
        
        logger.log_change(
            action="DROP_TABLE",
            table_name="test",
            details={},
            user="giovanny"
        )
        
        assert logger.audit_log[0]["user"] == "giovanny"

    def test_multiple_log_entries(self):
        """Test multiple log entries"""
        logger = AuditLogger()
        
        for i in range(5):
            logger.log_change(
                action=f"ACTION_{i}",
                table_name=f"table_{i}",
                details={}
            )
        
        assert len(logger.audit_log) == 5


# ============================================================================
# BACKUP MANAGER TESTS
# ============================================================================

class TestBackupManager:
    """Tests for BackupManager"""

    @pytest.mark.asyncio
    async def test_create_backup_returns_id(self):
        """Test backup creation returns ID"""
        manager = BackupManager()
        
        backup_id = await manager.create_backup("my_backup")
        
        assert backup_id.startswith("backup_")
        assert "my_backup" in backup_id

    @pytest.mark.asyncio
    async def test_create_backup_stored(self):
        """Test that backup is stored"""
        manager = BackupManager()
        
        backup_id = await manager.create_backup("test")
        
        assert backup_id in manager.backups
        assert manager.backups[backup_id]["name"] == "test"
        assert manager.backups[backup_id]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_verify_backup_valid(self):
        """Test backup verification for valid backup"""
        manager = BackupManager()
        
        backup_id = await manager.create_backup("test")
        is_valid = await manager.verify_backup(backup_id)
        
        assert is_valid

    @pytest.mark.asyncio
    async def test_verify_backup_invalid(self):
        """Test backup verification fails for nonexistent backup"""
        manager = BackupManager()
        
        is_valid = await manager.verify_backup("nonexistent")
        
        assert not is_valid


# ============================================================================
# DATABASE AGENT TESTS
# ============================================================================

class TestDatabaseAgent:
    """Tests for main DatabaseAgent"""

    def test_agent_initialization(self):
        """Test agent initializes correctly"""
        agent = DatabaseAgent()
        
        assert agent.config.name == "Nexus"
        assert agent.schema_manager is not None
        assert agent.migration_engine is not None
        assert agent.audit_logger is not None
        assert agent.backup_manager is not None

    def test_validate_input_invalid_type(self, database_agent):
        """Test validation fails for invalid input type"""
        from base_agent import AgentInput
        
        input_data = AgentInput(request_id="test")
        
        is_valid, error = database_agent.validate_input(input_data)
        
        assert not is_valid

    def test_validate_input_missing_table_for_create(self, database_agent):
        """Test validation fails when create_table action lacks table_definition"""
        input_data = DatabaseAgentInput(
            request_id="test",
            action="create_table"
        )
        
        is_valid, error = database_agent.validate_input(input_data)
        
        assert not is_valid
        assert "table_definition" in error

    def test_validate_input_valid_create_table(self, database_agent, sample_table):
        """Test validation passes for valid create_table input"""
        input_data = DatabaseAgentInput(
            request_id="test",
            action="create_table",
            table_definition=sample_table
        )
        
        is_valid, error = database_agent.validate_input(input_data)
        
        assert is_valid

    @pytest.mark.asyncio
    async def test_execute_create_table(self, database_agent, sample_table):
        """Test create_table execution"""
        input_data = DatabaseAgentInput(
            request_id="req_001",
            action="create_table",
            table_definition=sample_table
        )
        
        output = await database_agent.execute(input_data)
        
        assert output.status == AgentStatus.SUCCESS
        assert output.schema_hash is not None
        assert output.result["table_name"] == "clientes"

    @pytest.mark.asyncio
    async def test_execute_migrate(self, database_agent, sample_migration):
        """Test migrate execution"""
        input_data = DatabaseAgentInput(
            request_id="req_002",
            action="migrate",
            migration=sample_migration
        )
        
        output = await database_agent.execute(input_data)
        
        assert output.status == AgentStatus.SUCCESS
        assert output.migration_id is not None

    @pytest.mark.asyncio
    async def test_execute_audit(self, database_agent):
        """Test audit execution"""
        input_data = DatabaseAgentInput(
            request_id="req_003",
            action="audit"
        )
        
        output = await database_agent.execute(input_data)
        
        assert output.status == AgentStatus.SUCCESS
        assert "total_changes" in output.result

    @pytest.mark.asyncio
    async def test_execute_backup(self, database_agent):
        """Test backup execution"""
        input_data = DatabaseAgentInput(
            request_id="req_004",
            action="backup"
        )
        
        output = await database_agent.execute(input_data)
        
        assert output.status == AgentStatus.SUCCESS
        assert output.backup_location is not None

    @pytest.mark.asyncio
    async def test_execute_invalid_action(self, database_agent):
        """Test execution fails for invalid action"""
        input_data = DatabaseAgentInput(
            request_id="req_005",
            action="invalid_action"
        )
        
        output = await database_agent.execute(input_data)
        
        assert output.status == AgentStatus.FAILED
        assert len(output.errors) > 0

    @pytest.mark.asyncio
    async def test_execute_records_execution_time(self, database_agent, sample_table):
        """Test that execution time is recorded"""
        input_data = DatabaseAgentInput(
            request_id="req_006",
            action="create_table",
            table_definition=sample_table
        )
        
        output = await database_agent.execute(input_data)
        
        assert output.execution_time_ms > 0

    def test_get_status(self, database_agent):
        """Test agent status reporting"""
        status = database_agent.get_status()
        
        assert "name" in status
        assert "version" in status
        assert "status" in status
        assert status["name"] == "Nexus"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestDatabaseAgentIntegration:
    """Integration tests for full workflows"""

    @pytest.mark.asyncio
    async def test_full_workflow_create_and_migrate(self, database_agent, sample_table):
        """Test full workflow: create table then migrate"""
        # Step 1: Create table
        create_input = DatabaseAgentInput(
            request_id="req_001",
            action="create_table",
            table_definition=sample_table
        )
        
        create_output = await database_agent.execute(create_input)
        assert create_output.status == AgentStatus.SUCCESS
        
        # Step 2: Create migration
        migration = SchemaMigration(
            version="1.0.1",
            name="add_email",
            tables_modified=["clientes"],
            sql_script="ALTER TABLE clientes ADD COLUMN email VARCHAR(100);"
        )
        
        migrate_input = DatabaseAgentInput(
            request_id="req_002",
            action="migrate",
            migration=migration
        )
        
        migrate_output = await database_agent.execute(migrate_input)
        assert migrate_output.status == AgentStatus.SUCCESS
        
        # Step 3: Verify audit log
        audit_input = DatabaseAgentInput(
            request_id="req_003",
            action="audit"
        )
        
        audit_output = await database_agent.execute(audit_input)
        assert audit_output.result["total_changes"] >= 2

    @pytest.mark.asyncio
    async def test_column_name_validation(self):
        """Test column name validation"""
        agent = DatabaseAgent()
        
        # Invalid column name (special characters)
        table_def = TableDefinition(
            name="test",
            columns=[
                ColumnDefinition(name="test-column", type=ColumnType.VARCHAR),
                ColumnDefinition(name="empresa_id", type=ColumnType.INT),
                ColumnDefinition(name="bodega_id", type=ColumnType.INT),
            ]
        )
        
        with pytest.raises(ValueError):
            table_def.model_validate(table_def.model_dump())


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
