"""
Analizador estático de Vector para Python (AST): complejidad ciclomática, tamaño, anidamiento,
patrones inseguros (OWASP) y mantenibilidad. No ejecuta el código analizado.
"""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Optional, Tuple

SEVERITIES = ("critica", "alta", "media", "baja")
WEIGHTS = {"critica": 2.5, "alta": 1.0, "media": 0.3, "baja": 0.05}
COMPLEXITY_MEDIUM, COMPLEXITY_HIGH = 10, 20
LENGTH_MEDIUM, LENGTH_HIGH = 60, 120
MAX_NESTING = 4
MAX_PARAMS = 7

_SECRET_NAME = re.compile(r"(?i)(password|passwd|pwd|secret|token|api_?key|clave|contrase(n|ñ)a|private_?key)")
_SECRET_PLACEHOLDER = re.compile(
    r"(?i)^(|x+|\*+|changeme|cambiar.*|tu_.*|your_.*|<.*>|\$\{.*\}|\{.*\}|%\(.*\)s|example|ejemplo|test.*|dummy|password|pass|secret|contrase(n|ñ)a)$"
)
_CONNECTION_SECRET = re.compile(r"(?i)\b(?:pwd|password)\s*=\s*([^;'\"\s][^;'\"]{2,})")
_TODO = re.compile(r"#.*\b(TODO|FIXME|XXX|HACK)\b")
_BRANCHES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler, ast.Assert, ast.comprehension)
_BLOCKS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "request"}
_SQL_HINT = re.compile(r"(?i)\b(select|insert|update|delete|exec|merge)\b")


@dataclass(frozen=True)
class Finding:
    archivo: str
    linea: int
    regla: str
    categoria: str
    severidad: str
    mensaje: str


@dataclass(frozen=True)
class FunctionMetrics:
    archivo: str
    nombre: str
    linea: int
    lineas: int
    complejidad: int
    anidamiento: int
    parametros: int


def looks_like_secret(value: str) -> bool:
    """Texto con forma de credencial: 8+ caracteres, sin espacios y al menos dos clases (letras, dígitos, símbolos)."""
    text = value.strip()
    if len(text) < 8 or " " in text or _SECRET_PLACEHOLDER.match(text):
        return False
    classes = (any(c.isalpha() for c in text), any(c.isdigit() for c in text), any(not c.isalnum() for c in text))
    return sum(classes) >= 2 or len(text) >= 24


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _keyword(call: ast.Call, name: str) -> Optional[ast.expr]:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _is_true(node: Optional[ast.expr]) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


_CONSTANT_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]*$")


def _is_str(node: ast.expr) -> bool:
    return isinstance(node, ast.JoinedStr) or (isinstance(node, ast.Constant) and isinstance(node.value, str))


def _is_constant_reference(node: ast.expr) -> bool:
    """NOMBRE o self._NOMBRE: constantes por convención (listas de columnas, etc.)."""
    return isinstance(node, (ast.Name, ast.Attribute)) and bool(_CONSTANT_NAME.match(_dotted(node).rsplit(".", 1)[-1]))


def _is_dynamic_string(node: ast.expr) -> bool:
    """f-string, '...' % x, '...'.format(...) o concatenación de texto con valores no constantes."""
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) and not _is_constant_reference(v.value) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return _is_str(node.left)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        sides = (node.left, node.right)
        stringy = any(_is_str(s) or _is_dynamic_string(s) for s in sides)
        return stringy and not all(isinstance(s, ast.Constant) or _is_constant_reference(s) for s in sides)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        return _is_str(node.func.value)
    return False


def _string_text(node: ast.expr) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(node, ast.BinOp):
        return _string_text(node.left) + _string_text(node.right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return _string_text(node.func.value)
    return ""


def _complexity(function: ast.AST) -> int:
    total = 1
    stack = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(node, _BRANCHES):
            total += 1
        if isinstance(node, ast.comprehension):
            total += len(node.ifs)
        elif isinstance(node, ast.BoolOp):
            total += len(node.values) - 1
        elif hasattr(ast, "match_case") and isinstance(node, ast.match_case):
            total += 1
        stack.extend(ast.iter_child_nodes(node))
    return total


def _nesting(node: ast.AST, depth: int = 0) -> int:
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        deepest = max(deepest, _nesting(child, depth + 1 if isinstance(child, _BLOCKS) else depth))
    return deepest


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str, is_test: bool) -> None:
        self.path = path
        self.is_test = is_test
        self.findings: List[Finding] = []
        self.functions: List[FunctionMetrics] = []
        self.classes = 0

    def add(self, node: ast.AST, rule: str, category: str, severity: str, message: str) -> None:
        self.findings.append(Finding(self.path, getattr(node, "lineno", 0), rule, category, severity, message))

    # ------------------------------------------------------------ estructura

    def _function(self, node) -> None:
        length = (node.end_lineno or node.lineno) - node.lineno + 1
        complexity = _complexity(node)
        nesting = _nesting(node)
        args = node.args
        params = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
        if args.args and args.args[0].arg in ("self", "cls"):
            params -= 1
        self.functions.append(FunctionMetrics(self.path, node.name, node.lineno, length, complexity, nesting, params))
        if complexity > COMPLEXITY_HIGH:
            self.add(node, "complejidad_alta", "complejidad", "alta", f"{node.name}: complejidad ciclomática {complexity} (> {COMPLEXITY_HIGH})")
        elif complexity > COMPLEXITY_MEDIUM:
            self.add(node, "complejidad_media", "complejidad", "media", f"{node.name}: complejidad ciclomática {complexity} (> {COMPLEXITY_MEDIUM})")
        if length > LENGTH_HIGH:
            self.add(node, "funcion_muy_larga", "mantenibilidad", "alta", f"{node.name}: {length} líneas (> {LENGTH_HIGH})")
        elif length > LENGTH_MEDIUM:
            self.add(node, "funcion_larga", "mantenibilidad", "media", f"{node.name}: {length} líneas (> {LENGTH_MEDIUM})")
        if nesting > MAX_NESTING:
            self.add(node, "anidamiento_profundo", "complejidad", "media", f"{node.name}: {nesting} niveles de anidamiento (> {MAX_NESTING})")
        if params > MAX_PARAMS:
            self.add(node, "demasiados_parametros", "mantenibilidad", "baja", f"{node.name}: {params} parámetros (> {MAX_PARAMS})")
        if not self.is_test and not node.name.startswith("_") and length > 15 and ast.get_docstring(node) is None:
            self.add(node, "sin_docstring", "mantenibilidad", "baja", f"{node.name}: función pública de {length} líneas sin docstring")
        self.generic_visit(node)

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes += 1
        if not self.is_test and not node.name.startswith("_") and ast.get_docstring(node) is None:
            body_lines = (node.end_lineno or node.lineno) - node.lineno + 1
            if body_lines > 30:
                self.add(node, "sin_docstring", "mantenibilidad", "baja", f"clase {node.name} sin docstring")
        self.generic_visit(node)

    # ------------------------------------------------------------ seguridad

    _DANGEROUS_CALLS = {
        "eval": ("ejecucion_dinamica", "critica", "ejecuta código arbitrario (OWASP A03)"),
        "exec": ("ejecucion_dinamica", "critica", "ejecuta código arbitrario (OWASP A03)"),
        "builtins.eval": ("ejecucion_dinamica", "critica", "ejecuta código arbitrario (OWASP A03)"),
        "builtins.exec": ("ejecucion_dinamica", "critica", "ejecuta código arbitrario (OWASP A03)"),
        "os.system": ("comando_shell", "alta", "pasa la orden a la shell (OWASP A03)"),
        "os.popen": ("comando_shell", "alta", "pasa la orden a la shell (OWASP A03)"),
        "pickle.loads": ("deserializacion_insegura", "alta", "con datos no confiables ejecuta código (OWASP A08)"),
        "pickle.load": ("deserializacion_insegura", "alta", "con datos no confiables ejecuta código (OWASP A08)"),
        "marshal.loads": ("deserializacion_insegura", "alta", "con datos no confiables ejecuta código (OWASP A08)"),
        "dill.loads": ("deserializacion_insegura", "alta", "con datos no confiables ejecuta código (OWASP A08)"),
    }

    def _dangerous_call(self, node: ast.Call, name: str) -> None:
        if name in self._DANGEROUS_CALLS:
            rule, severity, message = self._DANGEROUS_CALLS[name]
            self.add(node, rule, "seguridad", severity, f"{name}() {message}")
        elif name.startswith("subprocess.") and _is_true(_keyword(node, "shell")):
            self.add(node, "subprocess_shell", "seguridad", "alta", f"{name}(shell=True) permite inyección de comandos (OWASP A03)")
        elif name == "yaml.load" and "Safe" not in _dotted(_keyword(node, "Loader") or ast.Name(id="")):
            self.add(node, "yaml_inseguro", "seguridad", "alta", "yaml.load sin SafeLoader (usa yaml.safe_load)")
        elif name in ("hashlib.md5", "hashlib.sha1"):
            flag = _keyword(node, "usedforsecurity")
            if not (isinstance(flag, ast.Constant) and flag.value is False):
                self.add(node, "hash_debil", "seguridad", "media", f"{name} no es apto para seguridad (OWASP A02)")

    def _network_call(self, node: ast.Call, name: str) -> None:
        is_http = name.startswith(("requests.", "httpx.")) and name.rsplit(".", 1)[-1] in _HTTP_METHODS
        if (is_http or name == "urllib.request.urlopen") and _keyword(node, "timeout") is None:
            self.add(node, "http_sin_timeout", "fiabilidad", "media", f"{name}() sin timeout puede bloquear el proceso")
        verify = _keyword(node, "verify")
        if isinstance(verify, ast.Constant) and verify.value is False:
            self.add(node, "tls_sin_verificar", "seguridad", "alta", "verify=False desactiva la validación TLS (OWASP A02)")

    def _sql_call(self, node: ast.Call, name: str) -> None:
        if name.rsplit(".", 1)[-1] not in ("execute", "executemany", "exec_driver_sql") or not node.args:
            return
        query = node.args[0]
        if _is_dynamic_string(query) and _SQL_HINT.search(_string_text(query) or "select"):
            self.add(node, "sql_interpolado", "seguridad", "alta", "SQL construido con interpolación de texto; usa parámetros (OWASP A03)")

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted(node.func)
        self._dangerous_call(node, name)
        self._network_call(node, name)
        self._sql_call(node, name)
        self.generic_visit(node)

    def _secret_assignment(self, node: ast.AST, target: ast.expr, value: Optional[ast.expr]) -> None:
        name = _dotted(target) if not isinstance(target, ast.Constant) else str(target.value)
        if not name or not _SECRET_NAME.search(name.rsplit(".", 1)[-1]):
            return
        if isinstance(value, ast.Constant) and isinstance(value.value, str) and not self.is_test and looks_like_secret(value.value):
            self.add(node, "secreto_en_codigo", "seguridad", "critica", f"{name}: credencial escrita en el código (OWASP A07)")

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._secret_assignment(node, target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._secret_assignment(node, node.target, node.value)
        self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> None:
        if node.arg:
            self._secret_assignment(node.value, ast.Name(id=node.arg), node.value)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                self._secret_assignment(value, key, value)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and not self.is_test:
            match = _CONNECTION_SECRET.search(node.value)
            if match and not _SECRET_PLACEHOLDER.match(match.group(1).strip()):
                self.add(node, "secreto_en_cadena_conexion", "seguridad", "critica", "Cadena de conexión con contraseña en el código (OWASP A07)")

    # ------------------------------------------------------------ errores

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.add(node, "except_desnudo", "fiabilidad", "media", "except: sin tipo captura también KeyboardInterrupt/SystemExit")
        elif len(node.body) == 1 and isinstance(node.body[0], ast.Pass) and _dotted(node.type) in ("Exception", "BaseException"):
            self.add(node, "error_silenciado", "fiabilidad", "baja", "except Exception: pass oculta errores")
        self.generic_visit(node)


def _code_lines(source: str) -> int:
    return sum(1 for line in source.splitlines() if line.strip() and not line.strip().startswith("#"))


def analyze_source(path: str, source: str) -> Tuple[List[Finding], List[FunctionMetrics], Dict[str, int], Optional[str]]:
    is_test = "/tests/" in f"/{path}" or path.rsplit("/", 1)[-1].startswith("test_")
    source = source.lstrip("\ufeff")
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as e:
        finding = Finding(path, e.lineno or 0, "error_sintaxis", "fiabilidad", "critica", f"Error de sintaxis: {e.msg}")
        return [finding], [], {"lineas": _code_lines(source), "clases": 0}, e.msg
    visitor = _Visitor(path, is_test)
    visitor.visit(tree)
    for number, line in enumerate(source.splitlines(), start=1):
        if _TODO.search(line):
            visitor.findings.append(Finding(path, number, "pendiente", "mantenibilidad", "baja", line.strip()[:120]))
    return visitor.findings, visitor.functions, {"lineas": _code_lines(source), "clases": visitor.classes}, None


def score(findings: Iterable[Finding], lines: int) -> float:
    counts = {s: 0 for s in SEVERITIES}
    for f in findings:
        counts[f.severidad] += 1
    per_kloc = sum(counts[s] * WEIGHTS[s] for s in ("alta", "media", "baja")) * 1000 / max(lines, 1000)
    penalty = counts["critica"] * WEIGHTS["critica"] + per_kloc
    return round(max(0.0, 10.0 - min(10.0, penalty)), 2)


def analyze_files(sources: Dict[str, str], max_findings: int = 500) -> Dict[str, object]:
    findings: List[Finding] = []
    functions: List[FunctionMetrics] = []
    lines = classes = 0
    syntax_errors = []
    for path, source in sources.items():
        file_findings, file_functions, stats, error = analyze_source(path, source)
        findings += file_findings
        functions += file_functions
        lines += stats["lineas"]
        classes += stats["clases"]
        if error:
            syntax_errors.append({"archivo": path, "error": error})
    ordered = sorted(findings, key=lambda f: (SEVERITIES.index(f.severidad), f.archivo, f.linea))
    complexities = [f.complejidad for f in functions]
    by_severity = {s: sum(1 for f in findings if f.severidad == s) for s in SEVERITIES}
    by_category: Dict[str, int] = {}
    for f in findings:
        by_category[f.categoria] = by_category.get(f.categoria, 0) + 1
    return {
        "archivos": len(sources),
        "lineas_codigo": lines,
        "funciones": len(functions),
        "clases": classes,
        "complejidad_promedio": round(sum(complexities) / len(complexities), 2) if complexities else 0,
        "complejidad_maxima": max(complexities, default=0),
        "funciones_mas_complejas": [asdict(f) for f in sorted(functions, key=lambda f: f.complejidad, reverse=True)[:10]],
        "puntuacion": score(findings, lines),
        "por_severidad": by_severity,
        "por_categoria": by_category,
        "total_hallazgos": len(findings),
        "hallazgos": [asdict(f) for f in ordered[:max_findings]],
        "hallazgos_truncados": len(ordered) > max_findings,
        "errores_sintaxis": syntax_errors,
    }
