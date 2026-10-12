"""Nexus en proceso sobre una aplicación generada: empresas y entornos ({app}_{entorno}) sin levantar la API.

    python scripts/nexus_entorno.py llavia empresa piloto "Piloto interno"
    python scripts/nexus_entorno.py llavia desplegar piloto --empresas plataforma,piloto
    python scripts/nexus_entorno.py llavia entornos

Imprime el resultado en JSON por stdout (Orbit lo lee desde scripts/piloto.py de cada aplicación) y sale con 1 si el
despliegue falla. La API equivalente es POST /api/v1/nexus/aplicaciones/{app}/entornos/{entorno}/desplegar.

acceso-datos: excepcion-administracion (herramienta de administración de Nexus sobre las bases destino)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from src.agents.database_agent.dependencies import build_default_apps_service  # noqa: E402
from src.agents.security_agent.config import load_sqlserver_settings  # noqa: E402
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError  # noqa: E402
from src.agents.sqlserver import SqlServerClient  # noqa: E402


def propietario(id_aplicacion: str) -> str:
    with SqlServerClient(load_sqlserver_settings(), 30).cursor() as cur:
        cur.execute("SELECT propietario FROM dbo.nexus_aplicaciones WHERE id_aplicacion = ?", (id_aplicacion,))
        fila = cur.fetchone()
    if fila is None:
        sys.exit(f"La aplicación {id_aplicacion} no está registrada en Nexus")
    return str(fila[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("aplicacion")
    parser.add_argument("--actor", default=os.getenv("NEXUS_ACTOR", "giovanny"))
    acciones = parser.add_subparsers(dest="accion", required=True)
    empresa = acciones.add_parser("empresa", help="Registra una empresa en la aplicación (idempotente)")
    empresa.add_argument("id_empresa")
    empresa.add_argument("nombre")
    desplegar = acciones.add_parser("desplegar", help="Despliega las migraciones en la base del entorno")
    desplegar.add_argument("entorno")
    desplegar.add_argument("--empresas", required=True, help="Separadas por coma")
    acciones.add_parser("entornos", help="Entornos desplegados y su versión")
    args = parser.parse_args()

    apps = build_default_apps_service()
    duenio = propietario(args.aplicacion)
    try:
        if args.accion == "empresa":
            actuales = {e["id_empresa"] for e in apps.get_app(duenio, args.aplicacion)["empresas"]}
            resultado = ({"id_empresa": args.id_empresa, "ya_registrada": True} if args.id_empresa in actuales
                         else apps.add_company(args.actor, duenio, args.aplicacion,
                                               {"id_empresa": args.id_empresa, "nombre": args.nombre}))
        elif args.accion == "desplegar":
            empresas = [e.strip() for e in args.empresas.split(",") if e.strip()]
            resultado = apps.deploy_environment(args.actor, duenio, args.aplicacion, args.entorno, empresas)
        else:
            resultado = apps.environments(duenio, args.aplicacion)
    except (InvalidInputError, ConflictError, NotFoundError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 2
    print(json.dumps(resultado, ensure_ascii=False))
    fallido = resultado.get("despliegue", {}).get("estado") == "fallido"
    return 1 if fallido else 0


if __name__ == "__main__":
    sys.exit(main())
