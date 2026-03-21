#!/bin/bash
# =============================================================================
# Local Database Reset Script
# Resets local Supabase and applies migrations from both projects
# =============================================================================
#
# Usage:
#   ./local_db_reset.sh              # Full reset with all migrations
#   ./local_db_reset.sh --login-only # Only apply auth migrations
#   ./local_db_reset.sh --help       # Show help
#
# Prerequisites:
#   - Supabase CLI installed
#   - psql installed
#   - Run from project root (user_profiler/)
# =============================================================================

set -e

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Database connection
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-54322}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"
DB_NAME="${DB_NAME:-postgres}"
DB_URL="postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"

# Directories
MAIN_SUPABASE_DIR="$PROJECT_ROOT/supabase/data"
LOGIN_SUPABASE_DIR="$PROJECT_ROOT/supabase/auth"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Reset local Supabase database and apply migrations from both projects."
    echo ""
    echo "Options:"
    echo "  --login-only    Only apply auth migrations (skip full reset)"
    echo "  --help          Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  DB_HOST         Database host (default: localhost)"
    echo "  DB_PORT         Database port (default: 54322)"
    echo "  DB_USER         Database user (default: postgres)"
    echo "  DB_PASSWORD     Database password (default: postgres)"
}

apply_login_migrations() {
    print_info "Applying auth migrations..."

    if [ ! -d "$LOGIN_SUPABASE_DIR/migrations" ]; then
        print_error "Login migrations directory not found: $LOGIN_SUPABASE_DIR/migrations"
        exit 1
    fi

    for migration_file in "$LOGIN_SUPABASE_DIR/migrations"/*.sql; do
        if [ -f "$migration_file" ]; then
            filename=$(basename "$migration_file")
            print_info "  Applying: $filename"
            psql "$DB_URL" -f "$migration_file" -q
        fi
    done

    print_info "Login migrations applied successfully"
}

full_reset() {
    print_info "Starting full database reset..."

    # Change to project root for supabase commands
    cd "$PROJECT_ROOT"

    # Check if supabase is running
    if ! supabase status --workdir supabase/data &>/dev/null; then
        print_warn "Supabase is not running. Starting supabase..."
        supabase start --workdir supabase/data
    fi

    # Reset main supabase (applies supabase/data/ migrations)
    print_info "Resetting main supabase database..."
    supabase db reset --workdir supabase/data --debug 2>&1 | grep -v "^DEBUG" || true

    # Apply login migrations
    apply_login_migrations

    print_info "Database reset complete!"
}

# Parse arguments
LOGIN_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --login-only)
            LOGIN_ONLY=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Main execution
if [ "$LOGIN_ONLY" = true ]; then
    apply_login_migrations
else
    full_reset
fi
