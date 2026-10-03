"""Vector (DevelopmentAgent): análisis AST, plantillas y escritura git sin tocar master ni el árbol de trabajo."""

import ast

import pytest

from src.agents.development_agent import analyzer, scaffold
from src.agents.development_agent.dependencies import set_vector_service
from src.agents.development_agent.repository import InMemoryAnalysisRepository
from src.agents.development_agent.service import VectorService
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError
from src.api.routes import vector_routes
from tests.unit.agent_api import build_api, git, headers, init_repo

RISKY = '''
import os, requests

API_TOKEN = "k9f8a7b6c5d4e3f2a1b0c"
TOKEN_TYPE = "Bearer"

def run(cursor, user):
    eval(user)
    os.system("dir " + user)
    cursor.execute(f"SELECT * FROM usuarios WHERE nombre = '{user}'")
    requests.get("https://example.com")
    try:
        pass
    except:
        pass
'''


def rules(result):
    return {f["regla"] for f in result["hallazgos"]}


def test_analyzer_finds_security_and_reliability_issues():
    result = analyzer.analyze_files({"src/riesgo.py": RISKY})
    found = rules(result)
    assert {"ejecucion_dinamica", "secreto_en_codigo", "comando_shell", "sql_interpolado", "http_sin_timeout",
            "except_desnudo"} <= found
    assert result["por_severidad"]["critica"] == 2
    assert not any("TOKEN_TYPE" in f["mensaje"] for f in result["hallazgos"])
    assert 0 <= result["puntuacion"] < 10


def test_analyzer_ignores_placeholders_and_parameterized_sql():
    clean = '''
PASSWORD = "<tu-contraseña>"
CONN = "Server=x;PWD=${DB_PASSWORD}"

def get(cursor, uid):
    """Lee un usuario."""
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (uid,))
'''
    result = analyzer.analyze_files({"src/limpio.py": clean})
    assert result["por_severidad"]["critica"] == 0 and "sql_interpolado" not in rules(result)
    assert result["puntuacion"] == 10


def test_analyzer_reports_syntax_errors():
    result = analyzer.analyze_files({"src/roto.py": "def x(:\n"})
    assert result["errores_sintaxis"] and result["errores_sintaxis"][0]["archivo"] == "src/roto.py"


def test_scaffold_generates_valid_clean_code():
    files = scaffold.generate("inventario", "Producto", [{"nombre": "nombre", "tipo": "str"}, {"nombre": "stock", "tipo": "int"}])
    assert "src/api/routes/inventario_routes.py" in files and "sql/inventario.sql" in files
    for path, content in files.items():
        if path.endswith(".py"):
            ast.parse(content)
    review = analyzer.analyze_files({p: c for p, c in files.items() if p.endswith(".py")})
    assert review["por_severidad"]["critica"] == 0
    with pytest.raises(scaffold.ScaffoldError):
        scaffold.generate("Inventario-Malo", None, [{"nombre": "x", "tipo": "str"}])


@pytest.fixture
def vector(tmp_path):
    repo = init_repo(tmp_path / "repo")
    return VectorService(repo, InMemoryAnalysisRepository()), tmp_path / "repo"


def test_analysis_uses_tracked_files_and_is_recorded(vector):
    service, path = vector
    (path / "src" / "borrador.py").write_text("eval('1')\n", encoding="utf-8")
    result = service.analyze_paths("ana", ["src"])
    assert result["archivos"] == 1 and result["por_severidad"]["critica"] == 0
    assert service.analyze_paths("ana", ["src"], solo_versionados=False)["por_severidad"]["critica"] == 1
    assert service.history()["total"] == 2
    with pytest.raises(InvalidInputError):
        service.analyze_paths("ana", ["../fuera"])
    with pytest.raises(InvalidInputError):
        service.analyze_paths("ana", ["venv"])


def test_commits_go_to_work_branches_without_touching_master(vector):
    service, path = vector
    master = git(path, "rev-parse", "master")
    status_before = git(path, "status", "--porcelain")
    result = service.commit_files("ana", "feature/nuevo", {"src/nuevo.py": 'def hola():\n    """Saludo."""\n    return 1\n'},
                                  "Agrega hola")
    assert result["rama_creada"] == "si" and result["padre"] == master
    assert git(path, "rev-parse", "master") == master
    assert git(path, "status", "--porcelain") == status_before
    assert git(path, "show", "feature/nuevo:src/nuevo.py").startswith("def hola")
    assert "Commit generado por Vector para ana" in git(path, "log", "-1", "--format=%B", "feature/nuevo")

    with pytest.raises(InvalidInputError):
        service.commit_files("ana", "master", {"src/x.py": "x = 1\n"}, "directo a master")
    with pytest.raises(ConflictError):
        service.commit_files("ana", "feature/nuevo", {"src/malo.py": "eval(input())\n"}, "código peligroso")
    with pytest.raises(ConflictError):
        service.commit_files("ana", "feature/nuevo", {"src/nuevo.py": 'def hola():\n    """Saludo."""\n    return 1\n'}, "sin cambios")
    with pytest.raises(InvalidInputError):
        service.commit_files("ana", "feature/nuevo", {".github/workflows/x.yml": "on: push\n"}, "fuera de rutas")


def test_branches_diff_and_scaffold(vector):
    service, path = vector
    assert service.create_branch("feature/base")["commit"] == git(path, "rev-parse", "HEAD")
    with pytest.raises(ConflictError):
        service.create_branch("feature/base")
    spec = {"modulo": "clientes", "entidad": "Cliente", "campos": [{"nombre": "nombre", "tipo": "str"}]}
    preview = service.scaffold_preview(spec)
    assert preview["ya_existen"] == [] and preview["revision"]["por_severidad"]["critica"] == 0
    applied = service.scaffold_apply("ana", spec, "vector/clientes")
    assert "src/agents/clientes_module/service.py" in applied["archivos"]
    with pytest.raises(ConflictError):
        service.scaffold_apply("ana", spec, "vector/clientes")
    diff = service.diff("master", "vector/clientes")
    assert diff["lineas_agregadas"] > 0 and any(f["archivo"] == "sql/clientes.sql" for f in diff["archivos"])
    with pytest.raises(NotFoundError):
        service.commits("feature/no-existe")


@pytest.fixture
def api(tmp_path):
    client, repo, _ = build_api([vector_routes.router], [("codigo", "ver"), ("codigo", "escribir")])
    set_vector_service(VectorService(init_repo(tmp_path / "repo"), InMemoryAnalysisRepository()))
    yield client, repo
    set_vector_service(None)
    set_security_service(None)


def test_api_permissions_and_audited_writes(api):
    client, repo = api
    assert client.get("/api/v1/vector/salud").json()["git"] == "disponible"
    assert client.post("/api/v1/vector/analisis", json={}).status_code == 401
    assert client.post("/api/v1/vector/analisis", json={}, headers=headers(client, "luis")).status_code == 403
    auth = headers(client)
    assert client.post("/api/v1/vector/analisis/codigo", json={"codigo": "exec('x')\n"}, headers=auth).json()["por_severidad"]["critica"] == 1
    created = client.post("/api/v1/vector/ramas", json={"nombre": "feature/api"}, headers=auth)
    assert created.status_code == 201
    assert client.post("/api/v1/vector/ramas", json={"nombre": "main"}, headers=auth).status_code == 400
    _, entries = repo.list_audit("gio", None, None, None, None, None, 50, 0)
    assert "vector_rama_crear" in {e.accion for e in entries}
