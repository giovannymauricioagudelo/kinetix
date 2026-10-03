"""
Plantillas de Vector: genera un módulo de negocio completo con la arquitectura del proyecto
(entidad → repositorio en memoria/SQL Server → servicio → router con permisos de Sentinel → pruebas → DDL).
"""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass
from string import Template
from typing import Dict, List, Tuple

MODULE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
ENTITY = re.compile(r"^[A-Z][A-Za-z0-9]{1,40}$")
FIELD = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
FIELD_TYPES = {"str": ("str", "NVARCHAR(200)"), "int": ("int", "INT"), "float": ("float", "DECIMAL(18, 4)"), "bool": ("bool", "BIT")}
SAMPLES = {"str": '"ejemplo"', "int": "1", "float": "1.5", "bool": "True"}
RESERVED = frozenset({"id_empresa", "creado_por", "fecha_creacion"})


class ScaffoldError(ValueError):
    pass


@dataclass(frozen=True)
class FieldSpec:
    nombre: str
    tipo: str
    requerido: bool


def _snake(camel: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", camel).lower()


def _camel(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_") if part)


def parse_spec(modulo: str, entidad: str, campos: List[Dict[str, object]]) -> Tuple[str, str, List[FieldSpec]]:
    if not MODULE.match(modulo or "") or keyword.iskeyword(modulo):
        raise ScaffoldError("modulo: minúsculas, números y '_' (2 a 41 caracteres)")
    entidad = entidad or _camel(modulo)
    if not ENTITY.match(entidad):
        raise ScaffoldError("entidad: CamelCase con letra inicial mayúscula")
    if not 1 <= len(campos) <= 30:
        raise ScaffoldError("Define entre 1 y 30 campos")
    id_field = f"id_{_snake(entidad)}"
    fields, seen = [], set()
    for raw in campos:
        name, kind = str(raw.get("nombre") or ""), str(raw.get("tipo") or "str")
        if not FIELD.match(name) or keyword.iskeyword(name) or name in RESERVED or name == id_field:
            raise ScaffoldError(f"Nombre de campo inválido o reservado: {name!r}")
        if name in seen:
            raise ScaffoldError(f"Campo duplicado: {name}")
        if kind not in FIELD_TYPES:
            raise ScaffoldError(f"Tipo de campo no soportado: {kind!r} (str, int, float o bool)")
        seen.add(name)
        fields.append(FieldSpec(name, kind, bool(raw.get("requerido", True))))
    return modulo, entidad, sorted(fields, key=lambda f: not f.requerido)


REPOSITORY = Template('''"""Persistencia de $Entity: contrato, implementación en memoria y SQL Server (tabla dbo.$table)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import astuple, dataclass
from datetime import datetime
from typing import Dict, List, Optional

from src.agents.sqlserver import SqlServerClient


@dataclass(frozen=True)
class $Entity:
    $id_field: str
    id_empresa: str
$dataclass_fields
    creado_por: str = ""
    fecha_creacion: Optional[datetime] = None


class ${Entity}Repository(ABC):
    @abstractmethod
    def list(self, id_empresa: str, limit: int) -> List[$Entity]: ...

    @abstractmethod
    def get(self, id_empresa: str, item_id: str) -> Optional[$Entity]: ...

    @abstractmethod
    def create(self, item: $Entity) -> None: ...

    @abstractmethod
    def update(self, item: $Entity) -> bool: ...

    @abstractmethod
    def delete(self, id_empresa: str, item_id: str) -> bool: ...


class InMemory${Entity}Repository(${Entity}Repository):
    def __init__(self) -> None:
        self._items: Dict[str, $Entity] = {}
        self._lock = threading.Lock()

    def list(self, id_empresa: str, limit: int) -> List[$Entity]:
        return [i for i in self._items.values() if i.id_empresa == id_empresa][:limit]

    def get(self, id_empresa: str, item_id: str) -> Optional[$Entity]:
        item = self._items.get(item_id)
        return item if item and item.id_empresa == id_empresa else None

    def create(self, item: $Entity) -> None:
        with self._lock:
            self._items[item.$id_field] = item

    def update(self, item: $Entity) -> bool:
        with self._lock:
            if self.get(item.id_empresa, item.$id_field) is None:
                return False
            self._items[item.$id_field] = item
            return True

    def delete(self, id_empresa: str, item_id: str) -> bool:
        with self._lock:
            if self.get(id_empresa, item_id) is None:
                return False
            del self._items[item_id]
            return True


class SqlServer${Entity}Repository(${Entity}Repository):
    _COLUMNS = "$sql_columns"

    def __init__(self, client: SqlServerClient) -> None:
        self._db = client

    def list(self, id_empresa: str, limit: int) -> List[$Entity]:
        with self._db.cursor() as cur:
            cur.execute(f"SELECT TOP (?) {self._COLUMNS} FROM dbo.$table WHERE id_empresa = ? ORDER BY fecha_creacion DESC",
                        (limit, id_empresa))
            return [$Entity(*row) for row in cur.fetchall()]

    def get(self, id_empresa: str, item_id: str) -> Optional[$Entity]:
        with self._db.cursor() as cur:
            cur.execute(f"SELECT {self._COLUMNS} FROM dbo.$table WHERE id_empresa = ? AND $id_field = ?", (id_empresa, item_id))
            row = cur.fetchone()
        return $Entity(*row) if row else None

    def create(self, item: $Entity) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(f"INSERT INTO dbo.$table ({self._COLUMNS}) VALUES ($placeholders)", astuple(item))

    def update(self, item: $Entity) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute("UPDATE dbo.$table SET $set_clause WHERE id_empresa = ? AND $id_field = ?",
                        ($update_values, item.id_empresa, item.$id_field))
            return cur.rowcount == 1

    def delete(self, id_empresa: str, item_id: str) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute("DELETE FROM dbo.$table WHERE id_empresa = ? AND $id_field = ?", (id_empresa, item_id))
            return cur.rowcount == 1
''')

SERVICE = Template('''"""Casos de uso de $Entity: validación y CRUD por empresa."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Callable, Dict

from src.agents.common import iso, new_id, utcnow
from src.agents.$package.repository import $Entity, ${Entity}Repository
from src.agents.security_agent.models import InvalidInputError, NotFoundError

FIELDS: Dict[str, tuple] = {
$fields_spec
}
MAX_TEXT = 200


def clean(data: Dict[str, Any], partial: bool = False) -> Dict[str, Any]:
    unknown = set(data) - set(FIELDS)
    if unknown:
        raise InvalidInputError(f"Campos desconocidos: {', '.join(sorted(unknown))}")
    result: Dict[str, Any] = {}
    for name, (kind, required) in FIELDS.items():
        value = data.get(name)
        if value is None:
            if required and not partial:
                raise InvalidInputError(f"{name} es obligatorio")
            continue
        if kind is float and isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        if not isinstance(value, kind) or (kind is not bool and isinstance(value, bool)):
            raise InvalidInputError(f"{name} debe ser de tipo {kind.__name__}")
        if kind is str and (not value.strip() or len(value) > MAX_TEXT):
            raise InvalidInputError(f"{name} debe tener entre 1 y {MAX_TEXT} caracteres")
        result[name] = value
    return result


def view(item: $Entity) -> Dict[str, Any]:
    data = asdict(item)
    data["fecha_creacion"] = iso(item.fecha_creacion)
    return data


class ${Entity}Service:
    def __init__(self, repository: ${Entity}Repository, clock: Callable = utcnow) -> None:
        self._repo = repository
        self._clock = clock

    def _get(self, id_empresa: str, item_id: str) -> $Entity:
        item = self._repo.get(id_empresa, item_id)
        if item is None:
            raise NotFoundError(f"$Entity no encontrado: {item_id}")
        return item

    def list(self, id_empresa: str, limit: int = 50) -> Dict[str, Any]:
        items = self._repo.list(id_empresa, max(1, min(limit, 500)))
        return {"total": len(items), "$plural": [view(i) for i in items]}

    def get(self, id_empresa: str, item_id: str) -> Dict[str, Any]:
        return view(self._get(id_empresa, item_id))

    def create(self, actor: str, id_empresa: str, data: Dict[str, Any]) -> Dict[str, Any]:
        item = $Entity($id_field=new_id("$prefix"), id_empresa=id_empresa, creado_por=actor,
                       fecha_creacion=self._clock(), **clean(data))
        self._repo.create(item)
        return view(item)

    def update(self, id_empresa: str, item_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        updated = replace(self._get(id_empresa, item_id), **clean(data, partial=True))
        if not self._repo.update(updated):
            raise NotFoundError(f"$Entity no encontrado: {item_id}")
        return view(updated)

    def delete(self, id_empresa: str, item_id: str) -> Dict[str, Any]:
        if not self._repo.delete(id_empresa, item_id):
            raise NotFoundError(f"$Entity no encontrado: {item_id}")
        return {"eliminado": item_id}
''')

DEPENDENCIES = Template('''"""Instancia compartida de ${Entity}Service (${ENV}_REPOSITORY=memory para desarrollo sin SQL Server)."""

from __future__ import annotations

from typing import Optional

from src.agents.common import Lazy, sqlserver_client, use_memory
from src.agents.$package.repository import InMemory${Entity}Repository
from src.agents.$package.service import ${Entity}Service


def build_default_service() -> ${Entity}Service:
    if use_memory("${ENV}_REPOSITORY"):
        return ${Entity}Service(InMemory${Entity}Repository())
    from src.agents.$package.repository import SqlServer${Entity}Repository

    return ${Entity}Service(SqlServer${Entity}Repository(sqlserver_client("${ENV}_QUERY_TIMEOUT_SECONDS")))


_service = Lazy(build_default_service)


def get_${module}_service() -> ${Entity}Service:
    return _service.get()


def set_${module}_service(service: Optional[${Entity}Service]) -> None:
    _service.set(service)
''')

ROUTES = Template('''"""$Entity — CRUD por empresa protegido con permisos de Sentinel ($module:ver / $module:gestionar)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from src.agents.$package.dependencies import get_${module}_service
from src.agents.$package.service import ${Entity}Service
from src.agents.security_agent.dependencies import get_security_service, require_permission, translate_errors
from src.agents.security_agent.models import Principal
from src.agents.security_agent.service import SecurityService
from src.api.routes._common import client_ip, ok

PERM_VIEW = "$module:ver"
PERM_MANAGE = "$module:gestionar"
UNAVAILABLE = "Servicio de $module no disponible temporalmente"

router = APIRouter(prefix="/api/v1/$route", tags=["$Entity"])
_can_view = require_permission(PERM_VIEW)
_can_manage = require_permission(PERM_MANAGE)


class ${Entity}Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
$body_fields


class ${Entity}Patch(BaseModel):
    model_config = ConfigDict(extra="forbid")
$patch_fields


@router.get("")
def list_items(limite: int = Query(50, ge=1, le=500), principal: Principal = Depends(_can_view),
               service: ${Entity}Service = Depends(get_${module}_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok(service.list(principal.id_empresa, limite))


@router.post("", status_code=201)
def create_item(body: ${Entity}Body, request: Request, principal: Principal = Depends(_can_manage),
                service: ${Entity}Service = Depends(get_${module}_service),
                security: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        item = service.create(principal.nombre_usuario, principal.id_empresa, body.model_dump(exclude_none=True))
        security.record_audit(principal, "${module}_crear", f"$module:{item['$id_field']}", ip=client_ip(request))
        return ok({"$singular": item})


@router.get("/{item_id}")
def get_item(item_id: str, principal: Principal = Depends(_can_view),
             service: ${Entity}Service = Depends(get_${module}_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        return ok({"$singular": service.get(principal.id_empresa, item_id)})


@router.patch("/{item_id}")
def update_item(item_id: str, body: ${Entity}Patch, request: Request, principal: Principal = Depends(_can_manage),
                service: ${Entity}Service = Depends(get_${module}_service),
                security: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        item = service.update(principal.id_empresa, item_id, body.model_dump(exclude_unset=True, exclude_none=True))
        security.record_audit(principal, "${module}_actualizar", f"$module:{item_id}", ip=client_ip(request))
        return ok({"$singular": item})


@router.delete("/{item_id}")
def delete_item(item_id: str, request: Request, principal: Principal = Depends(_can_manage),
                service: ${Entity}Service = Depends(get_${module}_service),
                security: SecurityService = Depends(get_security_service)) -> Dict[str, Any]:
    with translate_errors(UNAVAILABLE):
        result = service.delete(principal.id_empresa, item_id)
        security.record_audit(principal, "${module}_eliminar", f"$module:{item_id}", ip=client_ip(request))
        return ok(result)
''')

TESTS = Template('''"""Pruebas generadas por Vector para $Entity: servicio y API con repositorio en memoria."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agents.$package.dependencies import set_${module}_service
from src.agents.$package.repository import InMemory${Entity}Repository
from src.agents.$package.service import ${Entity}Service
from src.agents.security_agent import SecurityService
from src.agents.security_agent.config import SecuritySettings
from src.agents.security_agent.dependencies import set_security_service
from src.agents.security_agent.models import InvalidInputError, NotFoundError
from src.api.routes import ${module}_routes, sentinel_routes
from tests.unit.test_sentinel_agent import PASSWORDS, seeded_repository

SAMPLE = {$sample}


def test_service_crud_is_scoped_by_company():
    service = ${Entity}Service(InMemory${Entity}Repository())
    created = service.create("ana", "gio", SAMPLE)
    assert service.get("gio", created["$id_field"])["$first_field"] == SAMPLE["$first_field"]
    assert service.list("otra_empresa")["total"] == 0
    with pytest.raises(NotFoundError):
        service.get("otra_empresa", created["$id_field"])
    with pytest.raises(InvalidInputError):
        service.create("ana", "gio", {**SAMPLE, "campo_inexistente": 1})
    assert service.delete("gio", created["$id_field"])["eliminado"] == created["$id_field"]


@pytest.fixture
def client():
    repo = seeded_repository()
    for perm_id, accion in (("p_${module}_ver", "ver"), ("p_${module}_gestionar", "gestionar")):
        repo.add_permission(perm_id, "$module", accion)
        repo.grant_permission("rol_admin", perm_id)
    set_security_service(SecurityService(repo, SecuritySettings(secret_key="vector-generated-" + "x" * 32)))
    set_${module}_service(${Entity}Service(InMemory${Entity}Repository()))
    sentinel_routes._ip_limiter._hits.clear()
    app = FastAPI()
    app.include_router(sentinel_routes.router)
    app.include_router(${module}_routes.router)
    yield TestClient(app)
    set_security_service(None)
    set_${module}_service(None)


def test_api_requires_permission_and_supports_crud(client):
    assert client.get("/api/v1/$route").status_code == 401
    session = client.post("/api/v1/sentinel/autenticar",
                          json={"nombre_usuario": "ana", "contrasena": PASSWORDS["ana"], "id_empresa": "gio"}).json()
    auth = {"Authorization": f"Bearer {session['token_acceso']}"}
    created = client.post("/api/v1/$route", json=SAMPLE, headers=auth)
    assert created.status_code == 201
    item_id = created.json()["$singular"]["$id_field"]
    assert client.get(f"/api/v1/$route/{item_id}", headers=auth).status_code == 200
    assert client.patch(f"/api/v1/$route/{item_id}", json={"$first_field": SAMPLE["$first_field"]}, headers=auth).status_code == 200
    assert client.delete(f"/api/v1/$route/{item_id}", headers=auth).status_code == 200
    assert client.get(f"/api/v1/$route/{item_id}", headers=auth).status_code == 404
''')

SQL = Template('''--| ============================================================================ |
--| $Entity - tabla y permisos generados por Vector                              |
--| Idempotente: se puede ejecutar varias veces y no borra datos                 |
--| ============================================================================ |

USE kinetix;
GO

--| Tabla dbo.$table: un registro de $Entity por empresa |
IF OBJECT_ID(N'dbo.$table', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.$table (
        $id_field NVARCHAR(40) NOT NULL CONSTRAINT PK_$table PRIMARY KEY CLUSTERED,
        id_empresa NVARCHAR(100) NOT NULL,
$sql_fields
        creado_por NVARCHAR(200) NULL,
        fecha_creacion DATETIME2 NOT NULL CONSTRAINT DF_${table}_fecha DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX idx_${table}_empresa_fecha ON dbo.$table(id_empresa, fecha_creacion DESC);
END
GO

--| Permisos $module:ver y $module:gestionar para rol_admin |
DECLARE @con_nombre BIT = CASE WHEN COL_LENGTH('dbo.permisos', 'nombre_permiso') IS NULL THEN 0 ELSE 1 END;
IF NOT EXISTS (SELECT 1 FROM dbo.permisos WHERE id = 'perm_${module}_ver')
BEGIN
    IF @con_nombre = 1
        EXEC sp_executesql N'INSERT INTO dbo.permisos (id, nombre_permiso, recurso, accion, descripcion)
            VALUES (''perm_${module}_ver'', N''Ver $Entity'', ''$module'', ''ver'', N''Consultar $module'')';
    ELSE
        INSERT INTO dbo.permisos (id, recurso, accion, descripcion) VALUES ('perm_${module}_ver', '$module', 'ver', N'Consultar $module');
END
IF NOT EXISTS (SELECT 1 FROM dbo.permisos WHERE id = 'perm_${module}_gestionar')
BEGIN
    IF @con_nombre = 1
        EXEC sp_executesql N'INSERT INTO dbo.permisos (id, nombre_permiso, recurso, accion, descripcion)
            VALUES (''perm_${module}_gestionar'', N''Gestionar $Entity'', ''$module'', ''gestionar'', N''Crear, actualizar y eliminar $module'')';
    ELSE
        INSERT INTO dbo.permisos (id, recurso, accion, descripcion)
        VALUES ('perm_${module}_gestionar', '$module', 'gestionar', N'Crear, actualizar y eliminar $module');
END
INSERT INTO dbo.roles_permisos (id_rol, id_permiso)
SELECT 'rol_admin', p.id FROM dbo.permisos p
WHERE p.id IN ('perm_${module}_ver', 'perm_${module}_gestionar')
  AND EXISTS (SELECT 1 FROM dbo.roles WHERE id = 'rol_admin')
  AND NOT EXISTS (SELECT 1 FROM dbo.roles_permisos rp WHERE rp.id_rol = 'rol_admin' AND rp.id_permiso = p.id);
GO
''')


def generate(modulo: str, entidad: str, campos: List[Dict[str, object]]) -> Dict[str, str]:
    """Rutas del repositorio → contenido de cada archivo generado."""
    module, entity, fields = parse_spec(modulo, entidad, campos)
    package = f"{module}_module"
    id_field = f"id_{_snake(entity)}"
    columns = [id_field, "id_empresa", *(f.nombre for f in fields), "creado_por", "fecha_creacion"]

    def py_type(f: FieldSpec) -> str:
        return FIELD_TYPES[f.tipo][0]

    dataclass_fields = "\n".join(
        f"    {f.nombre}: {py_type(f)}" if f.requerido else f"    {f.nombre}: Optional[{py_type(f)}] = None" for f in fields
    )
    body_fields = "\n".join(
        (f"    {f.nombre}: {py_type(f)} = " + ("Field(..., min_length=1, max_length=200)" if f.tipo == "str" else "Field(...)"))
        if f.requerido else f"    {f.nombre}: Optional[{py_type(f)}] = None"
        for f in fields
    )
    values = {
        "Entity": entity,
        "module": module,
        "package": package,
        "table": module,
        "route": module.replace("_", "-"),
        "plural": module,
        "singular": _snake(entity),
        "prefix": module[:3],
        "ENV": module.upper(),
        "id_field": id_field,
        "first_field": fields[0].nombre,
        "dataclass_fields": dataclass_fields,
        "sql_columns": ", ".join(columns),
        "placeholders": ", ".join("?" for _ in columns),
        "set_clause": ", ".join(f"{f.nombre} = ?" for f in fields),
        "update_values": ", ".join(f"item.{f.nombre}" for f in fields),
        "fields_spec": "\n".join(f'    "{f.nombre}": ({py_type(f)}, {f.requerido}),' for f in fields),
        "body_fields": body_fields,
        "patch_fields": "\n".join(f"    {f.nombre}: Optional[{py_type(f)}] = None" for f in fields),
        "sample": ", ".join(f'"{f.nombre}": {SAMPLES[f.tipo]}' for f in fields),
        "sql_fields": "\n".join(f"        {f.nombre} {FIELD_TYPES[f.tipo][1]} {'NOT NULL' if f.requerido else 'NULL'}," for f in fields),
    }
    return {
        f"src/agents/{package}/__init__.py": f'"""Módulo {entity} generado por Vector."""\n',
        f"src/agents/{package}/repository.py": REPOSITORY.substitute(values),
        f"src/agents/{package}/service.py": SERVICE.substitute(values),
        f"src/agents/{package}/dependencies.py": DEPENDENCIES.substitute(values),
        f"src/api/routes/{module}_routes.py": ROUTES.substitute(values),
        f"tests/unit/test_{module}_module.py": TESTS.substitute(values),
        f"sql/{module}.sql": SQL.substitute(values),
    }
