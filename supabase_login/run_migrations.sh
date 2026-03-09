#!/bin/bash
# Run all supabase_login migrations against local Supabase via psql.
# Uses psql directly instead of supabase CLI to avoid conflicts with
# the main project's supabase instance on the same localhost.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATIONS_DIR="$SCRIPT_DIR/supabase/migrations"

# Local Supabase default connection (port 54322, password from supabase start)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-54322}"
DB_NAME="${DB_NAME:-postgres}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"

export PGPASSWORD="$DB_PASSWORD"

echo "Applying supabase_login migrations to $DB_HOST:$DB_PORT/$DB_NAME"

# Apply each migration file in sorted order
applied=0
for migration in $(ls "$MIGRATIONS_DIR"/*.sql 2>/dev/null | sort); do
    version=$(basename "$migration")
    echo "  APPLY $version"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$migration" -q
    applied=$((applied + 1))
done

echo "Done. Applied: $applied"
