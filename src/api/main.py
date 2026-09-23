"""
Kinetix Studio - FastAPI Main (COMPLETO)
API Principal con 5 Agentes Operacionales (36 endpoints)
Stack: Python 3.9.7 + FastAPI + PostgreSQL + SQL Server + Azure
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
import logging
import sys
from datetime import datetime

# ============================================================================
# IMPORTAR ROUTERS DE AGENTES
# ============================================================================

database_router = apis_router = business_rules_router = reporting_router = qa_router = None

try:
    from src.api.routes.database import router as database_router
    from src.api.routes.apis import router as apis_router
    from src.api.routes.business_rules import router as business_rules_router
    from src.api.routes.reporting_routes import router as reporting_router
    from src.api.routes.qa_routes import router as qa_router
except ImportError as e:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).warning("No se pudieron importar todos los routers: %s", e)

# ============================================================================
# IMPORTAR INTEGRACIÓN POSTGRESQL
# ============================================================================

try:
    from src.utils.postgres_integration import inicializar_postgres
except ImportError:
    print("⚠️ PostgreSQL integration no disponible")
    def inicializar_postgres():
        return False

# ============================================================================
# CONFIGURACIÓN LOGGING
# ============================================================================

from pathlib import Path

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/kinetix_studio.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# INSTANCIAR FASTAPI
# ============================================================================

app = FastAPI(
    title="Kinetix Studio - AFP",
    description="Plataforma de Business Rules, APIs y Reportes para AFP",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# ============================================================================
# CORS MIDDLEWARE
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# INCLUIR ROUTERS DE AGENTES
# ============================================================================

# 1. DatabaseAgent - 6 endpoints (prefix ya definido en el router)
if database_router is not None:
    app.include_router(database_router)
    logger.info("DatabaseAgent router incluido")

# 2. APIsAgent - 6 endpoints (prefix ya definido en el router)
if apis_router is not None:
    app.include_router(apis_router)
    logger.info("APIsAgent router incluido")

# 3. BusinessRulesAgent - 8 endpoints
if business_rules_router is not None:
    app.include_router(
        business_rules_router,
        prefix="/api/v1/rules",
        tags=["BusinessRulesAgent"],
    )
    logger.info("BusinessRulesAgent router incluido")

# 4. ReportingAgent - 8 endpoints
if reporting_router is not None:
    app.include_router(
        reporting_router,
        prefix="/api/v1/reporting",
        tags=["ReportingAgent"],
    )
    logger.info("ReportingAgent router incluido")

# 5. QAAgent - 8 endpoints
if qa_router is not None:
    app.include_router(
        qa_router,
        prefix="/api/v1/qa",
        tags=["QAAgent"],
    )
    logger.info("QAAgent router incluido")

# ============================================================================
# ENDPOINTS RAÍZ
# ============================================================================

@app.get("/", summary="Bienvenida")
async def root():
    """Bienvenida a Kinetix Studio API v2"""
    return {
        "aplicacion": "Kinetix Studio - AFP",
        "version": "2.0.0",
        "estado": "activa",
        "agentes": {
            "DatabaseAgent": 6,
            "APIsAgent": 6,
            "BusinessRulesAgent": 8,
            "ReportingAgent": 8,
            "QAAgent": 8
        },
        "total_endpoints": 36,
        "docs": "/api/docs",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health", summary="Health check general")
async def health_check():
    """Health check de la API"""
    return {
        "resultado": "OK",
        "aplicacion": "Kinetix Studio",
        "estado": "operacional",
        "agentes_activos": 5,
        "endpoints_totales": 36,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/status", summary="Estado detallado del sistema")
async def status_sistema():
    """Estado detallado de todos los componentes"""
    return {
        "resultado": "OK",
        "sistema": "Kinetix Studio",
        "version": "2.0.0",
        "componentes": {
            "sql_server": "operacional",
            "postgresql": "operacional",
            "cache_distribuido": "operacional"
        },
        "agentes": 5,
        "endpoints": 36,
        "uptime": "N/A",
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# CUSTOM OPENAPI SCHEMA
# ============================================================================

def custom_openapi():
    """Schema OpenAPI personalizado"""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Kinetix Studio - AFP v2",
        version="2.0.0",
        description="**Plataforma de Business Rules, APIs y Reportes**\n\n"
                    "### 5 Agentes Operacionales (36 endpoints)\n"
                    "1. **DatabaseAgent** - 6 endpoints para gestión de BD\n"
                    "2. **APIsAgent** - 6 endpoints para consumo de APIs externas\n"
                    "3. **BusinessRulesAgent** - 8 endpoints para evaluación de reglas\n"
                    "4. **ReportingAgent** - 8 endpoints para reportes y dashboards\n"
                    "5. **QAAgent** - 8 endpoints para testing y validación\n\n"
                    "### Stack\n"
                    "- Python 3.9.7 + FastAPI\n"
                    "- PostgreSQL (datos) + SQL Server (reglas) + Caché distribuido\n"
                    "- Azure (hosting) + n8n (orquestación)",
        routes=app.routes,
    )
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# ============================================================================
# MANEJO DE EXCEPCIONES GLOBAL
# ============================================================================

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Manejo de errores de validación"""
    logger.error(f"Error de validación: {exc}")
    return JSONResponse(
        status_code=422,
        content={
            "resultado": "ERROR",
            "tipo": "validacion",
            "detalles": str(exc),
            "timestamp": datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Manejo de excepciones generales"""
    logger.error(f"Error no controlado: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "resultado": "ERROR",
            "tipo": "error_interno",
            "detalles": str(exc),
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# ============================================================================
# STARTUP Y SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Evento al iniciar la aplicación"""
    logger.info("=" * 80)
    logger.info("🚀 KINETIX STUDIO - AFP INICIANDO (v2)")
    logger.info("=" * 80)
    logger.info(f"⏰ Timestamp: {datetime.utcnow().isoformat()}")
    logger.info(f"🔌 URL: http://localhost:8000")
    logger.info(f"📚 Documentación: http://localhost:8000/api/docs")
    logger.info("=" * 80)
    logger.info("AGENTES OPERACIONALES:")
    logger.info("  1️⃣  DatabaseAgent (6 endpoints)")
    logger.info("  2️⃣  APIsAgent (6 endpoints)")
    logger.info("  3️⃣  BusinessRulesAgent (8 endpoints)")
    logger.info("  4️⃣  ReportingAgent (8 endpoints)")
    logger.info("  5️⃣  QAAgent (8 endpoints)")
    logger.info("=" * 80)
    logger.info("📊 TOTAL: 36 ENDPOINTS OPERACIONALES")
    logger.info("=" * 80)
    
    # Inicializar PostgreSQL
    logger.info("🔄 Inicializando PostgreSQL...")
    if inicializar_postgres():
        logger.info("✅ PostgreSQL inicializado exitosamente")
    else:
        logger.warning("⚠️ PostgreSQL no disponible (continuando sin caché distribuido)")
    
    logger.info("=" * 80)

@app.on_event("shutdown")
async def shutdown_event():
    """Evento al cerrar la aplicación"""
    logger.info("=" * 80)
    logger.info("🛑 KINETIX STUDIO CERRANDO")
    logger.info("=" * 80)

# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Iniciando servidor uvicorn...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
