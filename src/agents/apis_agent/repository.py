"""Persistencia de Synapse: integraciones por empresa (synapse_integraciones) y bitácora de llamadas (synapse_llamadas)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient, afectadas, ejecutar


@dataclass(frozen=True)
class Integration:
    id_integracion: str
    id_empresa: str
    nombre: str
    url_base: str
    tipo_auth: str
    fecha_creacion: datetime
    fecha_modificacion: datetime
    descripcion: str = ""
    auth_meta: Dict[str, Any] = field(default_factory=dict)
    credencial: Optional[str] = None
    encabezados: Dict[str, str] = field(default_factory=dict)
    timeout_s: float = 15.0
    reintentos: int = 2
    limite_por_minuto: int = 60
    estado: str = "activa"
    especificacion: Optional[Dict[str, Any]] = None
    version: int = 1
    creado_por: str = ""
    ultimo_estado_salud: Optional[str] = None
    ultima_verificacion: Optional[datetime] = None


@dataclass(frozen=True)
class CallRecord:
    id_llamada: str
    id_integracion: str
    id_empresa: str
    metodo: str
    ruta: str
    exito: bool
    duracion_ms: float
    intentos: int
    origen: str
    fecha: datetime
    usuario: str = ""
    id_operacion: Optional[str] = None
    codigo_http: Optional[int] = None
    error: Optional[str] = None


class IntegrationRepository(ABC):
    @abstractmethod
    def create(self, integration: Integration) -> bool:
        """False si ya existe una integración con ese nombre en la empresa."""

    @abstractmethod
    def get(self, id_integracion: str, id_empresa: str) -> Optional[Integration]: ...

    @abstractmethod
    def list(self, id_empresa: str) -> List[Integration]: ...

    @abstractmethod
    def count(self, id_empresa: str) -> int: ...

    @abstractmethod
    def update(self, integration: Integration, expected_version: int) -> bool:
        """Control optimista: False si la versión cambió (o el nombre choca con otra integración)."""

    @abstractmethod
    def delete(self, id_integracion: str, id_empresa: str) -> bool: ...

    @abstractmethod
    def set_health(self, id_integracion: str, estado: str, at: datetime) -> None: ...

    @abstractmethod
    def log_call(self, record: CallRecord) -> None: ...

    @abstractmethod
    def calls(self, id_empresa: str, id_integracion: Optional[str], desde: Optional[datetime], limit: int) -> List[CallRecord]:
        """Más recientes primero."""

    @abstractmethod
    def ping(self) -> None: ...


class InMemoryIntegrationRepository(IntegrationRepository):
    def __init__(self) -> None:
        self._items: Dict[str, Integration] = {}
        self._calls: List[CallRecord] = []
        self._lock = threading.Lock()

    def _name_taken(self, integration: Integration) -> bool:
        return any(i.id_empresa == integration.id_empresa and i.nombre.lower() == integration.nombre.lower()
                   and i.id_integracion != integration.id_integracion for i in self._items.values())

    def create(self, integration: Integration) -> bool:
        with self._lock:
            if self._name_taken(integration):
                return False
            self._items[integration.id_integracion] = integration
            return True

    def get(self, id_integracion: str, id_empresa: str) -> Optional[Integration]:
        item = self._items.get(id_integracion)
        return item if item and item.id_empresa == id_empresa else None

    def list(self, id_empresa: str) -> List[Integration]:
        return sorted((i for i in self._items.values() if i.id_empresa == id_empresa), key=lambda i: i.nombre.lower())

    def count(self, id_empresa: str) -> int:
        return len(self.list(id_empresa))

    def update(self, integration: Integration, expected_version: int) -> bool:
        with self._lock:
            current = self.get(integration.id_integracion, integration.id_empresa)
            if current is None or current.version != expected_version or self._name_taken(integration):
                return False
            self._items[integration.id_integracion] = replace(integration, version=expected_version + 1)
            return True

    def delete(self, id_integracion: str, id_empresa: str) -> bool:
        with self._lock:
            if self.get(id_integracion, id_empresa) is None:
                return False
            del self._items[id_integracion]
            self._calls = [c for c in self._calls if c.id_integracion != id_integracion]
            return True

    def set_health(self, id_integracion: str, estado: str, at: datetime) -> None:
        with self._lock:
            item = self._items.get(id_integracion)
            if item:
                self._items[id_integracion] = replace(item, ultimo_estado_salud=estado, ultima_verificacion=at)

    def log_call(self, record: CallRecord) -> None:
        with self._lock:
            self._calls.append(record)

    def calls(self, id_empresa: str, id_integracion: Optional[str], desde: Optional[datetime], limit: int) -> List[CallRecord]:
        items = [c for c in self._calls if c.id_empresa == id_empresa and id_integracion in (None, c.id_integracion)
                 and (desde is None or c.fecha >= desde)]
        return sorted(items, key=lambda c: c.fecha, reverse=True)[:limit]

    def ping(self) -> None:
        return None


class SqlServerIntegrationRepository(IntegrationRepository):
    """Persistencia sobre los procedimientos del esquema synapse de la base kinetix."""

    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def ping(self) -> None:
        self._db.ping()

    @staticmethod
    def _integration(row) -> Integration:
        return Integration(
            id_integracion=row[0], id_empresa=row[1], nombre=row[2], descripcion=row[3] or "", url_base=row[4], tipo_auth=row[5],
            auth_meta=loads(row[6], {}), credencial=row[7], encabezados=loads(row[8], {}), timeout_s=float(row[9]),
            reintentos=row[10], limite_por_minuto=row[11], estado=row[12], especificacion=loads(row[13]), version=row[14],
            creado_por=row[15] or "", fecha_creacion=row[16], fecha_modificacion=row[17], ultimo_estado_salud=row[18],
            ultima_verificacion=row[19],
        )

    @staticmethod
    def _values(i: Integration) -> Dict[str, Any]:
        return dict(id_integracion=i.id_integracion, id_empresa=i.id_empresa, nombre=i.nombre, descripcion=i.descripcion,
                    url_base=i.url_base, tipo_auth=i.tipo_auth, auth_meta=dumps(i.auth_meta), credencial_cifrada=i.credencial,
                    encabezados=dumps(i.encabezados), timeout_s=i.timeout_s, reintentos=i.reintentos,
                    limite_por_minuto=i.limite_por_minuto, estado=i.estado,
                    especificacion=dumps(i.especificacion) if i.especificacion is not None else None)

    def create(self, integration: Integration) -> bool:
        i = integration
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "synapse.integracion_insertar", **self._values(i), version=i.version,
                                      creado_por=i.creado_por, fecha_creacion=i.fecha_creacion,
                                      fecha_modificacion=i.fecha_modificacion, ultimo_estado_salud=i.ultimo_estado_salud,
                                      ultima_verificacion=i.ultima_verificacion)) == 1

    def get(self, id_integracion: str, id_empresa: str) -> Optional[Integration]:
        with self._db.cursor() as cur:
            row = ejecutar(cur, "synapse.integracion_obtener", id_integracion=id_integracion, id_empresa=id_empresa).fetchone()
        return self._integration(row) if row else None

    def list(self, id_empresa: str) -> List[Integration]:
        with self._db.cursor() as cur:
            rows = ejecutar(cur, "synapse.integracion_listar", id_empresa=id_empresa).fetchall()
        return [self._integration(r) for r in rows]

    def count(self, id_empresa: str) -> int:
        with self._db.cursor() as cur:
            return ejecutar(cur, "synapse.integracion_contar", id_empresa=id_empresa).fetchone()[0]

    def update(self, integration: Integration, expected_version: int) -> bool:
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "synapse.integracion_actualizar", **self._values(integration),
                                      fecha_modificacion=integration.fecha_modificacion, version_esperada=expected_version)) == 1

    def delete(self, id_integracion: str, id_empresa: str) -> bool:
        with self._db.cursor(commit=True) as cur:
            return afectadas(ejecutar(cur, "synapse.integracion_eliminar", id_integracion=id_integracion, id_empresa=id_empresa)) == 1

    def set_health(self, id_integracion: str, estado: str, at: datetime) -> None:
        with self._db.cursor(commit=True) as cur:
            ejecutar(cur, "synapse.integracion_salud", id_integracion=id_integracion, estado=estado, fecha=at)

    def log_call(self, record: CallRecord) -> None:
        r = record
        with self._db.cursor(commit=True) as cur:
            ejecutar(cur, "synapse.llamada_insertar", id_llamada=r.id_llamada, id_integracion=r.id_integracion,
                     id_empresa=r.id_empresa, metodo=r.metodo, ruta=r.ruta[:500], id_operacion=r.id_operacion,
                     codigo_http=r.codigo_http, exito=r.exito, duracion_ms=r.duracion_ms, intentos=r.intentos,
                     error=(r.error or None) and r.error[:500], origen=r.origen, usuario=r.usuario, fecha=r.fecha)

    def calls(self, id_empresa: str, id_integracion: Optional[str], desde: Optional[datetime], limit: int) -> List[CallRecord]:
        with self._db.cursor() as cur:
            rows = ejecutar(cur, "synapse.llamada_listar", id_empresa=id_empresa, id_integracion=id_integracion or None,
                            desde=desde or None, limite=limit).fetchall()
        return [CallRecord(id_llamada=r[0], id_integracion=r[1], id_empresa=r[2], metodo=r[3], ruta=r[4], id_operacion=r[5],
                           codigo_http=r[6], exito=bool(r[7]), duracion_ms=float(r[8]), intentos=r[9], error=r[10], origen=r[11],
                           usuario=r[12] or "", fecha=r[13]) for r in rows]
