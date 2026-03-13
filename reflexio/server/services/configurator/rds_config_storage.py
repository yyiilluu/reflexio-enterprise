import json
import logging
import traceback

from reflexio_commons.config_schema import (
    Config,
)

from reflexio.server import FERNET_KEYS
from reflexio.server.db.database import SessionLocal
from reflexio.server.db.db_models import Organization
from reflexio.server.db.login_supabase_client import get_login_supabase_client
from reflexio.server.services.configurator.config_storage import ConfigStorage
from reflexio.server.services.storage.supabase_storage_utils import (
    get_organization_config,
    set_organization_config,
)
from reflexio.utils.encrypt_manager import EncryptManager

logger = logging.getLogger(__name__)


class RdsConfigStorage(ConfigStorage):
    """
    Supabase database-based configuration storage implementation.
    Saves/loads configuration to/from Supabase database with encryption.
    Supports both SQLAlchemy SessionLocal and Supabase Python client.
    """

    def __init__(self, org_id: str):
        super().__init__(org_id)
        # Load fernet key from environment and set up the encryption manager.
        self.encrypt_manager: EncryptManager = EncryptManager(fernet_keys=FERNET_KEYS)

    def get_default_config(self) -> Config:
        """
        Returns a default configuration for Supabase storage.
        Uses LOGIN_SUPABASE_URL and LOGIN_SUPABASE_KEY from environment as defaults.

        Returns:
            Config: Default configuration with Supabase storage type
        """
        return Config(storage_config=None)

    def load_config(self) -> Config:
        """
        Loads the current configuration from Supabase database. If the organization does
        not exist, or if no config exists, or if the current saved config is no longer valid,
        this routine creates a default one but will not update the persistent storage.

        Returns:
            Config: Loaded configuration object
        """
        # Use Supabase client if SessionLocal is None
        if SessionLocal is None:
            return self._load_config_supabase()
        return self._load_config_session()

    def _load_config_supabase(self) -> Config:
        """
        Load config using Supabase Python client.

        Returns:
            Config: Loaded configuration object
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

    def _load_config_session(self) -> Config:
        """
        Load config using SQLAlchemy SessionLocal.

        Returns:
            Config: Loaded configuration object
        """
        with SessionLocal() as session:
            try:
                org: Organization = (
                    session.query(Organization)
                    .filter(Organization.id == self.org_id)
                    .first()
                )
                if not org:
                    return self.get_default_config()

                config_raw_encrypted = org.configuration_json
                config_raw_decrypted = None
                if config_raw_encrypted is not None:
                    config_raw_decrypted = self.encrypt_manager.decrypt(
                        encrypted_value=str(config_raw_encrypted)
                    )
                return Config(**json.loads(str(config_raw_decrypted)))
            except Exception:
                return self.get_default_config()

    def save_config(self, config: Config) -> None:
        """
        Saves the configuration to the Supabase database.

        Args:
            config (Config): Configuration object to save
        """
        # Use Supabase client if SessionLocal is None
        if SessionLocal is None:
            self._save_config_supabase(config)
        else:
            self._save_config_session(config)

    def _save_config_supabase(self, config: Config) -> None:
        """
        Save config using Supabase Python client.

        Args:
            config (Config): Configuration object to save
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

    def _save_config_session(self, config: Config) -> None:
        """
        Save config using SQLAlchemy SessionLocal.

        Args:
            config (Config): Configuration object to save
        """
        with SessionLocal() as session:
            try:
                org: Organization = (
                    session.query(Organization)
                    .filter(Organization.id == self.org_id)
                    .first()
                )
                if not org:
                    logger.error("Org %s cannot be found!", self.org_id)
                    return

                config_raw_decrypted: str = config.model_dump_json()
                config_raw_encrypted = self.encrypt_manager.encrypt(
                    value=config_raw_decrypted
                )
                if not config_raw_encrypted:
                    return

                org.configuration_json = config_raw_encrypted  # type: ignore[reportAttributeAccessIssue]
                session.commit()
            except Exception as e:
                logger.error("%s", e)
                tbs = traceback.format_exc().split("\n")
                for tb in tbs:
                    logger.error("  %s", tb)
