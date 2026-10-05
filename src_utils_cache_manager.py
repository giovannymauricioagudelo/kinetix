"""
src/utils/cache_manager.py
Multi-Layered Cache Manager (Redis + In-Memory)
Soporta: key-value, patterns, TTL inteligente, warm-up
"""

import json
import logging
import asyncio
from typing import Optional, Any, Dict, List, Set
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)

# ============================================================================
# IN-MEMORY CACHE LAYER (Layer 1 - Ultra Fast)
# ============================================================================

class InMemoryCache:
    """Caché en memoria para acceso ultra-rápido"""
    
    def __init__(self, max_size: int = 1000):
        self.data: Dict[str, tuple] = {}  # (value, expires_at)
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
    
    async def get(self, key: str) -> Optional[Any]:
        """Obtener del caché en memoria"""
        if key not in self.data:
            self.misses += 1
            return None
        
        value, expires_at = self.data[key]
        
        if expires_at and datetime.now() > expires_at:
            # Expirado
            del self.data[key]
            self.misses += 1
            return None
        
        self.hits += 1
        return value
    
    async def set(self, key: str, value: Any, ttl_seconds: int = 3600):
        """Guardar en caché en memoria"""
        expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
        
        # Eviction policy: simple LRU (FIFO)
        if len(self.data) >= self.max_size:
            first_key = next(iter(self.data))
            del self.data[first_key]
        
        self.data[key] = (value, expires_at)
    
    async def delete(self, key: str):
        """Eliminar del caché"""
        self.data.pop(key, None)
    
    async def clear(self):
        """Limpiar todo el caché"""
        self.data.clear()
    
    def get_stats(self) -> Dict:
        """Estadísticas del caché"""
        total = self.hits + self.misses
        hit_ratio = (self.hits / total * 100) if total > 0 else 0
        return {
            "layer": "in_memory",
            "size": len(self.data),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": f"{hit_ratio:.2f}%"
        }


# ============================================================================
# REDIS CACHE LAYER (Layer 2 - Distributed)
# ============================================================================

class RedisCache:
    """Caché distribuida con Redis"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis = None
        self.connected = False
        self.hits = 0
        self.misses = 0
    
    async def connect(self):
        """Conectar a Redis"""
        try:
            import aioredis
            self.redis = await aioredis.create_redis_pool(self.redis_url)
            self.connected = True
            logger.info("✅ Conectado a Redis")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo conectar a Redis: {e}")
            self.connected = False
    
    async def get(self, key: str) -> Optional[Any]:
        """Obtener de Redis"""
        if not self.connected or not self.redis:
            return None
        
        try:
            value = await self.redis.get(key)
            if value:
                self.hits += 1
                return json.loads(value)
            self.misses += 1
            return None
        except Exception as e:
            logger.error(f"Redis GET error: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl_seconds: int = 3600):
        """Guardar en Redis"""
        if not self.connected or not self.redis:
            return
        
        try:
            serialized = json.dumps(value, default=str)
            await self.redis.setex(key, ttl_seconds, serialized)
        except Exception as e:
            logger.error(f"Redis SET error: {e}")
    
    async def delete(self, key: str):
        """Eliminar de Redis"""
        if not self.connected or not self.redis:
            return
        
        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Redis DELETE error: {e}")
    
    async def clear_pattern(self, pattern: str):
        """Limpiar por patrón (pattern matching)"""
        if not self.connected or not self.redis:
            return
        
        try:
            # SCAN para encontrar keys que coincidan con patrón
            cursor = 0
            keys_to_delete = []
            
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern)
                keys_to_delete.extend(keys)
                
                if cursor == 0:
                    break
            
            if keys_to_delete:
                await self.redis.delete(*keys_to_delete)
                logger.info(f"🧹 Borrados {len(keys_to_delete)} keys con patrón '{pattern}'")
        
        except Exception as e:
            logger.error(f"Redis CLEAR_PATTERN error: {e}")
    
    async def close(self):
        """Cerrar conexión con Redis"""
        if self.redis:
            self.redis.close()
            await self.redis.wait_closed()
    
    def get_stats(self) -> Dict:
        """Estadísticas de Redis"""
        total = self.hits + self.misses
        hit_ratio = (self.hits / total * 100) if total > 0 else 0
        return {
            "layer": "redis",
            "connected": self.connected,
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": f"{hit_ratio:.2f}%"
        }


# ============================================================================
# CACHE MANAGER (Orchestrator)
# ============================================================================

class CacheManager:
    """
    Gestor de caché multi-layered
    
    Layer 1 (In-Memory): Ultra-rápido, local
    Layer 2 (Redis): Distribuido, compartido entre instancias
    
    Lookup: Memory → Redis → Database
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        in_memory_size: int = 1000,
        default_ttl: int = 3600
    ):
        self.in_memory = InMemoryCache(max_size=in_memory_size)
        self.redis = RedisCache(redis_url=redis_url)
        self.default_ttl = default_ttl
        self.total_lookups = 0
        self.layer1_hits = 0
        self.layer2_hits = 0
    
    async def init(self):
        """Inicializar caché"""
        await self.redis.connect()
        logger.info("🚀 CacheManager inicializado (L1: In-Memory, L2: Redis)")
    
    # ========================================================================
    # MAIN OPERATIONS
    # ========================================================================
    
    async def get(self, key: str) -> Optional[Any]:
        """Obtener del caché (intenta L1, luego L2)"""
        self.total_lookups += 1
        
        # Layer 1: In-Memory
        value = await self.in_memory.get(key)
        if value is not None:
            self.layer1_hits += 1
            return value
        
        # Layer 2: Redis
        value = await self.redis.get(key)
        if value is not None:
            self.layer2_hits += 1
            # Guardar en L1 para futuros accesos
            await self.in_memory.set(key, value, self.default_ttl)
            return value
        
        # Miss
        return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None
    ):
        """Guardar en caché (L1 y L2)"""
        ttl = ttl_seconds or self.default_ttl
        
        # Guardar en ambos niveles
        await self.in_memory.set(key, value, ttl)
        await self.redis.set(key, value, ttl)
    
    async def delete(self, key: str):
        """Eliminar del caché"""
        await self.in_memory.delete(key)
        await self.redis.delete(key)
    
    async def clear_pattern(self, pattern: str):
        """
        Limpiar caché por patrón (usar después de cambiar BD)
        
        Ejemplos:
        - "rule:*" → borra todos los cachs de reglas
        - "user:123:*" → borra todo del usuario 123
        - "*" → borra todo (peligroso)
        """
        # Redis soporta pattern matching nativo
        await self.redis.clear_pattern(pattern)
        
        # Para in-memory, buscar manualmente
        keys_to_delete = [
            k for k in self.in_memory.data.keys()
            if self._match_pattern(k, pattern)
        ]
        for key in keys_to_delete:
            await self.in_memory.delete(key)
        
        logger.info(f"🧹 Cache invalidado: {len(keys_to_delete)} keys borrados")
    
    # ========================================================================
    # WARM-UP (Precarga de caché)
    # ========================================================================
    
    async def warmup(
        self,
        queries: List[dict],
        db_fetch_fn=None
    ):
        """
        Precarga del caché antes de recibir requests
        
        Ejemplo:
        queries = [
            {"key": "rule:1", "query": "SELECT * FROM rules WHERE id=1"},
            {"key": "rule:2", "query": "SELECT * FROM rules WHERE id=2"},
        ]
        await cache.warmup(queries, db_fetch_fn=db.fetch)
        """
        if not db_fetch_fn:
            logger.warning("No db_fetch_fn provided, skipping warmup")
            return
        
        logger.info(f"🔥 Iniciando precarga de {len(queries)} items...")
        
        for item in queries:
            try:
                key = item["key"]
                query = item["query"]
                
                # Ejecutar query
                result = await db_fetch_fn(query)
                
                # Guardar en caché
                ttl = item.get("ttl", self.default_ttl)
                await self.set(key, result, ttl)
                
            except Exception as e:
                logger.error(f"Warmup error para {item.get('key')}: {e}")
        
        logger.info("✅ Precarga completada")
    
    # ========================================================================
    # STATISTICS & MONITORING
    # ========================================================================
    
    def get_stats(self) -> Dict:
        """Obtener estadísticas de caché"""
        l1_stats = self.in_memory.get_stats()
        l2_stats = self.redis.get_stats()
        
        # Hit ratio global
        total_hits = self.layer1_hits + self.layer2_hits
        global_hit_ratio = (
            (total_hits / self.total_lookups * 100)
            if self.total_lookups > 0
            else 0
        )
        
        return {
            "cache_manager": {
                "total_lookups": self.total_lookups,
                "layer1_hits": self.layer1_hits,
                "layer2_hits": self.layer2_hits,
                "global_hit_ratio": f"{global_hit_ratio:.2f}%"
            },
            "layer1": l1_stats,
            "layer2": l2_stats,
            "timestamp": datetime.now().isoformat()
        }
    
    # ========================================================================
    # UTILITIES
    # ========================================================================
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """Simple pattern matching (Redis-style)"""
        import fnmatch
        return fnmatch.fnmatch(key, pattern)
    
    async def close(self):
        """Cerrar conexiones"""
        await self.redis.close()


# ============================================================================
# CACHE DECORATORS
# ============================================================================

def cached(ttl: int = 3600, pattern: Optional[str] = None):
    """
    Decorador para cachear resultados de funciones
    
    Ejemplo:
    @cached(ttl=3600)
    async def get_rule(rule_id):
        return await db.fetch(...)
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            from src.api.main import cache_manager
            
            # Generar cache key
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Intentar caché
            cached_result = await cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Ejecutar función
            result = await func(*args, **kwargs)
            
            # Guardar en caché
            await cache_manager.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

"""
# En main.py

cache_manager = CacheManager()

@app.on_event("startup")
async def startup():
    await cache_manager.init()

# En routers

@app.get("/rule/{rule_id}")
async def get_rule(rule_id: int):
    cached = await cache_manager.get(f"rule:{rule_id}")
    if cached:
        return cached
    
    result = await db.fetch(f"SELECT * FROM rules WHERE id={rule_id}")
    await cache_manager.set(f"rule:{rule_id}", result, ttl_seconds=3600)
    return result

# Monitoreo

@app.get("/cache/stats")
async def cache_stats():
    return cache_manager.get_stats()

# Invalidación

@app.post("/cache/invalidate")
async def invalidate(pattern: str = "rule:*"):
    await cache_manager.clear_pattern(pattern)
    return {"status": "invalidated"}
"""
