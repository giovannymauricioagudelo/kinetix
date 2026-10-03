"""
Acceso a git para Orbit y Vector: lectura del repositorio, tags de release y commits sin tocar el árbol de trabajo.

Los commits se construyen con plumbing (hash-object, índice temporal, commit-tree, update-ref): nunca se hace
checkout ni se modifica el índice del desarrollador, y master/main no se pueden escribir.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Dict, Iterator, List, Optional, Sequence

PROTECTED_BRANCHES = frozenset({"master", "main"})
BRANCH = re.compile(r"^(feature|fix|chore|vector)/[a-z0-9][a-z0-9._-]{0,80}$")
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,199}(~\d{1,4}|\^)?$")
TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,199}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
ZERO_SHA = "0" * 40


class GitError(Exception):
    """Fallo de git con un mensaje apto para el cliente (entrada inválida o comando rechazado)."""


class GitUnavailable(GitError):
    """git no está instalado o no respondió a tiempo."""


class GitConflict(GitError):
    pass


class GitRefNotFound(GitError):
    pass


@contextmanager
def domain_errors() -> Iterator[None]:
    """Traduce errores de git a los errores de dominio que la API convierte en 400/404/409 (no disponible → 503)."""
    from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError

    try:
        yield
    except GitUnavailable:
        raise
    except GitConflict as e:
        raise ConflictError(str(e)) from e
    except GitRefNotFound as e:
        raise NotFoundError(str(e)) from e
    except GitError as e:
        raise InvalidInputError(str(e)) from e


def check_ref(ref: str) -> str:
    ref = (ref or "").strip()
    if ref == "HEAD" or SHA.match(ref):
        return ref
    if not REF.match(ref) or ".." in ref or ref.endswith((".lock", "/", ".")) or "//" in ref:
        raise GitError(f"Referencia git inválida: {ref!r}")
    return ref


def check_branch(name: str) -> str:
    name = (name or "").strip()
    if name in PROTECTED_BRANCHES:
        raise GitError(f"La rama {name} está protegida: Vector solo escribe en ramas de trabajo")
    if not BRANCH.match(name) or ".." in name or name.endswith(".lock"):
        raise GitError("La rama debe ser feature/, fix/, chore/ o vector/ seguido de minúsculas, números, '.', '_' o '-'")
    return name


def check_repo_path(path: str, allowed_roots: Sequence[str]) -> str:
    """Ruta relativa POSIX dentro de alguno de los directorios permitidos (sin '..' ni rutas absolutas)."""
    raw = (path or "").replace("\\", "/").strip()
    pure = PurePosixPath(raw)
    if not raw or pure.is_absolute() or ":" in raw or any(part in ("", ".", "..") for part in pure.parts):
        raise GitError(f"Ruta inválida: {path!r}")
    if allowed_roots and pure.parts[0] not in allowed_roots:
        raise GitError(f"Ruta fuera de los directorios permitidos ({', '.join(allowed_roots)}): {path!r}")
    return str(pure)


class GitRepository:
    def __init__(self, path: str, git: str = "git", timeout_seconds: int = 60) -> None:
        self.path = str(Path(path).resolve())
        self._git = git
        self._timeout = timeout_seconds

    def _run(self, *args: str, stdin: Optional[bytes] = None, env: Optional[Dict[str, str]] = None,
             timeout: Optional[int] = None, check: bool = True) -> str:
        full_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", **(env or {})}
        try:
            result = subprocess.run(
                [self._git, "-C", self.path, *args], input=stdin, capture_output=True, env=full_env,
                timeout=timeout or self._timeout, check=False,
            )
        except FileNotFoundError as e:
            raise GitUnavailable("git no está instalado o no está en el PATH") from e
        except subprocess.TimeoutExpired as e:
            raise GitUnavailable(f"git {args[0]} superó el tiempo límite") from e
        if check and result.returncode != 0:
            lines = [line for line in result.stderr.decode("utf-8", "replace").splitlines() if line.strip()]
            raise GitError(f"git {args[0]} falló: {lines[-1] if lines else 'código ' + str(result.returncode)}")
        return result.stdout.decode("utf-8", "replace")

    # ================================================================ lectura

    def resolve(self, ref: str) -> Optional[str]:
        out = self._run("rev-parse", "--verify", "--quiet", f"{check_ref(ref)}^{{commit}}", check=False).strip()
        return out if SHA.match(out) else None

    def head(self) -> str:
        sha = self.resolve("HEAD")
        if sha is None:
            raise GitRefNotFound("El repositorio no tiene commits")
        return sha

    def current_branch(self) -> str:
        return self._run("rev-parse", "--abbrev-ref", "HEAD").strip()

    def status(self) -> Dict[str, object]:
        lines = self._run("status", "--porcelain=v1", "--branch").splitlines()
        header = lines[0][3:] if lines and lines[0].startswith("## ") else ""
        branch, _, tracking = header.partition("...")
        upstream, ahead, behind = None, 0, 0
        if tracking:
            upstream = tracking.split(" ")[0]
            ahead_match = re.search(r"ahead (\d+)", tracking)
            behind_match = re.search(r"behind (\d+)", tracking)
            ahead = int(ahead_match.group(1)) if ahead_match else 0
            behind = int(behind_match.group(1)) if behind_match else 0
        entries = lines[1:]
        untracked = [e[3:] for e in entries if e.startswith("??")]
        changed = [e[3:] for e in entries if not e.startswith("??")]
        return {
            "rama": branch or None,
            "upstream": upstream,
            "adelante": ahead,
            "atras": behind,
            "commit": self.resolve("HEAD"),
            "archivos_modificados": changed,
            "archivos_sin_seguimiento": len(untracked),
            "arbol_limpio": not changed,
        }

    def tracked_clean(self) -> bool:
        return not self._run("status", "--porcelain=v1", "--untracked-files=no").strip()

    def branches(self) -> List[Dict[str, str]]:
        out = self._run("for-each-ref", "refs/heads", "--sort=-committerdate",
                        "--format=%(refname:short)%09%(objectname)%09%(committerdate:iso-strict)%09%(subject)")
        result = []
        for line in out.splitlines():
            name, sha, date, subject = (line.split("\t") + ["", "", "", ""])[:4]
            result.append({"nombre": name, "commit": sha, "fecha": date, "asunto": subject,
                           "protegida": name in PROTECTED_BRANCHES})
        return result

    def branch_exists(self, name: str) -> bool:
        return self.resolve(f"refs/heads/{name}") is not None

    def log(self, ref: str = "HEAD", limit: int = 20) -> List[Dict[str, str]]:
        out = self._run("log", f"--max-count={max(1, min(limit, 500))}", "--format=%H%x1f%an%x1f%aI%x1f%s",
                        check_ref(ref), "--")
        commits = []
        for line in out.splitlines():
            sha, author, date, subject = (line.split("\x1f") + ["", "", "", ""])[:4]
            commits.append({"commit": sha, "autor": author, "fecha": date, "asunto": subject})
        return commits

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        result = subprocess.run(
            [self._git, "-C", self.path, "merge-base", "--is-ancestor", check_ref(ancestor), check_ref(descendant)],
            capture_output=True, timeout=self._timeout, check=False,
        )
        return result.returncode == 0

    def diff(self, base: str, target: str, max_patch_bytes: int = 200_000) -> Dict[str, object]:
        base, target = check_ref(base), check_ref(target)
        files = []
        for line in self._run("diff", "--numstat", "--no-renames", base, target, "--").splitlines():
            added, removed, path = (line.split("\t") + ["", "", ""])[:3]
            files.append({
                "archivo": path,
                "agregadas": int(added) if added.isdigit() else None,
                "eliminadas": int(removed) if removed.isdigit() else None,
            })
        patch = self._run("diff", "--no-color", "--no-renames", base, target, "--")
        encoded = patch.encode("utf-8")
        return {
            "base": base,
            "destino": target,
            "archivos": files,
            "lineas_agregadas": sum(f["agregadas"] or 0 for f in files),
            "lineas_eliminadas": sum(f["eliminadas"] or 0 for f in files),
            "parche": encoded[:max_patch_bytes].decode("utf-8", "ignore"),
            "parche_truncado": len(encoded) > max_patch_bytes,
        }

    def tags(self, pattern: str = "*", limit: int = 50) -> List[Dict[str, str]]:
        out = self._run("for-each-ref", f"refs/tags/{pattern}", "--sort=-creatordate", f"--count={max(1, min(limit, 500))}",
                        "--format=%(refname:short)%09%(*objectname)%09%(objectname)%09%(creatordate:iso-strict)%09%(contents:subject)")
        tags = []
        for line in out.splitlines():
            name, peeled, obj, date, subject = (line.split("\t") + ["", "", "", "", ""])[:5]
            tags.append({"tag": name, "commit": peeled or obj, "fecha": date, "mensaje": subject})
        return tags

    def tracked_files(self, prefix: str) -> List[str]:
        out = self._run("ls-files", "-z", "--", prefix)
        return [p for p in out.split("\0") if p]

    def file_exists(self, ref: str, path: str) -> bool:
        result = subprocess.run(
            [self._git, "-C", self.path, "cat-file", "-e", f"{check_ref(ref)}:{path}"],
            capture_output=True, timeout=self._timeout, check=False,
        )
        return result.returncode == 0

    def remote_url(self, remote: str = "origin") -> Optional[str]:
        url = self._run("remote", "get-url", remote, check=False).strip()
        return url or None

    # ================================================================ escritura

    def create_tag(self, name: str, commit: str, message: str) -> None:
        if not TAG.match(name) or ".." in name:
            raise GitError(f"Nombre de tag inválido: {name!r}")
        self._run("tag", "-a", name, check_ref(commit), "-m", message)

    def delete_tag(self, name: str) -> None:
        if not TAG.match(name):
            raise GitError(f"Nombre de tag inválido: {name!r}")
        self._run("tag", "-d", name)

    def push_tag(self, name: str, remote: str = "origin", timeout: int = 120) -> None:
        if not TAG.match(name):
            raise GitError(f"Nombre de tag inválido: {name!r}")
        self._run("push", remote, f"refs/tags/{name}:refs/tags/{name}", timeout=timeout)

    def create_branch(self, name: str, base: str) -> str:
        name = check_branch(name)
        if self.branch_exists(name):
            raise GitConflict(f"La rama {name} ya existe")
        base_sha = self.resolve(base)
        if base_sha is None:
            raise GitRefNotFound(f"No existe la referencia base {base!r}")
        self._run("update-ref", f"refs/heads/{name}", base_sha, ZERO_SHA)
        return base_sha

    def commit_files(self, branch: str, files: Dict[str, str], message: str, base: str = "HEAD") -> Dict[str, str]:
        """Crea un commit en `branch` con `files` (ruta → contenido) partiendo de su punta o de `base` si no existe."""
        branch = check_branch(branch)
        if not files:
            raise GitError("No hay archivos para el commit")
        current = self.resolve(f"refs/heads/{branch}")
        parent = current or self.resolve(base)
        if parent is None:
            raise GitRefNotFound(f"No existe la referencia base {base!r}")
        with tempfile.TemporaryDirectory(prefix="kinetix-git-") as tmp:
            env = {"GIT_INDEX_FILE": os.path.join(tmp, "index")}
            self._run("read-tree", parent, env=env)
            for path, content in files.items():
                blob = self._run("hash-object", "-w", "--stdin", stdin=content.encode("utf-8")).strip()
                self._run("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
            tree = self._run("write-tree", env=env).strip()
        if tree == self._run("rev-parse", f"{parent}^{{tree}}").strip():
            raise GitConflict("Los archivos son idénticos a los de la rama: no hay cambios que commitear")
        commit = self._run("commit-tree", tree, "-p", parent, "-m", message).strip()
        self._run("update-ref", f"refs/heads/{branch}", commit, current or ZERO_SHA)
        return {"rama": branch, "commit": commit, "padre": parent, "rama_creada": "no" if current else "si"}
