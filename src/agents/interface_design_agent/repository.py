"""Persistencia de Aurora: sistemas de diseño (aurora_sistemas) y sus componentes (aurora_componentes)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient, afectadas, ejecutar


@dataclass(frozen=True)
class DesignSystem:
    id_sistema: str
    nombre: str
    id_empresa: str
    nivel_wcag: str
    tokens: Dict[str, Any]
    version: int = 1
    estado: str = "activo"
    creado_por: str = ""
    fecha_creacion: Optional[datetime] = None
    fecha_modificacion: Optional[datetime] = None
    componentes: List[Dict[str, Any]] = field(default_factory=list)
    total_componentes: int = 0


class DesignRepository(ABC):
    @abstractmethod
    def create(self, system: DesignSystem) -> bool:
        """False si ya existe un sistema con ese nombre en la empresa."""

    @abstractmethod
    def get(self, id_sistema: str, id_empresa: str) -> Optional[DesignSystem]: ...

    @abstractmethod
    def list(self, id_empresa: str) -> List[DesignSystem]:
        """Sin componentes (solo el conteo en la vista)."""

    @abstractmethod
    def update_tokens(self, id_sistema: str, id_empresa: str, tokens: Dict[str, Any], expected_version: int,
                      nivel_wcag: str, now: datetime) -> bool:
        """Control optimista: False si la versión cambió entre la lectura y la escritura."""

    @abstractmethod
    def upsert_component(self, id_sistema: str, component: Dict[str, Any], now: datetime) -> bool:
        """True si el componente se creó, False si se actualizó."""

    @abstractmethod
    def delete_component(self, id_sistema: str, nombre: str) -> bool: ...

    @abstractmethod
    def ping(self) -> None: ...


class InMemoryDesignRepository(DesignRepository):
    def __init__(self) -> None:
        self._systems: Dict[str, DesignSystem] = {}
        self._lock = threading.Lock()

    def create(self, system: DesignSystem) -> bool:
        with self._lock:
            if any(s.id_empresa == system.id_empresa and s.nombre.lower() == system.nombre.lower() for s in self._systems.values()):
                return False
            self._systems[system.id_sistema] = system
            return True

    def get(self, id_sistema: str, id_empresa: str) -> Optional[DesignSystem]:
        system = self._systems.get(id_sistema)
        return system if system and system.id_empresa == id_empresa else None

    def list(self, id_empresa: str) -> List[DesignSystem]:
        found = [replace(s, componentes=[], total_componentes=len(s.componentes))
                 for s in self._systems.values() if s.id_empresa == id_empresa]
        return sorted(found, key=lambda s: s.fecha_modificacion or datetime.min, reverse=True)

    def update_tokens(self, id_sistema, id_empresa, tokens, expected_version, nivel_wcag, now) -> bool:
        with self._lock:
            current = self.get(id_sistema, id_empresa)
            if current is None or current.version != expected_version:
                return False
            self._systems[id_sistema] = replace(current, tokens=tokens, version=current.version + 1,
                                                nivel_wcag=nivel_wcag, fecha_modificacion=now)
            return True

    def upsert_component(self, id_sistema: str, component: Dict[str, Any], now: datetime) -> bool:
        with self._lock:
            current = self._systems[id_sistema]
            others = [c for c in current.componentes if c["nombre"].lower() != component["nombre"].lower()]
            created = len(others) == len(current.componentes)
            self._systems[id_sistema] = replace(current, componentes=sorted([*others, component], key=lambda c: c["nombre"]),
                                                fecha_modificacion=now)
            return created

    def delete_component(self, id_sistema: str, nombre: str) -> bool:
        with self._lock:
            current = self._systems[id_sistema]
            remaining = [c for c in current.componentes if c["nombre"].lower() != nombre.lower()]
            self._systems[id_sistema] = replace(current, componentes=remaining)
            return len(remaining) != len(current.componentes)

    def ping(self) -> None:
        return None


class SqlServerDesignRepository(DesignRepository):
    """Persistencia sobre los procedimientos del esquema aurora de la base kinetix."""

    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def ping(self) -> None:
        self._db.ping()

    @staticmethod
    def _system(row, components: Optional[List[Dict[str, Any]]] = None, total: Optional[int] = None) -> DesignSystem:
        components = components or []
        return DesignSystem(
            id_sistema=row[0], nombre=row[1], id_empresa=row[2], nivel_wcag=row[3], tokens=loads(row[4], {}),
            version=row[5], estado=row[6], creado_por=row[7] or "", fecha_creacion=row[8], fecha_modificacion=row[9],
            componentes=components, total_componentes=len(components) if total is None else total,
        )

    def create(self, system: DesignSystem) -> bool:
        s = system
        with self._db.cursor(commit=True) as cur:
            created = afectadas(ejecutar(
                cur, "aurora.sistema_insertar", id_sistema=s.id_sistema, nombre=s.nombre, id_empresa=s.id_empresa,
                nivel_wcag=s.nivel_wcag, tokens=dumps(s.tokens), version=s.version, estado=s.estado, creado_por=s.creado_por,
                fecha_creacion=s.fecha_creacion, fecha_modificacion=s.fecha_modificacion))
            if created != 1:
                return False
            for component in s.componentes:
                self._insert_component(cur, s.id_sistema, component, s.fecha_creacion)
            return True

    @staticmethod
    def _insert_component(cur, id_sistema: str, component: Dict[str, Any], now: Optional[datetime]) -> None:
        ejecutar(cur, "aurora.componente_insertar", id_sistema=id_sistema, nombre=component["nombre"], tipo=component["tipo"],
                 especificacion=dumps(component), fecha_modificacion=now)

    def get(self, id_sistema: str, id_empresa: str) -> Optional[DesignSystem]:
        with self._db.cursor() as cur:
            row = ejecutar(cur, "aurora.sistema_obtener", id_sistema=id_sistema, id_empresa=id_empresa).fetchone()
            if row is None:
                return None
            cur.nextset()
            components = [loads(r[0], {}) for r in cur.fetchall()]
        return self._system(row, [c for c in components if c])

    def list(self, id_empresa: str) -> List[DesignSystem]:
        with self._db.cursor() as cur:
            rows = ejecutar(cur, "aurora.sistema_listar", id_empresa=id_empresa).fetchall()
        return [self._system(r, total=r[10] or 0) for r in rows]

    def update_tokens(self, id_sistema, id_empresa, tokens, expected_version, nivel_wcag, now) -> bool:
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "aurora.sistema_actualizar_tokens", id_sistema=id_sistema, id_empresa=id_empresa,
                                      tokens=dumps(tokens), nivel_wcag=nivel_wcag, ahora=now,
                                      version_esperada=expected_version)) == 1

    def upsert_component(self, id_sistema: str, component: Dict[str, Any], now: datetime) -> bool:
        with self._db.cursor(commit=True) as cur:
            row = ejecutar(cur, "aurora.componente_guardar", id_sistema=id_sistema, nombre=component["nombre"],
                           tipo=component["tipo"], especificacion=dumps(component), ahora=now).fetchone()
            return bool(row[0])

    def delete_component(self, id_sistema: str, nombre: str) -> bool:
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "aurora.componente_eliminar", id_sistema=id_sistema, nombre=nombre)) == 1
