"""
Casos de uso de Prism: ejecución asíncrona de pytest con cobertura, descubrimiento de pruebas, lint, conflictos
entre reglas de Matrix y la compuerta de calidad que consume Orbit antes de liberar un commit.
"""

from __future__ import annotations

import ast
import logging
import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.agents.business_rules_agent.agent import BusinessRule
from src.agents.common import iso, new_id, utcnow
from src.agents.git_tools import GitRepository, check_repo_path, domain_errors
from src.agents.qa_agent.conflicts import find_conflicts
from src.agents.qa_agent.repository import QUEUED, RUNNING, TestRun, TestRunRepository
from src.agents.qa_agent.runner import ERROR, TestRunner
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError

logger = logging.getLogger(__name__)

VERSION = "1.0.0"
TEST_ROOTS = ("tests",)
LINT_ROOTS = ("src", "tests", "scripts")
DEFAULT_TARGETS = ["tests"]
NODE_ID = re.compile(r"^[\w\[\]\-.:]{1,200}$")
KEYWORD = re.compile(r"^[\w][\w\s\-.\[\]()]{0,199}$")
MAX_TARGETS = 20

RulesSource = Callable[[Optional[int]], List[BusinessRule]]
SecurityGate = Callable[[], Dict[str, Any]]
Submit = Callable[[Callable[[], None]], Any]


def count_tests(source: str) -> int:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    total = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            total += 1
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            total += sum(1 for n in node.body
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"))
    return total


def run_view(run: TestRun, detail: bool = False) -> Dict[str, Any]:
    view = {
        "id_ejecucion": run.id_ejecucion, "estado": run.estado, "objetivos": run.objetivos, "filtro": run.filtro,
        "con_cobertura": run.con_cobertura, "suite_completa": run.suite_completa, "commit": run.commit_git,
        "arbol_limpio": run.arbol_limpio, "total": run.total, "pasadas": run.pasadas, "fallidas": run.fallidas,
        "omitidas": run.omitidas, "errores": run.errores, "cobertura": run.cobertura, "duracion_s": run.duracion_s,
        "iniciada_por": run.iniciada_por, "fecha_inicio": iso(run.fecha_inicio), "fecha_fin": iso(run.fecha_fin),
        "mensaje": run.detalle.get("mensaje"),
    }
    if detail:
        view.update({k: run.detalle.get(k, []) for k in ("fallos", "cobertura_archivos")})
        view["salida"] = run.detalle.get("salida", "")
    return view


class PrismService:
    def __init__(self, runner: TestRunner, repository: TestRunRepository, git: GitRepository,
                 rules_source: Optional[RulesSource] = None, security_gate: Optional[SecurityGate] = None,
                 min_coverage: float = 80.0, clock: Callable = utcnow, submit: Optional[Submit] = None) -> None:
        self._runner = runner
        self._repo = repository
        self._git = git
        self._rules = rules_source
        self._security = security_gate
        self.min_coverage = min_coverage
        self._clock = clock
        self._submit = submit or ThreadPoolExecutor(max_workers=1, thread_name_prefix="prism").submit
        self._lock = threading.Lock()
        self._active: Optional[str] = None

    def ping(self) -> None:
        self._repo.ping()

    def recover(self) -> int:
        abandoned = self._repo.abandon_unfinished(self._clock())
        if abandoned:
            logger.warning("Prism marcó %s ejecuciones interrumpidas como error", abandoned)
        return abandoned

    @property
    def active_run(self) -> Optional[str]:
        return self._active

    # ================================================================ descubrimiento y lint

    def discover(self) -> Dict[str, Any]:
        root = Path(self._git.path)
        with domain_errors():
            tracked = [p for p in self._git.tracked_files("tests") if Path(p).name.startswith("test_") and p.endswith(".py")]
        files = []
        for rel in tracked:
            path = root / rel
            if path.is_file():
                files.append({"archivo": rel, "pruebas": count_tests(path.read_text(encoding="utf-8-sig", errors="replace"))})
        by_suite: Counter = Counter()
        for f in files:
            parts = f["archivo"].split("/")
            by_suite[parts[1] if len(parts) > 2 else "raiz"] += f["pruebas"]
        return {"archivos": len(files), "total_pruebas": sum(f["pruebas"] for f in files),
                "por_suite": dict(by_suite), "detalle": sorted(files, key=lambda f: f["archivo"])}

    def lint(self, rutas: Optional[List[str]] = None) -> Dict[str, Any]:
        paths = []
        for raw in rutas or ["src"]:
            with domain_errors():
                paths.append(check_repo_path(raw, LINT_ROOTS))
        return {"rutas": paths, **self._runner.lint(paths)}

    def rule_conflicts(self, id_empresa: Optional[int] = None) -> Dict[str, Any]:
        if self._rules is None:
            raise RuntimeError("Matrix no está disponible para Prism")
        return find_conflicts(self._rules(id_empresa))

    # ================================================================ ejecuciones

    @staticmethod
    def _targets(objetivos: Optional[List[str]]) -> List[str]:
        targets = objetivos or DEFAULT_TARGETS
        if len(targets) > MAX_TARGETS:
            raise InvalidInputError(f"Máximo {MAX_TARGETS} objetivos")
        clean = []
        for raw in targets:
            path, sep, node = (raw or "").partition("::")
            with domain_errors():
                path = check_repo_path(path, TEST_ROOTS)
            if sep and not NODE_ID.match(node):
                raise InvalidInputError(f"Identificador de prueba inválido: {raw!r}")
            clean.append(f"{path}::{node}" if sep else path)
        return clean

    def start_run(self, actor: str, objetivos: Optional[List[str]] = None, filtro: Optional[str] = None,
                  con_cobertura: bool = True) -> Dict[str, Any]:
        targets = self._targets(objetivos)
        keyword = (filtro or "").strip() or None
        if keyword and not KEYWORD.match(keyword):
            raise InvalidInputError("filtro: expresión -k con letras, números, espacios, '_', '-', '.', '[]' o '()'")
        with domain_errors():
            commit, clean = self._git.head(), self._git.tracked_clean()
        with self._lock:
            if self._active is not None:
                raise ConflictError(f"Ya hay una ejecución en curso: {self._active}")
            run = TestRun(
                id_ejecucion=new_id("pe"), objetivos=targets, filtro=keyword, con_cobertura=con_cobertura,
                suite_completa=targets == DEFAULT_TARGETS and keyword is None, estado=QUEUED, commit_git=commit,
                arbol_limpio=clean, iniciada_por=actor, fecha_inicio=self._clock(),
            )
            self._repo.create(run)
            self._active = run.id_ejecucion
        try:
            self._submit(lambda: self._execute(run))
        except Exception:
            self._finish(replace(run, estado=ERROR, fecha_fin=self._clock(), detalle={"mensaje": "No se pudo encolar"}))
            raise
        return run_view(run)

    def _finish(self, run: TestRun) -> None:
        try:
            self._repo.update(run)
        finally:
            with self._lock:
                self._active = None

    def _execute(self, run: TestRun) -> None:
        running = replace(run, estado=RUNNING)
        try:
            self._repo.update(running)
            outcome = self._runner.run(run.objetivos, run.filtro, run.con_cobertura)
            final = replace(
                running, estado=outcome.estado, total=outcome.total, pasadas=outcome.pasadas, fallidas=outcome.fallidas,
                omitidas=outcome.omitidas, errores=outcome.errores, cobertura=outcome.cobertura,
                duracion_s=outcome.duracion_s, fecha_fin=self._clock(),
                detalle={"mensaje": outcome.mensaje, "fallos": outcome.fallos,
                         "cobertura_archivos": outcome.cobertura_archivos, "salida": outcome.salida},
            )
        except Exception as e:
            logger.exception("Prism: la ejecución %s falló", run.id_ejecucion)
            final = replace(running, estado=ERROR, fecha_fin=self._clock(), detalle={"mensaje": f"Error interno: {type(e).__name__}"})
        self._finish(final)

    def get_run(self, id_ejecucion: str) -> Dict[str, Any]:
        run = self._repo.get(id_ejecucion)
        if run is None:
            raise NotFoundError(f"Ejecución no encontrada: {id_ejecucion}")
        return run_view(run, detail=True)

    def list_runs(self, limite: int = 20, estado: Optional[str] = None) -> Dict[str, Any]:
        runs = self._repo.recent(max(1, min(limite, 200)), estado)
        return {"total": len(runs), "en_curso": self._active, "ejecuciones": [run_view(r) for r in runs]}

    # ================================================================ compuerta de calidad

    def quality_gate(self, ref: str = "HEAD") -> Dict[str, Any]:
        with domain_errors():
            commit = self._git.resolve(ref)
        if commit is None:
            raise NotFoundError(f"No existe la referencia {ref!r}")
        run = self._repo.latest_full_run(commit)
        checks = [
            {"nombre": "pruebas", "aprobado": bool(run and run.estado == "aprobada"),
             "detalle": f"{run.pasadas}/{run.total} pasadas ({run.estado})" if run
             else "No hay ejecución completa con cobertura para este commit"},
            {"nombre": "cobertura", "aprobado": bool(run and run.cobertura is not None and run.cobertura >= self.min_coverage),
             "detalle": f"{run.cobertura if run else None}% (mínimo {self.min_coverage}%)"},
            {"nombre": "arbol_limpio", "aprobado": bool(run and run.arbol_limpio),
             "detalle": "Las pruebas corrieron sin cambios locales en archivos versionados" if run and run.arbol_limpio
             else "Las pruebas no corrieron sobre un árbol limpio"},
        ]
        if self._security is not None:
            security = self._security()
            checks.append({"nombre": "seguridad", "aprobado": security["criticos"] == 0,
                           "detalle": f"{security['criticos']} hallazgos críticos (Vector, puntuación {security['puntuacion']})",
                           "hallazgos": security.get("hallazgos_criticos", [])})
        return {"commit": commit, "referencia": ref, "aprobada": all(c["aprobado"] for c in checks),
                "cobertura_minima": self.min_coverage, "id_ejecucion": run.id_ejecucion if run else None,
                "comprobaciones": checks}

    # ================================================================ métricas

    def metrics(self, dias: int = 30) -> Dict[str, Any]:
        since = self._clock() - timedelta(days=max(1, min(dias, 365)))
        runs = [r for r in self._repo.recent(1000) if r.fecha_inicio >= since and r.estado not in (QUEUED, RUNNING)]
        approved = sum(1 for r in runs if r.estado == "aprobada")
        failures: Counter = Counter(f["prueba"] for r in runs for f in r.detalle.get("fallos", []))
        coverage = [{"fecha": iso(r.fecha_inicio), "commit": r.commit_git, "cobertura": r.cobertura}
                    for r in reversed(runs) if r.suite_completa and r.cobertura is not None]
        return {
            "dias": dias, "ejecuciones": len(runs), "aprobadas": approved,
            "fallidas": sum(1 for r in runs if r.estado == "fallida"), "con_error": sum(1 for r in runs if r.estado == ERROR),
            "tasa_aprobacion": round(100 * approved / len(runs), 2) if runs else None,
            "duracion_promedio_s": round(sum(r.duracion_s for r in runs) / len(runs), 2) if runs else None,
            "cobertura_actual": coverage[-1]["cobertura"] if coverage else None, "cobertura_minima": self.min_coverage,
            "tendencia_cobertura": coverage[-30:],
            "pruebas_mas_fallidas": [{"prueba": n, "fallos": c} for n, c in failures.most_common(10)],
        }
