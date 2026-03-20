# Supabase Migration Guide

Guide for running database migrations on local and remote Supabase instances.

## Overview

Reflexio uses **two separate Supabase databases**:

| Database | Directory | Purpose | Default Location |
|----------|-----------|---------|------------------|
| **Main** | `supabase/data/` | User profiles, interactions, feedbacks, embeddings | Local (`127.0.0.1:54322`) |
| **Login** | `supabase/auth/` | Organizations, login credentials, API keys, invitation codes | Cloud (`*.supabase.co`) or Local |

When schema changes are needed (new tables, columns, functions, etc.), migration files are created in the respective `migrations/` directory and applied to the target database.

## Supabase CLI

The [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) is the official tool for managing database migrations.

### Installing Supabase CLI

```bash
# macOS
brew install supabase/tap/supabase

# npm (requires Node.js 20+)
npm install -g supabase

# Or run via npx
npx supabase <command>
```

### Initial Setup

```bash
# Login to Supabase
supabase login

# Link to your remote project
supabase link --project-ref your-project-ref

# Pull existing schema from remote (first time only)
supabase db pull
```

### Creating Migrations

```bash
# Create a new empty migration file
supabase migration new add_user_preferences

# This creates: supabase/migrations/YYYYMMDDHHmmss_add_user_preferences.sql
```

### Applying Migrations to Remote

```bash
# Preview changes (dry run)
supabase db push --dry-run

# Push migrations to remote database
supabase db push
```

### Generating Migrations from Schema Changes

If you made changes directly in the Supabase dashboard or SQL editor:

```bash
# Generate migration from remote schema diff
supabase db diff --schema public -f my_changes

# Or pull all remote changes as a migration
supabase db pull
```

### Key CLI Commands

| Command | Description |
|---------|-------------|
| `supabase migration new <name>` | Create new migration file |
| `supabase db push` | Push local migrations to remote |
| `supabase db push --dry-run` | Preview migrations without applying |
| `supabase db pull` | Pull remote schema changes as migration |
| `supabase db diff --schema public` | Show schema differences |
| `supabase db reset` | Reset local database and reapply migrations |
| `supabase migration repair <version> --status=applied` | Fix migration history |
| `supabase migration squash` | Combine multiple migrations into one |

### CLI Workflow Example

```bash
# 1. Create a new migration
supabase migration new add_analytics_table

# 2. Edit the migration file
# supabase/migrations/20251206120000_add_analytics_table.sql

# 3. Test locally (if using local Supabase)
supabase db reset

# 4. Preview changes on remote
supabase db push --dry-run

# 5. Apply to remote
supabase db push
```

---

## Applying Login Migrations to Local Supabase

The `supabase/auth/` migrations are normally applied to a cloud Supabase project. To apply them to your **local** Supabase instance (e.g., for local development), run the SQL files directly via `psql`:

```bash
# Local Supabase DB: postgresql://postgres:postgres@127.0.0.1:54322/postgres

# Apply all login migrations in order
psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" \
  -f supabase/auth/migrations/20251206000001_create_organizations.sql

psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" \
  -f supabase/auth/migrations/20251228052539_add_verify_and_count_col.sql

psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" \
  -f supabase/auth/migrations/20260118120000_add_is_self_managed_col.sql

psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" \
  -f supabase/auth/migrations/20260211000001_create_invitation_codes.sql
```

These migrations use `IF NOT EXISTS` / `ADD COLUMN` patterns, so they are safe to re-run.

**Note**: These are applied directly via `psql` rather than `supabase migration up` because `supabase/auth/` is a separate Supabase project with its own `config.toml`. The `supabase migration up` command only processes migrations in the `supabase/data/` directory linked to the local instance.

---

## Migration Files

Migration files are stored in `supabase/migrations/` with the naming convention:

```
YYYYMMDDHHMMSS_description.sql
```

Example:
```
20251113205946_init.sql.sql
20251113220000_exclude_archived_feedbacks.sql
20251120062400_add_user_col_to_interaction_table.sql
```

### Creating a New Migration

1. Create a new SQL file in `supabase/migrations/`:
   ```bash
   # Use timestamp format: YYYYMMDDHHMMSS
   touch supabase/migrations/$(date +%Y%m%d%H%M%S)_your_migration_name.sql
   ```

2. Add your SQL statements to the file:
   ```sql
   -- Example: Add a new column
   ALTER TABLE interactions ADD COLUMN IF NOT EXISTS new_column TEXT;

   -- Example: Create a new function
   CREATE OR REPLACE FUNCTION my_function()
   RETURNS void AS $$
   BEGIN
       -- function body
   END;
   $$ LANGUAGE plpgsql;
   ```

3. Run the migration:
   ```bash
   supabase db push
   ```

## Best Practices

1. **Always backup before migrating production**
   ```bash
   # Export via Supabase dashboard or pg_dump
   pg_dump "postgres://user:pass@host:port/db" > backup_$(date +%Y%m%d).sql
   ```

2. **Test migrations locally first**
   - Use a local Supabase instance or development project
   - Verify the migration works before applying to production

3. **Use IF NOT EXISTS / IF EXISTS**
   - Makes migrations idempotent (safe to run multiple times)
   ```sql
   CREATE TABLE IF NOT EXISTS my_table (...);
   ALTER TABLE my_table ADD COLUMN IF NOT EXISTS new_col TEXT;
   DROP TABLE IF EXISTS old_table;
   ```

4. **Keep migrations small and focused**
   - One logical change per migration file
   - Easier to debug and rollback if needed

## Troubleshooting

### Connection Refused

```
Error: connection refused
```

**Fix**: Check your database connection URL:
- Ensure you're using the correct pooler URL
- Verify the password doesn't contain special characters that need URL encoding
- Check if your IP is allowed in Supabase network restrictions

### Permission Denied

```
Error: permission denied for table/function
```

**Fix**: Ensure you're using the **service_role** key, not the anon key.

### Migration Already Applied

The migration system tracks applied migrations. If a migration was already applied, it will be skipped. This is normal behavior.

### SSL Certificate Error

```
Error: SSL certificate verify failed
```

**Fix**: Add `?sslmode=require` to your database URL:
```
postgres://user:pass@host:port/db?sslmode=require
```

## Quick Reference

```bash
# Install CLI
brew install supabase/tap/supabase

# Login and link project
supabase login
supabase link --project-ref your-project-ref

# Create and push migration
supabase migration new my_change
supabase db push --dry-run  # preview
supabase db push            # apply

# Pull remote changes
supabase db pull

# Reset remote supabase
supabase db reset --linked
```

---

## Resources

- [Supabase CLI Documentation](https://supabase.com/docs/reference/cli/introduction)
- [Database Migrations Guide](https://supabase.com/docs/guides/deployment/database-migrations)
- [Local Development with Supabase](https://supabase.com/docs/guides/local-development/overview)
