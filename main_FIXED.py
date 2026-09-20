"""
AFP Main FastAPI Application
Integrates all agents via REST API
VERSIÓN FINAL - CORRECTAMENTE ORDENADA
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# ✅ PASO 1: CREAR APP PRIMERO (ANTES de cualquier otra cosa)
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle - startup and shutdown events"""
    # ===== STARTUP =====
    logger.info("=" * 70)
    logger.info("🚀 AFP APPLICATION STARTING")
    logger.info("=" * 70)
    logger.info("")
    logger.info("📦 AGENTS AVAILABLE:")
    logger.info("  ✅ Database Agent       - Schema management & migrations")
    logger.info("  ✅ APIs Agent           - REST API generation")
    logger.info("  ✅ Business Rules Agent - Logic & validations")
    logger.info("  ⏳ Reporting Agent      - Report generation (Semana 3)")
    logger.info("  ⏳ QA Agent            - Testing & QA (Semana 4)")
    logger.info("  ⏳ Git Deployment Agent - Version control (Semana 4)")
    logger.info("  ⏳ Development Agent    - Infrastructure (Semana 4)")
    logger.info("  ⏳ Custom AI Agents     - Custom domains (Semana 5)")
    logger.info("")
    logger.info("🌐 API ENDPOINTS:")
    logger.info("  📚 Swagger UI: http://localhost:8000/docs")
    logger.info("  📚 ReDoc:      http://localhost:8000/redoc")
    logger.info("  🔍 OpenAPI:    http://localhost:8000/openapi.json")
    logger.info("")
    logger.info("=" * 70)

    yield

    # ===== SHUTDOWN =====
    logger.info("=" * 70)
    logger.info("🛑 AFP APPLICATION SHUTTING DOWN")
    logger.info("=" * 70)


# ✅ CREAR APP AQUÍ
app = FastAPI(
    title="Application Factory Platform (AFP)",
    description="Fábrica de Aplicaciones Inteligente - NO-CODE platform with 8 AI Agents",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# ============================================================================
# ✅ PASO 2: IMPORTAR ROUTES (DESPUÉS de crear app)
# ============================================================================

try:
    from src.api.routes import database
    logger.info("✅ database routes loaded")
except ImportError as e:
    logger.warning(f"⚠️  database routes import failed: {str(e)}")
    database = None

try:
    from src.api.routes import apis
    logger.info("✅ apis routes loaded")
except ImportError as e:
    logger.warning(f"⚠️  apis routes import failed: {str(e)}")
    apis = None

try:
    from src.api.routes import business_rules
    logger.info("✅ business_rules routes loaded")
except ImportError as e:
    logger.warning(f"⚠️  business_rules routes import failed: {str(e)}")
    business_rules = None

# ============================================================================
# ✅ PASO 3: REGISTRAR ROUTERS (DESPUÉS de importar)
# ============================================================================

if database:
    app.include_router(database.router)
    logger.info("✅ DatabaseAgent router registered")

if apis:
    app.include_router(apis.router)
    logger.info("✅ APIsAgent router registered")

if business_rules:
    app.include_router(business_rules.router)
    logger.info("✅ BusinessRulesAgent router registered")

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
# ROOT ENDPOINTS
# ============================================================================

@app.get("/", response_model=dict, summary="App Info")
async def root() -> dict:
    """Root endpoint - application information"""
    return {
        "app_name": "AFP - Fábrica de Aplicaciones Inteligente",
        "version": "0.2.0",
        "status": "running ✅",
        "timestamp": datetime.utcnow().isoformat(),
        "description": "Intelligent application factory with multi-agent architecture",
        "agents": {
            "database": {
                "name": "DatabaseAgent",
                "version": "0.1.0",
                "status": "operational",
                "endpoints_prefix": "/api/v1/database"
            },
            "apis": {
                "name": "APIsAgent",
                "version": "0.1.0",
                "status": "operational",
                "endpoints_prefix": "/api/v1/apis"
            },
            "business_rules": {
                "name": "BusinessRulesAgent",
                "version": "0.1.0",
                "status": "operational",
                "endpoints_prefix": "/api/v1/rules"
            }
        },
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json"
        }
    }


@app.get("/health", response_model=dict, summary="Health Check")
async def health() -> dict:
    """Health check endpoint"""
    return {
        "status": "healthy ✅",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/status", response_model=dict, summary="Detailed Status")
async def status() -> dict:
    """Get detailed status of all components"""
    return {
        "app_status": "running ✅",
        "app_version": "0.2.0",
        "timestamp": datetime.utcnow().isoformat(),
        "agents": {
            "database": {
                "status": "operational",
                "version": "0.1.0",
                "endpoints": 6
            },
            "apis": {
                "status": "operational",
                "version": "0.1.0",
                "endpoints": 6
            },
            "business_rules": {
                "status": "operational",
                "version": "0.1.0",
                "endpoints": 8
            }
        },
        "total_endpoints": 20
    }


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 errors"""
    return JSONResponse(
        status_code=404,
        content={
            "status": "error",
            "message": "Endpoint not found",
            "path": str(request.url),
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# ============================================================================
# DEVELOPMENT SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting development server...")
    
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
