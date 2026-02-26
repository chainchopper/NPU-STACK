#!/usr/bin/env bash
# NPU-STACK Frontend Launcher
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting NPU-STACK Frontend..."
echo "UI: http://localhost:5173"
echo "Press Ctrl+C to stop."
echo ""

cd "$SCRIPT_DIR/frontend"

# Install node modules if missing
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

npm run dev
