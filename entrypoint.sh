#!/bin/bash

echo "=== TourPass Starting ==="
echo "C++ Backend on port ${PORT:-8080}"
echo "Agent Service on port ${AGENT_PORT:-8090}"

cleanup() {
    echo "Shutting down..."
    kill $CPP_PID 2>/dev/null || true
    kill $AGENT_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd /app

# Start C++ backend FIRST (this is the main service)
echo "Starting C++ backend..."
/app/tourpass &
CPP_PID=$!

# Start Agent service in background (non-fatal)
echo "Starting Agent service..."
python3 -m uvicorn agent.main:app \
    --host 127.0.0.1 \
    --port "${AGENT_PORT:-8090}" \
    --workers 1 \
    --log-level info &
AGENT_PID=$!

echo "Both services started. C++ PID=$CPP_PID Agent PID=$AGENT_PID"

# Wait for C++ backend (main process)
wait $CPP_PID