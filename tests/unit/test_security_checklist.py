"""Checklist fundamental de seguridad de la fábrica."""

from src.agents import security_checklist
from src.agents.orchestrator_agent.agent import SECURITY_SPRINT


def test_ownership_covers_user_practices():
    ids = {p["id"] for p in security_checklist.practices()}
    assert {
        "autenticacion", "claves_api_servidor", "https", "contrasenas_hash", "validacion_servidor",
        "xss", "csrf", "cors", "cabeceras", "cookies_sesion", "limite_peticiones", "archivos",
        "pagos_servidor", "dependencias", "secretos_git", "pruebas_protecciones",
    } <= ids


def test_sprint_tasks_match_cortex_security_sprint():
    assert SECURITY_SPRINT[0] == "seguridad"
    assert SECURITY_SPRINT[4] == security_checklist.sprint_tasks()
    assert SECURITY_SPRINT[3] == security_checklist.exit_criteria()
    assert "docs/seguridad.md" in SECURITY_SPRINT[3]
    assert [a.codename for a, _ in SECURITY_SPRINT[4]] == [
        "Sentinel", "Synapse", "Nexus", "Aurora", "Vector", "Orbit", "Prism", "Argus",
    ]
