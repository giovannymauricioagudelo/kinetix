"""
Casos de uso de Orbit: un despliegue es un tag anotado release/<entorno>/<fecha> sobre un commit de la rama de
release que pasó la compuerta de Prism (producción además exige el mismo commit desplegado antes en staging).
Opcionalmente publica el tag en origin y dispara un workflow de GitHub Actions; revertir = re-etiquetar un commit
que ya estuvo desplegado con éxito.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.agents.common import iso, new_id, utcnow
from src.agents.git_deployment_agent.repository import FAILED, REJECTED, SUCCESS, Deployment, DeploymentRepository
from src.agents.git_tools import GitError, GitRepository, check_ref, domain_errors
from src.agents.github_client import GitHubClient, GitHubError
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError

VERSION = "1.0.0"
ENVIRONMENTS = ("staging", "produccion")
PREVIOUS_STAGE = {"produccion": "staging"}
TAG_PREFIX = "release"

QualityGate = Callable[[str], Dict[str, Any]]


def commit_timestamp(moment: datetime) -> str:
    return moment.strftime("%d%m%Y %H:%M:%S")


def deployment_view(d: Deployment) -> Dict[str, Any]:
    return {
        "id_despliegue": d.id_despliegue, "entorno": d.entorno, "tipo": d.tipo, "estado": d.estado, "commit": d.commit_git,
        "tag": d.tag, "tag_publicado": d.tag_publicado, "id_origen": d.id_origen, "notas": d.notas,
        "iniciado_por": d.iniciado_por, "fecha_inicio": iso(d.fecha_inicio), "fecha_fin": iso(d.fecha_fin),
        "compuerta": d.compuerta, "workflow": d.workflow, "bitacora": d.bitacora,
    }


class DeploymentRejected(ConflictError):
    def __init__(self, message: str, deployment: Dict[str, Any]) -> None:
        super().__init__(message)
        self.deployment = deployment


class OrbitService:
    def __init__(self, git: GitRepository, repository: DeploymentRepository, quality_gate: QualityGate,
                 github: Optional[GitHubClient] = None, workflow: Optional[str] = None, release_branch: str = "master",
                 remote: str = "origin", clock: Callable = utcnow, local_clock: Callable[[], datetime] = datetime.now) -> None:
        self._git = git
        self._repo = repository
        self._gate = quality_gate
        self._github = github
        self.workflow = workflow or None
        self.release_branch = release_branch
        self._remote = remote
        self._clock = clock
        self._local_clock = local_clock

    def ping(self) -> None:
        self._repo.ping()

    @property
    def github_configured(self) -> bool:
        return bool(self._github and self._github.configured)

    @staticmethod
    def _env(entorno: str) -> str:
        if entorno not in ENVIRONMENTS:
            raise InvalidInputError(f"entorno debe ser {' o '.join(ENVIRONMENTS)}")
        return entorno

    def _resolve(self, ref: str) -> str:
        with domain_errors():
            commit = self._git.resolve(ref)
        if commit is None:
            raise NotFoundError(f"No existe la referencia {ref!r}")
        return commit

    # ================================================================ consulta

    def current(self, entorno: str) -> Optional[Deployment]:
        history = self._repo.successful(entorno, 1)
        return history[0] if history else None

    def repository_info(self) -> Dict[str, Any]:
        with domain_errors():
            status = self._git.status()
            remote = self._git.remote_url(self._remote)
        return {
            "ruta": self._git.path, "remoto": remote, "rama_release": self.release_branch, **status,
            "github": {"configurado": self.github_configured, "repositorio": self._github.repository if self._github else None,
                       "workflow": self.workflow},
            "entornos": {env: (deployment_view(d) if (d := self.current(env)) else None) for env in ENVIRONMENTS},
        }

    def releases(self, entorno: Optional[str] = None, limite: int = 50) -> Dict[str, Any]:
        pattern = f"{TAG_PREFIX}/{self._env(entorno)}" if entorno else TAG_PREFIX
        with domain_errors():
            tags = self._git.tags(pattern, limite)
        return {"total": len(tags), "releases": tags}

    def list_deployments(self, entorno: Optional[str] = None, estado: Optional[str] = None, limite: int = 20) -> Dict[str, Any]:
        items = self._repo.recent(max(1, min(limite, 200)), self._env(entorno) if entorno else None, estado)
        return {"total": len(items), "despliegues": [deployment_view(d) for d in items]}

    def get_deployment(self, id_despliegue: str) -> Dict[str, Any]:
        d = self._repo.get(id_despliegue)
        if d is None:
            raise NotFoundError(f"Despliegue no encontrado: {id_despliegue}")
        return deployment_view(d)

    # ================================================================ despliegue

    def _check_options(self, publicar_tag: bool, lanzar_workflow: bool) -> None:
        if lanzar_workflow and not publicar_tag:
            raise InvalidInputError("lanzar_workflow requiere publicar_tag: GitHub solo ve tags publicados en origin")
        if lanzar_workflow and not (self.github_configured and self.workflow):
            raise ConflictError("GitHub Actions no está configurado: define GITHUB_TOKEN y ORBIT_GITHUB_WORKFLOW")

    def _reject(self, base: Deployment, reasons: List[str]) -> None:
        rejected = replace(base, estado=REJECTED, fecha_fin=self._clock(),
                           bitacora=[*base.bitacora, *({"paso": "rechazo", "mensaje": r} for r in reasons)])
        self._repo.save(rejected)
        raise DeploymentRejected("Despliegue rechazado: " + "; ".join(reasons), deployment_view(rejected))

    def _release(self, base: Deployment, publicar_tag: bool, lanzar_workflow: bool) -> Dict[str, Any]:
        log = list(base.bitacora)
        tag = f"{TAG_PREFIX}/{base.entorno}/{base.fecha_inicio:%Y%m%d-%H%M%S}"
        with domain_errors():
            if self._git.resolve(f"refs/tags/{tag}") is not None:
                raise ConflictError(f"El tag {tag} ya existe; reintenta en un segundo")
            summary = "Reversión" if base.tipo == "reversion" else "Release"
            message = (f"{summary} {base.entorno} de {base.commit_git[:12]} por {base.iniciado_por}"
                       + (f"\n\n{base.notas}" if base.notas else "") + f"\n\n{commit_timestamp(self._local_clock())}")
            self._git.create_tag(tag, base.commit_git, message)
        log.append({"paso": "tag", "mensaje": f"Tag anotado {tag} creado sobre {base.commit_git}"})
        state, published, workflow = SUCCESS, False, {}
        if publicar_tag:
            try:
                self._git.push_tag(tag, self._remote)
                published = True
                log.append({"paso": "publicacion", "mensaje": f"Tag publicado en {self._remote}"})
            except GitError as e:
                state = FAILED
                log.append({"paso": "publicacion", "mensaje": f"No se pudo publicar el tag: {e}"})
                try:
                    self._git.delete_tag(tag)
                    log.append({"paso": "limpieza", "mensaje": f"Tag local {tag} eliminado"})
                except GitError:
                    log.append({"paso": "limpieza", "mensaje": f"No se pudo eliminar el tag local {tag}"})
                tag = None
        if lanzar_workflow and state == SUCCESS:
            try:
                self._github.dispatch_workflow(self.workflow, tag)
                workflow = {"nombre": self.workflow, "ref": tag, "disparado": True}
                log.append({"paso": "workflow", "mensaje": f"Workflow {self.workflow} disparado sobre {tag}"})
            except GitHubError as e:
                state = FAILED
                workflow = {"nombre": self.workflow, "ref": tag, "disparado": False, "error": str(e)}
                log.append({"paso": "workflow", "mensaje": f"No se pudo disparar {self.workflow}: {e}"})
        final = replace(base, estado=state, tag=tag, tag_publicado=published, workflow=workflow, bitacora=log,
                        fecha_fin=self._clock())
        self._repo.save(final)
        return deployment_view(final)

    def deploy(self, actor: str, entorno: str, referencia: str = "HEAD", publicar_tag: bool = False,
               lanzar_workflow: bool = False, notas: Optional[str] = None) -> Dict[str, Any]:
        env = self._env(entorno)
        self._check_options(publicar_tag, lanzar_workflow)
        commit = self._resolve(referencia)
        base = Deployment(id_despliegue=new_id("od"), entorno=env, tipo="despliegue", commit_git=commit, estado="en_curso",
                          iniciado_por=actor, fecha_inicio=self._clock(), notas=(notas or "").strip()[:500] or None,
                          bitacora=[{"paso": "inicio", "mensaje": f"{referencia} → {commit}"}])
        reasons: List[str] = []
        with domain_errors():
            if not self._git.is_ancestor(commit, check_ref(self.release_branch)):
                reasons.append(f"el commit no está integrado en {self.release_branch}")
        gate = self._gate(commit)
        base = replace(base, compuerta=gate)
        if not gate.get("aprobada"):
            failing = [c["nombre"] for c in gate.get("comprobaciones", []) if not c.get("aprobado")]
            reasons.append("compuerta de Prism no aprobada (" + ", ".join(failing) + ")")
        previous = PREVIOUS_STAGE.get(env)
        if previous and not self._repo.succeeded_with(previous, commit):
            reasons.append(f"el commit no se ha desplegado con éxito en {previous}")
        if reasons:
            self._reject(base, reasons)
        return self._release(base, publicar_tag, lanzar_workflow)

    def rollback(self, actor: str, entorno: str, motivo: str, id_despliegue: Optional[str] = None,
                 publicar_tag: bool = False, lanzar_workflow: bool = False) -> Dict[str, Any]:
        env = self._env(entorno)
        if not 5 <= len((motivo or "").strip()) <= 500:
            raise InvalidInputError("motivo: entre 5 y 500 caracteres")
        self._check_options(publicar_tag, lanzar_workflow)
        history = self._repo.successful(env, 50)
        if not history:
            raise ConflictError(f"No hay despliegues exitosos en {env} a los que volver")
        current = history[0]
        if id_despliegue:
            target = self._repo.get(id_despliegue)
            if target is None:
                raise NotFoundError(f"Despliegue no encontrado: {id_despliegue}")
            if target.entorno != env or target.estado != SUCCESS:
                raise ConflictError("Solo se puede volver a un despliegue exitoso del mismo entorno")
        else:
            target = next((d for d in history[1:] if d.commit_git != current.commit_git), None)
            if target is None:
                raise ConflictError(f"No hay un commit anterior distinto al actual en {env}")
        if target.commit_git == current.commit_git:
            raise ConflictError("Ese commit ya es el desplegado actualmente")
        self._resolve(target.commit_git)
        base = Deployment(
            id_despliegue=new_id("od"), entorno=env, tipo="reversion", commit_git=target.commit_git, estado="en_curso",
            iniciado_por=actor, fecha_inicio=self._clock(), id_origen=target.id_despliegue, notas=motivo.strip(),
            compuerta={"omitida": True, "motivo": f"Commit aprobado previamente en {target.id_despliegue} ({target.tag})"},
            bitacora=[{"paso": "inicio", "mensaje": f"Reversión de {current.commit_git[:12]} a {target.commit_git[:12]}"}],
        )
        return self._release(base, publicar_tag, lanzar_workflow)

    # ================================================================ verificación y GitHub

    def verify(self, entorno: Optional[str] = None) -> Dict[str, Any]:
        result = []
        for env in [self._env(entorno)] if entorno else ENVIRONMENTS:
            d = self.current(env)
            if d is None:
                result.append({"entorno": env, "actual": None})
                continue
            with domain_errors():
                tag_commit = self._git.resolve(f"refs/tags/{d.tag}") if d.tag else None
            item = {"entorno": env, "actual": deployment_view(d), "tag_existe": tag_commit is not None,
                    "tag_valido": tag_commit == d.commit_git}
            if self.github_configured:
                try:
                    item["github"] = self._github.commit_checks(d.commit_git)
                except GitHubError as e:
                    item["github"] = {"error": str(e)}
            result.append(item)
        return {"entornos": result,
                "consistente": all(i["actual"] is None or i["tag_valido"] for i in result)}

    def _require_github(self) -> GitHubClient:
        if self._github is None:
            raise ConflictError("GitHub no está configurado: define GITHUB_TOKEN")
        return self._github

    def workflow_runs(self, limite: int = 20, rama: Optional[str] = None, workflow: Optional[str] = None) -> Dict[str, Any]:
        with domain_errors():
            branch = check_ref(rama) if rama else None
        runs = self._require_github().workflow_runs(limite, branch, workflow or None)
        return {"total": len(runs), "ejecuciones": runs}

    def commit_status(self, referencia: str) -> Dict[str, Any]:
        with domain_errors():
            sha = self._git.resolve(referencia) or check_ref(referencia)
        return self._require_github().commit_checks(sha)
