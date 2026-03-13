import logging
import os
import sys
from pathlib import Path

import colorlog
from dotenv import load_dotenv

from reflexio import data

# Load environment variables from .env file
load_dotenv()

# OpenAI related
OPENAI_API_KEY = os.environ.get(
    "OPENAI_API_KEY",
    "",
).strip()

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

# Local file related

LOCAL_STORAGE_PATH = os.environ.get(
    "LOCAL_STORAGE_PATH", str(Path(data.__file__).parent)
).strip() or str(Path(data.__file__).parent)

# Local SQLite database file related

SQLITE_FILE_DIRECTORY = os.environ.get(
    "SQLITE_FILE_DIRECTORY", str(Path(data.__file__).parent)
).strip() or str(Path(data.__file__).parent)

# Interaction cleanup configuration

INTERACTION_CLEANUP_THRESHOLD = int(
    os.environ.get("INTERACTION_CLEANUP_THRESHOLD", "250000")
)
INTERACTION_CLEANUP_DELETE_COUNT = int(
    os.environ.get("INTERACTION_CLEANUP_DELETE_COUNT", "50000")
)

# Logging

DEBUG_LOG_TO_CONSOLE = os.environ.get("DEBUG_LOG_TO_CONSOLE", "").strip().lower()
root_logger = logging.getLogger()

logging.addLevelName(25, "MODEL_RESPONSE")

if DEBUG_LOG_TO_CONSOLE and DEBUG_LOG_TO_CONSOLE not in ("false", "0", "no"):
    # Enable verbose logging to console with colored output
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(name)s - %(levelname)s - %(message)s",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "reset",
                "MODEL_RESPONSE": "cyan",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
else:
    # Default to WARNING level when DEBUG_LOG_TO_CONSOLE is not set or is false
    root_logger.setLevel(logging.WARNING)
