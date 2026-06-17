#!/bin/bash

echo "=== TourPass Starting ==="
echo "C++ Backend on port ${PORT:-8080}"
echo "Agent Service on port ${AGENT_PORT:-8090}"
echo "Agent implementation: ${AGENT_IMPL:-multi}"

MONITOR_PID=0

cleanup() {
    echo "Shutting down..."
    kill $CPP_PID 2>/dev/null || true
    kill $AGENT_PID 2>/dev/null || true
    kill $MONITOR_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd /app

# Start C++ backend FIRST (this is the main service)
echo "Starting C++ backend..."
/app/tourpass &
CPP_PID=$!

if [ "${AGENT_IMPL:-multi}" = "legacy" ]; then
    AGENT_APP="agent.main:app"
else
    AGENT_APP="api_multi_agent:app"
fi

# Start Agent service in background (non-fatal)
echo "Starting Agent service (${AGENT_APP})..."
python3 -m uvicorn "${AGENT_APP}" \
    --host 127.0.0.1 \
    --port "${AGENT_PORT:-8090}" \
    --workers 1 \
    --log-level info &
AGENT_PID=$!

echo "Both services started. C++ PID=$CPP_PID Agent PID=$AGENT_PID"

# Monitor agent and restart if it dies
(
    while true; do
        sleep 10
        if ! kill -0 $AGENT_PID 2>/dev/null; then
            echo "Agent process died, restarting..."
            python3 -m uvicorn "${AGENT_APP}" \
                --host 127.0.0.1 \
                --port "${AGENT_PORT:-8090}" \
                --workers 1 --log-level info &
            AGENT_PID=$!
            echo "Agent restarted. New PID=$AGENT_PID"
        fi
    done
) &
MONITOR_PID=$!

# Wait for C++ backend (main process)
wait $CPP_PID
kill $MONITOR_PID 2>/dev/null || true
