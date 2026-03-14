# Reflexio
Description: AI agent memory system that makes AI agents personalized and self-improving from user interactions.

## Main Components

| Directory | Description | Details |
|-----------|-------------|---------|
| `reflexio/server/` | FastAPI backend - processes interactions, generates profiles, extracts feedback | [README](reflexio/server/README.md) |
| `reflexio/reflexio_lib/` | Core library - `Reflexio` orchestrator connecting API to services | `reflexio_lib.py` |
| `reflexio/reflexio_client/` | Python SDK for interacting with Reflexio API | [README](reflexio/README.md) |
| `reflexio/reflexio_commons/` | Shared schemas and configuration models | [README](reflexio/README.md) |
| `reflexio/website/` | Next.js frontend - profiles, interactions, feedbacks, evaluations, skills, account, auth UI | `app/`, `components/` |
| `supabase/` | Local Supabase - user data (profiles, interactions, feedbacks), atomic lock RPC | Migrations |
| `supabase_login/` | Cloud Supabase - authentication (organizations, API keys) | [README](supabase_login/README.md) |
| `demo/` | Conversation simulation demo - scenarios, simulator, and live viewer | [README](demo/readme.md) |
| `docs/` | Deployment guides | AWS ECS, Supabase migration, AWS SES email setup |

## Architecture

```
Client (SDK/Web)
  -> FastAPI (server/api.py)
    -> get_reflexio() (server/cache/)
      -> Reflexio (reflexio_lib/)
        -> GenerationService (server/services/)
          ├─> ProfileGenerationService -> ProfileExtractor(s) -> Storage
          ├─> FeedbackGenerationService -> FeedbackExtractor(s) -> Storage
          └─> GroupEvaluationScheduler (deferred 10 min) -> Evaluator(s) -> Storage
```

## Prerequisites

| Tool | Version | Purpose | Install |
|------|---------|---------|---------|
| uv | latest | Python dependency management | [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) |
| Node.js + npm | >= 18 | Frontend and docs build | [nodejs.org](https://nodejs.org/) |
| Supabase CLI | latest | Local database (optional for self-host) | [supabase.com/docs/guides/cli](https://supabase.com/docs/guides/cli/getting-started) |

## Quick Start

```shell
cp .env.example .env                         # Configure environment (set at least one LLM API key)
uv sync                                      # Install Python dependencies (includes workspace packages)
npm --prefix reflexio/website install         # Install frontend dependencies
npm --prefix reflexio/public_docs install     # Install docs dependencies
./run_services.sh                             # Starts API (8081), Website (8080), Docs (8082), and Supabase
./stop_services.sh                            # Stop app services (Supabase keeps running)
./stop_services.sh --full                     # Stop everything including Supabase
```

**Claude Code users:** Run `/run-services` (in claude code) instead of `./run_services.sh` (in bash) — it auto-installs missing dependencies, health-checks services, and diagnoses/fixes/retries on failure.

**Self-Host Mode** (no database, no auth):
```shell
# Set SELF_HOST=true in .env (requires S3 config for org settings, see .env.example)
./run_services.sh  # Data stored in reflexio/data/
```

## Database Setup

**User Data (Local Supabase):**

Prerequisite: [Docker Desktop](https://docs.docker.com/desktop/) must be installed and running.

```shell
supabase start && supabase db reset  # Start and create schema
```

**Cloud Auth (supabase_login/):**
- Separate cloud Supabase for organization credentials
- See `supabase_login/README.md`

## Development

```shell
docker compose -f ./docker-compose-local.yaml up -d --build
```

**Testing:**
```python
import reflexio
client = reflexio.ReflexioClient(api_key="your-api-key", url_endpoint="http://127.0.0.1:8081/")
```
See `notebooks/reflexio_cookbook.ipynb` and `reflexio/tests/readme.md`

## Deployment

**AWS ECS (cost-optimized):** See `docs/aws-ecs-deployment-minimal.md`

**Docker:**
```shell
docker build -t reflexio-amd64:latest -f Dockerfile.base .
sh reflexio/scripts/deploy_ecs.sh
```

## Publishing

```shell
# Update versions in pyproject.toml files first
cd reflexio/reflexio_commons && uv build && uv publish
cd reflexio/reflexio_client && uv build && uv publish
```

## Key Rules

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
