"""
Script para agregar self.version a DatabaseAgent.__init__
Ejecutar: python fix_database_version.py
"""

import sys
from pathlib import Path

file_path = Path("src/agents/database_agent/database_agent.py")

if not file_path.exists():
    print(f"❌ Error: No se encontró {file_path}")
    sys.exit(1)

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Buscar la línea super().__init__(config) después de DatabaseAgent.__init__
    search_text = "        super().__init__(config)"
    add_text = '\n        self.version = "0.1.0"'
    
    if search_text in content and "self.version" not in content:
        # Agregar después de super().__init__(config)
        content = content.replace(
            search_text,
            search_text + add_text
        )
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Atributo 'self.version' agregado exitosamente")
        print("")
        print("Ahora ejecuta:")
        print("  python run.py")
    
    elif "self.version" in content:
        print("ℹ️  DatabaseAgent ya tiene self.version")
    else:
        print("⚠️  No se pudo aplicar el cambio automático")
        print("")
        print("AGREGA MANUALMENTE en database_agent.py:")
        print("  Después de: super().__init__(config)")
        print("  Agrega: self.version = \"0.1.0\"")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
