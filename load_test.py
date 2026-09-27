"""
KINETIX STUDIO - LOAD TESTING SUITE
Probar aplicaciones bajo carga masiva (1M+ usuarios)

Ejecutar:
    locust -f load_test.py --host=http://localhost:8000 -u 10000 -r 100 -t 5m
"""

from locust import HttpUser, task, between, TaskSet, constant
import random
import string
import json

# ============================================================================
# USER BEHAVIOR PATTERNS
# ============================================================================

class KinetixLoadTesting(TaskSet):
    """Patrones de comportamiento para testing"""
    
    def on_start(self):
        """Setup inicial para cada usuario"""
        self.rule_ids = list(range(1, 1000))  # Simular 1000 reglas
        self.user_id = random.randint(1, 100000)
        self.session_id = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    
    # ========================================================================
    # HEALTH & STATUS
    # ========================================================================
    
    @task(1)
    def health_check(self):
        """Health check (bajo peso)"""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")
    
    @task(1)
    def readiness_check(self):
        """Readiness check"""
        with self.client.get("/health/ready", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")
    
    @task(2)
    def metrics(self):
        """Obtener métricas"""
        with self.client.get("/metrics/status", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Metrics error: {response.status_code}")
    
    # ========================================================================
    # READ OPERATIONS (HIGH FREQUENCY)
    # ========================================================================
    
    @task(30)
    def get_rule(self):
        """Obtener regla (cache heavy)"""
        rule_id = random.choice(self.rule_ids)
        with self.client.get(f"/api/v1/matrix/rules/{rule_id}", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                response.success()  # Expected for some IDs
            elif response.status_code == 429:
                response.success()  # Rate limited (expected under load)
            elif response.status_code == 503:
                response.success()  # Circuit breaker open (expected)
            else:
                response.failure(f"Unexpected status: {response.status_code}")
    
    @task(20)
    def list_rules(self):
        """Listar reglas con paginación"""
        page = random.randint(1, 100)
        with self.client.get(
            f"/api/v1/matrix/rules?page={page}&limit=50",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                response.success()
            elif response.status_code == 503:
                response.success()
            else:
                response.failure(f"List error: {response.status_code}")
    
    # ========================================================================
    # WRITE OPERATIONS (MODERATE FREQUENCY)
    # ========================================================================
    
    @task(5)
    def create_rule(self):
        """Crear nueva regla"""
        rule_data = {
            "name": f"RULE_{random.randint(1000, 9999)}",
            "description": f"Test rule {self.user_id}",
            "scope_level": random.choice(["global", "business_line", "empresa"]),
            "priority": random.randint(1, 100),
            "status": "active"
        }
        
        with self.client.post(
            "/api/v1/matrix/rules",
            json=rule_data,
            catch_response=True
        ) as response:
            if response.status_code == 201:
                response.success()
            elif response.status_code == 429:
                response.success()
            elif response.status_code == 503:
                response.success()
            else:
                response.failure(f"Create error: {response.status_code}")
    
    @task(3)
    def update_rule(self):
        """Actualizar regla"""
        rule_id = random.choice(self.rule_ids)
        update_data = {
            "status": random.choice(["active", "inactive"]),
            "priority": random.randint(1, 100)
        }
        
        with self.client.put(
            f"/api/v1/matrix/rules/{rule_id}",
            json=update_data,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                response.success()
            elif response.status_code == 429:
                response.success()
            elif response.status_code == 503:
                response.success()
            else:
                response.failure(f"Update error: {response.status_code}")
    
    # ========================================================================
    # REPORT GENERATION (ASYNC HEAVY)
    # ========================================================================
    
    @task(2)
    def generate_report(self):
        """Generar reporte (queue)"""
        report_config = {
            "type": random.choice(["summary", "detailed", "audit"]),
            "date_range": random.choice(["daily", "weekly", "monthly"]),
            "include_charts": random.choice([True, False])
        }
        
        with self.client.post(
            "/api/v1/insight/reports/generate",
            json=report_config,
            catch_response=True
        ) as response:
            if response.status_code == 202:
                response.success()
            elif response.status_code == 429:
                response.success()
            elif response.status_code == 503:
                response.success()
            else:
                response.failure(f"Report error: {response.status_code}")
    
    # ========================================================================
    # COMPLEX OPERATIONS
    # ========================================================================
    
    @task(1)
    def evaluate_rule(self):
        """Evaluar regla compleja (CPU intensive)"""
        evaluation_request = {
            "rule_id": random.choice(self.rule_ids),
            "context": {
                "user_id": self.user_id,
                "transaction_amount": random.uniform(100, 10000),
                "account_age_days": random.randint(1, 3650),
                "previous_violations": random.randint(0, 5)
            }
        }
        
        with self.client.post(
            "/api/v1/matrix/rules/evaluate",
            json=evaluation_request,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 400:
                response.failure(f"Invalid request: {response.text}")
            elif response.status_code == 429:
                response.success()
            elif response.status_code == 503:
                response.success()
            else:
                response.failure(f"Evaluation error: {response.status_code}")

# ============================================================================
# LOAD TEST CONFIGURATIONS
# ============================================================================

class LightLoad(HttpUser):
    """Carga ligera: 100 usuarios concurrentes"""
    tasks = [KinetixLoadTesting]
    wait_time = between(1, 3)

class NormalLoad(HttpUser):
    """Carga normal: 1,000 usuarios concurrentes"""
    tasks = [KinetixLoadTesting]
    wait_time = between(0.5, 2)

class HeavyLoad(HttpUser):
    """Carga pesada: 10,000 usuarios concurrentes"""
    tasks = [KinetixLoadTesting]
    wait_time = between(0.1, 0.5)

class StressTest(HttpUser):
    """Test de estrés: 100,000+ usuarios"""
    tasks = [KinetixLoadTesting]
    wait_time = constant(0)  # Sin espera entre requests

# ============================================================================
# EJEMPLO DE EJECUCIÓN
# ============================================================================

"""
1. LIGHT LOAD (100 usuarios, 1 RPS):
   locust -f load_test.py --host=http://localhost:8000 -u 100 -r 10 -t 5m

2. NORMAL LOAD (1,000 usuarios, 10 RPS):
   locust -f load_test.py --host=http://localhost:8000 -u 1000 -r 100 -t 10m

3. HEAVY LOAD (10,000 usuarios, 100 RPS):
   locust -f load_test.py --host=http://localhost:8000 -u 10000 -r 500 -t 15m

4. STRESS TEST (100,000+ usuarios):
   locust -f load_test.py --host=http://localhost:8000 -u 100000 -r 10000 -t 30m

5. CON GUI HEADLESS (sin interfaz web):
   locust -f load_test.py --host=http://localhost:8000 \
     -u 10000 -r 500 -t 15m \
     --csv=results --headless

6. DISTRIBUTED TESTING (múltiples máquinas):
   # Máquina master
   locust -f load_test.py --host=http://localhost:8000 --master
   
   # Máquina worker 1
   locust -f load_test.py --host=http://localhost:8000 --worker --master-host=<master-ip>
   
   # Máquina worker 2
   locust -f load_test.py --host=http://localhost:8000 --worker --master-host=<master-ip>

MÉTRICAS A MONITOREAR:
- Response time (p50, p95, p99)
- Requests per second (RPS)
- Error rate (%)
- Circuit breaker state
- Cache hit ratio
- Database connection pool status
- Memory usage
- CPU usage

CASOS DE ÉXITO:
✅ P99 latency < 100ms incluso bajo 100K usuarios
✅ Error rate < 1% (excepto rate limiting intencional)
✅ Cache hit ratio > 80%
✅ Circuit breakers se abren/cierran correctamente
✅ No hay memory leaks
✅ Escalado horizontal automático
"""
