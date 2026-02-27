# About the code base
- backend FastAPI server requires OpenAI key, so the server is already started and running on http://localhost:8081 (or custom port — check `run_services.sh`)
- frontend website is also already started and running on http://localhost:8080 (or custom port — check `run_services.sh`)
- You can test your changes by sending api request to above endpoints
- run command in poetry env
- never change env variable value in .env file

# Test account for API
if need to login, login with username "local_supabase" with password "s" to test the api end to end. login using `http://localhost:8081/token` api
Use Curl to test api and get test information for investigation, which is faster than going through with web browser like chrome.
Test with Chrome when there is frontend related task.

# Activate env before run any command
activate poetry env before running any test or script in the repo using `source $(poetry env info --path)/bin/activate`

# Local Packages: reflexio_commons and reflexio_client
The `reflexio_commons` and `reflexio_client` packages are in the main repository.

**File locations**:
- `reflexio_commons` Python source: `reflexio/reflexio_commons/reflexio_commons/`
- `reflexio_client` Python source: `reflexio/reflexio_client/reflexio/`

**Installation**: `reflexio-commons` is installed via Poetry path dependency in editable mode (`develop = true`).

**When modifying schemas**: Edit files in `reflexio/reflexio_commons/reflexio_commons/api_schema/`

# Supabase migration
use supabase cli `supabase migration up` to apply migrations locally instead of using the migration script which will migrate non-local storage as well.

# Use/Update README.md
- `README.md` is code navigation hint (code map) for you at project root level and maybe component levels (e.g., `reflexio/server/README.md`).
- Read only related `README.md` for the change during planning for the change
- `how_to_write_readme.md` contains instruction to update `README.md`

# Guideline to how to write code
- Always design the UI carefully without over complication
- Ensure same UI style across the entire project
- Use FastAPI as backend
- Use poetry command to add and manage python packages
- Suggest to me if there is a better architecture pattern when writing the code and ask for clarification before writing if needed

# Building frontend
- Build UI frontend with ShadCN. Try to use packages instead of building things from the scratch.
- Always design the UI carefully without over complication
- Ensure same UI style across the entire project. Always use same UI style for similar components to ensure consistency.

# Building backend
- when implement a new change to API, validate your change by sending sample CURL request to the API, server is started at http://localhost:8081

# Python docstring example
Generate python code with docstring in the following example
```
def check_string_token_overlap(str1: str, str2: str, threshold: float = 0.7) -> bool:
    """
    Check if two strings have significant token overlap, indicating they might be referring to the same thing.
    This is useful for fuzzy matching when exact string matching is too strict.

    Args:
        str1 (str): First string to compare
        str2 (str): Second string to compare
        threshold (float): Minimum overlap ratio required to consider strings as matching (0.0 to 1.0)

    Returns:
        bool: True if strings have significant overlap, False otherwise
    """
```

# Git Worktree Development
When working in a git worktree, services must run on different ports.

## Port Convention: +10 offset
| Service | Default | Worktree |
|---------|---------|----------|
| Backend | 8081 | 8091 |
| Frontend | 8080 | 8090 |
| Docs | 8082 | 8092 |

## Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| BACKEND_PORT | 8081 | FastAPI server port |
| FRONTEND_PORT | 8080 | Next.js dev server port |
| DOCS_PORT | 8082 | MkDocs server port |
| API_BACKEND_URL | auto-derived | Auto-set to http://localhost:$BACKEND_PORT |

## Setup Checklist
1. git worktree add ../reflexio-feature feature-branch
2. cd ../reflexio-feature
3. Copy .env from main worktree
4. poetry install && (cd reflexio/website && npm install)
5. export BACKEND_PORT=8091 FRONTEND_PORT=8090 DOCS_PORT=8092
6. ./run_services.sh
7. To stop: set same env vars, then ./stop_services.sh

## Notes
- Supabase is shared across worktrees (54321/54322) — no changes needed
- Do NOT modify .env for port variables — export in shell instead
- API testing: use http://localhost:$BACKEND_PORT/token
