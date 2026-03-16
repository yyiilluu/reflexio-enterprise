# About the code base
- Backend (FastAPI) and frontend (Next.js) require `./run_services.sh` to start — check its output for ports
- Use curl for API testing (faster); use Chrome for frontend tasks
- Run commands in uv env (use `uv run <cmd>` or activate `.venv`)
- Never change env variable values in .env file

# API Authentication
Use `REFLEXIO_API_KEY` from `.env` to authenticate API requests. Pass it as a Bearer token:
```
curl -H "Authorization: Bearer $REFLEXIO_API_KEY" http://localhost:$BACKEND_PORT/...
```
Or with the Python client:
```python
from reflexio import ReflexioClient
client = ReflexioClient(url_endpoint=f"http://localhost:{BACKEND_PORT}")  # picks up REFLEXIO_API_KEY from env automatically
```

# Local Packages: reflexio_commons and reflexio_client
The `reflexio_commons` and `reflexio_client` packages are in the main repository.

**File locations**:
- `reflexio_commons` Python source: `reflexio/reflexio_commons/reflexio_commons/`
- `reflexio_client` Python source: `reflexio/reflexio_client/reflexio/`

**Installation**: `reflexio-commons` is installed via uv workspace dependency.

**When modifying schemas**: Edit files in `reflexio/reflexio_commons/reflexio_commons/api_schema/`

# Supabase migration
use supabase cli `supabase migration up` to apply migrations locally instead of using the migration script which will migrate non-local storage as well.

# Development Guidelines
- Use FastAPI as backend, ShadCN for frontend UI — prefer existing packages over building from scratch
- Ensure consistent UI style across the entire project
- Use `uv` to add and manage python packages
- Suggest better architecture patterns and ask for clarification before writing if needed

# Code Quality Tools
- **Python**: Ruff (lint + format), Pyright (type check)
- **TypeScript/JavaScript**: Biome (lint + format), tsc (type check)

# Git Worktree Development
When working in a git worktree, services must run on different ports. Use `/run-services` skill for automatic port handling.

## Setup Checklist
1. `git worktree add ../reflexio-feature feature-branch`
2. `cd ../reflexio-feature`
3. Copy `.env` from main worktree
4. `uv sync && uv pip install -e reflexio/reflexio_commons -e reflexio/reflexio_client && (cd reflexio/website && npm install)`
5. `export BACKEND_PORT=8091 FRONTEND_PORT=8090 DOCS_PORT=8092`
6. `./run_services.sh` (or `/run-services` skill)

## Notes
- Supabase is shared across worktrees (54321/54322) — no changes needed
- Do NOT modify .env for port variables — export in shell instead
- **Worktree editable packages**: `uv sync` resolves workspace editable installs from the lockfile, which may point to a different worktree. Running `uv pip install -e` after `uv sync` forces them to resolve to the current worktree.
