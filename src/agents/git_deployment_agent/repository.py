"""Historial de despliegues de Orbit (tabla orbit_despliegues)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient

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
    _COLUMNS = ("id_despliegue, entorno, tipo, commit_git, estado, iniciado_por, fecha_inicio, tag, tag_publicado, "
                "id_origen, notas, fecha_fin, compuerta, workflow, bitacora")

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
            cur.execute(
                f"INSERT INTO dbo.orbit_despliegues ({self._COLUMNS}) VALUES ({', '.join('?' * 15)})",
                (d.id_despliegue, d.entorno, d.tipo, d.commit_git, d.estado, d.iniciado_por[:200], d.fecha_inicio, d.tag,
                 d.tag_publicado, d.id_origen, d.notas, d.fecha_fin, dumps(d.compuerta), dumps(d.workflow), dumps(d.bitacora)),
            )

    def get(self, id_despliegue: str) -> Optional[Deployment]:
        with self._db.cursor() as cur:
            cur.execute(f"SELECT {self._COLUMNS} FROM dbo.orbit_despliegues WHERE id_despliegue = ?", (id_despliegue,))
            row = cur.fetchone()
        return self._deployment(row) if row else None

    def recent(self, limit: int, entorno: Optional[str] = None, estado: Optional[str] = None) -> List[Deployment]:
        where, params = [], [limit]
        if entorno:
            where.append("entorno = ?")
            params.append(entorno)
        if estado:
            where.append("estado = ?")
            params.append(estado)
        sql = f"SELECT TOP (?) {self._COLUMNS} FROM dbo.orbit_despliegues"
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self._db.cursor() as cur:
            cur.execute(sql + " ORDER BY fecha_inicio DESC", tuple(params))
            return [self._deployment(r) for r in cur.fetchall()]

    def succeeded_with(self, entorno: str, commit: str) -> bool:
        with self._db.cursor() as cur:
            cur.execute("SELECT TOP 1 1 FROM dbo.orbit_despliegues WHERE entorno = ? AND commit_git = ? AND estado = 'exitoso'",
                        (entorno, commit))
            return cur.fetchone() is not None
