import json
import traceback
from pathlib import Path

from reflexio_commons.config_schema import (
    Config,
    StorageConfigLocal,
)

from reflexio import data
from reflexio.server import FERNET_KEYS
from reflexio.server.services.configurator.config_storage import ConfigStorage
from reflexio.utils.encrypt_manager import EncryptManager


class LocalJsonConfigStorage(ConfigStorage):
    """
    Local JSON file-based configuration storage implementation.
    Saves/loads configuration to/from local JSON files with encryption.
    """

    def __init__(self, org_id: str, base_dir: str | None = None):
        super().__init__(org_id=org_id)
        if base_dir:
            # Ensure base_dir is absolute
            base_path = Path(base_dir)
            abs_base_dir = (
                str(base_path.resolve()) if not base_path.is_absolute() else base_dir
            )
            self.base_dir = str(Path(abs_base_dir) / "configs")
            self.config_file = str(Path(self.base_dir) / f"config_{org_id}.json")
            print(
                f"LocalJsonConfigStorage will save config for {org_id} to a local file at {self.config_file}"
            )
        else:
            self.base_dir = str(Path(data.__file__).parent / "configs")
            self.config_file = str(Path(self.base_dir) / f"config_{org_id}.json")

        # Load fernet key from environment and set up the encryption manager.
        self.encrypt_manager: EncryptManager | None = None
        if FERNET_KEYS:
            self.encrypt_manager = EncryptManager(fernet_keys=FERNET_KEYS)

    def get_default_config(self) -> Config:
        """
        Returns a default configuration that is uninitialized for local storage.

        Returns:
            Config: Default configuration with local storage type
        """
        base_path = Path(self.base_dir)
        abs_base_dir = (
            str(base_path.resolve()) if not base_path.is_absolute() else self.base_dir
        )
        return Config(
            storage_config=StorageConfigLocal(dir_path=abs_base_dir),
        )

    def load_config(self) -> Config:
        """
        Loads the current configuration from local JSON file. If the file doesn't exist,
        creates a default configuration and saves it.

        Returns:
            Config: Loaded configuration object
        """
        if not Path(self.config_file).exists():
            config = self.get_default_config()
            self._save_config_to_local_dir(config=config)
            return config

        try:
            with Path(self.config_file).open(encoding="utf-8") as f:
                config_raw = f.read()
                config_content = None
                if config_raw:
                    if self.encrypt_manager:
                        config_content = self.encrypt_manager.decrypt(
                            encrypted_value=config_raw
                        )
                    else:
                        config_content = config_raw
                config: Config = Config(**json.loads(str(config_content)))
                return config
        except Exception as e:
            print(f"{str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                print(f"  {tb}")
            # Create a default config if anything goes wrong.
            return self.get_default_config()

    def save_config(self, config: Config) -> None:
        """
        Saves the configuration to the local JSON file.

        Args:
            config (Config): Configuration object to save
        """
        if self.base_dir and self.config_file:
            self._save_config_to_local_dir(config=config)
        else:
            print(
                f"Cannot save config for org {self.org_id}: no local directory configured"
            )

    def _save_config_to_local_dir(self, config: Config) -> None:
        """
        Saves configuration to the local JSON file.

        Args:
            config (Config): Configuration object to save
        """
        if not (self.base_dir and self.config_file):
            raise ValueError("base_dir and config_file must be set")

        Path(self.base_dir).mkdir(parents=True, exist_ok=True)
        try:
            with Path(self.config_file).open("w", encoding="utf-8") as f:
                config_raw: str = config.model_dump_json()
                if self.encrypt_manager:
                    config_raw_encrypted = self.encrypt_manager.encrypt(
                        value=config_raw
                    )
                else:
                    config_raw_encrypted = config_raw

                f.write(config_raw_encrypted)  # type: ignore[reportArgumentType]
        except Exception as e:
            print(f"{str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                print(f"  {tb}")
