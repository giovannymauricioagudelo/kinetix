import sys
from pathlib import Path

root = Path(__file__).parent
# Raíz del proyecto (imports src.agents.*) y agents (imports planos database_agent)
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "src" / "agents"))