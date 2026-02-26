#!/usr/bin/env bash
# NPU-STACK Backend Launcher
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting NPU-STACK Backend..."
echo "API:  http://localhost:8000"
echo "Docs: http://localhost:8000/docs"
echo "Press Ctrl+C to stop."
echo ""

# Activate venv if it exists
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
elif [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

cd "$SCRIPT_DIR/backend"
python main.py
