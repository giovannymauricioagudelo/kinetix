"""
Muestra los permisos de Nexus, Matrix, Sentinel y Argus, a qué roles están asignados y qué ve cada usuario.
Uso: venv\\Scripts\\python.exe scripts\\check_agent_permissions.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from src.agents.security_agent.config import load_sqlserver_settings  # noqa: E402

AGENT_PERMISSIONS = "p.id LIKE 'perm_nexus_%' OR p.id LIKE 'perm_matrix_%' OR p.id LIKE 'perm_sentinel_%' OR p.id LIKE 'perm_argus_%'"


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
    finally:
        conn.close()


if __name__ == "__main__":
    main()
