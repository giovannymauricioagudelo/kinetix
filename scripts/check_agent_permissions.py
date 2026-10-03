"""
Muestra los permisos de los agentes (Nexus, Matrix, Sentinel, Argus, Aurora, Vector, Prism, Orbit, Insight),
a qué roles están asignados, qué ve cada usuario y si existen las tablas de la plataforma.
Uso: venv\\Scripts\\python.exe scripts\\check_agent_permissions.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from src.agents.security_agent.config import load_sqlserver_settings  # noqa: E402

AGENT_PREFIXES = ("nexus", "matrix", "sentinel", "argus", "aurora", "vector", "prism", "orbit", "insight")
AGENT_PERMISSIONS = "(" + " OR ".join(f"p.id LIKE 'perm_{a}_%'" for a in AGENT_PREFIXES) + ")"
PLATFORM_TABLES = ("aurora_sistemas", "aurora_componentes", "vector_analisis", "prism_ejecuciones", "orbit_despliegues",
                   "insight_programaciones", "insight_reportes")


def main() -> None:
    conn = pyodbc.connect(load_sqlserver_settings().connection_string())
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT p.id, p.recurso + ':' + p.accion FROM dbo.permisos p WHERE {AGENT_PERMISSIONS} ORDER BY p.id")
        for perm_id, name in cur.fetchall():
            print(f"permiso  {perm_id:<18} {name}")
        cur.execute(
            f"SELECT rp.id_rol, COUNT(*) FROM dbo.roles_permisos rp JOIN dbo.permisos p ON p.id = rp.id_permiso "
            f"WHERE {AGENT_PERMISSIONS} GROUP BY rp.id_rol ORDER BY rp.id_rol"
        )
        for role, total in cur.fetchall():
            print(f"rol      {role:<18} {total} permisos de agentes")
        cur.execute(
            f"SELECT u.nombre_usuario, STRING_AGG(p.recurso + ':' + p.accion, ', ') WITHIN GROUP (ORDER BY p.recurso, p.accion) "
            f"FROM dbo.usuarios u JOIN dbo.usuarios_roles ur ON ur.id_usuario = u.id "
            f"JOIN dbo.roles_permisos rp ON rp.id_rol = ur.id_rol JOIN dbo.permisos p ON p.id = rp.id_permiso "
            f"WHERE {AGENT_PERMISSIONS} GROUP BY u.nombre_usuario ORDER BY u.nombre_usuario"
        )
        for user, perms in cur.fetchall():
            print(f"usuario  {user:<18} {perms}")
        cur.execute(
            "SELECT name FROM sys.indexes WHERE name IN ('idx_auditoria_reglas_regla_fecha', 'idx_reglas_estado_prioridad') ORDER BY name"
        )
        print("indices ", [r[0] for r in cur.fetchall()])
        cur.execute(f"SELECT name FROM sys.tables WHERE name IN ({', '.join('?' * len(PLATFORM_TABLES))}) ORDER BY name", PLATFORM_TABLES)
        found = {r[0] for r in cur.fetchall()}
        print("tablas  ", sorted(found), "faltan:", sorted(set(PLATFORM_TABLES) - found) or "ninguna")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
