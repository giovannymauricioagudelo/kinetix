"""Cliente mínimo de la GitHub REST API para Orbit: ejecuciones de Actions, disparo de workflows y estado de commits."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import httpx

REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
WORKFLOW = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_REMOTE = re.compile(r"github\.com[:/]+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


class GitHubNotConfigured(Exception):
    pass


class GitHubError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def repository_from_remote(url: Optional[str]) -> Optional[str]:
    match = _REMOTE.search(url or "")
    return f"{match.group(1)}/{match.group(2)}" if match else None


def _run_view(run: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": run.get("id"),
        "workflow": run.get("name"),
        "evento": run.get("event"),
        "rama": run.get("head_branch"),
        "commit": run.get("head_sha"),
        "estado": run.get("status"),
        "conclusion": run.get("conclusion"),
        "creado": run.get("created_at"),
        "actualizado": run.get("updated_at"),
        "url": run.get("html_url"),
    }


class GitHubClient:
    def __init__(self, token: Optional[str], repository: Optional[str], api_url: str = "https://api.github.com",
                 timeout_seconds: float = 15, transport: Optional[httpx.BaseTransport] = None) -> None:
        self.repository = repository if repository and REPOSITORY.match(repository) else None
        self._token = token or None
        self._api_url = api_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._token and self.repository)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.configured:
            raise GitHubNotConfigured("GitHub no está configurado: define GITHUB_TOKEN (y GITHUB_REPOSITORY si origin no es GitHub)")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            with httpx.Client(base_url=self._api_url, headers=headers, timeout=self._timeout, transport=self._transport) as client:
                response = client.request(method, f"/repos/{self.repository}{path}", **kwargs)
        except httpx.HTTPError as e:
            raise GitHubError(f"No se pudo contactar a GitHub: {type(e).__name__}") from e
        if response.status_code >= 400:
            try:
                detail = response.json().get("message", "")
            except ValueError:
                detail = response.text[:200]
            raise GitHubError(f"GitHub respondió {response.status_code}: {detail}", response.status_code)
        return response.json() if response.content else None

    def workflow_runs(self, limit: int = 20, branch: Optional[str] = None, workflow: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"per_page": max(1, min(limit, 100))}
        if branch:
            params["branch"] = branch
        if workflow:
            if not WORKFLOW.match(workflow):
                raise GitHubError("Nombre de workflow inválido")
            path = f"/actions/workflows/{workflow}/runs"
        else:
            path = "/actions/runs"
        data = self._request("GET", path, params=params) or {}
        return [_run_view(r) for r in data.get("workflow_runs", [])]

    def dispatch_workflow(self, workflow: str, ref: str, inputs: Optional[Dict[str, str]] = None) -> None:
        if not WORKFLOW.match(workflow or ""):
            raise GitHubError("Nombre de workflow inválido")
        self._request("POST", f"/actions/workflows/{workflow}/dispatches", json={"ref": ref, "inputs": inputs or {}})

    def commit_checks(self, ref: str) -> Dict[str, Any]:
        runs = (self._request("GET", f"/commits/{ref}/check-runs", params={"per_page": 100}) or {}).get("check_runs", [])
        status = self._request("GET", f"/commits/{ref}/status") or {}
        checks = [
            {"nombre": r.get("name"), "estado": r.get("status"), "conclusion": r.get("conclusion"), "url": r.get("html_url")}
            for r in runs
        ]
        statuses = status.get("statuses") or []
        failing = [c for c in checks if c["conclusion"] not in (None, "success", "skipped", "neutral")]
        pending = [c for c in checks if c["estado"] != "completed"]
        statuses_ok = not statuses or status.get("state") == "success"
        return {
            "referencia": ref,
            "estado_combinado": status.get("state") if statuses else None,
            "checks": checks,
            "fallidos": len(failing),
            "pendientes": len(pending),
            "aprobado": bool(checks or statuses) and not failing and not pending and statuses_ok,
        }


def github_from_env(remote_url: Optional[str]) -> GitHubClient:
    repository = os.getenv("GITHUB_REPOSITORY") or repository_from_remote(remote_url)
    return GitHubClient(os.getenv("GITHUB_TOKEN"), repository, os.getenv("GITHUB_API_URL", "https://api.github.com"))
