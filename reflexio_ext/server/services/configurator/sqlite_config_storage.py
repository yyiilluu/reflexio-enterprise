"""
SQLite/SQLAlchemy-based configuration storage adapter.

Stores/loads organization configuration via a local SQLite database
with Fernet encryption at rest. Extracted from the former RdsConfigStorage
as part of the Ports & Adapters refactoring.
"""

import json
import logging
import traceback

from reflexio.server.services.configurator.config_storage import ConfigStorage
from reflexio_commons.config_schema import Config

from reflexio_ext.server import FERNET_KEYS
from reflexio_ext.server.db.database import SessionLocal
from reflexio_ext.server.db.db_models import Organization
from reflexio_ext.utils.encrypt_manager import EncryptManager

logger = logging.getLogger(__name__)


class SqliteConfigStorage(ConfigStorage):
    """SQLite-backed configuration storage.

    Reads/writes encrypted configuration JSON from the ``organizations``
    table's ``configuration_json`` column via SQLAlchemy.

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
        """Load configuration from SQLite via SQLAlchemy.

        Queries the organizations table for the encrypted config JSON,
        decrypts it, and returns the parsed Config. Falls back to the
        default config on any error.

        Returns:
            Config: Loaded configuration object.
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
            except json.JSONDecodeError, TypeError, KeyError, ValueError:
                return self.get_default_config()

    def save_config(self, config: Config) -> None:
        """Save configuration to SQLite via SQLAlchemy.

        Serializes the config to JSON, encrypts it, and writes it to the
        organizations table.

        Args:
            config (Config): Configuration object to save.
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
