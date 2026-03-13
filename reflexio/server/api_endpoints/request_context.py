from reflexio.server.services.configurator.configurator import SimpleConfigurator
from typing import Optional

from reflexio.server.prompt.prompt_manager import PromptManager


class RequestContext:
    def __init__(
        self,
        org_id: str,
        storage_base_dir: Optional[str] = None,
        configurator: Optional[SimpleConfigurator] = None,
    ):
        self.org_id = str(org_id)
        self.storage_base_dir = storage_base_dir
        self.configurator = configurator or SimpleConfigurator(
            org_id, base_dir=storage_base_dir
        )
        self.prompt_manager = PromptManager()
        self.storage = self.configurator.create_storage(
            storage_config=self.configurator.get_current_storage_configuration(),
        )

    def is_storage_configured(self) -> bool:
        """Check if storage is configured and available.

        Returns:
            bool: True if storage is configured, False otherwise
        """
        return self.storage is not None
