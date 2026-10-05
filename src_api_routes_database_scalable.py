"""
src/api/routes/database_scalable.py
NEXUS Agent - Database Operations (Async/Await + Connection Pooling)
58 líneas → 120 líneas (versión escalable)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import asyncpg
from datetime import datetime
from typing import Optional, List

from src.utils.cache_manager import CacheManager
from src.utils.circuit_breaker import CircuitBreaker

router = APIRouter(prefix="/api/v1/nexus", tags=["NEXUS - Database Agent"])

# ============================================================================
# DEPENDENCIES
# ============================================================================

async def get_db_pool() -> asyncpg.pool.Pool:
    """Inyectar pool de conexiones PostgreSQL"""
    from src.api.main import db_pools
    return db_pools.pg_pool

async def get_cache() -> CacheManager:
    """Inyectar caché distribuida"""
    from src.api.main import cache_manager
    return cache_manager

async def get_circuit_breaker() -> CircuitBreaker:
    """Inyectar circuit breaker para BD"""
    from src.api.main import db_pools
    return db_pools.circuit_breaker_db

# ============================================================================
# ENDPOINTS ESCALABLES
# ============================================================================

@router.get("/health", summary="Health check del agente NEXUS")
async def nexus_health():
    """Estado operacional del agente de base de datos"""
    return {
        "agent": "NEXUS",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "operations": ["query", "insert", "update", "delete", "transaction"]
    }

@router.post("/query", summary="Ejecutar query genérica")
async def execute_query(
    request: Request,
    query: str,
    params: Optional[dict] = None,
    pool: asyncpg.pool.Pool = Depends(get_db_pool),
    cache: CacheManager = Depends(get_cache),
    cb: CircuitBreaker = Depends(get_circuit_breaker)
):
    """
    Ejecutar query de base de datos con caché y circuit breaker.
    
    Flujo:
    1. Cache hit → retorna inmediatamente
    2. Cache miss → ejecuta query con circuit breaker
    3. Guarda resultado en caché por 1 hora
    4. Si circuit está abierto → error 503
    """
    
    # Generar cache key
    cache_key = f"query:{query}:{str(params)}"
    
    # 1. INTENTAR CACHÉ
    cached_result = await cache.get(cache_key)
    if cached_result:
        return {
            "source": "cache",
            "cache_hit": True,
            "result": cached_result,
            "timestamp": datetime.now().isoformat()
        }
    
    # 2. EJECUTAR QUERY CON CIRCUIT BREAKER
    try:
        async with cb:
            async with pool.acquire() as conn:
                if params:
                    result = await conn.fetch(query, *params.values())
                else:
                    result = await conn.fetch(query)
    
    except Exception as e:
        from src.utils.circuit_breaker import CircuitBreakerOpen
        if isinstance(e, CircuitBreakerOpen):
            return {
                "error": "Database circuit breaker is open",
                "status_code": 503,
                "request_id": request.state.request_id
            }
        raise
    
    # 3. GUARDAR EN CACHÉ
    await cache.set(cache_key, result, ttl_seconds=3600)
    
    return {
        "source": "database",
        "cache_hit": False,
        "result": result,
        "cached": True,
        "timestamp": datetime.now().isoformat()
    }

@router.post("/insert", summary="Insertar registros")
async def insert_record(
    request: Request,
    table: str,
    data: dict,
    pool: asyncpg.pool.Pool = Depends(get_db_pool),
    cache: CacheManager = Depends(get_cache),
    cb: CircuitBreaker = Depends(get_circuit_breaker)
):
    """Insertar registro en tabla especificada"""
    
    try:
        async with cb:
            async with pool.acquire() as conn:
                # Construir INSERT query dinámicamente
                columns = ", ".join(data.keys())
                values_placeholder = ", ".join([f"${i+1}" for i in range(len(data))])
                query = f"INSERT INTO {table} ({columns}) VALUES ({values_placeholder}) RETURNING id"
                
                record_id = await conn.fetchval(query, *data.values())
    
    except Exception as e:
        from src.utils.circuit_breaker import CircuitBreakerOpen
        if isinstance(e, CircuitBreakerOpen):
            raise HTTPException(status_code=503, detail="Database service unavailable")
        raise HTTPException(status_code=500, detail=str(e))
    
    # Invalidar caché de tabla
    await cache.clear_pattern(f"query:{table}*")
    
    return {
        "status": "inserted",
        "id": record_id,
        "table": table,
        "timestamp": datetime.now().isoformat()
    }

@router.put("/update/{table}/{record_id}", summary="Actualizar registro")
async def update_record(
    request: Request,
    table: str,
    record_id: int,
    data: dict,
    pool: asyncpg.pool.Pool = Depends(get_db_pool),
    cache: CacheManager = Depends(get_cache),
    cb: CircuitBreaker = Depends(get_circuit_breaker)
):
    """Actualizar registro existente"""
    
    try:
        async with cb:
            async with pool.acquire() as conn:
                # Construir UPDATE query dinámicamente
                set_clause = ", ".join([f"{k}=${i+1}" for i, k in enumerate(data.keys())])
                query = f"UPDATE {table} SET {set_clause} WHERE id=${len(data)+1} RETURNING *"
                
                updated = await conn.fetchrow(query, *data.values(), record_id)
    
    except Exception as e:
        from src.utils.circuit_breaker import CircuitBreakerOpen
        if isinstance(e, CircuitBreakerOpen):
            raise HTTPException(status_code=503, detail="Database service unavailable")
        raise
    
    # Invalidar caché
    await cache.delete(f"{table}:{record_id}")
    await cache.clear_pattern(f"query:{table}*")
    
    return {
        "status": "updated",
        "record": updated,
        "timestamp": datetime.now().isoformat()
    }

@router.delete("/delete/{table}/{record_id}", summary="Eliminar registro")
async def delete_record(
    request: Request,
    table: str,
    record_id: int,
    pool: asyncpg.pool.Pool = Depends(get_db_pool),
    cache: CacheManager = Depends(get_cache),
    cb: CircuitBreaker = Depends(get_circuit_breaker)
):
    """Eliminar registro de tabla"""
    
    try:
        async with cb:
            async with pool.acquire() as conn:
                await conn.execute(f"DELETE FROM {table} WHERE id=$1", record_id)
    
    except Exception as e:
        from src.utils.circuit_breaker import CircuitBreakerOpen
        if isinstance(e, CircuitBreakerOpen):
            raise HTTPException(status_code=503, detail="Database service unavailable")
        raise
    
    # Invalidar caché
    await cache.delete(f"{table}:{record_id}")
    await cache.clear_pattern(f"query:{table}*")
    
    return {
        "status": "deleted",
        "table": table,
        "id": record_id,
        "timestamp": datetime.now().isoformat()
    }

@router.post("/transaction", summary="Ejecutar transacción")
async def execute_transaction(
    request: Request,
    queries: List[dict],  # [{"query": "...", "params": {...}}, ...]
    pool: asyncpg.pool.Pool = Depends(get_db_pool),
    cache: CacheManager = Depends(get_cache),
    cb: CircuitBreaker = Depends(get_circuit_breaker)
):
    """
    Ejecutar múltiples queries en una transacción
    
    Garantiza atomicidad: todo éxito o todo fallo
    """
    
    try:
        async with cb:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    results = []
                    for q in queries:
                        result = await conn.fetch(q["query"], *q.get("params", {}).values())
                        results.append(result)
    
    except Exception as e:
        from src.utils.circuit_breaker import CircuitBreakerOpen
        if isinstance(e, CircuitBreakerOpen):
            raise HTTPException(status_code=503, detail="Database service unavailable")
        raise
    
    # Invalidar toda caché de queries
    await cache.clear_pattern("query:*")
    
    return {
        "status": "transaction_completed",
        "queries_executed": len(queries),
        "results": results,
        "timestamp": datetime.now().isoformat()
    }

@router.post("/cache/invalidate", summary="Invalidar caché por patrón")
async def invalidate_cache(
    pattern: str = "rule:*",
    cache: CacheManager = Depends(get_cache)
):
    """
    Limpiar caché por patrón (después de modificar BD)
    Ejemplo: pattern="rule:*" borra todo el caché de reglas
    """
    await cache.clear_pattern(pattern)
    return {
        "status": "cache_invalidated",
        "pattern": pattern,
        "timestamp": datetime.now().isoformat()
    }

@router.get("/stats", summary="Estadísticas del agente NEXUS")
async def nexus_stats(
    pool: asyncpg.pool.Pool = Depends(get_db_pool),
    cache: CacheManager = Depends(get_cache)
):
    """Métricas operacionales del agente"""
    
    # Pool stats
    pool_size = len(pool._holders) if hasattr(pool, '_holders') else 0
    
    return {
        "agent": "NEXUS",
        "metrics": {
            "pool": {
                "active_connections": pool_size,
                "min_size": 10,
                "max_size": 50
            },
            "timestamp": datetime.now().isoformat()
        }
    }
