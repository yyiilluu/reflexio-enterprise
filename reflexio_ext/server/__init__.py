"""Enterprise server package — enterprise-specific environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()

# Login database (separate cloud Supabase for auth)
LOGIN_SUPABASE_URL = os.environ.get("LOGIN_SUPABASE_URL", "").strip()
LOGIN_SUPABASE_KEY = os.environ.get("LOGIN_SUPABASE_KEY", "").strip()

# Encryption related
# FERNET_KEYS is a comma separated key of fernet keys. Put the most recent key at the front.
FERNET_KEYS = os.environ.get(
    "FERNET_KEYS",
    "",
).strip()

# S3 Config Storage
CONFIG_S3_ACCESS_KEY = os.environ.get("CONFIG_S3_ACCESS_KEY", "").strip()
CONFIG_S3_SECRET_KEY = os.environ.get("CONFIG_S3_SECRET_KEY", "").strip()
CONFIG_S3_REGION = os.environ.get("CONFIG_S3_REGION", "").strip()
CONFIG_S3_PATH = os.environ.get("CONFIG_S3_PATH", "").strip()
