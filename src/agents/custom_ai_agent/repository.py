"""
Persistencia de Genesis: agentes personalizados (genesis_agentes), invocaciones con su consumo de tokens
(genesis_invocaciones), código generado (genesis_generaciones) y presupuesto mensual por empresa (genesis_presupuestos).
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient, afectadas, ejecutar


@dataclass(frozen=True)
class CustomAgent:
    id_agente: str
    id_empresa: str
    nombre: str
    prompt_sistema: str
    fecha_creacion: datetime
    fecha_modificacion: datetime
    descripcion: str = ""
    proveedor: str = "auto"
    nivel: str = "auto"
    temperatura: Optional[float] = None
    max_tokens: int = 1024
    estado: str = "activo"
    version: int = 1
    creado_por: str = ""


@dataclass(frozen=True)
class Invocation:
    id_invocacion: str
    id_empresa: str
    tipo: str
    estado: str
    usuario: str
    fecha: datetime
    id_agente: Optional[str] = None
    proveedor: Optional[str] = None
    modelo: Optional[str] = None
    nivel: Optional[str] = None
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: Optional[float] = None
    duracion_ms: float = 0
    error: Optional[str] = None
    prompt: Optional[str] = None
    respuesta: Optional[str] = None


@dataclass(frozen=True)
class Generation:
    id_generacion: str
    id_empresa: str
    id_invocacion: str
    tipo: str
    lenguaje: str
    descripcion: str
    ruta_sugerida: str
    contenido: str
    usuario: str
    fecha: datetime
    analisis: Dict[str, Any] = field(default_factory=dict)
    puntuacion: Optional[float] = None
    criticos: int = 0
    estado: str = "generada"
    rama: Optional[str] = None
    commit_git: Optional[str] = None


class GenesisRepository(ABC):
    @abstractmethod
    def create_agent(self, agent: CustomAgent) -> bool:
        """False si ya existe un agente con ese nombre en la empresa."""

    @abstractmethod
    def get_agent(self, id_agente: str, id_empresa: str) -> Optional[CustomAgent]: ...

    @abstractmethod
    def list_agents(self, id_empresa: str, include_archived: bool) -> List[CustomAgent]: ...

    @abstractmethod
    def update_agent(self, agent: CustomAgent, expected_version: int) -> bool: ...

    @abstractmethod
    def record_invocation(self, invocation: Invocation) -> None: ...

    @abstractmethod
    def invocations(self, id_empresa: str, id_agente: Optional[str], limit: int) -> List[Invocation]: ...

    @abstractmethod
    def usage(self, id_empresa: str, since: datetime) -> List[Dict[str, Any]]:
        """Por proveedor/modelo/estado: invocaciones, tokens de entrada y salida, costo."""

    @abstractmethod
    def save_generation(self, generation: Generation) -> None: ...

    @abstractmethod
    def get_generation(self, id_generacion: str, id_empresa: str) -> Optional[Generation]: ...

    @abstractmethod
    def list_generations(self, id_empresa: str, limit: int) -> List[Generation]: ...

    @abstractmethod
    def mark_committed(self, id_generacion: str, id_empresa: str, rama: str, commit_git: str) -> bool:
        """Solo una vez: False si ya estaba commiteada."""

    @abstractmethod
    def get_budget(self, id_empresa: str) -> Optional[int]: ...

    @abstractmethod
    def set_budget(self, id_empresa: str, tokens: int, actor: str, now: datetime) -> None: ...

    @abstractmethod
    def ping(self) -> None: ...


def _aggregate(items: List[Invocation]) -> List[Dict[str, Any]]:
    groups: Dict[tuple, Dict[str, Any]] = {}
    for i in items:
        empty = {"proveedor": i.proveedor, "modelo": i.modelo, "estado": i.estado, "invocaciones": 0, "tokens_entrada": 0,
                 "tokens_salida": 0, "costo_usd": 0.0}
        row = groups.setdefault((i.proveedor, i.modelo, i.estado), empty)
        row["invocaciones"] += 1
        row["tokens_entrada"] += i.tokens_entrada
        row["tokens_salida"] += i.tokens_salida
        row["costo_usd"] += i.costo_usd or 0.0
    return list(groups.values())


class InMemoryGenesisRepository(GenesisRepository):
    def __init__(self) -> None:
        self._agents: Dict[str, CustomAgent] = {}
        self._invocations: List[Invocation] = []
        self._generations: Dict[str, Generation] = {}
        self._budgets: Dict[str, int] = {}
        self._lock = threading.Lock()

    def _taken(self, agent: CustomAgent) -> bool:
        return any(a.id_empresa == agent.id_empresa and a.nombre.lower() == agent.nombre.lower() and a.id_agente != agent.id_agente
                   for a in self._agents.values())

    def create_agent(self, agent: CustomAgent) -> bool:
        with self._lock:
            if self._taken(agent):
                return False
            self._agents[agent.id_agente] = agent
            return True

    def get_agent(self, id_agente: str, id_empresa: str) -> Optional[CustomAgent]:
        agent = self._agents.get(id_agente)
        return agent if agent and agent.id_empresa == id_empresa else None

    def list_agents(self, id_empresa: str, include_archived: bool) -> List[CustomAgent]:
        return sorted((a for a in self._agents.values() if a.id_empresa == id_empresa and (include_archived or a.estado == "activo")),
                      key=lambda a: a.nombre.lower())

    def update_agent(self, agent: CustomAgent, expected_version: int) -> bool:
        with self._lock:
            current = self.get_agent(agent.id_agente, agent.id_empresa)
            if current is None or current.version != expected_version or self._taken(agent):
                return False
            self._agents[agent.id_agente] = replace(agent, version=expected_version + 1)
            return True

    def record_invocation(self, invocation: Invocation) -> None:
        with self._lock:
            self._invocations.append(invocation)

    def invocations(self, id_empresa: str, id_agente: Optional[str], limit: int) -> List[Invocation]:
        items = [i for i in self._invocations if i.id_empresa == id_empresa and id_agente in (None, i.id_agente)]
        return sorted(items, key=lambda i: i.fecha, reverse=True)[:limit]

    def usage(self, id_empresa: str, since: datetime) -> List[Dict[str, Any]]:
        return _aggregate([i for i in self._invocations if i.id_empresa == id_empresa and i.fecha >= since])

    def save_generation(self, generation: Generation) -> None:
        with self._lock:
            self._generations[generation.id_generacion] = generation

    def get_generation(self, id_generacion: str, id_empresa: str) -> Optional[Generation]:
        item = self._generations.get(id_generacion)
        return item if item and item.id_empresa == id_empresa else None

    def list_generations(self, id_empresa: str, limit: int) -> List[Generation]:
        items = [g for g in self._generations.values() if g.id_empresa == id_empresa]
        return sorted(items, key=lambda g: g.fecha, reverse=True)[:limit]

    def mark_committed(self, id_generacion: str, id_empresa: str, rama: str, commit_git: str) -> bool:
        with self._lock:
            item = self.get_generation(id_generacion, id_empresa)
            if item is None or item.estado != "generada":
                return False
            self._generations[id_generacion] = replace(item, estado="commiteada", rama=rama, commit_git=commit_git)
            return True

    def get_budget(self, id_empresa: str) -> Optional[int]:
        return self._budgets.get(id_empresa)

    def set_budget(self, id_empresa: str, tokens: int, actor: str, now: datetime) -> None:
        self._budgets[id_empresa] = tokens

    def ping(self) -> None:
        return None


class SqlServerGenesisRepository(GenesisRepository):
    """Persistencia sobre los procedimientos del esquema genesis de la base kinetix."""

    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def ping(self) -> None:
        self._db.ping()

    @staticmethod
    def _agent(r) -> CustomAgent:
        return CustomAgent(id_agente=r[0], id_empresa=r[1], nombre=r[2], descripcion=r[3] or "", prompt_sistema=r[4], proveedor=r[5],
                           nivel=r[6], temperatura=float(r[7]) if r[7] is not None else None, max_tokens=r[8], estado=r[9], version=r[10],
                           creado_por=r[11] or "", fecha_creacion=r[12], fecha_modificacion=r[13])

    @staticmethod
    def _generation(r) -> Generation:
        return Generation(id_generacion=r[0], id_empresa=r[1], id_invocacion=r[2], tipo=r[3], lenguaje=r[4], descripcion=r[5],
                          ruta_sugerida=r[6], contenido=r[7], analisis=loads(r[8], {}), puntuacion=float(r[9]) if r[9] is not None else None,
                          criticos=r[10], estado=r[11], rama=r[12], commit_git=r[13], usuario=r[14] or "", fecha=r[15])

    @staticmethod
    def _agent_values(a: CustomAgent) -> Dict[str, Any]:
        return dict(id_agente=a.id_agente, id_empresa=a.id_empresa, nombre=a.nombre, descripcion=a.descripcion,
                    prompt_sistema=a.prompt_sistema, proveedor=a.proveedor, nivel=a.nivel, temperatura=a.temperatura,
                    max_tokens=a.max_tokens, estado=a.estado)

    def create_agent(self, agent: CustomAgent) -> bool:
        a = agent
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "genesis.agente_insertar", **self._agent_values(a), version=a.version,
                                      creado_por=a.creado_por, fecha_creacion=a.fecha_creacion,
                                      fecha_modificacion=a.fecha_modificacion)) == 1

    def get_agent(self, id_agente: str, id_empresa: str) -> Optional[CustomAgent]:
        with self._db.cursor() as cur:
            row = ejecutar(cur, "genesis.agente_obtener", id_agente=id_agente, id_empresa=id_empresa).fetchone()
        return self._agent(row) if row else None

    def list_agents(self, id_empresa: str, include_archived: bool) -> List[CustomAgent]:
        with self._db.cursor() as cur:
            rows = ejecutar(cur, "genesis.agente_listar", id_empresa=id_empresa, incluir_archivados=include_archived).fetchall()
        return [self._agent(r) for r in rows]

    def update_agent(self, agent: CustomAgent, expected_version: int) -> bool:
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "genesis.agente_actualizar", **self._agent_values(agent),
                                      fecha_modificacion=agent.fecha_modificacion, version_esperada=expected_version)) == 1

    def record_invocation(self, invocation: Invocation) -> None:
        i = invocation
        with self._db.cursor(commit=True) as cur:
            ejecutar(cur, "genesis.invocacion_insertar", id_invocacion=i.id_invocacion, id_empresa=i.id_empresa,
                     id_agente=i.id_agente, tipo=i.tipo, proveedor=i.proveedor, modelo=i.modelo, nivel=i.nivel,
                     tokens_entrada=i.tokens_entrada, tokens_salida=i.tokens_salida, costo_usd=i.costo_usd,
                     duracion_ms=i.duracion_ms, estado=i.estado, error=(i.error or None) and i.error[:1000], usuario=i.usuario,
                     fecha=i.fecha, prompt=i.prompt, respuesta=i.respuesta)

    def invocations(self, id_empresa: str, id_agente: Optional[str], limit: int) -> List[Invocation]:
        with self._db.cursor() as cur:
            rows = ejecutar(cur, "genesis.invocacion_listar", id_empresa=id_empresa, id_agente=id_agente or None,
                            limite=limit).fetchall()
        return [Invocation(id_invocacion=r[0], id_empresa=r[1], id_agente=r[2], tipo=r[3], proveedor=r[4], modelo=r[5], nivel=r[6],
                           tokens_entrada=r[7], tokens_salida=r[8], costo_usd=float(r[9]) if r[9] is not None else None,
                           duracion_ms=float(r[10]), estado=r[11], error=r[12], usuario=r[13] or "", fecha=r[14], prompt=r[15],
                           respuesta=r[16]) for r in rows]

    def usage(self, id_empresa: str, since: datetime) -> List[Dict[str, Any]]:
        with self._db.cursor() as cur:
            rows = ejecutar(cur, "genesis.consumo", id_empresa=id_empresa, desde=since).fetchall()
        return [{"proveedor": r[0], "modelo": r[1], "estado": r[2], "invocaciones": r[3], "tokens_entrada": int(r[4] or 0),
                 "tokens_salida": int(r[5] or 0), "costo_usd": float(r[6] or 0)} for r in rows]

    def save_generation(self, generation: Generation) -> None:
        g = generation
        with self._db.cursor(commit=True) as cur:
            ejecutar(cur, "genesis.generacion_insertar", id_generacion=g.id_generacion, id_empresa=g.id_empresa,
                     id_invocacion=g.id_invocacion, tipo=g.tipo, lenguaje=g.lenguaje, descripcion=g.descripcion,
                     ruta_sugerida=g.ruta_sugerida, contenido=g.contenido, analisis=dumps(g.analisis), puntuacion=g.puntuacion,
                     criticos=g.criticos, estado=g.estado, rama=g.rama, commit_git=g.commit_git, usuario=g.usuario, fecha=g.fecha)

    def get_generation(self, id_generacion: str, id_empresa: str) -> Optional[Generation]:
        with self._db.cursor() as cur:
            row = ejecutar(cur, "genesis.generacion_obtener", id_generacion=id_generacion, id_empresa=id_empresa).fetchone()
        return self._generation(row) if row else None

    def list_generations(self, id_empresa: str, limit: int) -> List[Generation]:
        with self._db.cursor() as cur:
            rows = ejecutar(cur, "genesis.generacion_listar", id_empresa=id_empresa, limite=limit).fetchall()
        return [self._generation(r) for r in rows]

    def mark_committed(self, id_generacion: str, id_empresa: str, rama: str, commit_git: str) -> bool:
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "genesis.generacion_marcar_commit", id_generacion=id_generacion, id_empresa=id_empresa,
                                      rama=rama, commit_git=commit_git)) == 1

    def get_budget(self, id_empresa: str) -> Optional[int]:
        with self._db.cursor() as cur:
            row = ejecutar(cur, "genesis.presupuesto_obtener", id_empresa=id_empresa).fetchone()
        return int(row[0]) if row else None

    def set_budget(self, id_empresa: str, tokens: int, actor: str, now: datetime) -> None:
        with self._db.cursor(commit=True) as cur:
            ejecutar(cur, "genesis.presupuesto_fijar", id_empresa=id_empresa, tokens=tokens, actor=actor, ahora=now)
