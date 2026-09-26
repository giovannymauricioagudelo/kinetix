"""Unit tests for Genesis (CustomAIAgent)."""

from src.agents.custom_ai_agent.agent import CustomAIAgent, GenerationRequest, SolutionType


def test_agent_uses_genesis_codename():
    agent = CustomAIAgent()
    assert agent.name == "Genesis"


def test_start_generation():
    agent = CustomAIAgent()
    solution = agent.start_generation(
        GenerationRequest(prompt="Generar función de suma", solution_type=SolutionType.CODE)
    )
    assert solution.solution_id.startswith("sol-")
    assert solution.status.value == "generating"
