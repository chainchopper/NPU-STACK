#!/usr/bin/env bash
# NPU-STACK Backend Launcher
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${NPU_STACK_BACKEND_PORT:-8010}"

echo "Starting NPU-STACK Backend..."
echo "API:  http://localhost:${BACKEND_PORT}"
echo "Docs: http://localhost:${BACKEND_PORT}/api/docs"
echo "Press Ctrl+C to stop."
echo ""

# Activate venv if it exists
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
elif [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

cd "$SCRIPT_DIR"
export NPU_STACK_BACKEND_PORT="$BACKEND_PORT"
python -m uvicorn backend.main:app --host 127.0.0.1 --port "$BACKEND_PORT"
