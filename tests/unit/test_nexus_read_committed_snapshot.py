"""Nexus activa READ_COMMITTED_SNAPSHOT (aislamiento estándar de Atlas) en las bases SQL Server de las aplicaciones."""

from src.agents.database_agent.provisioner import SqlServerProvisioner


class _Cursor:
    def __init__(self, estado):
        self._estado = estado
        self._fila = None
        self.sentencias = []

    def execute(self, sql, params=()):
        self.sentencias.append(sql)
        if sql.startswith("SELECT is_read_committed_snapshot_on"):
            self._fila = None if self._estado is None else (self._estado,)
        return self

    def fetchone(self):
        return self._fila


class _Conexion:
    def __init__(self, cursor):
        self._cursor = cursor
        self.cerrada = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.cerrada = True


def _provisionador(estado):
    cursor = _Cursor(estado)
    conexiones = []
    prov = SqlServerProvisioner(settings=None)

    def conectar(database, autocommit):
        assert database == "master" and autocommit is True
        conexiones.append(_Conexion(cursor))
        return conexiones[-1]

    prov._connect = conectar
    return prov, cursor, conexiones


def test_activa_snapshot_si_falta():
    prov, cursor, conexiones = _provisionador(False)
    assert prov._ensure_read_committed_snapshot("llavia") is True
    assert cursor.sentencias[-1] == "ALTER DATABASE [llavia] SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE"
    assert all(c.cerrada for c in conexiones)


def test_no_toca_la_base_si_ya_esta_activo():
    prov, cursor, _ = _provisionador(True)
    assert prov._ensure_read_committed_snapshot("llavia") is False
    assert not any(s.startswith("ALTER DATABASE") for s in cursor.sentencias)


def test_base_inexistente_no_falla():
    prov, cursor, _ = _provisionador(None)
    assert prov._ensure_read_committed_snapshot("nueva") is False
    assert len(cursor.sentencias) == 1
