"""
Script para ejecutar AFP desde la raíz del proyecto
Ejecutar: python run.py
"""

import sys
from pathlib import Path

# Agregar la raíz al path
root = Path(__file__).parent
sys.path.insert(0, str(root))

# Ahora importar y ejecutar
if __name__ == "__main__":
    import uvicorn
    from src.api.main import app
    
    print("")
    print("=" * 70)
    print("🚀 AFP APPLICATION STARTING")
    print("=" * 70)
    print("")
    print("📚 Swagger UI: http://localhost:8000/docs")
    print("📚 ReDoc:      http://localhost:8000/redoc")
    print("")
    print("=" * 70)
    print("")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
