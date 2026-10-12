"""Regla de la fábrica: los agentes solo llaman procedimientos almacenados (acceso-datos-procedimientos.mdc)."""

import re
from pathlib import Path

import pytest

from src.agents.development_agent.analyzer import analyze_source
from src.agents.sqlserver import ESQUEMAS, llamada

ROOT = Path(__file__).resolve().parents[2]


def test_src_sin_sql_de_datos_en_linea():
    hallazgos = []
    for archivo in sorted((ROOT / "src").rglob("*.py")):
        ruta = archivo.relative_to(ROOT).as_posix()
        findings, *_ = analyze_source(ruta, archivo.read_text(encoding="utf-8"))
        hallazgos += [f"{ruta}:{f.linea}" for f in findings if f.regla == "sql_en_linea"]
    assert hallazgos == [], f"SQL de datos en línea (usa un procedimiento de los esquemas {ESQUEMAS}): {hallazgos}"


def test_procedimientos_llamados_existen_en_la_migracion():
    migracion = (ROOT / "KINETIX_PROCEDIMIENTOS.sql").read_text(encoding="utf-8")
    definidos = set(re.findall(r"CREATE OR ALTER PROCEDURE (\w+\.\w+)", migracion))
    llamados = set()
    for archivo in (ROOT / "src" / "agents").rglob("*.py"):
        llamados |= set(re.findall(rf"\"((?:{'|'.join(ESQUEMAS)})\.[a-z][a-z0-9_]*)\"", archivo.read_text(encoding="utf-8")))
    assert llamados - definidos == set()
    assert definidos - llamados == set()


def test_llamada_compone_exec_con_parametros_con_nombre():
    assert llamada("sentinel.usuario_obtener", ["id_usuario"]) == "EXEC sentinel.usuario_obtener @id_usuario = ?"
    assert llamada("vector.analisis_listar", []) == "EXEC vector.analisis_listar"


@pytest.mark.parametrize(
    "procedimiento, parametros",
    [
        ("dbo.usuarios", ["x"]),
        ("app.inmueble_obtener", []),
        ("sentinel.x; DROP TABLE y", []),
        ("sentinel.usuario_obtener", ["id = 1; --"]),
        ("Sentinel.usuario_obtener", []),
    ],
)
def test_llamada_rechaza_nombres_no_validos(procedimiento, parametros):
    with pytest.raises(ValueError):
        llamada(procedimiento, parametros)
