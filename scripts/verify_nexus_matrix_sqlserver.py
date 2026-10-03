"""
Verificación de Nexus y Matrix contra SQL Server real sin dejar cambios: todo corre en una transacción con rollback.
Uso: venv\\Scripts\\python.exe scripts\\verify_nexus_matrix_sqlserver.py
"""

from __future__ import annotations

import re
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from src.agents.business_rules_agent.repository import SqlServerRulesRepository  # noqa: E402
from src.agents.business_rules_agent.service import RulesService  # noqa: E402
from src.agents.database_agent.catalog import SqlServerCatalog  # noqa: E402
from src.agents.database_agent.database_agent import ColumnDefinition, ColumnType, TableDefinition  # noqa: E402
from src.agents.database_agent.service import NexusService  # noqa: E402
from src.agents.security_agent.config import load_sqlserver_settings  # noqa: E402
from src.agents.security_agent.models import InvalidInputError  # noqa: E402
from src.agents.sqlserver import SqlServerClient  # noqa: E402


class RollbackClient(SqlServerClient):
    """Comparte una sola conexión sin commit para que todas las operaciones se reviertan al final."""

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.connection = pyodbc.connect(settings.connection_string(), autocommit=False)

    @contextmanager
    def cursor(self, commit=False, autocommit=False, timeout=None):
        yield self.connection.cursor()


def step(name, fn):
    try:
        print(f"OK   {name}: {fn()}")
    except Exception as e:
        print(f"FAIL {name}: {type(e).__name__}: {e}")


def main() -> None:
    client = RollbackClient(load_sqlserver_settings())
    try:
        cur = client.connection.cursor()
        script = (ROOT / "NEXUS_MATRIX_SCHEMA.sql").read_text(encoding="utf-8-sig")
        for batch in (b for b in re.split(r"^\s*GO\s*$", script, flags=re.M | re.I) if b.strip()):
            cur.execute(batch)
            while cur.nextset():
                pass
        cur.execute("SELECT COUNT(*) FROM dbo.permisos WHERE id LIKE 'perm_nexus_%' OR id LIKE 'perm_matrix_%'")
        print(f"OK   migración (ensayo): {cur.fetchone()[0]} permisos nuevos")

        rules = RulesService(SqlServerRulesRepository(client))
        step("matrix listar reglas", lambda: rules.list_rules()["total"])
        step("matrix evaluar aplicables (empresa 1, retail)", lambda: {
            k: v for k, v in rules.evaluate_applicable(
                {"deuda_pendiente": 6000, "edad": 30, "ventas_mes": 2000, "ingreso_mensual": 800, "estado_laboral": "activo"},
                "verificacion", id_empresa=1, linea_negocio="retail",
            ).items() if k in ("decision", "reglas_evaluadas", "reglas_cumplidas", "valores_calculados")
        })
        step("matrix crear regla", lambda: rules.create_rule({
            "id_regla": "ZZ_VERIFICACION", "nombre": "Verificación", "nivel_alcance": "empresa", "id_empresa": 1,
            "condiciones": [{"campo": "monto", "operador": "gte", "valor": 100}, {"campo": "vip", "operador": "eq", "valor": True, "operador_logico": "OR"}],
            "acciones": [{"tipo": "calculate", "detalles": {"descuento": "monto * 0.1"}}, {"tipo": "notify", "detalles": {"mensaje": "Descuento"}}],
        }, "verificacion")["condiciones"])
        step("matrix evaluar regla nueva", lambda: rules.evaluate_rule("ZZ_VERIFICACION", {"monto": 500}, "verificacion", id_empresa=1)["valores_calculados"])
        step("matrix actualizar + archivar", lambda: (
            rules.update_rule("ZZ_VERIFICACION", {"nombre": "Verificación 2", "acciones": [{"tipo": "allow", "detalles": {"mensaje": "ok"}}]}, "verificacion")["nombre"],
            rules.archive_rule("ZZ_VERIFICACION", "verificacion")["estado"],
        ))
        step("matrix auditoría", lambda: rules.audit("ZZ_VERIFICACION")["total"])
        step("matrix analítica", lambda: {k: v for k, v in rules.analytics().items() if k in ("evaluaciones", "reglas_activas")})

        nexus = NexusService(SqlServerCatalog(client), max_rows=5)
        step("nexus tablas", lambda: nexus.tables()["total"])
        step("nexus describir reglas_negocio", lambda: (lambda t: (t["clave_primaria"], len(t["columnas"]), len(t["indices"])))(nexus.table("reglas_negocio")))
        step("nexus procedimientos", lambda: [p["nombre"] for p in nexus.procedures()["procedimientos"]])
        step("nexus ejecutar sp_listar_reglas_por_alcance", lambda: (lambda r: (len(r["conjuntos_resultado"][0]["filas"]), r["conjuntos_resultado"][0]["truncado"]))(
            nexus.execute_procedure("sp_listar_reglas_por_alcance", {"nivel_alcance": "global"})))
        def translated_error():
            try:
                nexus.execute_procedure("sp_obtener_auditoria", {"dias": 7})
            except InvalidInputError as e:
                return str(e)
            raise AssertionError("SQL Server debía rechazar la llamada sin @id_regla")

        step("nexus error de SQL Server se traduce", translated_error)
        step("nexus crear tabla (DDL real)", lambda: nexus.create_table(TableDefinition(
            name="zz_verificacion_nexus",
            columns=[
                ColumnDefinition(name="id", type=ColumnType.BIGINT, primary_key=True),
                ColumnDefinition(name="empresa_id", type=ColumnType.INT, nullable=False),
                ColumnDefinition(name="bodega_id", type=ColumnType.INT, nullable=False),
                ColumnDefinition(name="nombre", type=ColumnType.VARCHAR, default="sin nombre"),
                ColumnDefinition(name="activo", type=ColumnType.BOOLEAN, default="true"),
                ColumnDefinition(name="datos", type=ColumnType.JSON),
            ],
            description="Tabla de verificación",
        ))["creada"])
        step("nexus tabla creada visible", lambda: [i["nombre"] for i in nexus.table("zz_verificacion_nexus")["indices"]])
        step("nexus historial de respaldos", lambda: nexus.backups(3)["total"])
    finally:
        client.connection.rollback()
        client.connection.close()
        print("ROLLBACK aplicado: la base quedó sin cambios")


if __name__ == "__main__":
    main()
