import json
import traceback

from reflexio.server.services.configurator.config_storage import ConfigStorage
from reflexio_commons.config_schema import Config

from reflexio_ext.server import (
    CONFIG_S3_ACCESS_KEY,
    CONFIG_S3_PATH,
    CONFIG_S3_REGION,
    CONFIG_S3_SECRET_KEY,
    FERNET_KEYS,
)
from reflexio_ext.utils.encrypt_manager import EncryptManager
from reflexio_ext.utils.s3_utils import S3Utils


class S3ConfigStorage(ConfigStorage):
    """
    S3-based configuration storage implementation.
    Saves/loads configuration to/from S3 with optional encryption.
    """

    def __init__(
        self,
        org_id: str,
        s3_path: str | None = None,
        s3_region: str | None = None,
        s3_access_key: str | None = None,
        s3_secret_key: str | None = None,
    ):
        """
        Initialize S3 configuration storage.

        Args:
            org_id (str): Organization ID
            s3_path (Optional[str]): S3 bucket path, falls back to CONFIG_S3_PATH env var
            s3_region (Optional[str]): AWS region, falls back to CONFIG_S3_REGION env var
            s3_access_key (Optional[str]): AWS access key, falls back to CONFIG_S3_ACCESS_KEY env var
            s3_secret_key (Optional[str]): AWS secret key, falls back to CONFIG_S3_SECRET_KEY env var
        """
        super().__init__(org_id=org_id)

        # Use provided params or fall back to env vars
        self.s3_path = s3_path or CONFIG_S3_PATH
        self.s3_region = s3_region or CONFIG_S3_REGION
        self.s3_access_key = s3_access_key or CONFIG_S3_ACCESS_KEY
        self.s3_secret_key = s3_secret_key or CONFIG_S3_SECRET_KEY

        # Config file key in S3
        self.config_file_key = f"configs/config_{org_id}.json"

        # Initialize S3 utils
        self.s3_utils = S3Utils(
            s3_path=self.s3_path,
            aws_region=self.s3_region,
            aws_access_key=self.s3_access_key,
            aws_secret_key=self.s3_secret_key,
        )

        print(
            f"S3ConfigStorage will save config for {org_id} to S3 at {self.s3_path}/{self.config_file_key}"
        )

        # Load fernet key from environment and set up the encryption manager.
        self.encrypt_manager: EncryptManager | None = None
        if FERNET_KEYS:
            self.encrypt_manager = EncryptManager(fernet_keys=FERNET_KEYS)

    def get_default_config(self) -> Config:
        """
        Returns a default configuration that is uninitialized for S3 storage.

        Returns:
            Config: Default configuration with no storage config set
        """
        return Config(storage_config=None)

    def load_config(self) -> Config:
        """
        Loads the current configuration from S3. If the file doesn't exist,
        returns a default configuration.

        Returns:
            Config: Loaded configuration object
        """
        try:
            # Check if file exists
            if not self.s3_utils.file_exists(self.config_file_key):
                return self.get_default_config()

            # Read raw content from S3 (we need to handle encryption ourselves)
            response = self.s3_utils.s3_client.get_object(
                Bucket=self.s3_path, Key=self.config_file_key
            )
            config_raw = response["Body"].read().decode("utf-8")

            if not config_raw:
                return self.get_default_config()

            # Decrypt if encryption is enabled
            if self.encrypt_manager:
                config_content = self.encrypt_manager.decrypt(
                    encrypted_value=config_raw
                )
            else:
                config_content = config_raw

            config: Config = Config(**json.loads(str(config_content)))
            return config

        except Exception as e:
            print(f"Error loading config from S3: {str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                print(f"  {tb}")
            # Return default config if anything goes wrong
            return self.get_default_config()

    def save_config(self, config: Config) -> None:
        """
        Saves the configuration to S3.

        Args:
            config (Config): Configuration object to save
        """
        try:
            config_raw: str = config.model_dump_json()

            # Encrypt if encryption is enabled
            if self.encrypt_manager:
                config_raw_encrypted = self.encrypt_manager.encrypt(value=config_raw)
            else:
                config_raw_encrypted = config_raw

            # Write to S3
            self.s3_utils.s3_client.put_object(
                Bucket=self.s3_path,
                Key=self.config_file_key,
                Body=config_raw_encrypted,
                ContentType="application/json",
            )

        except Exception as e:
            print(f"Error saving config to S3: {str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                print(f"  {tb}")
