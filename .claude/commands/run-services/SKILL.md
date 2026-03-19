---
name: run-services
description: Start all local services (backend, frontend, docs) with dependency checking, error diagnosis, and automatic recovery. Handles missing npm/python packages, port conflicts, and stale processes.
---

# Run Services

Start all local development services with pre-flight dependency checks and automatic error recovery.

## Overview

This command automates the full startup workflow:
0. Smart port selection — auto-detects free port group or reuses current worktree's ports
1. Pre-flight dependency checks (uv sync, venv, npm, worktree editable packages)
2. Starts Supabase (if not already running)
3. Stops any existing services (only if needed)
4. Starts all services via `run_services.sh`
5. Health-checks each service (including Supabase)
6. Ensures test account exists (after backend is healthy)
7. Diagnoses and fixes failures, then retries (up to 2 retries)

## Port Configuration

Ports are allocated in groups of 3 with a +10 offset between groups:

| Group | Frontend | Backend | Docs |
|-------|----------|---------|------|
| Default | 8080 | 8081 | 8082 |
| +10 | 8090 | 8091 | 8092 |
| +20 | 8100 | 8101 | 8102 |
| +30 | 8110 | 8111 | 8112 |
| +40 | 8120 | 8121 | 8122 |

| Service | Env Var | Base Port |
|---------|---------|-----------|
| Frontend (Next.js) | `FRONTEND_PORT` | 8080 |
| Backend (FastAPI) | `BACKEND_PORT` | 8081 |
| Docs (Fumadocs) | `DOCS_PORT` | 8082 |
| Supabase REST | - | 54321 |
| Supabase DB | - | 54322 |

Step 0 (Smart Port Selection) determines which group to use automatically, unless ports are already set via environment variables.

## Execution Steps

### Step 0: Smart Port Selection

**Pre-check:** If `BACKEND_PORT`, `FRONTEND_PORT`, or `DOCS_PORT` are already set in the environment, skip auto-detection entirely and use those values directly. Report "Using pre-configured ports" and proceed to Step 1.

**0.1** Get current worktree root:
```bash
WORKTREE_ROOT=$(git rev-parse --show-toplevel)
```

**0.2** For each port group (offset 0, 10, 20, 30, 40 — max 5 attempts), check all 3 ports in the group. For each port, determine its status:

```bash
PID=$(lsof -t -i:$PORT 2>/dev/null | head -1)
```

If no PID → port is **free**.

If PID exists, get the process's working directory:
```bash
PROC_CWD=$(lsof -a -p $PID -d cwd -Fn 2>/dev/null | tail -1 | sed 's/^n//')
```

Then classify:
- **own** — `$PROC_CWD` starts with `$WORKTREE_ROOT` (use prefix match, since child processes like Next.js run from subdirectories like `$WORKTREE_ROOT/reflexio/website`)
- **other** — `$PROC_CWD` does NOT start with `$WORKTREE_ROOT`

**0.3** Decision per group:
- All 3 ports are **free** or **own** → **use this group**. Any "own" ports will be restarted in Step 3.
- Any port is **other** → **skip this group**, try the next offset (+10)
- All 5 groups exhausted → report error: "All port groups (8080-8122) are occupied by other worktrees. Free some ports or set BACKEND_PORT/FRONTEND_PORT/DOCS_PORT manually."

**0.4** Export the chosen ports:
```bash
export FRONTEND_PORT=<8080+N>
export BACKEND_PORT=<8081+N>
export DOCS_PORT=<8082+N>
export API_BACKEND_URL="http://localhost:${BACKEND_PORT}"
```

Report which group was selected and why, e.g.:
- "Using default ports (8080/8081/8082) — all free"
- "Using default ports (8080/8081/8082) — restarting own services"
- "Using offset +10 ports (8090/8091/8092) — default ports occupied by another worktree"

Also record whether any ports in the chosen group were "own" (needs stop) or all "free" (skip stop).

### Step 1: Pre-flight Dependency Checks

Run these checks before starting anything. They are idempotent and fast when deps are already installed.

**Python dependencies (run first — creates `.venv` if missing):**
```bash
uv sync --frozen
```
Note: Use `--frozen` to install from the existing lockfile without re-resolving. Plain `uv sync` may fail due to dependency conflicts (e.g., `appworld` in the benchmarks group pins `fastapi<0.111.0` which conflicts with the main project's `fastapi>=0.111.1`). If `--frozen` fails (e.g., no lockfile), fall back to `uv sync` and report the error.

**Activate virtual environment (after `uv sync` so `.venv` exists):**
```bash
source .venv/bin/activate
```
This is critical — `run_services.sh` uses bare `uvicorn` which will resolve to the system Homebrew binary if the venv is not activated, causing `ModuleNotFoundError` for project dependencies.

**Worktree editable packages:**
In a git worktree, `uv sync` may resolve `reflexio_commons` and `reflexio_client` to a different worktree's path. Check and fix:
```bash
python -c "import reflexio_commons; import os; assert os.path.abspath(reflexio_commons.__file__).startswith(os.path.abspath('.'))" 2>/dev/null || uv pip install -e reflexio/reflexio_commons -e reflexio/reflexio_client
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

### Step 2: Start Supabase

First, health-check the Supabase REST endpoint directly — another project's Supabase instance may already be running on the shared ports (54321/54322), which is fine since Supabase is shared across worktrees:
```bash
curl --max-time 10 -s -o /dev/null -w "%{http_code}" http://127.0.0.1:54321/rest/v1/
```

If healthy (200), skip `supabase start` entirely — use the existing instance.

If not healthy, try starting:
```bash
supabase status --workdir supabase/data > /dev/null 2>&1 || supabase start --workdir supabase/data
```

If `supabase start` fails with "port is already allocated" for port 54322, another Supabase instance is running but unhealthy. Try `supabase stop --project-id <project_id>` (the project ID is shown in the error message) and retry. If it fails for other reasons, check Docker Desktop is running and report to user.

Also attempt to apply any pending migrations (non-blocking):
```bash
supabase migration up --workdir supabase/data 2>&1 || echo "Migration sync skipped — this is expected when Supabase is shared across worktrees with different migration histories"
```
Note: `migration up` will fail if the shared Supabase instance has migrations from a different branch. This is harmless — warn but do not treat as a failure.

### Step 3: Stop Existing Services (Conditional)

**If any ports in the chosen group were classified as "own" in Step 0:** stop existing services first:
```bash
./stop_services.sh
```
Wait 2 seconds for ports to fully release.

**If all ports were "free":** skip this step entirely — nothing to stop.

### Step 4: Start Services

**Important:** The venv MUST be activated before running `run_services.sh`, because the script uses bare `uvicorn` which will otherwise resolve to the system Homebrew binary.

Run `run_services.sh` in the background with the activated venv and exported port variables:
```bash
source .venv/bin/activate && FRONTEND_PORT=$FRONTEND_PORT BACKEND_PORT=$BACKEND_PORT DOCS_PORT=$DOCS_PORT ./run_services.sh > /tmp/reflexio-services.log 2>&1 &
```

Wait ~15 seconds for services to boot. Next.js compilation takes time on first request.

### Step 5: Health Check Each Service

Check each service individually. Use `curl --max-time 10 -s -o /dev/null -w "%{http_code}"` to get HTTP status codes.

**Supabase:**
```bash
curl --max-time 10 -s -o /dev/null -w "%{http_code}" http://127.0.0.1:54321/rest/v1/
```
Expected: 200

**Backend:**
```bash
curl --max-time 10 -s -o /dev/null -w "%{http_code}" http://localhost:${BACKEND_PORT}/health
```
Expected: 200

**Frontend:**
```bash
curl --max-time 10 -s -o /dev/null -w "%{http_code}" http://localhost:${FRONTEND_PORT}
```
Expected: 200 or 3xx (redirect is OK)

**Docs:**
```bash
curl --max-time 10 -s -o /dev/null -w "%{http_code}" http://localhost:${DOCS_PORT}
```
Expected: 200 or 3xx (redirect is OK)

A status of `000` means the service is not responding at all.

### Step 6: Ensure Test Account

**Only run this step if the backend health check in Step 5 returned 200.** If the backend is not healthy, skip this step entirely.

**6.1** Try to log in with the test account:
```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:${BACKEND_PORT}/token \
  -d "username=user@reflexio_test.com&password=rflx123456"
```

**6.2** If status is `200` → account exists. Report "Test account already exists" and continue to Step 8.

**6.3** If status is not `200` → create the account:
```bash
curl -s -w "\n%{http_code}" -X POST http://localhost:${BACKEND_PORT}/api/register \
  -d "username=user@reflexio_test.com&password=rflx123456"
```

**6.4** After registration, the account is unverified. Mark it verified via Supabase DB:
```bash
PGPASSWORD=postgres psql -h localhost -p 54322 -U postgres -d postgres -c \
  "UPDATE organizations SET is_verified = true WHERE email = 'user@reflexio_test.com';"
```

**6.5** Verify the account works by logging in again:
```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:${BACKEND_PORT}/token \
  -d "username=user@reflexio_test.com&password=rflx123456"
```
If `200` → report "Test account created: user@reflexio_test.com / rflx123456".
If not `200` → warn "Test account creation failed — manual setup may be needed" but do not treat as a service failure.

### Step 7: On Failure — Diagnose and Fix

If any health check fails, read the log for error details:
```bash
cat /tmp/reflexio-services.log
```

Also check if processes are even running:
```bash
lsof -i:${BACKEND_PORT} -i:${FRONTEND_PORT} -i:${DOCS_PORT}
```

#### Common Failure Patterns and Fixes

**a. "Cannot find package" / "Cannot find module" (npm)**
An npm dependency is missing. Fix:
```bash
# Identify which service (website or public_docs) from the error path
cd reflexio/website && npm install   # or reflexio/public_docs
```
Then retry from Step 4.

**b. "ModuleNotFoundError" / "ImportError" (Python — general)**
A Python dependency is missing. Fix:
```bash
uv sync --frozen
```
If that doesn't resolve it, install the specific missing package:
```bash
uv pip install --python .venv/bin/python <package-name>
```
Then retry from Step 4.

**b1. "python-multipart" RuntimeError**
FastAPI raises `RuntimeError: Form data requires "python-multipart"` if `python-multipart` is not installed. This can happen when `uv sync --frozen` resolves from a lockfile that doesn't include it. Fix:
```bash
uv pip install --python .venv/bin/python python-multipart
```
Then retry from Step 4.

**b2. "ModuleNotFoundError" for `reflexio_commons` or `reflexio_client` (worktree path mismatch)**
In a worktree, editable packages may resolve to a different worktree's path. Fix:
```bash
uv pip install -e reflexio/reflexio_commons -e reflexio/reflexio_client
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

**f. Supabase "docker not running"**
Docker Desktop must be running for Supabase. Report to user and ask them to start Docker Desktop.

**g. Supabase port conflict ("port is already allocated")**
Another Supabase project is running on 54321/54322. First check if it's healthy:
```bash
curl --max-time 10 -s -o /dev/null -w "%{http_code}" http://127.0.0.1:54321/rest/v1/
```
If healthy (200), just use the existing instance — Supabase is shared across worktrees.
If not healthy, stop the conflicting project (the project ID is shown in the error message):
```bash
supabase stop --project-id <project_id>
```
Then retry from Step 2.

#### Retry Logic

- Maximum 2 retries after applying a fix
- Each retry starts from Step 4 (stop, start, health check)
- If all retries exhausted, report final status with error details

### Step 8: Report Final Status

Report a summary table:

```
Service    | Port  | Status
-----------|-------|-------
Supabase   | 54321 | Running
Backend    | 8091  | Running
Frontend   | 8090  | Running
Docs       | 8092  | Running

Test account: user@reflexio_test.com / rflx123456 — Ready
Port group: offset +10 (8090/8091/8092) — default ports occupied by another worktree
```

Include the port group selection reason in the summary (e.g., "all free", "restarting own services", "default ports occupied by another worktree").

If all services are running, confirm success. If any failed after retries, show:
- The specific error message from logs
- Suggested manual debugging steps

## Important Notes

- **Do NOT modify `.env` files** — port overrides come from shell environment variables only
- **Logs location**: `/tmp/reflexio-services.log` contains combined service output
- **Smart port selection**: Ports are auto-detected unless `BACKEND_PORT`, `FRONTEND_PORT`, or `DOCS_PORT` env vars are already set
- If the user mentions a specific service to start (e.g., "just start the backend"), adapt the workflow to only start/check that service
