"""
Casos de uso de Vector: análisis estático del repositorio, plantillas de módulos y escritura en git
(ramas de trabajo y commits sin checkout; master/main protegidas; no se commitea código con hallazgos críticos).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.agents.common import iso, new_id, utcnow
from src.agents.development_agent import analyzer, scaffold
from src.agents.development_agent.repository import AnalysisRecord, AnalysisRepository
from src.agents.git_tools import GitRepository, check_branch, check_ref, check_repo_path, domain_errors
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError

VERSION = "1.0.0"
ANALYSIS_ROOTS = ("src", "tests", "scripts")
WRITE_ROOTS = ("src", "tests", "scripts", "docs", "sql")
SKIP_DIRS = frozenset({"__pycache__", "venv", ".venv", "node_modules", ".git"})
SNIPPET_NAME = re.compile(r"^[A-Za-z0-9_.\-]{1,100}$")
MAX_FILES = 2000
MAX_FILE_BYTES = 200_000
MAX_COMMIT_FILES = 50


def commit_timestamp(moment: datetime) -> str:
    return moment.strftime("%d%m%Y %H:%M:%S")


class VectorService:
    def __init__(self, git: GitRepository, repository: AnalysisRepository, clock: Callable = utcnow,
                 local_clock: Callable[[], datetime] = datetime.now) -> None:
        self._git = git
        self._repo = repository
        self._clock = clock
        self._local_clock = local_clock

    @property
    def repo_path(self) -> str:
        return self._git.path

    def ping(self) -> None:
        self._repo.ping()

    def git_status(self) -> Dict[str, Any]:
        with domain_errors():
            return {"rama": self._git.current_branch(), "commit": self._git.head()}

    # ================================================================ análisis

    def _collect(self, rutas: List[str], tracked_only: bool = True) -> Dict[str, str]:
        """Archivos .py de las rutas; en directorios solo los versionados en git salvo tracked_only=False."""
        root = Path(self._git.path)
        files: Dict[str, Path] = {}
        for raw in rutas or ["src"]:
            with domain_errors():
                relative = check_repo_path(raw, ANALYSIS_ROOTS)
            full = (root / relative).resolve()
            if root not in full.parents and full != root:
                raise InvalidInputError(f"Ruta fuera del repositorio: {raw!r}")
            if full.is_file():
                candidates = [full] if full.suffix == ".py" else []
            elif full.is_dir() and tracked_only:
                with domain_errors():
                    tracked = self._git.tracked_files(relative)
                candidates = [root / p for p in tracked if p.endswith(".py") and (root / p).is_file()]
            elif full.is_dir():
                candidates = [p for p in sorted(full.rglob("*.py")) if not SKIP_DIRS.intersection(p.relative_to(root).parts)]
            else:
                raise NotFoundError(f"No existe la ruta: {relative}")
            for path in candidates:
                files[path.relative_to(root).as_posix()] = path
            if len(files) > MAX_FILES:
                raise InvalidInputError(f"Demasiados archivos (máx. {MAX_FILES}); acota las rutas")
        if not files:
            raise InvalidInputError("No hay archivos .py en las rutas indicadas")
        return {rel: path.read_text(encoding="utf-8-sig", errors="replace") for rel, path in files.items()
                if path.stat().st_size <= MAX_FILE_BYTES}

    def _record(self, actor: str, target: str, result: Dict[str, Any]) -> Dict[str, Any]:
        record = AnalysisRecord(
            id_analisis=new_id("va"), objetivo=target, archivos=result["archivos"], lineas=result["lineas_codigo"],
            puntuacion=result["puntuacion"], criticos=result["por_severidad"]["critica"], altos=result["por_severidad"]["alta"],
            analizado_por=actor, fecha=self._clock(),
            resumen={k: result[k] for k in ("por_severidad", "por_categoria", "complejidad_promedio", "complejidad_maxima")}
            | {"hallazgos_principales": result["hallazgos"][:50]},
        )
        self._repo.save(record)
        return {"id_analisis": record.id_analisis, "objetivo": target, "fecha": iso(record.fecha), **result}

    def analyze_paths(self, actor: str, rutas: List[str], solo_versionados: bool = True) -> Dict[str, Any]:
        sources = self._collect(rutas, solo_versionados)
        return self._record(actor, ", ".join(rutas or ["src"]), analyzer.analyze_files(sources))

    def analyze_code(self, actor: str, codigo: str, nombre: str = "fragmento.py") -> Dict[str, Any]:
        if not SNIPPET_NAME.match(nombre or ""):
            raise InvalidInputError("nombre: letras, números, '_', '.' o '-' (máx. 100)")
        if not codigo.strip() or len(codigo.encode("utf-8")) > MAX_FILE_BYTES:
            raise InvalidInputError(f"codigo es obligatorio (máx. {MAX_FILE_BYTES} bytes)")
        return self._record(actor, f"fragmento:{nombre}", analyzer.analyze_files({nombre: codigo}))

    def history(self, limit: int = 20) -> Dict[str, Any]:
        records = self._repo.recent(max(1, min(limit, 200)))
        return {
            "total": len(records),
            "analisis": [
                {"id_analisis": r.id_analisis, "objetivo": r.objetivo, "archivos": r.archivos, "lineas": r.lineas,
                 "puntuacion": r.puntuacion, "criticos": r.criticos, "altos": r.altos,
                 "analizado_por": r.analizado_por, "fecha": iso(r.fecha), "resumen": r.resumen}
                for r in records
            ],
        }

    def security_gate(self, rutas: Optional[List[str]] = None) -> Dict[str, Any]:
        """Hallazgos críticos en el código del repositorio (usado por la compuerta de calidad de Prism)."""
        result = analyzer.analyze_files(self._collect(rutas or ["src"]))
        criticals = [f for f in result["hallazgos"] if f["severidad"] == "critica"]
        return {"puntuacion": result["puntuacion"], "criticos": len(criticals), "hallazgos_criticos": criticals[:20],
                "por_severidad": result["por_severidad"]}

    # ================================================================ git (lectura)

    def branches(self) -> Dict[str, Any]:
        with domain_errors():
            return {"actual": self._git.current_branch(), "ramas": self._git.branches()}

    def commits(self, rama: str, limite: int = 20) -> Dict[str, Any]:
        with domain_errors():
            ref = check_ref(rama)
            if self._git.resolve(ref) is None:
                raise NotFoundError(f"No existe la referencia {ref!r}")
            commits = self._git.log(ref, limite)
        return {"rama": ref, "total": len(commits), "commits": commits}

    def diff(self, base: str, destino: str) -> Dict[str, Any]:
        with domain_errors():
            for ref in (base, destino):
                if self._git.resolve(ref) is None:
                    raise NotFoundError(f"No existe la referencia {ref!r}")
            return self._git.diff(base, destino)

    # ================================================================ git (escritura)

    def create_branch(self, nombre: str, base: str = "HEAD") -> Dict[str, Any]:
        with domain_errors():
            base_sha = self._git.create_branch(nombre, base)
        return {"rama": nombre, "base": base, "commit": base_sha}

    def _commit(self, actor: str, rama: str, base: str, files: Dict[str, str], mensaje: str) -> Dict[str, Any]:
        python = {p: c for p, c in files.items() if p.endswith(".py")}
        review = analyzer.analyze_files(python) if python else None
        if review and review["por_severidad"]["critica"]:
            blocking = [f for f in review["hallazgos"] if f["severidad"] == "critica"][:10]
            raise ConflictError("Vector no commitea código con hallazgos críticos: "
                                + "; ".join(f"{f['archivo']}:{f['linea']} {f['mensaje']}" for f in blocking))
        message = f"{mensaje.strip()}\n\nCommit generado por Vector para {actor}. {commit_timestamp(self._local_clock())}"
        with domain_errors():
            result = self._git.commit_files(rama, files, message, base)
        return {**result, "archivos": sorted(files), "mensaje": message,
                "revision": {k: review[k] for k in ("puntuacion", "por_severidad", "total_hallazgos")} if review else None}

    def _validated_files(self, archivos: Dict[str, str]) -> Dict[str, str]:
        if not 1 <= len(archivos) <= MAX_COMMIT_FILES:
            raise InvalidInputError(f"Envía entre 1 y {MAX_COMMIT_FILES} archivos")
        clean: Dict[str, str] = {}
        for path, content in archivos.items():
            with domain_errors():
                relative = check_repo_path(path, WRITE_ROOTS)
            if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_FILE_BYTES:
                raise InvalidInputError(f"{relative}: el contenido debe ser texto de máximo {MAX_FILE_BYTES} bytes")
            clean[relative] = content
        return clean

    def commit_files(self, actor: str, rama: str, archivos: Dict[str, str], mensaje: str, base: str = "HEAD") -> Dict[str, Any]:
        if not 3 <= len((mensaje or "").strip()) <= 500:
            raise InvalidInputError("mensaje: entre 3 y 500 caracteres")
        return self._commit(actor, rama, base, self._validated_files(archivos), mensaje)

    # ================================================================ plantillas

    def _generate(self, spec: Dict[str, Any]) -> Dict[str, str]:
        try:
            return scaffold.generate(spec.get("modulo", ""), spec.get("entidad") or "", spec.get("campos") or [])
        except scaffold.ScaffoldError as e:
            raise InvalidInputError(str(e))

    def scaffold_preview(self, spec: Dict[str, Any], base: str = "HEAD") -> Dict[str, Any]:
        files = self._generate(spec)
        with domain_errors():
            existing = [p for p in files if self._git.file_exists(base, p)]
        review = analyzer.analyze_files({p: c for p, c in files.items() if p.endswith(".py")})
        return {
            "archivos": [{"ruta": p, "lineas": c.count("\n"), "contenido": c} for p, c in files.items()],
            "ya_existen": existing,
            "revision": {k: review[k] for k in ("puntuacion", "por_severidad", "total_hallazgos", "hallazgos")},
            "siguientes_pasos": [
                f"Aplicar {next(p for p in files if p.startswith('sql/'))} en SQL Server",
                f"Montar src/api/routes/{spec.get('modulo')}_routes.py en src/api/main.py",
            ],
        }

    def scaffold_apply(self, actor: str, spec: Dict[str, Any], rama: str, base: str = "HEAD",
                       mensaje: Optional[str] = None, sobrescribir: bool = False) -> Dict[str, Any]:
        with domain_errors():
            check_branch(rama)
            tip = rama if self._git.branch_exists(rama) else base
            files = self._generate(spec)
            existing = [p for p in files if self._git.file_exists(tip, p)]
        if existing and not sobrescribir:
            raise ConflictError(f"Ya existen en {tip}: {', '.join(existing)} (usa sobrescribir=true para reemplazarlos)")
        message = mensaje or f"Vector: módulo {spec.get('modulo')} generado desde plantilla (repositorio, servicio, API, pruebas y DDL)"
        return self._commit(actor, rama, base, files, message)
