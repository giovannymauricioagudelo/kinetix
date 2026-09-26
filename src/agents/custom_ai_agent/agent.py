"""
Genesis (CustomAIAgent) — genera código y soluciones AI automáticamente.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.agents.agent_catalog import GENESIS

logger = logging.getLogger(__name__)


class SolutionType(str, Enum):
    CODE = "code"
    SQL = "sql"
    DOCUMENT = "document"
    API = "api"


class SolutionStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    SAVED = "saved"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"


@dataclass
class GenerationRequest:
    prompt: str
    solution_type: SolutionType = SolutionType.CODE
    language: str = "python"
    requested_by: str = "api"

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("prompt is required")


@dataclass
class GeneratedSolution:
    solution_id: str
    prompt: str
    solution_type: SolutionType
    language: str
    status: SolutionStatus
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    generated_code: Optional[str] = None
    explanation: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class CustomAIAgent:
    """Agente de IA personalizada: generación automática de código y soluciones."""

    def __init__(self) -> None:
        self.name = GENESIS.codename
        self.version = "0.1.0"
        self._solutions: Dict[str, GeneratedSolution] = {}
        logger.info("✅ %s v%s initialized", self.name, self.version)

    def start_generation(self, request: GenerationRequest) -> GeneratedSolution:
        solution_id = f"sol-{len(self._solutions) + 1}"
        solution = GeneratedSolution(
            solution_id=solution_id,
            prompt=request.prompt,
            solution_type=request.solution_type,
            language=request.language,
            status=SolutionStatus.GENERATING,
            metadata={"requested_by": request.requested_by},
        )
        self._solutions[solution_id] = solution
        return solution

    def get_solution(self, solution_id: str) -> Optional[GeneratedSolution]:
        return self._solutions.get(solution_id)

    def list_solutions(self, limit: int = 50) -> List[GeneratedSolution]:
        items = list(self._solutions.values())
        return items[-limit:]
