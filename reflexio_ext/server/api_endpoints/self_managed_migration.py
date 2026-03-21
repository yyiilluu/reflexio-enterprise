"""
Background migration task for self-managed organizations.

Self-managed orgs (is_self_managed=True) are skipped by the deployment migration
script (run_all_migrations.py), so their databases need migration checks at login time.
This module provides a non-blocking background task to check and apply migrations.
"""

import logging
import threading

import cachetools

logger = logging.getLogger(__name__)

# TTL cache to throttle migration checks: skip orgs checked within the last 10 minutes.
# Thread-safe via explicit lock.
_check_cache: cachetools.TTLCache = cachetools.TTLCache(maxsize=256, ttl=600)
_cache_lock = threading.Lock()


def check_and_migrate_self_managed_org(org_id: str) -> None:
    """
    Background task entry point: check if a self-managed org's storage needs migration
    and apply it if necessary. Uses the storage interface (BaseStorage) via RequestContext
    so it works with any storage backend, not just Supabase.

    Args:
        org_id: Organization ID
    """
    # 1. Throttle check — skip if recently checked
    with _cache_lock:
        if org_id in _check_cache:
            logger.debug(
                "Self-managed migration: org %s recently checked, skipping",
                org_id,
            )
            return
        # Mark as checked early to avoid parallel runs
        _check_cache[org_id] = True

    try:
        # 2. Create RequestContext to get the org's storage via the standard config path
        from reflexio.server.api_endpoints.request_context import RequestContext

        request_context = RequestContext(org_id=org_id)
        storage = request_context.storage

        if storage is None:
            logger.debug(
                "Self-managed migration: org %s has no storage configured",
                org_id,
            )
            return

        # 3. Quick check if migration is needed
        if not storage.check_migration_needed():
            logger.debug("Self-managed migration: org %s is up-to-date", org_id)
            return

        # 4. Execute migration via storage interface
        logger.info(
            "Self-managed migration: org %s needs migration, executing...",
            org_id,
        )
        success = storage.migrate()

        if success:
            logger.info("Self-managed migration: org %s migration succeeded", org_id)
        else:
            logger.error("Self-managed migration: org %s migration failed", org_id)
            # Clear cache on failure so next login retries
            with _cache_lock:
                _check_cache.pop(org_id, None)

    except Exception as e:
        logger.exception("Self-managed migration: org %s error: %s", org_id, e)
        # Clear cache on failure so next login retries
        with _cache_lock:
            _check_cache.pop(org_id, None)
