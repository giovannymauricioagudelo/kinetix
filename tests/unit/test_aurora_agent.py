"""Aurora (InterfaceDesignAgent): tokens, contraste WCAG, correcciones, exportaciones y API protegida."""

import json

import pytest

from src.agents.interface_design_agent import design, exporters
from src.agents.interface_design_agent.dependencies import set_aurora_service
from src.agents.interface_design_agent.repository import InMemoryDesignRepository
from src.agents.interface_design_agent.service import AuroraService
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError
from src.api.routes import aurora_routes
from tests.unit.agent_api import build_api, headers


def test_contrast_follows_wcag_formula():
    assert design.contrast_ratio("#000000", "#FFFFFF") == 21
    assert design.contrast_ratio("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.01)
    assert design.normalize_hex("#abc") == "#AABBCC"
    with pytest.raises(design.DesignError):
        design.normalize_hex("red")
    report = design.contrast_report("#777777", "#FFFFFF")
    assert report["AA"]["texto"] is False and report["AA"]["texto_grande"] is True
    assert design.contrast_ratio(report["sugerencia_AA"], "#FFFFFF") >= 4.5


def test_tokens_cover_palettes_themes_and_breakpoints():
    tokens = design.build_tokens("#2563EB", "#7C3AED")
    assert set(design.PALETTES) <= set(tokens["color"])
    assert set(tokens["themes"]) == {"light", "dark"}
    assert tokens["breakpoints"] == design.BREAKPOINTS
    design.validate_tokens(tokens)


@pytest.mark.parametrize("override", [
    {"themes": {"light": {"primary": "red;}</style><script>"}}},
    {"spacing": {"md": "expression(alert(1))"}},
    {"desconocido": {"x": "1px"}},
])
def test_token_overrides_are_whitelisted(override):
    with pytest.raises(design.DesignError):
        design.merge_tokens(design.build_tokens("#2563EB", "#7C3AED"), override)


@pytest.fixture
def aurora():
    return AuroraService(InMemoryDesignRepository())


def test_system_lifecycle_is_tenant_scoped_and_versioned(aurora):
    created = aurora.create_system("ana", "gio", {"nombre": "Marca", "nivel_wcag": "AA"})
    assert created["version"] == 1 and created["total_componentes"] == len(design.DEFAULT_COMPONENTS)
    with pytest.raises(ConflictError):
        aurora.create_system("ana", "gio", {"nombre": "Marca"})
    with pytest.raises(NotFoundError):
        aurora.get_system(created["id_sistema"], "otra")

    updated = aurora.update_tokens(created["id_sistema"], "gio", {"themes": {"light": {"primary": "#1D4ED8"}}}, 1)
    assert updated["version"] == 2 and updated["tokens"]["themes"]["light"]["primary"] == "#1D4ED8"
    with pytest.raises(ConflictError):
        aurora.update_tokens(created["id_sistema"], "gio", {"themes": {"light": {"primary": "#000000"}}}, 1)
    with pytest.raises(InvalidInputError):
        aurora.update_tokens(created["id_sistema"], "gio", {"themes": {"light": {"primary": "azul"}}}, 2)


def test_accessibility_fixes_bring_contrast_to_aaa(aurora):
    system = aurora.create_system("ana", "gio", {"nombre": "AAA", "nivel_wcag": "AAA"})
    before = aurora.accessibility(system["id_sistema"], "gio", "AAA", aplicar=False)
    assert before["contraste_fallido"] > 0 and before["correcciones_aplicadas"] is False
    after = aurora.accessibility(system["id_sistema"], "gio", "AAA", aplicar=True)
    assert after["correcciones_aplicadas"] and after["contraste_fallido_despues"] == 0
    assert after["version_nueva"] == 2


def test_components_are_audited(aurora):
    system = aurora.create_system("ana", "gio", {"nombre": "Comp"})
    saved = aurora.upsert_component(system["id_sistema"], "gio", {"nombre": "Dialogo", "tipo": "modal"})
    assert saved["creado"] and {p["criterio"] for p in saved["problemas_accesibilidad"]} >= {"2.4.3", "2.1.2"}
    assert aurora.delete_component(system["id_sistema"], "gio", "Dialogo") == {"eliminado": "Dialogo"}
    with pytest.raises(NotFoundError):
        aurora.delete_component(system["id_sistema"], "gio", "Dialogo")


def test_exports_layouts_and_screens(aurora):
    system = aurora.create_system("ana", "gio", {"nombre": "Export"})
    sid = system["id_sistema"]
    css = aurora.export(sid, "gio", "css")
    assert ":root {" in css["contenido"] and '[data-theme="dark"]' in css["contenido"]
    assert css["archivo"] == "export-v1.css"
    assert json.loads(aurora.export(sid, "gio", "json")["contenido"])
    for fmt in exporters.EXPORT_FORMATS:
        assert aurora.export(sid, "gio", fmt)["bytes"] > 0
    layout = aurora.layout(sid, "gio", {"tipo": "grid", "columnas_escritorio": 12})
    assert "@media" in json.dumps(layout)
    screen = aurora.screen(sid, "gio", "login", "<script>alert(1)</script>", "es")
    assert "&lt;script&gt;" in screen["html"] and "<script>alert" not in screen["html"]
    assert 'class="kx-skip"' in screen["html"] and 'data-kx-reveal="f-contrasena"' in screen["html"]


@pytest.mark.parametrize("tipo, esperado", [
    ("dashboard", ('class="kx-kpis"', 'role="img"', "kx-feed", "data-kx-theme")),
    ("list", ("data-kx-table", "data-kx-export", 'aria-sort="none"', 'id="kx-bulk"', 'id="kx-empty"', 'id="kx-delete"')),
    ("form", ("data-kx-validate", "<fieldset>", "kx-actionbar", 'id="kx-discard"')),
    ("detail", ('role="tablist"', 'role="tabpanel"', "kx-timeline")),
    ("settings", ('role="switch"', 'id="s-idioma"')),
])
def test_screens_use_the_app_shell_and_add_functionality(aurora, tipo, esperado):
    sid = aurora.create_system("ana", "gio", {"nombre": f"S-{tipo}"})["id_sistema"]
    screen = aurora.screen(sid, "gio", tipo, "Talleres", "es")
    page = screen["html"]
    assert 'class="kx-shell"' in page and 'aria-current="page"' in page and 'aria-label="Breadcrumb"' in page
    assert all(fragment in page for fragment in esperado)
    assert screen["funcionalidades"] and "Sidebar" in screen["componentes_usados"]
    assert 'id="kx-company"' not in page


def test_screen_options_customize_entity_fields_and_companies(aurora):
    sid = aurora.create_system("ana", "gio", {"nombre": "Opciones"})["id_sistema"]
    options = {
        "entidad": "Vehículo", "entidad_plural": "Vehículos", "multiempresa": True,
        "empresas": ["Taller <Centro>", "Taller Sur"], "usuario": "Giovanny Agudelo",
        "campos": [{"nombre": "placa", "etiqueta": "Placa", "requerido": True},
                   {"nombre": "kilometraje", "etiqueta": "Kilometraje", "tipo": "number"},
                   {"nombre": "servicio", "etiqueta": "Servicio", "tipo": "select", "opciones": ["Aceite", "Frenos"]}],
        "columnas": ["placa", "servicio"],
    }
    listing = aurora.screen(sid, "gio", "list", "Talleres", "es", options)
    page = listing["html"]
    assert "Vehículos" in page and ">Placa" in page and "Kilometraje" not in page
    assert 'id="kx-company"' in page and "Taller &lt;Centro&gt;" in page and ">GA<" in page
    assert listing["opciones_aplicadas"]["columnas"] == ["placa", "servicio"]
    form = aurora.screen(sid, "gio", "form", "Talleres", "es", options)["html"]
    assert 'id="f-placa"' in form and 'type="number"' in form and "<option>Frenos</option>" in form

    for bad in ({"campos": [{"nombre": "Mal Nombre"}]}, {"columnas": ["inexistente"]},
                {"campos": [{"nombre": "x", "tipo": "archivo"}]}, {"multiempresa": "si"}):
        with pytest.raises(InvalidInputError):
            aurora.screen(sid, "gio", "list", "Talleres", "es", bad)


def test_screens_are_translated(aurora):
    sid = aurora.create_system("ana", "gio", {"nombre": "Idiomas"})["id_sistema"]
    english = aurora.screen(sid, "gio", "list", "Shop", "en")["html"]
    assert '<html lang="en">' in english and "Export CSV" in english and "Exportar CSV" not in english
    assert "Exportar CSV" in aurora.screen(sid, "gio", "list", "Loja", "pt")["html"]
    with pytest.raises(InvalidInputError):
        aurora.screen(sid, "gio", "list", "Shop", "fr")


@pytest.fixture
def api():
    client, repo, _ = build_api([aurora_routes.router], [("diseno", "ver"), ("diseno", "gestionar")])
    set_aurora_service(AuroraService(InMemoryDesignRepository()))
    yield client, repo
    set_aurora_service(None)
    set_security_service(None)


def test_api_requires_permissions_and_audits(api):
    client, repo = api
    assert client.get("/api/v1/aurora/salud").json()["agente"] == "Aurora"
    assert client.get("/api/v1/aurora/sistemas").status_code == 401
    assert client.get("/api/v1/aurora/sistemas", headers=headers(client, "luis")).status_code == 403

    auth = headers(client)
    created = client.post("/api/v1/aurora/sistemas", json={"nombre": "Web"}, headers=auth)
    assert created.status_code == 201
    sid = created.json()["sistema"]["id_sistema"]
    download = client.get(f"/api/v1/aurora/sistemas/{sid}/exportar?formato=css&descargar=true", headers=auth)
    assert download.headers["content-disposition"].startswith("attachment")
    assert client.post("/api/v1/aurora/contraste", json={"color_texto": "#000000", "color_fondo": "#FFFFFF"},
                       headers=auth).json()["relacion"] == 21
    screen = client.post(f"/api/v1/aurora/sistemas/{sid}/pantallas", headers=auth, json={
        "tipo": "detail", "nombre_app": "Citas", "opciones": {"entidad": "Cita", "campos": [{"nombre": "paciente"}]}})
    assert screen.status_code == 200 and screen.json()["opciones_aplicadas"]["campos"] == ["paciente"]
    assert "detail" in client.get("/api/v1/aurora/info", headers=auth).json()["pantallas"]
    _, entries = repo.list_audit("gio", None, None, None, None, None, 50, 0)
    assert "aurora_sistema_crear" in {e.accion for e in entries}
