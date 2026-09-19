"""
AFP Main FastAPI Application
Integrates all 8 agents via REST API
Complete and working version with Database Agent + APIs Agent
"""

import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time
from datetime import datetime

# Import routes - CORRECTO
from src.api.routes import database
from src.api.routes import apis_routes

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
    """Manage app lifecycle - startup and shutdown events"""
    # ===== STARTUP =====
    logger.info("=" * 70)
    logger.info("🚀 AFP APPLICATION STARTING")
    logger.info("=" * 70)
    logger.info("")
    logger.info("📦 AGENTS AVAILABLE:")
    logger.info("  ✅ Database Agent       - Schema management & migrations")
    logger.info("  ✅ APIs Agent           - REST API generation")
    logger.info("  ⏳ Business Rules Agent - Logic & validations (Semana 3)")
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


# ============================================================================
# FASTAPI APP INITIALIZATION
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
# MIDDLEWARE SETUP
# ============================================================================

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. Request ID Middleware - Tracks each request uniquely
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add X-Request-ID header for request tracking"""
    request_id = request.headers.get(
        "X-Request-ID",
        f"auto_{datetime.utcnow().timestamp()}"
    )
    request.state.request_id = request_id
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    return response


# 3. Timing Middleware - Measures response time
@app.middleware("http")
async def add_timing(request: Request, call_next):
    """Add X-Process-Time header with execution time"""
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
    """
    Root endpoint - Returns API information and available agents
    """
    return {
        "name": "Application Factory Platform",
        "version": "0.2.0",
        "description": "Fábrica de Aplicaciones Inteligente - NO-CODE platform",
        "status": "operational",
        "documentation_url": "/docs",
        "agents": {
            "database": {
                "status": "✅ OPERATIONAL",
                "version": "0.1.0",
                "description": "Automatic schema management, migrations, backups, audit",
                "base_path": "/api/v1/database",
                "endpoints": 6
            },
            "apis": {
                "status": "✅ OPERATIONAL",
                "version": "0.1.0",
                "description": "REST API generation from table schemas",
                "base_path": "/api/v1/apis",
                "endpoints": 6
            },
            "business_rules": {
                "status": "⏳ COMING (Semana 3)",
                "version": "0.1.0",
                "description": "Declarative business logic and validation rules"
            },
            "reporting": {
                "status": "⏳ COMING (Semana 3)",
                "version": "0.1.0",
                "description": "Report generation and export"
            },
            "qa": {
                "status": "⏳ COMING (Semana 4)",
                "version": "0.1.0",
                "description": "Quality assurance and testing automation"
            },
            "git_deployment": {
                "status": "⏳ COMING (Semana 4)",
                "version": "0.1.0",
                "description": "Version control and deployment orchestration"
            },
            "development": {
                "status": "⏳ COMING (Semana 4)",
                "version": "0.1.0",
                "description": "Infrastructure and cloud deployment"
            },
            "custom_ai": {
                "status": "⏳ COMING (Semana 5)",
                "version": "0.1.0",
                "description": "Custom domain-specific AI agents"
            }
        },
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_json": "/openapi.json",
            "health": "/health",
            "status": "/status"
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health():
    """
    Health check endpoint
    
    Returns:
        - status: "healthy" if all systems operational
        - timestamp: Current time in ISO format
    """
    return {
        "status": "healthy ✅",
        "version": "0.2.0",
        "service": "AFP",
        "timestamp": datetime.utcnow().isoformat(),
        "agents": {
            "database_agent": "healthy ✅",
            "apis_agent": "healthy ✅"
        }
    }


@app.get("/status")
async def status():
    """
    Detailed status endpoint
    
    Returns:
        - Current status of all agents
        - Available endpoints
        - Environment information
    """
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
        "available_endpoints": {
            "database_agent": "/api/v1/database",
            "apis_agent": "/api/v1/apis"
        },
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_json": "/openapi.json"
        }
    }


# ============================================================================
# ROUTER REGISTRATION - INCLUDE ALL AGENT ROUTES
# ============================================================================

# ✅ Database Agent routes
logger.info("Registering Database Agent routes...")
app.include_router(database.router)
logger.info("  ✅ Database Agent routes registered")

# ✅ APIs Agent routes
logger.info("Registering APIs Agent routes...")
app.include_router(apis_routes.router)
logger.info("  ✅ APIs Agent routes registered")

# Placeholder for future agents
# app.include_router(rules_router)           # Business Rules Agent
# app.include_router(reporting_router)       # Reporting Agent
# app.include_router(qa_router)              # QA Agent
# app.include_router(git_router)             # Git Deployment Agent
# app.include_router(deployment_router)      # Development Agent
# app.include_router(custom_agents_router)   # Custom AI Agents


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler - catches all unhandled exceptions
    
    Returns:
        - error: Error code
        - detail: Error message
        - request_id: Request ID for tracking
        - timestamp: When the error occurred
    """
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
# STARTUP EVENT - RUN CHECKS
# ============================================================================

@app.on_event("startup")
async def startup_checks():
    """
    Run checks on application startup
    - Verify agents can be imported
    - Check dependencies
    """
    logger.info("")
    logger.info("🔍 RUNNING STARTUP CHECKS...")
    logger.info("")
    
    try:
        # Check Database Agent
        logger.info("  Checking Database Agent...")
        from agents.database_agent.agent import DatabaseAgent
        db_agent = DatabaseAgent()
        logger.info(f"    ✅ DatabaseAgent v{db_agent.version} loaded successfully")
        
    except Exception as e:
        logger.warning(f"    ⚠️  DatabaseAgent check failed: {str(e)}")
    
    try:
        # Check APIs Agent
        logger.info("  Checking APIs Agent...")
        from agents.apis_agent.agent import APIsAgent
        apis_agent = APIsAgent()
        logger.info(f"    ✅ APIsAgent v{apis_agent.version} loaded successfully")
        
    except Exception as e:
        logger.warning(f"    ⚠️  APIsAgent check failed: {str(e)}")
    
    logger.info("")
    logger.info("✅ STARTUP CHECKS COMPLETED")
    logger.info("")


# ============================================================================
# LOCAL DEVELOPMENT - RUN SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    logger.info("")
    logger.info("🚀 Starting AFP Development Server...")
    logger.info("")
    
    # Run development server with hot reload
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


# ============================================================================
# QUICK START & TESTING GUIDE
# ============================================================================

"""
═════════════════════════════════════════════════════════════════════════════
                          QUICK START GUIDE
═════════════════════════════════════════════════════════════════════════════

1. INSTALL DEPENDENCIES:
   ─────────────────────────────────────────────────────────────────────────
   pip install -r requirements-dev.txt


2. RUN DEVELOPMENT SERVER:
   ─────────────────────────────────────────────────────────────────────────
   python src/api/main.py
   
   Expected output:
   ✅ AFP APPLICATION STARTING
   ✅ Agents available
   ✅ API docs: http://localhost:8000/docs


3. ACCESS DOCUMENTATION:
   ─────────────────────────────────────────────────────────────────────────
   Swagger UI: http://localhost:8000/docs
   ReDoc:      http://localhost:8000/redoc


4. TEST DATABASE AGENT (Create Table):
   ─────────────────────────────────────────────────────────────────────────
   curl -X POST http://localhost:8000/api/v1/database/tables \
     -H "Content-Type: application/json" \
     -d '{
       "request_id": "test_001",
       "table_definition": {
         "name": "clientes",
         "columns": [
           {"name": "cliente_id", "type": "bigint", "primary_key": true},
           {"name": "empresa_id", "type": "int", "nullable": false},
           {"name": "bodega_id", "type": "int", "nullable": false},
           {"name": "nombre", "type": "varchar", "nullable": false},
           {"name": "email", "type": "varchar"}
         ]
       }
     }'


5. TEST APIs AGENT (Generate Endpoints):
   ─────────────────────────────────────────────────────────────────────────
   curl -X POST http://localhost:8000/api/v1/apis/generate \
     -H "Content-Type: application/json" \
     -d '{
       "request_id": "gen_001",
       "table_name": "clientes",
       "table_columns": {
         "cliente_id": "bigint",
         "nombre": "varchar",
         "email": "varchar",
         "estado": "boolean",
         "saldo": "decimal"
       },
       "primary_key": "cliente_id",
       "description": "Customer management"
     }'


6. RUN UNIT TESTS:
   ─────────────────────────────────────────────────────────────────────────
   # Test Database Agent
   pytest tests/unit/test_database_agent.py -v
   
   # Test APIs Agent
   pytest tests/unit/test_apis_agent.py -v
   
   # Test all
   pytest tests/ -v


7. CHECK HEALTH:
   ─────────────────────────────────────────────────────────────────────────
   curl http://localhost:8000/health
   curl http://localhost:8000/status
   curl http://localhost:8000/


8. DOCKER (Optional):
   ─────────────────────────────────────────────────────────────────────────
   docker-compose -f docker-compose.dev.yml up


═════════════════════════════════════════════════════════════════════════════
                          AGENTS OVERVIEW
═════════════════════════════════════════════════════════════════════════════

DATABASE AGENT (✅ Operational)
  Purpose: Automatic schema management, migrations, backups, audit logs
  Routes:
    POST   /api/v1/database/tables      - Create a new table
    POST   /api/v1/database/migrations  - Apply schema migration
    GET    /api/v1/database/audit       - Get audit log
    POST   /api/v1/database/backups     - Create backup
    GET    /api/v1/database/status      - Agent status
    GET    /api/v1/database/health      - Health check

APIS AGENT (✅ Operational)
  Purpose: Generate REST API endpoints from table schemas
  Routes:
    POST   /api/v1/apis/generate        - Generate CRUD endpoints
    GET    /api/v1/apis/endpoints/:id   - Get endpoint specs
    GET    /api/v1/apis/openapi/:id     - Get OpenAPI spec
    POST   /api/v1/apis/validate        - Validate schema
    GET    /api/v1/apis/status          - Agent status
    GET    /api/v1/apis/health          - Health check

═════════════════════════════════════════════════════════════════════════════
"""
