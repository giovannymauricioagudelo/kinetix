"""
Crea el login kinetix_app (miembro de kinetix_app_rol: solo EXECUTE sobre los esquemas de los agentes) y comprueba
que no puede leer ni escribir tablas. Requiere aplicar antes KINETIX_PROCEDIMIENTOS.sql.

Uso (con la cuenta de Windows administradora de SQL Server; contraseña aleatoria si no se define KINETIX_SETUP_APP_PASSWORD):
    venv\\Scripts\\python.exe scripts\\provision_kinetix_app.py [--servidor localhost] [--escribir-env]

--escribir-env guarda SQLSERVER_APP_USER y SQLSERVER_APP_PASSWORD en .env (no versionado); sin esa opción se imprimen
para guardarlas en el gestor de secretos.

acceso-datos: excepcion-administracion (aprovisionamiento de login y usuario con credencial de administrador)
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

import pyodbc

ROOT = Path(__file__).resolve().parents[1]
BASE = "kinetix"
ROL = "kinetix_app_rol"
DRIVER = "ODBC Driver 18 for SQL Server"


def literal(texto: str) -> str:
    return "N'" + texto.replace("'", "''") + "'"


def conectar(servidor: str, base: str, usuario: str = "", contrasena: str = "") -> pyodbc.Connection:
    credencial = f"UID={usuario};PWD={contrasena}" if usuario else "Trusted_Connection=yes"
    return pyodbc.connect(f"Driver={{{DRIVER}}};Server={servidor};Database={base};{credencial};TrustServerCertificate=yes",
                          timeout=15, autocommit=True)


def provisionar(servidor: str, login: str, contrasena: str) -> None:
    cur = conectar(servidor, "master").cursor()
    nombre = "[" + login.replace("]", "]]") + "]"
    if cur.execute("SELECT 1 FROM sys.server_principals WHERE name = ?", login).fetchone():
        cur.execute(f"ALTER LOGIN {nombre} WITH PASSWORD = {literal(contrasena)}")
        print(f"Login {login}: contraseña actualizada.")
    else:
        cur.execute(f"CREATE LOGIN {nombre} WITH PASSWORD = {literal(contrasena)}, CHECK_POLICY = ON, DEFAULT_DATABASE = [{BASE}]")
        print(f"Login {login} creado.")
    cur.execute(f"USE [{BASE}]")
    if cur.execute("SELECT DATABASE_PRINCIPAL_ID(?)", ROL).fetchone()[0] is None:
        sys.exit(f"Falta el rol {ROL}: aplica antes KINETIX_PROCEDIMIENTOS.sql con scripts/apply_sql_migration.py.")
    if not cur.execute("SELECT 1 FROM sys.database_principals WHERE name = ?", login).fetchone():
        cur.execute(f"CREATE USER {nombre} FOR LOGIN {nombre} WITH DEFAULT_SCHEMA = dbo")
    cur.execute(f"ALTER ROLE {ROL} ADD MEMBER {nombre}")
    print(f"Usuario {login} en {BASE}, miembro de {ROL}.")


def verificar(servidor: str, login: str, contrasena: str) -> bool:
    cur = conectar(servidor, BASE, login, contrasena).cursor()
    q = lambda sql, *p: cur.execute(sql, *p).fetchone()[0]  # noqa: E731
    permiso = "SELECT HAS_PERMS_BY_NAME(?, N'OBJECT', ?)"
    checks = {
        "no es db_owner": q("SELECT IS_ROLEMEMBER(N'db_owner')") == 0,
        "no lee tablas directamente": q(permiso, "dbo.usuarios", "SELECT") == 0,
        "no escribe tablas directamente": q(permiso, "dbo.nexus_aplicaciones", "INSERT") == 0,
        "no puede borrar la auditoría": q(permiso, "dbo.bitacora_auditoria", "DELETE") == 0,
        "ejecuta los procedimientos de los agentes": q(permiso, "sentinel.usuario_obtener", "EXECUTE") == 1,
        "no puede crear tablas": q("SELECT HAS_PERMS_BY_NAME(DB_NAME(), N'DATABASE', N'CREATE TABLE')") == 0,
    }
    try:
        cur.execute("SELECT TOP 1 id FROM dbo.usuarios").fetchall()
        checks["SELECT directo denegado"] = False
    except pyodbc.Error:
        checks["SELECT directo denegado"] = True
    for nombre, ok in checks.items():
        print(f"  {'OK   ' if ok else 'FALLA'} {nombre}")
    return all(checks.values())


def escribir_env(login: str, contrasena: str) -> None:
    ruta = ROOT / ".env"
    lineas = ruta.read_text(encoding="utf-8").splitlines() if ruta.exists() else []
    valores = {"SQLSERVER_APP_USER": login, "SQLSERVER_APP_PASSWORD": contrasena}
    lineas = [ln for ln in lineas if ln.split("=", 1)[0].strip() not in valores]
    lineas += [f"{clave}={valor}" for clave, valor in valores.items()]
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"SQLSERVER_APP_USER y SQLSERVER_APP_PASSWORD escritas en {ruta} (no versionado). Reinicia la API.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--servidor", default=os.getenv("SQLSERVER_HOST", "localhost"))
    parser.add_argument("--login", default="kinetix_app")
    parser.add_argument("--escribir-env", action="store_true")
    args = parser.parse_args()
    contrasena = os.getenv("KINETIX_SETUP_APP_PASSWORD") or secrets.token_urlsafe(24) + "aA1!"
    try:
        provisionar(args.servidor, args.login, contrasena)
        if not verificar(args.servidor, args.login, contrasena):
            sys.exit("Hay comprobaciones fallidas: revisa el rol antes de usar este login.")
    except pyodbc.Error as e:
        sys.exit(f"Error de SQL Server: {e}")
    if args.escribir_env:
        escribir_env(args.login, contrasena)
    else:
        print(f"Define en .env: SQLSERVER_APP_USER={args.login} y SQLSERVER_APP_PASSWORD={contrasena}")


if __name__ == "__main__":
    main()
