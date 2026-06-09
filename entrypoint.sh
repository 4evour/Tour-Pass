#!/bin/bash
set -e

echo "=== TourPass Starting ==="
echo "C++ Backend on port ${PORT:-8080}"
echo "Agent Service on port ${AGENT_PORT:-8090}"

# Cleanup on exit
cleanup() {
    echo "Shutting down..."
    if [ -n "$AGENT_PID" ]; then
        kill "$AGENT_PID" 2>/dev/null || true
        wait "$AGENT_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# Start Agent service in background
cd /app
export PATH="/app/venv/bin:$PATH"

echo "Starting Agent service..."
python -m uvicorn agent.main:app \
    --host 127.0.0.1 \
    --port "${AGENT_PORT:-8090}" \
    --workers 1 \
    --log-level info &
AGENT_PID=$!

# Wait for Agent to be ready
echo "Waiting for Agent service..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:${AGENT_PORT:-8090}/agent/health > /dev/null 2>&1; then
        echo "Agent service ready!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "WARN: Agent service not ready after 30s, starting C++ backend anyway"
    fi
    sleep 1
done

# Start C++ backend (foreground)
echo "Starting C++ backend..."
/app/tourpass &
CPP_PID=$!

# Wait for either process to exit
wait -n $AGENT_PID $CPP_PID 2>/dev/null || wait