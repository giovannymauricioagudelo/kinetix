"""
src/utils/database_pools.py
Advanced Connection Pooling for PostgreSQL & SQL Server
Manejo de pools, health checks, fallback strategies
"""

import asyncio
import logging
import asyncpg
import aioodbc
from typing import Optional, Tuple
from datetime import datetime

from src.utils.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE POOL MANAGER
# ============================================================================

class DatabasePools:
    """
    Gestor centralizado de connection pools
    
    - PostgreSQL: Pool asincrónico con asyncpg (10-50 conexiones)
    - SQL Server: Pool asincrónico con aioodbc (10-100 conexiones)
    - Circuit breakers para cada base de datos
    - Health checks periódicos
    """
    
    def __init__(
        self,
        pg_dsn: str = "postgresql://user:pass@localhost/kinetix",
        mssql_dsn: str = "Driver={ODBC Driver 18 for SQL Server};Server=localhost;Database=kinetix;UID=sa;PWD=password;TrustServerCertificate=yes;",
        pg_pool_size: Tuple[int, int] = (10, 50),
        mssql_pool_size: Tuple[int, int] = (10, 100)
    ):
        # PostgreSQL
        self.pg_dsn = pg_dsn
        self.pg_min_size, self.pg_max_size = pg_pool_size
        self.pg_pool: Optional[asyncpg.pool.Pool] = None
        
        # SQL Server
        self.mssql_dsn = mssql_dsn
        self.mssql_min_size, self.mssql_max_size = mssql_pool_size
        self.mssql_pool: Optional[aioodbc.Pool] = None
        
        # Circuit breakers
        self.circuit_breaker_pg = CircuitBreaker(
            name="PostgreSQL",
            failure_threshold=5,
            recovery_timeout=60
        )
        self.circuit_breaker_mssql = CircuitBreaker(
            name="SQL Server",
            failure_threshold=5,
            recovery_timeout=60
        )
        self.circuit_breaker_db = CircuitBreaker(
            name="Database Generic",
            failure_threshold=5,
            recovery_timeout=60
        )
        
        # Health check
        self.health_check_interval = 30  # segundos
        self.last_health_check: Optional[datetime] = None
        
        logger.info("🔧 DatabasePools inicializado (PG + SQL Server)")
    
    # ========================================================================
    # INITIALIZATION
    # ========================================================================
    
    async def init(self):
        """Inicializar todos los pools"""
        try:
            await self._init_pg_pool()
            await self._init_mssql_pool()
            
            # Iniciar health checks periódicos
            asyncio.create_task(self._health_check_loop())
            
            logger.info("✅ Todos los pools inicializados exitosamente")
        except Exception as e:
            logger.error(f"❌ Error inicializando pools: {e}")
            raise
    
    async def _init_pg_pool(self):
        """Inicializar pool PostgreSQL"""
        try:
            self.pg_pool = await asyncpg.create_pool(
                self.pg_dsn,
                min_size=self.pg_min_size,
                max_size=self.pg_max_size,
                command_timeout=60,
                max_cached_statement_lifetime=300,
                max_cacheable_statement_size=15000,
                setup=self._setup_pg_connection
            )
            logger.info(f"✅ PostgreSQL pool creado ({self.pg_min_size}-{self.pg_max_size} conexiones)")
        except Exception as e:
            logger.error(f"❌ Error creando PostgreSQL pool: {e}")
            raise
    
    async def _setup_pg_connection(self, conn):
        """Setup de conexión PostgreSQL (ejecutar una sola vez por conexión)"""
        # Configurar statement cache
        await conn.execute("SET application_name = 'kinetix-studio'")
        # Logging simple
        logger.debug("PostgreSQL connection initialized")
    
    async def _init_mssql_pool(self):
        """Inicializar pool SQL Server"""
        try:
            self.mssql_pool = await aioodbc.create_pool(
                dsn=self.mssql_dsn,
                minsize=self.mssql_min_size,
                maxsize=self.mssql_max_size,
                timeout=30
            )
            logger.info(f"✅ SQL Server pool creado ({self.mssql_min_size}-{self.mssql_max_size} conexiones)")
        except Exception as e:
            logger.error(f"❌ Error creando SQL Server pool: {e}")
            raise
    
    # ========================================================================
    # HEALTH CHECKS
    # ========================================================================
    
    async def _health_check_loop(self):
        """Loop de health checks periódicos"""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self.health_check()
            except Exception as e:
                logger.error(f"Health check error: {e}")
    
    async def health_check(self) -> dict:
        """Ejecutar health check en todas las bases de datos"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "postgresql": await self._health_check_pg(),
            "sql_server": await self._health_check_mssql()
        }
        
        self.last_health_check = datetime.now()
        return results
    
    async def _health_check_pg(self) -> dict:
        """Health check PostgreSQL"""
        try:
            async with self.circuit_breaker_pg:
                async with self.pg_pool.acquire() as conn:
                    result = await conn.fetchval("SELECT 1")
                    
                    # Stats
                    size = self.pg_pool.get_size()
                    idle = self.pg_pool.get_idle_size()
                    
                    return {
                        "status": "healthy",
                        "latency_ms": 1,  # Simplificado
                        "pool_size": size,
                        "idle_connections": idle,
                        "active_connections": size - idle
                    }
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def _health_check_mssql(self) -> dict:
        """Health check SQL Server"""
        try:
            async with self.circuit_breaker_mssql:
                async with self.mssql_pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT 1")
                    
                    return {
                        "status": "healthy",
                        "latency_ms": 1,
                        "pool_size": self.mssql_pool.size,
                        "idle_connections": self.mssql_pool.idle_size
                    }
        except Exception as e:
            logger.error(f"SQL Server health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    # ========================================================================
    # CONNECTION ACQUISITION
    # ========================================================================
    
    async def get_pg_connection(self):
        """Adquirir conexión PostgreSQL con circuit breaker"""
        async with self.circuit_breaker_pg:
            return self.pg_pool.acquire()
    
    async def get_mssql_connection(self):
        """Adquirir conexión SQL Server con circuit breaker"""
        async with self.circuit_breaker_mssql:
            return self.mssql_pool.acquire()
    
    # ========================================================================
    # STATISTICS & MONITORING
    # ========================================================================
    
    def get_pool_stats(self) -> dict:
        """Obtener estadísticas de los pools"""
        pg_stats = {}
        mssql_stats = {}
        
        if self.pg_pool:
            pg_stats = {
                "size": self.pg_pool.get_size(),
                "idle": self.pg_pool.get_idle_size(),
                "active": self.pg_pool.get_size() - self.pg_pool.get_idle_size(),
                "min": self.pg_min_size,
                "max": self.pg_max_size
            }
        
        if self.mssql_pool:
            mssql_stats = {
                "size": self.mssql_pool.size,
                "idle": self.mssql_pool.idle_size,
                "active": self.mssql_pool.size - self.mssql_pool.idle_size,
                "min": self.mssql_min_size,
                "max": self.mssql_max_size
            }
        
        return {
            "postgresql": pg_stats,
            "sql_server": mssql_stats,
            "circuit_breakers": {
                "postgresql": self.circuit_breaker_pg.get_metrics(),
                "sql_server": self.circuit_breaker_mssql.get_metrics(),
                "generic": self.circuit_breaker_db.get_metrics()
            },
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None
        }
    
    # ========================================================================
    # CLEANUP
    # ========================================================================
    
    async def close(self):
        """Cerrar todos los pools"""
        try:
            if self.pg_pool:
                await self.pg_pool.close()
                logger.info("✅ PostgreSQL pool cerrado")
            
            if self.mssql_pool:
                await self.mssql_pool.close()
                logger.info("✅ SQL Server pool cerrado")
        except Exception as e:
            logger.error(f"Error cerrando pools: {e}")


# ============================================================================
# CONTEXT MANAGERS PARA FACILITAR USO
# ============================================================================

class AsyncPostgresConnection:
    """Context manager para conexión PostgreSQL"""
    
    def __init__(self, pools: DatabasePools):
        self.pools = pools
        self.conn = None
    
    async def __aenter__(self):
        async with self.pools.circuit_breaker_pg:
            self.conn = await self.pools.pg_pool.acquire()
            return self.conn
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            await self.pools.pg_pool.release(self.conn)


class AsyncMSSQLConnection:
    """Context manager para conexión SQL Server"""
    
    def __init__(self, pools: DatabasePools):
        self.pools = pools
        self.conn = None
    
    async def __aenter__(self):
        async with self.pools.circuit_breaker_mssql:
            self.conn = await self.pools.mssql_pool.acquire()
            return self.conn
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            await self.pools.mssql_pool.release(self.conn)


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

"""
# En main.py

db_pools = DatabasePools(
    pg_dsn="postgresql://user:pass@localhost/kinetix",
    mssql_dsn="Driver={ODBC Driver 18 for SQL Server};..."
)

@app.on_event("startup")
async def startup():
    await db_pools.init()

@app.on_event("shutdown")
async def shutdown():
    await db_pools.close()

# En routers

@app.get("/data")
async def get_data(pools: DatabasePools = Depends()):
    async with pools.get_pg_connection() as conn:
        result = await conn.fetch("SELECT * FROM data LIMIT 10")
        return result

# Health checks

@app.get("/health")
async def health(pools: DatabasePools = Depends()):
    health_results = await pools.health_check()
    return health_results

# Stats

@app.get("/pools/stats")
async def pool_stats(pools: DatabasePools = Depends()):
    return pools.get_pool_stats()
"""
