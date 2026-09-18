#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/pip install -r requirements-dev.txt

echo
echo "Entorno listo. Activa el venv y arranca la API:"
echo "  source venv/bin/activate"
echo "  python run.py"
echo
