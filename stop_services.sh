#!/bin/bash

FULL_STOP=false
if [ "$1" = "--full" ] || [ "$1" = "-f" ]; then
    FULL_STOP=true
fi

# Configurable ports (must match what was used in run_services.sh)
BACKEND_PORT=${BACKEND_PORT:-8081}
FRONTEND_PORT=${FRONTEND_PORT:-8080}
DOCS_PORT=${DOCS_PORT:-8082}

echo "Stopping services..."

# Stop FastAPI server — kill by port AND by process name to catch workers mid-request
PIDS=$(lsof -t -i:${BACKEND_PORT} 2>/dev/null)
UVICORN_PIDS=$(pgrep -f "uvicorn reflexio.server.api:app" 2>/dev/null)
ALL_PIDS=$(echo -e "${PIDS}\n${UVICORN_PIDS}" | sort -u | grep -v '^$')
if [ -n "$ALL_PIDS" ]; then
    echo "$ALL_PIDS" | xargs kill 2>/dev/null
    sleep 1
    # Force kill any survivors (uvicorn reload workers can ignore SIGTERM)
    PIDS=$(lsof -t -i:${BACKEND_PORT} 2>/dev/null)
    UVICORN_PIDS=$(pgrep -f "uvicorn reflexio.server.api:app" 2>/dev/null)
    ALL_PIDS=$(echo -e "${PIDS}\n${UVICORN_PIDS}" | sort -u | grep -v '^$')
    [ -n "$ALL_PIDS" ] && echo "$ALL_PIDS" | xargs kill -9 2>/dev/null
    echo "Stopped FastAPI server (${BACKEND_PORT})"
else
    echo "FastAPI server (${BACKEND_PORT}) not running"
fi

# Stop FastAPI server (port 8000)
PIDS=$(lsof -t -i:8000 2>/dev/null)
if [ -n "$PIDS" ]; then
    echo "$PIDS" | xargs kill 2>/dev/null
    sleep 1
    PIDS=$(lsof -t -i:8000 2>/dev/null)
    [ -n "$PIDS" ] && echo "$PIDS" | xargs kill -9 2>/dev/null
    echo "Stopped service on port 8000"
else
    echo "Port 8000 not in use"
fi

# Stop website
if pkill -f "next dev.*-p ${FRONTEND_PORT}" 2>/dev/null || pkill -f "npm run dev" 2>/dev/null; then
    echo "Stopped website (${FRONTEND_PORT})"
else
    echo "Website (${FRONTEND_PORT}) not running"
fi

# Stop docs
pkill -f "next dev.*-p ${DOCS_PORT}" && echo "Stopped docs" || echo "Docs not running"

# Stop Supabase (only with --full/-f flag)
if [ "$FULL_STOP" = true ]; then
    if supabase status --workdir supabase/data > /dev/null 2>&1; then
        supabase stop --workdir supabase/data
        echo "Stopped Supabase"
    else
        echo "Supabase not running"
    fi
fi

echo "All services stopped."
