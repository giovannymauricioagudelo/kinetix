"""
Script para corregir imports en database_agent.py
Ejecutar desde la raíz del proyecto: python fix_imports.py
"""

import sys
from pathlib import Path

# Ruta del archivo
file_path = Path("src/agents/database_agent/database_agent.py")

if not file_path.exists():
    print(f"❌ Error: No se encontró {file_path}")
    print(f"   Asegúrate de ejecutar este script desde: D:\\Desarrollo\\kinetix-studio\\")
    sys.exit(1)

try:
    # Leer el archivo
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Reemplazar el import
    original_import = "from base_agent import"
    new_import = "from src.agents.base_agent import"
    
    if original_import in content:
        content = content.replace(original_import, new_import)
        
        # Escribir el archivo
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Import corregido exitosamente en database_agent.py")
        print(f"   Cambio: '{original_import}' → '{new_import}'")
        print("")
        print("Ahora prueba:")
        print("  python src/api/main.py")
    else:
        print("ℹ️  El import ya está correcto o no se encontró")
        print(f"   Buscaba: '{original_import}'")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    sys.exit(1)
