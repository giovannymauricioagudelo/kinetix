"""
Base Agent - Abstract class for all AFP agents
Provides common interface, logging, and event emission
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime
from enum import Enum
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent execution status"""
    IDLE = "idle"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class AgentConfig(BaseModel):
    """Configuration for any agent"""
    name: str
    version: str = "0.1.0"
    timeout_seconds: int = 300
    retry_attempts: int = 3
    log_level: str = "INFO"


class AgentInput(BaseModel):
    """Base input for any agent"""
    request_id: str = Field(..., description="Unique request ID for tracking")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    """Base output from any agent"""
    request_id: str
    status: AgentStatus
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    result: Optional[Dict[str, Any]] = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    execution_time_ms: float
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        """Pydantic config"""
        use_enum_values = True


class BaseAgent(ABC):
    """
    Abstract base class for all AFP agents.
    
    Operational agents (codenames):
    - Nexus (DatabaseAgent)
    - Synapse (APIsAgent)
    - Matrix (BusinessRulesAgent)
    - Insight (ReportingAgent)
    - Prism (QAAgent)
    - Orbit (GitDeploymentAgent)
    - Vector (DevelopmentAgent)
    - Genesis (CustomAIAgent)
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize base agent
        
        Args:
            config: Agent configuration
        """
        self.config = config
        self.logger = logging.getLogger(f"agents.{config.name}")
        self.logger.setLevel(config.log_level)
        self.status = AgentStatus.IDLE

    @abstractmethod
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """
        Execute agent logic
        
        Args:
            input_data: Agent input
            
        Returns:
            AgentOutput with results
        """
        pass

    @abstractmethod
    def validate_input(self, input_data: AgentInput) -> tuple[bool, Optional[str]]:
        """
        Validate input data
        
        Args:
            input_data: Input to validate
            
        Returns:
            (is_valid, error_message)
        """
        pass

    async def emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Emit event to event bus (n8n)
        
        Args:
            event_type: Type of event (e.g., "SchemaChanged")
            payload: Event payload
        """
        event = {
            "agent": self.config.name,
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": payload
        }
        
        # TODO: Send to n8n event bus
        # For now, just log
        self.logger.info(f"Event emitted: {event_type}", extra={"event": event})

    async def process_with_retry(
        self, 
        input_data: AgentInput,
        max_retries: Optional[int] = None
    ) -> AgentOutput:
        """
        Execute with retry logic
        
        Args:
            input_data: Input data
            max_retries: Max retry attempts (uses config if not provided)
            
        Returns:
            AgentOutput
        """
        max_retries = max_retries or self.config.retry_attempts
        last_error = None

        for attempt in range(max_retries):
            try:
                self.logger.info(
                    f"Executing (attempt {attempt + 1}/{max_retries})",
                    extra={"request_id": input_data.request_id}
                )
                
                # Validate before execution
                is_valid, error_msg = self.validate_input(input_data)
                if not is_valid:
                    return AgentOutput(
                        request_id=input_data.request_id,
                        status=AgentStatus.FAILED,
                        errors=[f"Validation failed: {error_msg}"],
                        execution_time_ms=0
                    )

                # Execute
                output = await self.execute(input_data)
                
                if output.status in [AgentStatus.SUCCESS, AgentStatus.PARTIAL]:
                    self.logger.info(
                        f"Execution succeeded with status {output.status}",
                        extra={"request_id": input_data.request_id}
                    )
                    return output
                else:
                    raise Exception(f"Agent failed: {output.errors}")

            except Exception as e:
                last_error = str(e)
                self.logger.warning(
                    f"Attempt {attempt + 1} failed: {last_error}",
                    extra={"request_id": input_data.request_id}
                )
                
                if attempt < max_retries - 1:
                    # Wait before retry (exponential backoff)
                    wait_seconds = 2 ** attempt
                    self.logger.info(f"Retrying in {wait_seconds} seconds...")
                    # In real code: await asyncio.sleep(wait_seconds)

        # All retries failed
        self.logger.error(
            f"All {max_retries} attempts failed",
            extra={"request_id": input_data.request_id, "last_error": last_error}
        )
        
        return AgentOutput(
            request_id=input_data.request_id,
            status=AgentStatus.FAILED,
            errors=[f"Failed after {max_retries} attempts: {last_error}"],
            execution_time_ms=0
        )

    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "name": self.config.name,
            "version": self.config.version,
            "status": self.status.value,
            "timestamp": datetime.utcnow().isoformat()
        }
