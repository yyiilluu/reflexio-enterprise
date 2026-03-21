# Reflexio Scripts

This directory contains utility scripts for managing and analyzing the Reflexio system.

## Available Scripts

### count_tokens.py

Token counter for analyzing token usage in files and directories using OpenAI's tiktoken library.

**Installation:**
```bash
pip install tiktoken
# or install from requirements.txt
pip install -r requirements.txt
```

**Usage:**

```bash
# Count tokens in a single file
python count_tokens.py /path/to/file.py

# Count tokens in a directory (Python files only by default)
python count_tokens.py /path/to/directory

# Count tokens with specific model encoding
python count_tokens.py /path/to/file.py --model gpt-4o

# Count tokens in multiple file types
python count_tokens.py /path/to/directory --extensions .py,.md,.txt

# Hide per-file details (show only summary)
python count_tokens.py /path/to/directory --no-details
```

**Examples:**

```bash
# Count tokens in the entire server directory
python reflexio/scripts/count_tokens.py reflexio/server

# Count tokens in code_map.md
python reflexio/scripts/count_tokens.py reflexio/code_map.md

# Count tokens in all Python and Markdown files
python reflexio/scripts/count_tokens.py reflexio --extensions .py,.md

# Count tokens for GPT-4o model
python reflexio/scripts/count_tokens.py reflexio/server --model gpt-4o
```

**Output:**

The script provides:
- Total token count across all files
- Total character and line counts
- Per-file breakdown (sorted by token count)
- Error reporting for files that couldn't be processed

**Supported Models:**
- `gpt-4` (default)
- `gpt-4o`
- `gpt-3.5-turbo`
- `text-davinci-003`
- Any other OpenAI model supported by tiktoken

### test_supabase_connection.py

Test script to verify Supabase connection and database access.

**Purpose**: Validates that the Supabase database is accessible and all required tables and functions exist.

**Configuration Options**:

Provide configuration via command-line arguments:

**Command-line Arguments**:
- `--url`: Supabase project URL (required)
- `--key`: Supabase API key (required)
- `--tables`: Comma-separated list of tables to test (optional)

**Usage**:

```bash
# Test connection
python -m reflexio.scripts.test_supabase_connection \
  --url https://your-project.supabase.co \
  --key your-supabase-key

# Test specific tables only
python -m reflexio.scripts.test_supabase_connection \
  --url https://your-project.supabase.co \
  --key your-supabase-key \
  --tables profiles,interactions,requests
```

**What it tests**:
- ✓ Connection to Supabase
- ✓ Table accessibility (profiles, interactions, requests, feedbacks, etc.)
- ✓ Record counts for each table
- ✓ Database functions (match_profiles, match_interactions, etc.)
- ✓ Sample data retrieval (if records exist)

**Features**:
- Comprehensive connectivity testing
- Clear pass/fail reporting
- Detailed error messages
- Tests all standard Reflexio tables by default
- Validates custom database functions

### run_all_migrations.py

Deployment-time migration script that runs Supabase migrations for all organizations.

**Purpose**: Runs before FastAPI starts to ensure all organizations have the latest database schema.

**Modes**:
- **Self-host mode** (`SELF_HOST=true`): Loads local config and runs a single migration
- **Cloud mode**: Connects to login Supabase, fetches all orgs, decrypts configs, and migrates each

**Command-line Arguments**:
- `--dry-run`: List organizations without running migrations
- `--org-id`: Run migration for a single organization only
- `--continue-on-error`: Continue migrating other orgs if one fails

**Required Environment Variables**:
- `RUN_MIGRATION`: Must be "true" to run migrations
- Cloud mode: `LOGIN_SUPABASE_URL`, `LOGIN_SUPABASE_KEY`, `FERNET_KEYS`

**Usage**:

```bash
# Dry run (list orgs only)
python -m reflexio.scripts.run_all_migrations --dry-run

# Single org test
python -m reflexio.scripts.run_all_migrations --org-id "test-org"

# Full run with error tolerance
python -m reflexio.scripts.run_all_migrations --continue-on-error
```

### add_config_script.py

Script for adding configuration to the database.

### add_user_interactions_script.py

Script for adding user interactions to storage.

### add_user_profiles_script.py

Script for adding user profiles to storage.

### async_publish_interaction_script.py

Demonstrates asynchronous publishing of interactions to Reflexio without blocking execution.

**Purpose**: Shows how to publish interactions in the background while continuing to execute other code concurrently using async/await patterns.

**Key Features**:
- Async interaction publishing with ReflexioClient
- Background task execution
- Non-blocking concurrent operations

### simple_sync_publish.py

Shows how to publish interactions from synchronous code without blocking.

**Purpose**: Demonstrates calling async `publish_interaction` from pure synchronous code and continuing work immediately without waiting for the server response.

**Key Features**:
- Background thread execution of async tasks
- Helper function `run_async_in_background()` for running async code from sync context
- Daemon threads that don't prevent program exit

**Usage Pattern**:
```python
# Publish interaction and continue immediately
publish_interaction_sync(request_id="req_1", user_id="user_1", content="Hello")
# Continue with other work without waiting
```

### snapshot_manager.py

Local Supabase snapshot manager — save and restore database data across `supabase db reset` cycles.

**Purpose**: Snapshots all public-schema table data so you can restore it after a `supabase db reset`, even if new migrations have been added since the snapshot. Automatically runs any new data migrations on restore.

**Subcommands**:
- `create`: Dump table data via `pg_dump` + record applied migration versions
- `restore`: Load data via `pg_restore` + run data migrations added since the snapshot
- `list`: Show available snapshots with metadata

**Usage**:

```bash
# Create a snapshot before resetting
python -m reflexio.scripts.snapshot_manager create --name before_reset

# Reset the DB (re-applies all schema migrations, empties tables)
supabase db reset

# Restore the snapshot (by name)
python -m reflexio.scripts.snapshot_manager restore before_reset_20260207_120000

# List available snapshots
python -m reflexio.scripts.snapshot_manager list
```

**Options**:
- `create --name NAME`: Name prefix for the snapshot directory (default: `snapshot`)
- `restore NAME`: Snapshot name to restore (e.g. `before_reset_20260207_120000`)
- `restore --force`: Skip the empty-tables safety check
- `--db-url URL`: Override the default local PostgreSQL URL

**Snapshot contents** (saved to `reflexio/data/snapshots/{name}_{timestamp}/`):
- `data.dump` — pg_dump custom-format file (public schema data only)
- `metadata.json` — snapshot name, timestamp, and list of applied migrations at snapshot time

### analyze_db_usage.py

Analyze database usage over the past N days. Shows daily averages and line plots for interactions, profiles, feedbacks, raw feedbacks, and requests.

**Usage**:

```bash
python reflexio/scripts/analyze_db_usage.py --db-url "postgresql://user:pass@host:port/dbname"

# Custom time window
python reflexio/scripts/analyze_db_usage.py --db-url "..." --days 7
```

**Output**:
- Summary table with daily averages and totals per table
- Line plot saved as `db_usage_report.png`

**Requirements**: `matplotlib`, `psycopg2`

### play.py

Playground script for testing and experimentation with Reflexio features.

## Directory Structure

```
scripts/
├── README.md                          # This file
├── count_tokens.py                    # Token counter utility
├── test_supabase_connection.py        # Supabase connection test
├── run_all_migrations.py              # Multi-org deployment migrations
├── add_config_script.py               # Config management
├── add_user_interactions_script.py    # Interaction management
├── add_user_profiles_script.py        # Profile management
├── async_publish_interaction_script.py # Async publishing example
├── simple_sync_publish.py             # Sync-to-async publishing example
├── snapshot_manager.py                 # Local Supabase snapshot & restore
├── analyze_db_usage.py                # DB usage analysis & charting
├── play.py                            # Testing playground
├── db_operations/                     # Database operation scripts
└── super_admin/                       # Super admin utilities
```
