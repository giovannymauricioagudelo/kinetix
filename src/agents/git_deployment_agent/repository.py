"""Historial de despliegues de Orbit (tabla orbit_despliegues)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient, ejecutar

SUCCESS, FAILED, REJECTED = "exitoso", "fallido", "rechazado"


@dataclass(frozen=True)
class Deployment:
    id_despliegue: str
    entorno: str
    tipo: str
    commit_git: str
    estado: str
    iniciado_por: str
    fecha_inicio: datetime
    tag: Optional[str] = None
    tag_publicado: bool = False
    id_origen: Optional[str] = None
    notas: Optional[str] = None
    fecha_fin: Optional[datetime] = None
    compuerta: Dict[str, Any] = field(default_factory=dict)
    workflow: Dict[str, Any] = field(default_factory=dict)
    bitacora: List[Dict[str, str]] = field(default_factory=list)


class DeploymentRepository(ABC):
    @abstractmethod
    def save(self, deployment: Deployment) -> None: ...

    @abstractmethod
    def get(self, id_despliegue: str) -> Optional[Deployment]: ...

    @abstractmethod
    def recent(self, limit: int, entorno: Optional[str] = None, estado: Optional[str] = None) -> List[Deployment]: ...

    @abstractmethod
    def ping(self) -> None: ...

    def successful(self, entorno: str, limit: int = 50) -> List[Deployment]:
        return self.recent(limit, entorno, SUCCESS)

    def succeeded_with(self, entorno: str, commit: str) -> bool:
        return any(d.commit_git == commit for d in self.successful(entorno, 200))


class InMemoryDeploymentRepository(DeploymentRepository):
    def __init__(self) -> None:
        self._items: Dict[str, Deployment] = {}
        self._lock = threading.Lock()

    def save(self, deployment: Deployment) -> None:
        with self._lock:
            self._items[deployment.id_despliegue] = deployment

    def get(self, id_despliegue: str) -> Optional[Deployment]:
        return self._items.get(id_despliegue)

    def recent(self, limit: int, entorno: Optional[str] = None, estado: Optional[str] = None) -> List[Deployment]:
        items = sorted(self._items.values(), key=lambda d: d.fecha_inicio, reverse=True)
        return [d for d in items if (entorno is None or d.entorno == entorno) and (estado is None or d.estado == estado)][:limit]

    def ping(self) -> None:
        return None


class SqlServerDeploymentRepository(DeploymentRepository):
    """Persistencia sobre los procedimientos del esquema orbit de la base kinetix."""

    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def ping(self) -> None:
        self._db.ping()

    @staticmethod
    def _deployment(row) -> Deployment:
        return Deployment(
            id_despliegue=row[0], entorno=row[1], tipo=row[2], commit_git=row[3], estado=row[4], iniciado_por=row[5] or "",
            fecha_inicio=row[6], tag=row[7], tag_publicado=bool(row[8]), id_origen=row[9], notas=row[10], fecha_fin=row[11],
            compuerta=loads(row[12], {}), workflow=loads(row[13], {}), bitacora=loads(row[14], []),
        )

    def save(self, d: Deployment) -> None:
        with self._db.cursor(commit=True) as cur:
            ejecutar(cur, "orbit.despliegue_insertar", id_despliegue=d.id_despliegue, entorno=d.entorno, tipo=d.tipo,
                     commit_git=d.commit_git, estado=d.estado, iniciado_por=d.iniciado_por[:200], fecha_inicio=d.fecha_inicio,
                     tag=d.tag, tag_publicado=d.tag_publicado, id_origen=d.id_origen, notas=d.notas, fecha_fin=d.fecha_fin,
                     compuerta=dumps(d.compuerta), workflow=dumps(d.workflow), bitacora=dumps(d.bitacora))

    def get(self, id_despliegue: str) -> Optional[Deployment]:
        with self._db.cursor() as cur:
            row = ejecutar(cur, "orbit.despliegue_obtener", id_despliegue=id_despliegue).fetchone()
        return self._deployment(row) if row else None

    def recent(self, limit: int, entorno: Optional[str] = None, estado: Optional[str] = None) -> List[Deployment]:
        with self._db.cursor() as cur:
            rows = ejecutar(cur, "orbit.despliegue_listar", entorno=entorno or None, estado=estado or None, limite=limit).fetchall()
        return [self._deployment(r) for r in rows]

    def succeeded_with(self, entorno: str, commit: str) -> bool:
        with self._db.cursor() as cur:
            return ejecutar(cur, "orbit.despliegue_exitoso_con", entorno=entorno, commit_git=commit).fetchone() is not None
