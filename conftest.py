import sys
from pathlib import Path

# Agrega src al path para que pytest encuentre los módulos
sys.path.insert(0, str(Path(__file__).parent / "src"))