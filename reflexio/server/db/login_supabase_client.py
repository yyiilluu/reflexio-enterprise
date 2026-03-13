"""
Supabase client for the login/authentication database.

This module provides a singleton Supabase client for accessing the cloud-hosted
login database, which stores organization credentials and API keys.
"""

import logging

from reflexio.server import LOGIN_SUPABASE_KEY, LOGIN_SUPABASE_URL
from supabase import Client, create_client

logger = logging.getLogger(__name__)

_login_supabase_client: Client | None = None


def get_login_supabase_client() -> Client | None:
    """
    Get the singleton Supabase client for the login database.

    Returns:
        Client: Supabase client if LOGIN_SUPABASE_URL and LOGIN_SUPABASE_KEY are configured,
                None otherwise (falls back to SQLite).
    """
    global _login_supabase_client

    if _login_supabase_client is None:
        if LOGIN_SUPABASE_URL and LOGIN_SUPABASE_KEY:
            try:
                _login_supabase_client = create_client(
                    LOGIN_SUPABASE_URL, LOGIN_SUPABASE_KEY
                )
                logger.info("Login Supabase client connected to %s", LOGIN_SUPABASE_URL)
            except Exception as e:
                logger.error("Failed to create login Supabase client: %s", e)
                return None
        else:
            logger.debug(
                "LOGIN_SUPABASE_URL or LOGIN_SUPABASE_KEY not configured, "
                "falling back to SQLite"
            )
            return None

    return _login_supabase_client


def is_using_login_supabase() -> bool:
    """
    Check if the login database is using cloud Supabase.

    Returns:
        bool: True if using cloud Supabase, False if using SQLite fallback.
    """
    return bool(LOGIN_SUPABASE_URL and LOGIN_SUPABASE_KEY)
