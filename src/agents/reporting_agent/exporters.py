"""Exportación de reportes de Insight a CSV (seguro para hojas de cálculo) y JSON."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List

FORMATS = ("json", "csv")
MEDIA_TYPES = {"json": "application/json", "csv": "text/csv"}
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    text = str(value)
    if text.startswith(_FORMULA_PREFIXES) and not _is_number(text):
        return "'" + text
    return text


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def to_csv(columns: List[str], rows: List[Dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(c)) for c in columns])
    return "\ufeff" + buffer.getvalue()


def to_json(report: Dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, default=str)


def export(report: Dict[str, Any], fmt: str) -> str:
    if fmt == "csv":
        return to_csv(report["columnas"], report["filas"])
    return to_json(report)
