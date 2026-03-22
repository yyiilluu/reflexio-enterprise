import hashlib
import logging
import os
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from reflexio.server.services.configurator.local_json_config_storage import (
    LocalJsonConfigStorage,
)
from reflexio.server.services.storage.error import StorageError
from reflexio.server.services.storage.local_json_storage import LocalJsonStorage
from reflexio.server.services.storage.storage_base import BaseStorage
from reflexio_commons.config_schema import (
    Config,
    StorageConfig,
    StorageConfigLocal,
    StorageConfigSupabase,
    StorageConfigTest,
)

from reflexio_ext.server import (
    CONFIG_S3_ACCESS_KEY,
    CONFIG_S3_PATH,
    CONFIG_S3_REGION,
    CONFIG_S3_SECRET_KEY,
)
from reflexio_ext.server.db.database import SessionLocal
from reflexio_ext.server.services.configurator.s3_config_storage import S3ConfigStorage
from reflexio_ext.server.services.configurator.sqlite_config_storage import (
    SqliteConfigStorage,
)
from reflexio_ext.server.services.configurator.supabase_config_storage import (
    SupabaseConfigStorage,
)
from reflexio_ext.server.services.storage.supabase_storage import SupabaseStorage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Storage factory functions — one per StorageConfig type
# ---------------------------------------------------------------------------


def _create_local_json_storage(
    configurator: SimpleConfigurator, config: StorageConfigLocal
) -> BaseStorage:
    logger.info("Using local storage for org %s", configurator.org_id)
    return LocalJsonStorage(
        org_id=configurator.org_id,
        base_dir=configurator.base_dir,
        config=config,
    )


def _create_supabase_storage(
    configurator: SimpleConfigurator, config: StorageConfigSupabase
) -> BaseStorage:
    logger.info("Using Supabase storage for org %s", configurator.org_id)
    full_config = configurator.get_config()
    api_key_config = full_config.api_key_config if full_config else None
    llm_config = full_config.llm_config if full_config else None
    return SupabaseStorage(
        org_id=configurator.org_id,
        config=config,
        api_key_config=api_key_config,
        llm_config=llm_config,
    )


# Check if in self-host mode
SELF_HOST_MODE = os.getenv("SELF_HOST", "false").lower() == "true"


def is_s3_config_storage_ready() -> bool:
    """
    Check if all required S3 config storage parameters are set.

    Returns:
        bool: True if all CONFIG_S3_* env vars are set, False otherwise
    """
    return all(
        [CONFIG_S3_PATH, CONFIG_S3_REGION, CONFIG_S3_ACCESS_KEY, CONFIG_S3_SECRET_KEY]
    )


class SimpleConfigurator:
    def __init__(
        self, org_id: str, base_dir: str | None = None, config: Config | None = None
    ) -> None:
        self.org_id = org_id
        self.base_dir = base_dir

        if not config:
            # Choose the appropriate config storage based on priority:
            # 1. Local (if base_dir is explicitly provided - used for testing)
            # 2. S3 (if all CONFIG_S3_* env vars are set, required in self-host mode)
            # 3. Supabase (if SessionLocal is None - cloud mode)
            # 4. SQLite (local fallback)
            if base_dir:
                self.config_storage = LocalJsonConfigStorage(
                    org_id=org_id, base_dir=base_dir
                )
            elif is_s3_config_storage_ready():
                self.config_storage = S3ConfigStorage(org_id=org_id)
            elif SELF_HOST_MODE:
                # Self-host mode requires S3 config storage
                raise ValueError(
                    "SELF_HOST=true requires S3 config storage. "
                    "Set CONFIG_S3_PATH, CONFIG_S3_REGION, CONFIG_S3_ACCESS_KEY, CONFIG_S3_SECRET_KEY"
                )
            elif SessionLocal is None:
                # Cloud Supabase mode (no local database)
                self.config_storage = SupabaseConfigStorage(org_id=org_id)
            else:
                # Local SQLite fallback
                self.config_storage = SqliteConfigStorage(org_id=org_id)

            self.config = self.config_storage.load_config()
        else:
            self.config = config
        # This should not happen, raise an error for better debugging
        if not self.config:
            raise ValueError(f"Failed to load configuration for organization {org_id}")

    # ==============================
    # Configuration
    # ==============================

    def get_config(self) -> Config:
        return self.config

    def get_agent_context(self) -> str:
        context = self.get_config().agent_context_prompt
        if not context:
            return ""
        return context.strip()

    def set_config(self, config: Config) -> None:
        self.config = config
        self.config_storage.save_config(config=config)

    def set_config_by_name(
        self,
        config_name: str,
        config_value: str | int | float | bool | list | dict | BaseModel,
    ) -> None:
        if config_name not in self.config.model_fields:
            raise ValueError(f"Invalid config name: {config_name}")

        setattr(self.config, config_name, config_value)
        self.set_config(config=self.config)

    def delete_config_by_name(self, config_name: str) -> None:
        """
        Delete a config
        Args:
            config_name (str): name of the config to delete
        """
        if not hasattr(Config, config_name):
            raise ValueError(f"Invalid config name: {config_name}")
        # Get the default value from the field's annotation
        default_value = self.config.model_fields[config_name].default
        setattr(self.config, config_name, default_value)
        self.set_config(config=self.config)

    def delete_all_configs(self) -> None:
        """
        Delete all configs
        """
        self.config = self.config_storage.get_default_config()
        self.set_config(config=self.config)

    # ==============================
    # Storage
    # ==============================

    def get_current_storage_configuration(self) -> StorageConfig:
        """
        This routine returns the currently configured storage config.
        """
        return self.get_config().storage_config

    def get_storage_configuration_hash(
        self, storage_config: StorageConfig | None = None
    ) -> str:
        """
        This routine returns a hash of the storage configuration that uniquely identifies it.
        """
        if not storage_config:
            storage_config = self.get_current_storage_configuration()
        encoded_data = storage_config.model_dump_json().encode("utf-8")  # type: ignore[reportOptionalMemberAccess]
        md5_hasher = hashlib.md5(usedforsecurity=False)  # noqa: S324
        md5_hasher.update(encoded_data)
        return md5_hasher.hexdigest()

    # Registry: StorageConfig type → factory(configurator, config) → BaseStorage
    _STORAGE_FACTORIES: dict[type[StorageConfig], Callable[..., BaseStorage]] = {
        StorageConfigLocal: _create_local_json_storage,
        StorageConfigSupabase: _create_supabase_storage,
    }

    def create_storage(self, storage_config: StorageConfig) -> BaseStorage | None:
        """Create a storage based on the given storage config type.

        Uses the ``_STORAGE_FACTORIES`` registry to dispatch to the correct
        factory function. New backends can be added by registering entries
        in the dict without modifying this method.
        """
        if storage_config is None:
            return None
        factory = self._STORAGE_FACTORIES.get(type(storage_config))
        if factory is None:
            raise ValueError(
                f"No storage factory registered for {type(storage_config).__name__}"
            )
        return factory(self, storage_config)

    def is_storage_configured(self) -> bool:
        """
        Checks whether the configuration has a valid storage option configured
        """
        if not self.is_storage_config_ready_to_test(
            storage_config=self.get_current_storage_configuration(),
        ):
            return False
        return self.get_config().storage_config_test != StorageConfigTest.FAILED

    _STORAGE_READINESS_CHECKS: dict[type[StorageConfig], Callable[[Any], bool]] = {
        StorageConfigLocal: lambda c: bool(c.dir_path),
        StorageConfigSupabase: lambda c: bool(c.key and c.url and c.db_url),
    }

    def is_storage_config_ready_to_test(self, storage_config: StorageConfig) -> bool:
        """
        Checks whether the given storage configuration has been fully filled in and ready for test connection
        """
        check = self._STORAGE_READINESS_CHECKS.get(type(storage_config))
        return check(storage_config) if check else False

    def test_and_init_storage_config(
        self, storage_config: StorageConfig
    ) -> tuple[bool, str]:
        """
        This routine attempts to test whether the given storage configuration is valid and set up the storage to
        an init state (if not already initialized) so that it can be used by other services.

        Returns:
            tuple[bool, str]: (success, message)
        """
        if not self.is_storage_config_ready_to_test(storage_config=storage_config):
            return False, "Storage configuration is not ready to test"

        try:
            # Note that each storage controller will ensure that the corresponding storage configuration
            # is valid and the storage is properly initialized. Otherwise they will throw.
            storage = self.create_storage(storage_config=storage_config)

            # Migrate the storage to the latest version.
            if storage is not None:
                storage.migrate()
                return True, "Storage initialized successfully"
            return False, "Failed to create storage"
        except StorageError as e:
            logger.error("Storage initialization failed: %s", e.message)
            return False, e.message
        except Exception as e:
            logger.error("Storage initialization failed: %s", e)
            return False, str(e)
