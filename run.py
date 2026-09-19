"""
Script para ejecutar AFP desde la raíz del proyecto
Ejecutar: python run.py
O mejor aún: python -m uvicorn src.api.main:app --reload
"""

import sys
from pathlib import Path

# Agregar la raíz al path
root = Path(__file__).parent
sys.path.insert(0, str(root))

# Ahora importar y ejecutar
if __name__ == "__main__":
    import uvicorn
    
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
    
    # Usar string de importación para evitar warning
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
