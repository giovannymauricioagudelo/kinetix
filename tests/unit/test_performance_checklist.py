"""Checklist fundamental de rendimiento de la fábrica."""

from src.agents import performance_checklist
from src.agents.orchestrator_agent.agent import PERFORMANCE_SPRINT


def test_ownership_covers_user_practices():
    ids = {p["id"] for p in performance_checklist.practices()}
    assert {
        "esqueletos_carga", "imagenes_modernas", "cdn", "cola_trabajos", "evitar_n_plus_1",
        "brotli", "indices", "opentelemetry", "render_servidor", "listas_virtualizadas",
        "pool_conexiones", "cache", "pruebas_movil_red_lenta", "pruebas_carga",
    } <= ids


def test_sprint_tasks_match_cortex_performance_sprint():
    assert PERFORMANCE_SPRINT[0] == "rendimiento"
    assert PERFORMANCE_SPRINT[4] == performance_checklist.sprint_tasks()
    assert PERFORMANCE_SPRINT[3] == performance_checklist.exit_criteria()
    assert "docs/rendimiento.md" in PERFORMANCE_SPRINT[3]
