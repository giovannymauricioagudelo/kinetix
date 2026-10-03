"""Persistencia de Synapse: integraciones por empresa (synapse_integraciones) y bitácora de llamadas (synapse_llamadas)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.common import dumps, loads
from src.agents.sqlserver import SqlServerClient


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
    _COLUMNS = ("id_integracion, id_empresa, nombre, descripcion, url_base, tipo_auth, auth_meta, credencial_cifrada, encabezados, "
                "timeout_s, reintentos, limite_por_minuto, estado, especificacion, version, creado_por, fecha_creacion, "
                "fecha_modificacion, ultimo_estado_salud, ultima_verificacion")
    _CALL_COLUMNS = ("id_llamada, id_integracion, id_empresa, metodo, ruta, id_operacion, codigo_http, exito, duracion_ms, intentos, "
                     "error, origen, usuario, fecha")

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
    def _values(i: Integration) -> tuple:
        return (i.id_integracion, i.id_empresa, i.nombre, i.descripcion, i.url_base, i.tipo_auth, dumps(i.auth_meta), i.credencial,
                dumps(i.encabezados), i.timeout_s, i.reintentos, i.limite_por_minuto, i.estado,
                dumps(i.especificacion) if i.especificacion is not None else None, i.version, i.creado_por, i.fecha_creacion,
                i.fecha_modificacion, i.ultimo_estado_salud, i.ultima_verificacion)

    def create(self, integration: Integration) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                f"INSERT INTO dbo.synapse_integraciones ({self._COLUMNS}) SELECT {', '.join('?' * 20)} "
                "WHERE NOT EXISTS (SELECT 1 FROM dbo.synapse_integraciones WITH (UPDLOCK, HOLDLOCK) WHERE id_empresa = ? AND nombre = ?)",
                (*self._values(integration), integration.id_empresa, integration.nombre),
            )
            return cur.rowcount == 1

    def get(self, id_integracion: str, id_empresa: str) -> Optional[Integration]:
        with self._db.cursor() as cur:
            cur.execute(f"SELECT {self._COLUMNS} FROM dbo.synapse_integraciones WHERE id_integracion = ? AND id_empresa = ?",
                        (id_integracion, id_empresa))
            row = cur.fetchone()
        return self._integration(row) if row else None

    def list(self, id_empresa: str) -> List[Integration]:
        with self._db.cursor() as cur:
            cur.execute(f"SELECT {self._COLUMNS} FROM dbo.synapse_integraciones WHERE id_empresa = ? ORDER BY nombre", (id_empresa,))
            rows = cur.fetchall()
        return [self._integration(r) for r in rows]

    def count(self, id_empresa: str) -> int:
        with self._db.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM dbo.synapse_integraciones WHERE id_empresa = ?", (id_empresa,))
            return cur.fetchone()[0]

    def update(self, integration: Integration, expected_version: int) -> bool:
        i = integration
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dbo.synapse_integraciones SET nombre = ?, descripcion = ?, url_base = ?, tipo_auth = ?, auth_meta = ?, "
                "credencial_cifrada = ?, encabezados = ?, timeout_s = ?, reintentos = ?, limite_por_minuto = ?, estado = ?, "
                "especificacion = ?, version = version + 1, fecha_modificacion = ? "
                "WHERE id_integracion = ? AND id_empresa = ? AND version = ? AND NOT EXISTS ("
                "SELECT 1 FROM dbo.synapse_integraciones o WHERE o.id_empresa = ? AND o.nombre = ? AND o.id_integracion <> ?)",
                (i.nombre, i.descripcion, i.url_base, i.tipo_auth, dumps(i.auth_meta), i.credencial, dumps(i.encabezados), i.timeout_s,
                 i.reintentos, i.limite_por_minuto, i.estado, dumps(i.especificacion) if i.especificacion is not None else None,
                 i.fecha_modificacion, i.id_integracion, i.id_empresa, expected_version, i.id_empresa, i.nombre, i.id_integracion),
            )
            return cur.rowcount == 1

    def delete(self, id_integracion: str, id_empresa: str) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute("DELETE FROM dbo.synapse_integraciones WHERE id_integracion = ? AND id_empresa = ?", (id_integracion, id_empresa))
            return cur.rowcount == 1

    def set_health(self, id_integracion: str, estado: str, at: datetime) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute("UPDATE dbo.synapse_integraciones SET ultimo_estado_salud = ?, ultima_verificacion = ? WHERE id_integracion = ?",
                        (estado, at, id_integracion))

    def log_call(self, record: CallRecord) -> None:
        r = record
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                f"INSERT INTO dbo.synapse_llamadas ({self._CALL_COLUMNS}) VALUES ({', '.join('?' * 14)})",
                (r.id_llamada, r.id_integracion, r.id_empresa, r.metodo, r.ruta[:500], r.id_operacion, r.codigo_http, r.exito,
                 r.duracion_ms, r.intentos, (r.error or None) and r.error[:500], r.origen, r.usuario, r.fecha),
            )

    def calls(self, id_empresa: str, id_integracion: Optional[str], desde: Optional[datetime], limit: int) -> List[CallRecord]:
        sql = f"SELECT TOP (?) {self._CALL_COLUMNS} FROM dbo.synapse_llamadas WHERE id_empresa = ?"
        params: List[Any] = [limit, id_empresa]
        if id_integracion:
            sql += " AND id_integracion = ?"
            params.append(id_integracion)
        if desde:
            sql += " AND fecha >= ?"
            params.append(desde)
        with self._db.cursor() as cur:
            cur.execute(sql + " ORDER BY fecha DESC", params)
            rows = cur.fetchall()
        return [CallRecord(id_llamada=r[0], id_integracion=r[1], id_empresa=r[2], metodo=r[3], ruta=r[4], id_operacion=r[5],
                           codigo_http=r[6], exito=bool(r[7]), duracion_ms=float(r[8]), intentos=r[9], error=r[10], origen=r[11],
                           usuario=r[12] or "", fecha=r[13]) for r in rows]
