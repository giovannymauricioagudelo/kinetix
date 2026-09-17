"""
Script para corregir DatabaseAgent - Agregar atributo 'version'
Ejecutar: python fix_database_agent.py
"""

import sys
import re
from pathlib import Path

file_path = Path("src/agents/database_agent/database_agent.py")

if not file_path.exists():
    print(f"❌ Error: No se encontró {file_path}")
    sys.exit(1)

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Patrón para encontrar __init__ de DatabaseAgent
    pattern = r'(class DatabaseAgent.*?:\s*""".*?"""\s*)(def __init__\(self\):)'
    
    # Verificar si ya tiene version
    if 'self.version' in content:
        print("ℹ️  DatabaseAgent ya tiene el atributo 'version'")
    else:
        # Buscar la línea del __init__ y agregar version
        pattern2 = r'(def __init__\(self\):(?:\s+.*?\n)*?)(\s+logger\.info|def )'
        
        def add_version(match):
            init_content = match.group(1)
            next_line = match.group(2)
            
            # Si ya tiene logger.info o algo, agregar version antes
            if 'self.name' in init_content:
                # Ya tiene self.name, agregar después de él
                init_content = init_content.replace(
                    'self.name = ',
                    'self.name = '
                )
                # Agregar version después de name
                lines = init_content.split('\n')
                for i, line in enumerate(lines):
                    if 'self.name =' in line:
                        lines.insert(i+1, '        self.version = "0.1.0"')
                        break
                init_content = '\n'.join(lines)
            else:
                # No tiene self.name, agregarlo
                indent = '        '
                init_content += f'\n{indent}self.name = "DatabaseAgent"\n{indent}self.version = "0.1.0"'
            
            return init_content + '\n' + next_line
        
        content_new = re.sub(pattern2, add_version, content)
        
        if content_new != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content_new)
            print("✅ Atributo 'version' agregado a DatabaseAgent")
        else:
            print("ℹ️  No se pudo aplicar el cambio automático")
            print("")
            print("AGREGÁ MANUALMENTE en el __init__ de DatabaseAgent:")
            print("    self.version = \"0.1.0\"")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    sys.exit(1)
