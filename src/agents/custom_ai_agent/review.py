"""
Utilidades de Genesis sobre texto: redactar secretos antes de enviarlos a un proveedor, extraer el bloque de
código de una respuesta y revisar SQL o código no Python (el Python lo analiza Vector).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

_SECRETS = (
    re.compile(r"(?i)\b(pwd|password|passwd|contrase(?:n|ñ)a|clave)\s*([=:])\s*([^\s;'\",]{3,})"),
    re.compile(r"(?i)\b(api[_-]?key|secret|token|access[_-]?key)\s*([=:])\s*['\"]?([A-Za-z0-9_\-./+=]{12,})"),
    re.compile(r"(?i)\b(bearer)(\s+)([A-Za-z0-9_\-.=]{20,})"),
)
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)
_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+#.-]*)[ \t]*\r?\n(.*?)```", re.S)

_SQL_RULES = (
    ("critica", "sql_drop", re.compile(r"(?i)\bDROP\s+(DATABASE|TABLE|SCHEMA|LOGIN|USER)\b"), "Elimina objetos de la base"),
    ("critica", "sql_truncate", re.compile(r"(?i)\bTRUNCATE\s+TABLE\b"), "Vacía una tabla completa"),
    ("critica", "sql_xp_cmdshell", re.compile(r"(?i)\bxp_cmdshell\b"), "Ejecuta comandos del sistema operativo"),
    ("critica", "sql_permisos", re.compile(r"(?i)\b(GRANT|REVOKE|ALTER\s+(LOGIN|SERVER\s+ROLE|ROLE))\b"), "Modifica permisos o roles"),
    ("alta", "sql_dinamico", re.compile(r"(?i)\bEXEC(UTE)?\s*\(\s*(@|'[^']*'\s*\+)"), "SQL dinámico armado por concatenación"),
    ("media", "sql_select_asterisco", re.compile(r"(?i)\bSELECT\s+\*"), "SELECT * (columnas explícitas son más estables)"),
)
_STATEMENT = re.compile(r"(?is)(?<!ON\s)(?<!FOR\s)(?<!AFTER\s)(?<!OF\s)(?<!,\s)\b(DELETE|UPDATE)\b(?!\s*\()(.*?)(?=;|\bGO\b|\Z)")


def redact(text: str) -> Tuple[str, int]:
    """Reemplaza contraseñas, llaves y tokens evidentes por *** y devuelve cuántos se ocultaron."""
    count = 0

    def mask(match: re.Match) -> str:
        nonlocal count
        count += 1
        return f"{match.group(1)}{match.group(2)}***"

    for pattern in _SECRETS:
        text = pattern.sub(mask, text)
    text, keys = _PRIVATE_KEY.subn("***LLAVE PRIVADA***", text)
    return text, count + keys


def extract_code(text: str, language: str) -> str:
    blocks = _FENCE.findall(text or "")
    if not blocks:
        return (text or "").strip()
    preferred = [code for lang, code in blocks if lang.lower() in (language, {"python": "py", "typescript": "ts", "javascript": "js"}.get(language))]
    return max(preferred or [code for _, code in blocks], key=len).strip()


def _line(content: str, index: int) -> int:
    return content.count("\n", 0, index) + 1


def review_text(content: str, language: str, path: str) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    if language == "sql":
        for severity, rule, pattern, message in _SQL_RULES:
            for match in pattern.finditer(content):
                findings.append({"archivo": path, "linea": _line(content, match.start()), "severidad": severity, "regla": rule,
                                 "mensaje": message})
        for match in _STATEMENT.finditer(content):
            if not re.search(r"(?i)\bWHERE\b", match.group(2)):
                findings.append({"archivo": path, "linea": _line(content, match.start()), "severidad": "alta", "regla": "sql_sin_where",
                                 "mensaje": f"{match.group(1).upper()} sin WHERE afecta todas las filas"})
    for pattern in _SECRETS:
        for match in pattern.finditer(content):
            value = match.group(3)
            if not re.match(r"(?i)^(\$\{.*\}|<.*>|process\.env|os\.getenv|os\.environ|\*+|x+)", value):
                findings.append({"archivo": path, "linea": _line(content, match.start()), "severidad": "critica",
                                 "regla": "secreto_en_codigo", "mensaje": "Credencial escrita en el código; usa variables de entorno"})
    by_severity = {s: sum(1 for f in findings if f["severidad"] == s) for s in ("critica", "alta", "media", "baja")}
    penalty = 2.5 * by_severity["critica"] + 1.0 * by_severity["alta"] + 0.3 * by_severity["media"]
    return {"puntuacion": round(max(0.0, 10 - penalty), 2), "por_severidad": by_severity, "total_hallazgos": len(findings),
            "hallazgos": findings[:100]}
