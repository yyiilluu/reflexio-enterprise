"""
Database connection configuration for the login/authentication database.

Supports three modes (in priority order):
1. SELF_HOST_MODE with S3 - S3-based organization storage (no local database)
2. LOGIN_SUPABASE_URL + LOGIN_SUPABASE_KEY - Cloud Supabase via Python client
3. Fallback - Local SQLite file

Note: The local Supabase (SUPABASE_URL) is separate and used for user profile/memory data.
"""

import os
from pathlib import Path

from reflexio.server import SQLITE_FILE_DIRECTORY
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from reflexio_ext.server import (
    CONFIG_S3_ACCESS_KEY,
    CONFIG_S3_PATH,
    CONFIG_S3_REGION,
    CONFIG_S3_SECRET_KEY,
    LOGIN_SUPABASE_KEY,
    LOGIN_SUPABASE_URL,
)

# Check if in self-host mode
SELF_HOST_MODE = os.getenv("SELF_HOST", "false").lower() == "true"

# SQLite database filename for local development
sqlite_local_db_filename = "sql_app.db"


def _is_s3_config_ready() -> bool:
    """Check if all S3 config vars are set."""
    return all(
        [CONFIG_S3_PATH, CONFIG_S3_REGION, CONFIG_S3_ACCESS_KEY, CONFIG_S3_SECRET_KEY]
    )


# Connection priority:
# 1. SELF_HOST_MODE with S3 → S3 storage (operations use S3OrganizationStorage)
# 2. LOGIN_SUPABASE_URL + KEY → Cloud Supabase (operations use Supabase client)
# 3. Fallback → Local SQLite file

if SELF_HOST_MODE:
    if _is_s3_config_ready():
        print("Self-host mode enabled with S3 organization storage")
        # S3 mode - no local database needed
        SQLALCHEMY_DATABASE_URL = None
        engine = None
        SessionLocal = None
        Base = declarative_base()
    else:
        raise ValueError(
            "SELF_HOST=true requires S3 configuration. "
            "Set CONFIG_S3_PATH, CONFIG_S3_REGION, CONFIG_S3_ACCESS_KEY, CONFIG_S3_SECRET_KEY"
        )
elif LOGIN_SUPABASE_URL and LOGIN_SUPABASE_KEY:
    print(f"Using cloud Supabase for login: {LOGIN_SUPABASE_URL}")
    # When using Supabase client, SessionLocal should be None
    # All operations should use Supabase Python client directly
    SQLALCHEMY_DATABASE_URL = None
    engine = None
    SessionLocal = None
    Base = declarative_base()
else:
    print("Using local SQLite database for login")
    # Make sure the directory exists
    Path(SQLITE_FILE_DIRECTORY).mkdir(parents=True, exist_ok=True)
    SQLALCHEMY_DATABASE_URL = (
        f"sqlite:///{SQLITE_FILE_DIRECTORY}/{sqlite_local_db_filename}"
    )
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()


def ensure_sqlite_tables() -> None:
    """Create all tables in local SQLite if using SQLite fallback.

    Call this after all models have been imported to ensure tables exist.
    Safe to call multiple times (uses CREATE TABLE IF NOT EXISTS).
    """
    if engine is not None:
        Base.metadata.create_all(bind=engine)
