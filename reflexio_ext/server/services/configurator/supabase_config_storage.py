"""
Supabase-based configuration storage adapter.

Stores/loads organization configuration via the Supabase PostgREST API
with Fernet encryption at rest. Extracted from the former RdsConfigStorage
as part of the Ports & Adapters refactoring.
"""

import json
import logging
import traceback

from reflexio.server.services.configurator.config_storage import ConfigStorage
from reflexio_commons.config_schema import Config

from reflexio_ext.server import FERNET_KEYS
from reflexio_ext.server.db.login_supabase_client import get_login_supabase_client
from reflexio_ext.server.services.storage.supabase_storage_utils import (
    get_organization_config,
    set_organization_config,
)
from reflexio_ext.utils.encrypt_manager import EncryptManager

logger = logging.getLogger(__name__)


class SupabaseConfigStorage(ConfigStorage):
    """Supabase-backed configuration storage.

    Reads/writes encrypted configuration JSON from the ``organizations``
    table's ``configuration_json`` column via the Supabase Python client.

    Args:
        org_id (str): Organization identifier.
    """

    def __init__(self, org_id: str) -> None:
        super().__init__(org_id)
        self.encrypt_manager: EncryptManager = EncryptManager(fernet_keys=FERNET_KEYS)

    def get_default_config(self) -> Config:
        """Return a default uninitialized configuration.

        Returns:
            Config: Default configuration with no storage config set.
        """
        return Config(storage_config=None)

    def load_config(self) -> Config:
        """Load configuration from Supabase.

        Fetches the encrypted config JSON from the organizations table,
        decrypts it, and returns the parsed Config. Falls back to the
        default config on any error.

        Returns:
            Config: Loaded configuration object.
        """
        try:
            client = get_login_supabase_client()
            if not client:
                logger.warning(
                    "Login Supabase client not available, using default config"
                )
                return self.get_default_config()

            config_raw_encrypted = get_organization_config(client, self.org_id)
            if config_raw_encrypted is None:
                logger.warning(
                    "Organization %s not found or has no config", self.org_id
                )
                return self.get_default_config()

            config_raw_decrypted = self.encrypt_manager.decrypt(
                encrypted_value=str(config_raw_encrypted)
            )
            return Config(**json.loads(str(config_raw_decrypted)))
        except Exception as e:
            logger.error("Error loading config via Supabase: %s", e)
            return self.get_default_config()

    def save_config(self, config: Config) -> None:
        """Save configuration to Supabase.

        Serializes the config to JSON, encrypts it, and writes it to the
        organizations table via the Supabase client.

        Args:
            config (Config): Configuration object to save.
        """
        try:
            client = get_login_supabase_client()
            if not client:
                logger.error("Login Supabase client not available, cannot save config")
                return

            config_raw_decrypted: str = config.model_dump_json()
            config_raw_encrypted = self.encrypt_manager.encrypt(
                value=config_raw_decrypted
            )
            if not config_raw_encrypted:
                logger.error("Failed to encrypt config")
                return

            success = set_organization_config(client, self.org_id, config_raw_encrypted)
            if not success:
                logger.error("Org %s cannot be found!", self.org_id)
                return

            logger.info("Config saved successfully for org %s", self.org_id)
        except Exception as e:
            logger.error("Error saving config via Supabase: %s", e)
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                logger.error("  %s", tb)
