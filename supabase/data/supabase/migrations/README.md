# Supabase Database Migrations

This directory contains SQL migration files for the User Profiler database schema. Migrations are version-controlled and allow you to track and apply database changes systematically.

## Table of Contents

- [Understanding Local vs Remote](#understanding-local-vs-remote)
- [Quick Start](#quick-start)
- [Common Workflows](#common-workflows)
- [Command Reference](#command-reference)
- [Safety Guidelines](#safety-guidelines)
- [Troubleshooting](#troubleshooting)

---

## Understanding Local vs Remote

### LOCAL DB Commands
These commands **only affect your local development database** and never touch the cloud:

| Command | Effect |
|---------|--------|
| `supabase start` | Start local Supabase stack |
| `supabase stop` | Stop local Supabase stack |
| `supabase db reset` | Reset local DB to initial state and reapply migrations |
| `supabase db dump --local` | Dump local DB schema |
| `supabase migrate up --local` | Apply pending migrations locally |
| `supabase db diff --local` | Generate diff from local DB changes |

### REMOTE DB Commands
These commands **target your cloud database** and can modify production data:

| Command | Effect |
|---------|--------|
| `supabase link` | Link to cloud project |
| `supabase db push` | Apply migrations to cloud DB |
| `supabase db diff` | Generate diff against cloud DB |
| `supabase db commit` | Create migration based on cloud DB state |
| `supabase functions deploy` | Deploy edge functions to cloud |

### How to Check Link Status

```bash
# Check if linked to a cloud project
ls -la .supabase/

# The .supabase/ directory contains your cloud project reference
# If it doesn't exist, you're not linked to any cloud project
```

---

## Quick Start

### Initial Local Setup

```bash
# 1. Start local Supabase (PostgreSQL, PostgREST, Auth, etc.)
supabase start

# 2. Apply all migrations to local DB
supabase db reset

# 3. Access local Supabase Studio
# Open http://localhost:54323 in your browser
```

### Creating a New Migration

```bash
# Method 1: Create an empty migration file
supabase migration new <migration_name>

# Method 2: Generate migration from local DB changes
# (Make schema changes in Studio first, then run:)
supabase db diff --local -f <migration_name>

# Example:
supabase migration new add_user_preferences_table
```

### Applying Migrations

```bash
# Apply to local DB
supabase db reset

# Or apply specific migration
supabase migrate up --local
```

---

## Common Workflows

### 1. Local Development (Safe Mode)

This workflow ensures you never accidentally touch the cloud database:

```bash
# Ensure no cloud project is linked
supabase unlink

# Start local development
supabase start

# Make schema changes in Studio or via SQL files
# Generate migration from changes
supabase db diff --local -f my_new_feature

# Test migration
supabase db reset

# Commit migration file to git
git add supabase/migrations/*.sql
git commit -m "Add migration: my_new_feature"
```

### 2. Deploying to Cloud

When you're ready to deploy migrations to production:

```bash
# Link to your cloud project
supabase link --project-ref <your_project_ref>

# Push migrations to cloud
supabase db push

# Optional: Deploy edge functions
supabase functions deploy

# Return to local-only development (optional)
supabase unlink
```

### 3. Syncing from Cloud

If you need to pull schema changes from the cloud:

```bash
# Link to cloud project
supabase link --project-ref <your_project_ref>

# Generate migration from cloud DB differences
supabase db diff -f sync_from_cloud

# Review the generated migration file
# Apply to local DB
supabase db reset

# Unlink if desired
supabase unlink
```

---

## Command Reference

### Project Management

```bash
# Initialize Supabase in a project
supabase init

# Link to cloud project
supabase link --project-ref <project_ref>

# Unlink from cloud project
supabase unlink

# Check project status
supabase status
```

### Local Database

```bash
# Start local Supabase stack
supabase start

# Stop local Supabase stack
supabase stop

# Reset local DB (drops all data, reapplies migrations)
supabase db reset

# Dump local DB schema
supabase db dump --local -f schema.sql

# Dump local DB data
supabase db dump --local --data-only -f data.sql
```

### Migrations

```bash
# Create new migration file
supabase migration new <name>

# Apply pending migrations locally
supabase migrate up --local

# Generate migration from local schema changes
supabase db diff --local -f <migration_name>

# Generate migration from cloud schema differences
supabase db diff -f <migration_name>

# List migrations
supabase migration list

# Repair migration history (advanced)
supabase migration repair <version> --status applied
```

### Cloud Operations

```bash
# Push migrations to cloud
supabase db push

# Push specific migration
supabase db push --include-all

# Dry run (see what would be applied)
supabase db push --dry-run
```

---

## Safety Guidelines

### ⚠️ Critical Safety Rules

1. **Always use `--local` flag when experimenting**
   ```bash
   # Safe - local only
   supabase db diff --local -f test_feature

   # Dangerous - touches cloud!
   supabase db diff -f test_feature
   ```

2. **Verify link status before running commands**
   ```bash
   # Check if linked
   ls .supabase/

   # Unlink if you want local-only mode
   supabase unlink
   ```

3. **Use `--dry-run` before pushing to cloud**
   ```bash
   # Preview changes without applying
   supabase db push --dry-run
   ```

4. **Test migrations locally before deploying**
   ```bash
   # Always test locally first
   supabase db reset

   # Then deploy to cloud
   supabase link --project-ref <ref>
   supabase db push
   ```

5. **Never edit applied migration files**
   - Once a migration is applied (especially in production), never modify it
   - Create a new migration to make changes instead

### 🔒 Recommended Safe Workflow

For maximum safety during development:

```bash
# 1. Unlink from cloud (ensures local-only)
supabase unlink

# 2. Start local development
supabase start

# 3. Make changes and create migrations
supabase db diff --local -f my_changes

# 4. Test thoroughly
supabase db reset

# 5. When ready for production, link and deploy
supabase link --project-ref <ref>
supabase db push --dry-run  # Review first!
supabase db push            # Actually deploy

# 6. Unlink again (optional)
supabase unlink
```

---

## Troubleshooting

### Error: "Project not linked"

```bash
# Solution: Link to your cloud project
supabase link --project-ref <your_project_ref>
```

### Error: "Migration conflict detected"

```bash
# Check migration history
supabase migration list

# Repair migration status if needed
supabase migration repair <version> --status applied
```

### Local DB is out of sync

```bash
# Reset local DB and reapply all migrations
supabase db reset

# This will:
# 1. Drop all tables
# 2. Reapply all migration files in order
# 3. Run seed data (if configured)
```

### Want to start fresh locally

```bash
# Stop Supabase
supabase stop

# Remove local database
supabase db reset

# Or completely remove Supabase volumes
supabase stop --no-backup
```

### Accidentally ran command on cloud

```bash
# If migration was pushed to cloud by mistake:
# 1. DO NOT try to "undo" by modifying migration files
# 2. Create a new migration to revert changes
# 3. Example:
supabase migration new revert_accidental_change
# Edit the new migration file to reverse the changes
supabase db push
```

---

## Migration File Naming Convention

Migration files follow this pattern:
```
<timestamp>_<description>.sql
```

Example:
```
20251110010205_add_request_table.sql
```

- **Timestamp**: `YYYYMMDDHHmmss` format ensures proper ordering
- **Description**: Snake_case description of the change
- **Extension**: Always `.sql`

---

## Additional Resources

- [Supabase CLI Documentation](https://supabase.com/docs/guides/cli)
- [Supabase Local Development](https://supabase.com/docs/guides/local-development)
- [Migration Best Practices](https://supabase.com/docs/guides/database/migrations)

---

## Configuration

This project's Supabase configuration is stored in:
- **Config**: `supabase/config.toml`
- **Migrations**: `supabase/migrations/`
- **Seed data**: `supabase/seed.sql`

Local Supabase services run on:
- **API**: http://localhost:54321
- **Studio**: http://localhost:54323
- **Database**: postgresql://postgres:postgres@localhost:54322/postgres
