"""
AFP Main FastAPI Application
Integrates all 8 agents via REST API
"""

import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time
from datetime import datetime

# Import routes
from src.api.routes import apis_routes
from src.api.routes import database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# LIFESPAN MANAGEMENT
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle"""
    # Startup
    logger.info("=" * 60)
    logger.info("🚀 AFP APPLICATION STARTING")
    logger.info("=" * 60)
    logger.info("")
    logger.info("📦 Agents available:")
    logger.info("  ✅ Database Agent - Schema management")
    logger.info("  ✅ APIs Agent - REST API generation")
    logger.info("  ⏳ Business Rules Agent - (coming Semana 3)")
    logger.info("  ⏳ Reporting Agent - (coming Semana 3)")
    logger.info("  ⏳ QA Agent - (coming Semana 3)")
    logger.info("  ⏳ Git Deployment Agent - (coming Semana 3)")
    logger.info("  ⏳ Development Agent - (coming Semana 3)")
    logger.info("  ⏳ Custom AI Agents - (coming Semana 3)")
    logger.info("")
    logger.info("🌐 API available at: http://localhost:8000")
    logger.info("📚 API docs: http://localhost:8000/docs")
    logger.info("🔍 Alternative docs: http://localhost:8000/redoc")
    logger.info("")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown
    logger.info("=" * 60)
    logger.info("🛑 AFP APPLICATION SHUTTING DOWN")
    logger.info("=" * 60)


# ============================================================================
# FASTAPI APP
# ============================================================================

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
# MIDDLEWARE
# ============================================================================

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to tracking"""
    request_id = request.headers.get("X-Request-ID", f"auto_{datetime.utcnow().timestamp()}")
    request.state.request_id = request_id
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    return response


# Timing middleware
@app.middleware("http")
async def add_timing(request: Request, call_next):
    """Add timing header"""
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    
    response.headers["X-Process-Time"] = str(duration)
    
    return response


# ============================================================================
# ROOT ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Application Factory Platform",
        "version": "0.2.0",
        "description": "Fábrica de Aplicaciones Inteligente - NO-CODE platform",
        "status": "operational",
        "documentation": "/docs",
        "agents": {
            "database": {
                "status": "operational ✅",
                "version": "0.1.0",
                "description": "Automatic schema management",
                "endpoints": [
                    "POST /api/v1/database/tables - Create table",
                    "POST /api/v1/database/migrations - Apply migration",
                    "GET /api/v1/database/audit - Get audit log",
                    "POST /api/v1/database/backups - Create backup",
                    "GET /api/v1/database/status - Agent status",
                    "GET /api/v1/database/health - Health check"
                ]
            },
            "apis": {
                "status": "operational ✅",
                "version": "0.1.0",
                "description": "REST API generation",
                "endpoints": [
                    "POST /api/v1/apis/generate - Generate endpoints",
                    "GET /api/v1/apis/endpoints/{request_id} - Get endpoints",
                    "GET /api/v1/apis/openapi/{request_id} - Get OpenAPI spec",
                    "POST /api/v1/apis/validate - Validate schema",
                    "GET /api/v1/apis/status - Agent status",
                    "GET /api/v1/apis/health - Health check"
                ]
            },
            "business_rules": {
                "status": "coming_soon ⏳",
                "version": "0.1.0",
                "description": "Declarative business logic"
            },
            "reporting": {
                "status": "coming_soon ⏳",
                "version": "0.1.0",
                "description": "Report generation"
            },
            "qa": {
                "status": "coming_soon ⏳",
                "version": "0.1.0",
                "description": "Quality assurance and testing"
            },
            "git_deployment": {
                "status": "coming_soon ⏳",
                "version": "0.1.0",
                "description": "Version control and deployment"
            },
            "development": {
                "status": "coming_soon ⏳",
                "version": "0.1.0",
                "description": "Infrastructure deployment"
            },
            "custom_ai": {
                "status": "coming_soon ⏳",
                "version": "0.1.0",
                "description": "Custom domain agents"
            }
        },
        "documentation": {
            "api_docs": "/docs",
            "redoc": "/redoc",
            "openapi_json": "/openapi.json",
            "health": "/health",
            "status": "/status"
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy ✅",
        "version": "0.2.0",
        "timestamp": datetime.utcnow().isoformat(),
        "agents": {
            "database_agent": "healthy",
            "apis_agent": "healthy"
        }
    }


@app.get("/status")
async def status():
    """Detailed status endpoint"""
    return {
        "status": "running ✅",
        "version": "0.2.0",
        "environment": "development",
        "timestamp": datetime.utcnow().isoformat(),
        "agents": {
            "database_agent": "ready ✅",
            "apis_agent": "ready ✅",
            "business_rules_agent": "not_loaded ⏳",
            "reporting_agent": "not_loaded ⏳",
            "qa_agent": "not_loaded ⏳",
            "git_deployment_agent": "not_loaded ⏳",
            "development_agent": "not_loaded ⏳",
            "custom_ai_agents": "not_loaded ⏳"
        },
        "endpoints": {
            "database": "/api/v1/database",
            "apis": "/api/v1/apis"
        }
    }


# ============================================================================
# INCLUDE ROUTERS
# ============================================================================

# Database Agent routes
app.include_router(database.router)

# APIs Agent routes ✅ AGREGADO
app.include_router(apis_routes.router)

# Placeholder for other agents (will add as we create them)
# app.include_router(rules_router)
# app.include_router(reporting_router)
# app.include_router(qa_router)
# app.include_router(git_router)
# app.include_router(deployment_router)
# app.include_router(custom_agents_router)


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "An unexpected error occurred",
            "request_id": getattr(request.state, "request_id", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# ============================================================================
# STARTUP CHECKS
# ============================================================================

@app.on_event("startup")
async def startup_checks():
    """Run checks on startup"""
    logger.info("🔍 Running startup checks...")
    
    try:
        # Check if Database Agent can be imported
        from agents.database_agent.agent import DatabaseAgent
        db_agent = DatabaseAgent()
        logger.info(f"  ✅ DatabaseAgent imported successfully")
        
        # Check if APIs Agent can be imported
        from agents.apis_agent.agent import APIsAgent
        apis_agent = APIsAgent()
        logger.info(f"  ✅ APIsAgent imported successfully")
        
        logger.info("✅ All startup checks passed!")
        
    except Exception as e:
        logger.error(f"❌ Startup check failed: {str(e)}")
        logger.error("Note: This is non-fatal if agents aren't implemented yet")


# ============================================================================
# LOCAL DEVELOPMENT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Run development server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


"""
QUICK START:

1. Install dependencies:
   pip install -r requirements-dev.txt

2. Run development server:
   python src/api/main.py

3. Open API documentation:
   http://localhost:8000/docs

4. Test Database Agent:
   curl -X POST http://localhost:8000/api/v1/database/tables \
     -H "Content-Type: application/json" \
     -d '{
       "request_id": "test_001",
       "table_definition": {
         "name": "test_table",
         "columns": [
           {"name": "id", "type": "bigint", "primary_key": true},
           {"name": "empresa_id", "type": "int"},
           {"name": "bodega_id", "type": "int"},
           {"name": "name", "type": "varchar"}
         ]
       }
     }'

5. Test APIs Agent:
   curl -X POST http://localhost:8000/api/v1/apis/generate \
     -H "Content-Type: application/json" \
     -d '{
       "request_id": "gen_001",
       "table_name": "clientes",
       "table_columns": {
         "cliente_id": "bigint",
         "nombre": "varchar",
         "estado": "boolean"
       },
       "primary_key": "cliente_id"
     }'

6. Access Swagger UI:
   http://localhost:8000/docs

DOCKER:

1. Build image:
   docker build -f docker/Dockerfile -t afp:latest .

2. Run container:
   docker run -p 8000:8000 afp:latest

3. With docker-compose:
   docker-compose -f docker-compose.dev.yml up

PRODUCTION:

1. Set ENV=production
2. Use PostgreSQL (not SQLite)
3. Enable authentication (JWT)
4. Set CORS properly
5. Add rate limiting
6. Enable logging aggregation (Loki)
7. Setup monitoring (Prometheus)
8. Deploy to Azure/Kubernetes
"""
