#!/usr/bin/env bash
# NPU-STACK Full Platform Launcher
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "NPU-STACK - Starting Full Platform"
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "API Docs: http://localhost:8000/docs"
echo ""

# Start backend in background
echo "Starting backend..."
"$SCRIPT_DIR/run-backend.sh" &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

# Start frontend in foreground
echo "Starting frontend..."
"$SCRIPT_DIR/run-frontend.sh" &
FRONTEND_PID=$!

echo ""
echo "Both services started."
echo "  Backend PID:  $BACKEND_PID"
echo "  Frontend PID: $FRONTEND_PID"
echo ""
echo "Press Ctrl+C to stop both."

# Trap Ctrl+C to kill both
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM

# Wait for either to exit
wait
