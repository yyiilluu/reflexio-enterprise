# Reflexio
Description: AI agent memory system that makes AI agents personalized and self-improving from user interactions.

## Main Components

| Directory | Description | Details |
|-----------|-------------|---------|
| `open_source/reflexio/` | Git submodule — open-source Reflexio (server, core lib, client SDK, commons) | [README](open_source/reflexio/reflexio/README.md) |
| `reflexio_ext/` | Enterprise extensions — auth, OAuth, Supabase storage, enterprise API endpoints | [Scripts](reflexio_ext/scripts/README.md) |
| `website/` | Next.js frontend — profiles, interactions, feedbacks, evaluations, skills, settings, auth UI | [README](website/README.md) |
| `public_docs/` | Documentation site (Fumadocs/Next.js) | `content/docs/` |
| `supabase/data/` | Local Supabase — user data (profiles, interactions, feedbacks), atomic lock RPC | Migrations |
| `supabase/auth/` | Cloud Supabase — authentication (organizations, API keys) | [README](supabase/auth/README.md) |
| `demo/` | Conversation simulation demo — scenarios, simulator, and live viewer | [README](demo/readme.md) |
| `docker/` | Docker build and deployment files | `Dockerfile.base`, `Dockerfile.update`, `docker-compose.yaml`, `supervisord.conf` |
| `docs/` | Deployment guides | AWS ECS, Supabase migration, AWS SES email setup |
| `benchmarks/` | Performance benchmarks (LoCoMo, AppWorld, LongMemEval) | [README](benchmarks/locomo/README.md) |
| `notebooks/` | Jupyter notebooks — cookbook, demos, testing | `reflexio_cookbook.ipynb` |

## Architecture

```
Client (SDK/Web)
  -> Enterprise API (reflexio_ext/server/api.py)
    -> create_app() factory (open_source: server/api.py)
      -> get_reflexio() (server/cache/)
        -> Reflexio (reflexio_lib/)
          -> GenerationService (server/services/)
            ├─> ProfileGenerationService -> ProfileExtractor(s) -> Storage
            ├─> FeedbackGenerationService -> FeedbackExtractor(s) -> Storage
            └─> GroupEvaluationScheduler (deferred 10 min) -> Evaluator(s) -> Storage
    -> Enterprise Routers (login, oauth, self_managed_migration)
```

## Prerequisites

| Tool | Version | Purpose | Install |
|------|---------|---------|---------|
| uv | latest | Python dependency management | [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) |
| Node.js + npm | >= 18 | Frontend and docs build | [nodejs.org](https://nodejs.org/) |
| Biome | latest | TypeScript/JavaScript lint & format | `npm install --save-dev @biomejs/biome` (per-project) |
| Supabase CLI | latest | Local database (optional for self-host) | [supabase.com/docs/guides/cli](https://supabase.com/docs/guides/cli/getting-started) |

## Quick Start

```shell
cp .env.example .env                         # Configure environment (set at least one LLM API key)
uv sync                                      # Install Python dependencies (prod only)
npm --prefix website install                  # Install frontend dependencies
npm --prefix public_docs install              # Install docs dependencies
./run_services.sh                             # Starts API (8081), Website (8080), Docs (8082), and Supabase
./stop_services.sh                            # Stop app services (Supabase keeps running)
./stop_services.sh --full                     # Stop everything including Supabase
```

**Managing Python packages:**
```shell
uv add <package>                             # Add a prod dependency
uv add --dev <package>                       # Add a dev dependency (testing, linting, notebooks, etc.)
uv sync                                      # Install prod dependencies only
uv sync --group dev                          # Install prod + dev dependencies
uv sync --group docs                         # Install prod + docs dependencies
uv sync --all-groups                         # Install all dependency groups (dev, docs, benchmarks)
```

**Claude Code users:** Run `/run-services` (in claude code) instead of `./run_services.sh` (in bash) — it auto-installs missing dependencies, health-checks services, and diagnoses/fixes/retries on failure.

**Self-Host Mode** (no database, no auth):
```shell
# Set SELF_HOST=true in .env (requires S3 config for org settings, see .env.example)
./run_services.sh  # Data stored in open_source/reflexio/reflexio/data/
```

## Database Setup

**User Data (Local Supabase):**

Prerequisite: [Docker Desktop](https://docs.docker.com/desktop/) must be installed and running.

```shell
supabase start --workdir supabase/data && supabase db reset --workdir supabase/data  # Start and create schema
```

**Cloud Auth (supabase/auth/):**
- Separate cloud Supabase for organization credentials
- See `supabase/auth/README.md`

## Development

**Code Quality:**
- **Python:** Ruff (lint + format) and Pyright (type check)
- **TypeScript/JavaScript:** Biome (lint + format) and tsc (type check)

```shell
docker compose -f docker/docker-compose.yaml up -d --build
```

**Testing:**
```python
import reflexio
client = reflexio.ReflexioClient(api_key="your-api-key", url_endpoint="http://127.0.0.1:8081/")
```
See `notebooks/reflexio_cookbook.ipynb` and `open_source/reflexio/reflexio/tests/readme.md`

## Deployment

**AWS ECS (cost-optimized):** See `docs/aws-ecs-deployment-minimal.md`

**Docker:**
```shell
docker build -t reflexio-amd64:latest -f docker/Dockerfile.base .
sh reflexio_ext/scripts/deploy_ecs.sh
```

## Publishing

```shell
# Update versions in pyproject.toml files first
cd open_source/reflexio/reflexio/reflexio_commons && uv build && uv publish
cd open_source/reflexio/reflexio/reflexio_client && uv build && uv publish
```

## Key Rules

> Paths below refer to code within `open_source/reflexio/reflexio/` (the open-source server) unless otherwise noted.

**Reflexio**:
- **NEVER instantiate `Reflexio()` directly** in API endpoints
- **ALWAYS use** `get_reflexio()` from `server/cache/`

**Storage**:
- **NEVER import SupabaseStorage/LocalJsonStorage directly**
- **ALWAYS use** `request_context.storage` (type: BaseStorage)

**LLM**:
- **NEVER import OpenAIClient/ClaudeClient directly**
- **ALWAYS use** `LiteLLMClient` (uses LiteLLM for multi-provider support)

**Prompts**:
- **NEVER hardcode prompts**
- **ALWAYS use** `request_context.prompt_manager.render_prompt(prompt_id, variables)`

**Config**:
- **`tool_can_use` lives at root `Config` level** - Shared across success evaluation and feedback extraction (NOT per-`AgentSuccessConfig`)
