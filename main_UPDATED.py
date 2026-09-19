"""
FastAPI Application - Updated with Business Rules Agent
Punto de entrada de la aplicación con todos los agentes integrados
"""

import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from datetime import datetime

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# ============================================================================
# FASTAPI APP INIT
# ============================================================================

app = FastAPI(
    title="AFP - Fábrica de Aplicaciones Inteligente",
    description="Intelligent Application Factory with multi-agent architecture",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

logger.info("=" * 80)
logger.info("🚀 FastAPI App Initialization")
logger.info("=" * 80)

# ============================================================================
# ROUTE IMPORTS (WITH FALLBACKS)
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
# REGISTER ROUTERS
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
# ROOT ENDPOINTS
# ============================================================================

@app.get(
    "/",
    response_model=dict,
    summary="App Info",
    description="Get application information"
)
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


@app.get(
    "/health",
    response_model=dict,
    summary="Health Check",
    description="Simple health check endpoint"
)
async def health() -> dict:
    """Health check endpoint"""
    return {
        "status": "healthy ✅",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get(
    "/status",
    response_model=dict,
    summary="Detailed Status",
    description="Get detailed status of all agents"
)
async def status() -> dict:
    """Get detailed status of all components"""
    return {
        "app_status": "running ✅",
        "app_version": "0.2.0",
        "timestamp": datetime.utcnow().isoformat(),
        "agents": {
            "database": {
                "status": "operational" if database else "unavailable",
                "version": "0.1.0",
                "endpoints": 6 if database else 0
            },
            "apis": {
                "status": "operational" if apis else "unavailable",
                "version": "0.1.0",
                "endpoints": 6 if apis else 0
            },
            "business_rules": {
                "status": "operational" if business_rules else "unavailable",
                "version": "0.1.0",
                "endpoints": 8 if business_rules else 0
            }
        },
        "total_endpoints": sum([
            6 if database else 0,
            6 if apis else 0,
            8 if business_rules else 0
        ]) + 3  # +3 for root endpoints
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
# STARTUP & SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on app startup"""
    logger.info("=" * 80)
    logger.info("🚀 AFP Application Started")
    logger.info("=" * 80)
    logger.info(f"📍 Agents registered: {sum([bool(database), bool(apis), bool(business_rules)])}/3")
    logger.info(f"📚 Swagger UI: http://localhost:8000/docs")
    logger.info("=" * 80)


@app.on_event("shutdown")
async def shutdown_event():
    """Run on app shutdown"""
    logger.info("=" * 80)
    logger.info("🛑 AFP Application Shutdown")
    logger.info("=" * 80)


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
