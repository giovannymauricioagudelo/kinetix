"""
src/utils/circuit_breaker.py
Circuit Breaker Pattern Implementation for Enterprise Resilience
Patrón: CLOSED (normal) → OPEN (fallando) → HALF_OPEN (recuperando)
"""

import asyncio
import logging
from enum import Enum
from datetime import datetime, timedelta
from typing import Optional, Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# ============================================================================
# CIRCUIT BREAKER STATE MACHINE
# ============================================================================

class CircuitState(Enum):
    """Estados del circuit breaker"""
    CLOSED = "closed"          # Normal: acepta requests
    OPEN = "open"              # Fallando: rechaza requests
    HALF_OPEN = "half_open"    # Recuperándose: acepta 1 request


class CircuitBreakerMetrics:
    """Métricas del circuit breaker"""
    
    def __init__(self):
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.rejected_calls = 0
        self.last_failure_time: Optional[datetime] = None
        self.state_changes = []
    
    def record_success(self):
        self.total_calls += 1
        self.successful_calls += 1
    
    def record_failure(self):
        self.total_calls += 1
        self.failed_calls += 1
        self.last_failure_time = datetime.now()
    
    def record_rejection(self):
        self.rejected_calls += 1
    
    def record_state_change(self, from_state: CircuitState, to_state: CircuitState):
        self.state_changes.append({
            "from": from_state.value,
            "to": to_state.value,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_stats(self):
        success_rate = (
            (self.successful_calls / self.total_calls * 100) 
            if self.total_calls > 0 
            else 0
        )
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "rejected_calls": self.rejected_calls,
            "success_rate": f"{success_rate:.2f}%",
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "state_changes": len(self.state_changes)
        }


class CircuitBreakerOpen(Exception):
    """Excepción cuando circuit está abierto"""
    pass


class CircuitBreakerTimeout(Exception):
    """Excepción por timeout"""
    pass


class CircuitBreaker:
    """
    Circuit Breaker asíncrono para Python/FastAPI
    
    Protege contra fallos en cascada:
    - CLOSED: Operación normal, monitorea fallos
    - OPEN: Demasiados fallos, rechaza requests
    - HALF_OPEN: Intenta recuperarse, acepta 1 request
    
    Si recuperación es exitosa → CLOSED
    Si falla → OPEN de nuevo
    """
    
    def __init__(
        self,
        name: str = "CircuitBreaker",
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
        expected_exception: type = Exception,
        timeout: int = 30
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.expected_exception = expected_exception
        self.timeout = timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.metrics = CircuitBreakerMetrics()
        
        logger.info(f"🔧 {self.name} inicializado (threshold={failure_threshold}, timeout={recovery_timeout}s)")
    
    # ========================================================================
    # CONTEXT MANAGER
    # ========================================================================
    
    async def __aenter__(self):
        """Entrar al context (ejecutar operación)"""
        
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                # Cambiar a HALF_OPEN para intentar recuperación
                self._change_state(CircuitState.HALF_OPEN)
                logger.info(f"🔄 {self.name}: Intentando recuperación (HALF_OPEN)")
            else:
                # Aún no es tiempo de reintentar
                self.metrics.record_rejection()
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                raise CircuitBreakerOpen(
                    f"{self.name} está ABIERTO. Reintentando en {self.recovery_timeout - int(elapsed)}s"
                )
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Salir del context (registrar resultado)"""
        
        if exc_type is None:
            # ✅ ÉXITO
            self._on_success()
        elif exc_type and issubclass(exc_type, self.expected_exception):
            # ❌ FALLO
            self._on_failure()
            return False  # Re-raise exception
        
        return False
    
    # ========================================================================
    # STATE TRANSITIONS
    # ========================================================================
    
    def _on_success(self):
        """Registrar éxito"""
        self.metrics.record_success()
        
        if self.state == CircuitState.HALF_OPEN:
            # Recuperación exitosa
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self._change_state(CircuitState.CLOSED)
                logger.info(f"✅ {self.name}: Circuito CERRADO - recuperado exitosamente")
                self.failure_count = 0
                self.success_count = 0
        
        elif self.state == CircuitState.CLOSED:
            # Operación normal exitosa
            self.failure_count = 0
    
    def _on_failure(self):
        """Registrar fallo"""
        self.metrics.record_failure()
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        logger.warning(f"⚠️ {self.name}: Fallo registrado ({self.failure_count}/{self.failure_threshold})")
        
        if self.failure_count >= self.failure_threshold:
            self._change_state(CircuitState.OPEN)
            logger.error(f"🚫 {self.name}: Circuito ABIERTO - demasiadas fallas")
        
        elif self.state == CircuitState.HALF_OPEN:
            # Fallo durante recuperación
            self.success_count = 0
            self._change_state(CircuitState.OPEN)
            logger.error(f"🚫 {self.name}: Circuito ABIERTO - fallo durante recuperación")
    
    def _change_state(self, new_state: CircuitState):
        """Cambiar estado y registrar"""
        old_state = self.state
        self.state = new_state
        self.metrics.record_state_change(old_state, new_state)
    
    # ========================================================================
    # UTILITIES
    # ========================================================================
    
    def _should_attempt_reset(self) -> bool:
        """¿Es tiempo de intentar recuperación?"""
        if not self.last_failure_time:
            return False
        
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout
    
    def get_state(self) -> str:
        """Obtener estado actual"""
        return self.state.value
    
    def get_metrics(self) -> dict:
        """Obtener métricas"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "threshold": self.failure_threshold,
            "metrics": self.metrics.get_stats()
        }
    
    def reset(self):
        """Reset manual (solo para testing/admin)"""
        logger.warning(f"🔄 {self.name}: Reset manual iniciado")
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self._change_state(CircuitState.CLOSED)
    
    # ========================================================================
    # ASYNC DECORATOR (opcional)
    # ========================================================================
    
    def __call__(self, func: Callable) -> Callable:
        """
        Usar como decorador:
        
        @circuit_breaker
        async def risky_operation():
            ...
        """
        async def wrapper(*args, **kwargs):
            async with self:
                return await func(*args, **kwargs)
        return wrapper


# ============================================================================
# CIRCUIT BREAKER POOL (Múltiples por aplicación)
# ============================================================================

class CircuitBreakerPool:
    """Pool de circuit breakers para diferentes servicios"""
    
    def __init__(self):
        self.breakers: dict[str, CircuitBreaker] = {}
    
    def create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        **kwargs
    ) -> CircuitBreaker:
        """Crear circuit breaker para un servicio"""
        if name in self.breakers:
            return self.breakers[name]
        
        cb = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            **kwargs
        )
        self.breakers[name] = cb
        return cb
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Obtener circuit breaker existente"""
        return self.breakers.get(name)
    
    def get_all_metrics(self) -> dict:
        """Obtener métricas de todos los circuit breakers"""
        return {
            name: cb.get_metrics()
            for name, cb in self.breakers.items()
        }
    
    def reset_all(self):
        """Reset de todos los circuit breakers (admin only)"""
        for cb in self.breakers.values():
            cb.reset()
        logger.warning("🔄 Todos los circuit breakers reseteados")


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

"""
# En main.py

from src.utils.circuit_breaker import CircuitBreaker, CircuitBreakerPool

# Crear circuit breakers para diferentes servicios
cb_pool = CircuitBreakerPool()
cb_database = cb_pool.create("database", failure_threshold=5, recovery_timeout=60)
cb_api = cb_pool.create("external_api", failure_threshold=3, recovery_timeout=30)

# En routers

@app.get("/data")
async def get_data():
    try:
        async with cb_database:
            result = await db.query(...)
            return result
    except CircuitBreakerOpen:
        return JSONResponse(
            status_code=503,
            content={"error": "Database service temporarily unavailable"}
        )

# Monitoreo

@app.get("/circuit-breakers/status")
async def circuit_breaker_status():
    return cb_pool.get_all_metrics()
"""
