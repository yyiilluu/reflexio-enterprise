---
name: run-services
description: Start all local services (backend, frontend, docs) with dependency checking, error diagnosis, and automatic recovery. Handles missing npm/python packages, port conflicts, and stale processes.
---

# Run Services

Start all local development services with pre-flight dependency checks and automatic error recovery.

## Overview

This command automates the full startup workflow:
1. Checks and installs missing dependencies
2. Stops any existing services to free ports
3. Starts all services via `run_services.sh`
4. Health-checks each service
5. Diagnoses and fixes failures, then retries (up to 2 retries)

## Port Configuration

Read port values from environment variables (respect worktree offsets):

| Service | Env Var | Default |
|---------|---------|---------|
| Backend (FastAPI) | `BACKEND_PORT` | 8081 |
| Frontend (Next.js) | `FRONTEND_PORT` | 8080 |
| Docs (Fumadocs) | `DOCS_PORT` | 8082 |

## Execution Steps

### Step 1: Activate Poetry Environment

```bash
source $(poetry env info --path)/bin/activate
```

### Step 2: Pre-flight Dependency Checks

Run these checks before starting anything. They are idempotent and fast when deps are already installed.

**Python dependencies:**
```bash
poetry install
```

**Frontend dependencies (reflexio/website):**
Check if `node_modules` exists and has content. If missing or empty, install:
```bash
ls reflexio/website/node_modules/.package-lock.json 2>/dev/null || (cd reflexio/website && npm install)
```

**Docs dependencies (reflexio/public_docs):**
Check if `node_modules` exists and has content. If missing or empty, install:
```bash
ls reflexio/public_docs/node_modules/.package-lock.json 2>/dev/null || (cd reflexio/public_docs && npm install)
```

### Step 3: Stop Existing Services

Free ports before starting fresh:
```bash
./stop_services.sh
```

Wait 2 seconds for ports to fully release.

### Step 4: Start Services

Run `run_services.sh` in the background and capture output:
```bash
./run_services.sh > /tmp/reflexio-services.log 2>&1 &
```

Wait ~15 seconds for services to boot. Next.js compilation takes time on first request.

### Step 5: Health Check Each Service

Check each service individually. Use `curl --max-time 10 -s -o /dev/null -w "%{http_code}"` to get HTTP status codes.

**Backend:**
```bash
curl --max-time 10 -s -o /dev/null -w "%{http_code}" http://localhost:${BACKEND_PORT:-8081}/docs
```
Expected: 200

**Frontend:**
```bash
curl --max-time 10 -s -o /dev/null -w "%{http_code}" http://localhost:${FRONTEND_PORT:-8080}
```
Expected: 200 or 3xx (redirect is OK)

**Docs:**
```bash
curl --max-time 10 -s -o /dev/null -w "%{http_code}" http://localhost:${DOCS_PORT:-8082}
```
Expected: 200 or 3xx (redirect is OK)

A status of `000` means the service is not responding at all.

### Step 6: On Failure — Diagnose and Fix

If any health check fails, read the log for error details:
```bash
cat /tmp/reflexio-services.log
```

Also check if processes are even running:
```bash
lsof -i:${BACKEND_PORT:-8081} -i:${FRONTEND_PORT:-8080} -i:${DOCS_PORT:-8082}
```

#### Common Failure Patterns and Fixes

**a. "Cannot find package" / "Cannot find module" (npm)**
An npm dependency is missing. Fix:
```bash
# Identify which service (website or public_docs) from the error path
cd reflexio/website && npm install   # or reflexio/public_docs
```
Then retry from Step 4.

**b. "ModuleNotFoundError" / "ImportError" (Python)**
A Python dependency is missing. Fix:
```bash
poetry install
```
Then retry from Step 4.

**c. "Address already in use" / "EADDRINUSE"**
A port is still occupied. Fix:
```bash
# Kill whatever is on the port
lsof -t -i:PORT | xargs kill -9 2>/dev/null
```
Wait 2 seconds, then retry from Step 4.

**d. ".next build cache errors" / "ENOENT .next"**
Stale Next.js build artifacts. Fix:
```bash
rm -rf reflexio/website/.next reflexio/public_docs/.next
```
Then retry from Step 4.

**e. Script syntax errors or unknown errors**
Report the error output to the user and suggest manual steps. Do not retry.

#### Retry Logic

- Maximum 2 retries after applying a fix
- Each retry starts from Step 4 (stop, start, health check)
- If all retries exhausted, report final status with error details

### Step 7: Report Final Status

Report a summary table:

```
Service    | Port | Status
-----------|------|-------
Backend    | 8081 | Running
Frontend   | 8080 | Running
Docs       | 8082 | FAILED - [error summary]
```

If all services are running, confirm success. If any failed after retries, show:
- The specific error message from logs
- Suggested manual debugging steps

## Important Notes

- **Do NOT modify `.env` files** — port overrides come from shell environment variables only
- **Logs location**: `/tmp/reflexio-services.log` contains combined service output
- **Worktree support**: If `BACKEND_PORT`, `FRONTEND_PORT`, or `DOCS_PORT` env vars are set, those ports are used automatically
- If the user mentions a specific service to start (e.g., "just start the backend"), adapt the workflow to only start/check that service
