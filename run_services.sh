#!/bin/bash

# Configurable ports (override via env vars for worktree dev)
BACKEND_PORT=${BACKEND_PORT:-8081}
FRONTEND_PORT=${FRONTEND_PORT:-8080}
DOCS_PORT=${DOCS_PORT:-8082}
export API_BACKEND_URL=${API_BACKEND_URL:-"http://localhost:${BACKEND_PORT}"}

# Start Supabase (if not already running)
if ! supabase status --workdir supabase/data > /dev/null 2>&1; then
    echo "Starting Supabase..."
    supabase start --workdir supabase/data
else
    echo "Supabase already running"
fi

# Start first service
uvicorn reflexio.server.api:app --host 0.0.0.0 --port ${BACKEND_PORT} --reload --reload-include "reflexio/server/site_var/site_var_sources/*.json" &

# Start website
(cd reflexio/website && npx next dev -p ${FRONTEND_PORT}) &

# Start documentation server
(cd reflexio/public_docs && npx next dev -p ${DOCS_PORT}) &

# Keep container running
wait
