#!/usr/bin/env bash
# NPU-STACK Full Platform Launcher
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${NPU_STACK_BACKEND_PORT:-8010}"

echo "NPU-STACK - Starting Full Platform"
echo "Backend:  http://localhost:${BACKEND_PORT}"
echo "Frontend: http://localhost:5180"
echo "API Docs: http://localhost:${BACKEND_PORT}/api/docs"
echo "App Docs:  http://localhost:5180/documentation"
echo "GitBook:   http://localhost:3001"
echo ""

# Start backend in background
echo "Starting backend..."
export NPU_STACK_BACKEND_PORT="$BACKEND_PORT"
"$SCRIPT_DIR/run-backend.sh" &
BACKEND_PID=$!

# Wait for the actual backend readiness response and surface early exits.
backend_ready=false
for _ in $(seq 1 20); do
	if curl --fail --silent --max-time 2 "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
		backend_ready=true
		echo "Backend ready."
		break
	fi
	if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
		echo "[ERROR] Backend exited before readiness; inspect its output above."
		wait "$BACKEND_PID" || true
		exit 1
	fi
	sleep 1
done
if [ "$backend_ready" != true ]; then
	echo "[WARN] Backend did not become ready within 20 seconds."
fi

# Start shared GitBook host if Docker is available
DOCS_PID=""
if command -v docker >/dev/null 2>&1; then
	echo "Starting shared GitBook host..."
	docker compose --profile docs up shared-gitbook &
	DOCS_PID=$!
else
	echo "[WARN] Docker not found - shared GitBook host not launched."
fi

sleep 2

# Start frontend in foreground
echo "Starting frontend..."
"$SCRIPT_DIR/run-frontend.sh" &
FRONTEND_PID=$!

echo ""
echo "Both services started."
echo "  Backend PID:  $BACKEND_PID"
if [ -n "$DOCS_PID" ]; then
	echo "  Docs PID:     $DOCS_PID"
fi
echo "  Frontend PID: $FRONTEND_PID"
echo ""
echo "Press Ctrl+C to stop both."

# Trap Ctrl+C to kill both
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID $DOCS_PID 2>/dev/null; exit 0" SIGINT SIGTERM

# Wait for either to exit
wait
