"""Ejecución real de pruebas y lint para Prism: pytest (JUnit XML + cobertura JSON) y flake8 en subprocesos."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

APPROVED, FAILED, ERROR = "aprobada", "fallida", "error"
_PYTEST_EXIT = {2: "ejecución interrumpida", 3: "error interno de pytest", 4: "uso incorrecto de pytest", 5: "no se recolectó ninguna prueba"}


@dataclass
class RunOutcome:
    estado: str
    total: int = 0
    pasadas: int = 0
    fallidas: int = 0
    omitidas: int = 0
    errores: int = 0
    duracion_s: float = 0.0
    cobertura: Optional[float] = None
    fallos: List[Dict[str, str]] = field(default_factory=list)
    cobertura_archivos: List[Dict[str, Any]] = field(default_factory=list)
    mensaje: Optional[str] = None
    salida: str = ""


class TestRunner(ABC):
    __test__ = False

    @abstractmethod
    def run(self, targets: List[str], keyword: Optional[str], coverage: bool) -> RunOutcome: ...

    @abstractmethod
    def lint(self, paths: List[str]) -> Dict[str, Any]: ...


def parse_junit(path: Path) -> Dict[str, Any]:
    root = ET.parse(path).getroot()
    counts = {"total": 0, "pasadas": 0, "fallidas": 0, "omitidas": 0, "errores": 0}
    failures: List[Dict[str, str]] = []
    for case in root.iter("testcase"):
        counts["total"] += 1
        name = f"{case.get('classname', '')}::{case.get('name', '')}".strip(":")
        problem = next((child for child in case if child.tag in ("failure", "error")), None)
        if problem is not None:
            key = "fallidas" if problem.tag == "failure" else "errores"
            counts[key] += 1
            detail = (problem.get("message") or "") + "\n" + (problem.text or "")
            failures.append({"prueba": name, "tipo": problem.tag, "mensaje": detail.strip()[:800]})
        elif any(child.tag == "skipped" for child in case):
            counts["omitidas"] += 1
        else:
            counts["pasadas"] += 1
    return {**counts, "fallos": failures}


def parse_coverage(path: Path, worst: int = 10) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    files = [
        {"archivo": name.replace("\\", "/"), "cobertura": round(info["summary"]["percent_covered"], 2),
         "sentencias": info["summary"]["num_statements"], "sin_cubrir": info["summary"]["missing_lines"]}
        for name, info in data.get("files", {}).items() if info["summary"]["num_statements"]
    ]
    return {"cobertura": round(data["totals"]["percent_covered"], 2),
            "archivos": sorted(files, key=lambda f: (f["cobertura"], -f["sentencias"]))[:worst]}


class PytestRunner(TestRunner):
    def __init__(self, repo_path: str, python: str = sys.executable, timeout_seconds: int = 900,
                 coverage_source: str = "src") -> None:
        self._repo = repo_path
        self._python = python
        self._timeout = timeout_seconds
        self._coverage_source = coverage_source

    def _env(self, tmp: str) -> Dict[str, str]:
        return {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
                "COVERAGE_FILE": os.path.join(tmp, ".coverage")}

    def run(self, targets: List[str], keyword: Optional[str], coverage: bool) -> RunOutcome:
        with tempfile.TemporaryDirectory(prefix="prism-") as tmp:
            junit, cov_json = Path(tmp, "junit.xml"), Path(tmp, "coverage.json")
            command = [self._python, "-m", "pytest", *targets, "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                       "--tb=short", f"--junitxml={junit}"]
            if keyword:
                command += ["-k", keyword]
            if coverage:
                command += [f"--cov={self._coverage_source}", f"--cov-report=json:{cov_json}", "--cov-report="]
            start = time.perf_counter()
            try:
                proc = subprocess.run(command, cwd=self._repo, capture_output=True, timeout=self._timeout,
                                      env=self._env(tmp), check=False)
            except subprocess.TimeoutExpired:
                return RunOutcome(ERROR, duracion_s=round(time.perf_counter() - start, 2),
                                  mensaje=f"pytest superó el tiempo límite de {self._timeout} s")
            duration = round(time.perf_counter() - start, 2)
            output = (proc.stdout + proc.stderr).decode("utf-8", "replace")
            if not junit.exists():
                return RunOutcome(ERROR, duracion_s=duration, salida=output[-4000:],
                                  mensaje=_PYTEST_EXIT.get(proc.returncode, f"pytest terminó con código {proc.returncode}"))
            counts = parse_junit(junit)
            cov = parse_coverage(cov_json) if coverage and cov_json.exists() else {"cobertura": None, "archivos": []}
        if proc.returncode in _PYTEST_EXIT:
            state, message = ERROR, _PYTEST_EXIT[proc.returncode]
        else:
            state = APPROVED if proc.returncode == 0 and counts["total"] and not (counts["fallidas"] or counts["errores"]) else FAILED
            message = None
        return RunOutcome(
            state, counts["total"], counts["pasadas"], counts["fallidas"], counts["omitidas"], counts["errores"], duration,
            cov["cobertura"], counts["fallos"][:50], cov["archivos"], message, output[-4000:],
        )

    def lint(self, paths: List[str]) -> Dict[str, Any]:
        command = [self._python, "-m", "flake8", "--format=%(path)s\t%(row)d\t%(col)d\t%(code)s\t%(text)s", *paths]
        try:
            proc = subprocess.run(command, cwd=self._repo, capture_output=True, timeout=300, check=False)
        except subprocess.TimeoutExpired:
            raise RuntimeError("flake8 superó el tiempo límite")
        if proc.returncode not in (0, 1):
            raise RuntimeError("flake8 no está disponible: " + proc.stderr.decode("utf-8", "replace")[-300:])
        issues = []
        for line in proc.stdout.decode("utf-8", "replace").splitlines():
            parts = line.split("\t")
            if len(parts) == 5:
                issues.append({"archivo": parts[0].replace("\\", "/").removeprefix("./"), "linea": int(parts[1]),
                               "columna": int(parts[2]), "codigo": parts[3], "mensaje": parts[4]})
        by_code: Dict[str, int] = {}
        for issue in issues:
            by_code[issue["codigo"]] = by_code.get(issue["codigo"], 0) + 1
        return {"total": len(issues), "por_codigo": dict(sorted(by_code.items(), key=lambda kv: -kv[1])),
                "problemas": issues[:500], "truncado": len(issues) > 500}
