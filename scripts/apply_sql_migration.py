"""
Aplica un script .sql (lotes separados por GO) en una sola transacción, con las credenciales de .env.
Uso: venv\\Scripts\\python.exe scripts\\apply_sql_migration.py NEXUS_MATRIX_SCHEMA.sql
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from src.agents.security_agent.config import load_sqlserver_settings  # noqa: E402


def main(script_path: str) -> int:
    path = Path(script_path)
    if not path.is_absolute():
        path = ROOT / path
    batches = [b for b in re.split(r"^\s*GO\s*$", path.read_text(encoding="utf-8-sig"), flags=re.M | re.I) if b.strip()]
    conn = pyodbc.connect(load_sqlserver_settings().connection_string(), autocommit=False)
    try:
        cur = conn.cursor()
        for index, batch in enumerate(batches, start=1):
            try:
                cur.execute(batch)
                while cur.nextset():
                    pass
            except pyodbc.Error as e:
                conn.rollback()
                print(f"REVERTIDA: falló el lote {index} de {len(batches)}: {e}")
                return 1
        conn.commit()
        print(f"APLICADA: {path.name} ({len(batches)} lotes)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
