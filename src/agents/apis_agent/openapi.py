"""
Importación de especificaciones OpenAPI 3.x y Swagger 2.0 para Synapse: catálogo de operaciones con sus
parámetros, y armado/validación de cada llamada contra ese catálogo.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import yaml

from src.agents.security_agent.models import InvalidInputError

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
LOCATIONS = ("path", "query", "header")
MAX_OPERATIONS = 500
MAX_SPEC_BYTES = 2_000_000
OPERATION_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,100}$")
_SLUG = re.compile(r"[^A-Za-z0-9]+")
_TEMPLATE = re.compile(r"\{([^{}/]+)\}")


def load_text(content: str) -> Dict[str, Any]:
    if len(content.encode("utf-8")) > MAX_SPEC_BYTES:
        raise InvalidInputError(f"La especificación supera {MAX_SPEC_BYTES // 1_000_000} MB")
    try:
        data = json.loads(content)
    except ValueError:
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            raise InvalidInputError("La especificación no es JSON ni YAML válido") from None
    if not isinstance(data, dict):
        raise InvalidInputError("La especificación debe ser un objeto JSON/YAML")
    return data


def _resolve(node: Any, spec: Dict[str, Any]) -> Dict[str, Any]:
    """Solo referencias locales (#/...); las externas se ignoran."""
    for _ in range(10):
        if not isinstance(node, dict) or "$ref" not in node:
            break
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return {}
        target: Any = spec
        for part in ref[2:].split("/"):
            target = target.get(part.replace("~1", "/").replace("~0", "~")) if isinstance(target, dict) else None
        node = target
    return node if isinstance(node, dict) else {}


def _param(raw: Any, spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    p = _resolve(raw, spec)
    location, name = p.get("in"), p.get("name")
    if location not in (*LOCATIONS, "body") or not isinstance(name, str) or not name:
        return None
    schema = _resolve(p.get("schema"), spec)
    return {"nombre": name[:100], "en": location, "requerido": location == "path" or bool(p.get("required")),
            "tipo": schema.get("type") or p.get("type") or ("object" if location == "body" else "string")}


def _operation_id(raw: Any, method: str, path: str, used: set) -> str:
    candidate = raw if isinstance(raw, str) and OPERATION_ID.match(raw) else f"{method}_{_SLUG.sub('_', path).strip('_') or 'raiz'}"
    candidate = candidate[:100]
    unique, n = candidate, 2
    while unique in used:
        unique, n = f"{candidate[:95]}_{n}", n + 1
    used.add(unique)
    return unique


def _servers(spec: Dict[str, Any]) -> List[str]:
    if isinstance(spec.get("servers"), list):
        return [s["url"] for s in spec["servers"] if isinstance(s, dict) and isinstance(s.get("url"), str)][:10]
    if isinstance(spec.get("host"), str):
        schemes = spec.get("schemes") if isinstance(spec.get("schemes"), list) else ["https"]
        return [f"{scheme}://{spec['host']}{spec.get('basePath', '')}" for scheme in schemes][:10]
    return []


def parse_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    version = spec.get("openapi") or spec.get("swagger")
    if not isinstance(version, str) or version[:1] not in ("2", "3"):
        raise InvalidInputError("No es una especificación OpenAPI 3.x ni Swagger 2.0 (falta 'openapi' o 'swagger')")
    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise InvalidInputError("La especificación no declara rutas ('paths')")
    operations: List[Dict[str, Any]] = []
    used: set = set()
    for path, item in paths.items():
        item = _resolve(item, spec)
        if not isinstance(path, str) or not path.startswith("/"):
            continue
        shared = item.get("parameters") if isinstance(item.get("parameters"), list) else []
        for method in METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            own = op.get("parameters") if isinstance(op.get("parameters"), list) else []
            params: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for raw in [*shared, *own]:
                parsed = _param(raw, spec)
                if parsed:
                    params[(parsed["en"], parsed["nombre"])] = parsed
            body = _resolve(op.get("requestBody"), spec)
            body_param = next((p for p in params.values() if p["en"] == "body"), None)
            operations.append({
                "id_operacion": _operation_id(op.get("operationId"), method, path, used),
                "metodo": method.upper(),
                "ruta": path[:500],
                "resumen": str(op.get("summary") or op.get("description") or "")[:200],
                "parametros": [p for p in params.values() if p["en"] != "body"],
                "acepta_cuerpo": bool(body) or body_param is not None,
                "cuerpo_requerido": bool(body.get("required")) or bool(body_param and body_param["requerido"]),
                "obsoleta": bool(op.get("deprecated")),
            })
            if len(operations) > MAX_OPERATIONS:
                raise InvalidInputError(f"La especificación tiene más de {MAX_OPERATIONS} operaciones")
    if not operations:
        raise InvalidInputError("La especificación no tiene operaciones HTTP")
    info = spec.get("info") if isinstance(spec.get("info"), dict) else {}
    return {"formato": f"{'openapi' if 'openapi' in spec else 'swagger'} {version}", "titulo": str(info.get("title") or "")[:200],
            "version_api": str(info.get("version") or "")[:50], "servidores": _servers(spec), "operaciones": operations}


def _coerce(param: Dict[str, Any], value: Any) -> Any:
    kind = param["tipo"]
    try:
        if kind == "integer" and not isinstance(value, bool):
            return int(value)
        if kind == "number" and not isinstance(value, bool):
            return float(value)
        if kind == "boolean":
            if isinstance(value, bool):
                return value
            if str(value).lower() in ("true", "false"):
                return str(value).lower() == "true"
            raise ValueError
    except (TypeError, ValueError):
        raise InvalidInputError(f"El parámetro {param['nombre']} debe ser de tipo {kind}") from None
    if isinstance(value, (dict, list)) and kind not in ("array", "object"):
        raise InvalidInputError(f"El parámetro {param['nombre']} debe ser de tipo {kind}")
    return value


def build_call(operation: Dict[str, Any], parametros: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Dict[str, str]]:
    """Ruta con los parámetros de path sustituidos, parámetros de consulta y encabezados declarados."""
    declared = {p["nombre"]: p for p in operation["parametros"]}
    unknown = sorted(set(parametros) - set(declared))
    if unknown:
        raise InvalidInputError(f"Parámetros no declarados en {operation['id_operacion']}: {', '.join(unknown)}")
    path, query, headers = operation["ruta"], {}, {}
    for name, param in declared.items():
        value = parametros.get(name)
        if value is None:
            if param["requerido"]:
                raise InvalidInputError(f"Falta el parámetro obligatorio {name} ({param['en']})")
            continue
        value = _coerce(param, value)
        if param["en"] == "path":
            path = path.replace("{" + name + "}", quote(str(value), safe=""))
        elif param["en"] == "query":
            query[name] = value
        else:
            headers[name] = str(value)
    if _TEMPLATE.search(path):
        raise InvalidInputError("Faltan parámetros de ruta: " + ", ".join(_TEMPLATE.findall(path)))
    return path, query, headers


def match_operation(operations: List[Dict[str, Any]], method: str, path: str) -> Optional[Dict[str, Any]]:
    for op in operations:
        if op["metodo"] != method:
            continue
        pattern = "^" + _TEMPLATE.sub("[^/]+", re.escape(op["ruta"]).replace(r"\{", "{").replace(r"\}", "}")) + "$"
        if re.match(pattern, path):
            return op
    return None
