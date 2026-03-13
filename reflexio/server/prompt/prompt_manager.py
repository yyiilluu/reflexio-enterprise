"""
Prompt management using file system prompt bank
"""

import json
import logging
from pathlib import Path
from typing import Any

from .prompt_schema import Prompt, PromptBank

logger = logging.getLogger(__name__)


class PromptManager:
    """Prompt management using file system prompt bank"""

    def __init__(
        self,
        prompt_bank_path: str | None = None,
        version_override: dict[str, str] | None = None,
    ):
        """
        Initialize the PromptManager.

        Args:
            prompt_bank_path (str, optional): Path to the prompt bank directory.
            version_override (Dict[str, str], optional): key is prompt_id, value is version. If not provided, the active version is used.
        """

        if prompt_bank_path is None:
            # Default to prompt_bank directory relative to this file
            current_dir = Path(__file__).parent
            self.prompt_bank_path = current_dir / "prompt_bank"
        else:
            self.prompt_bank_path = Path(prompt_bank_path)

        self.version_override: dict[str, str] | None = version_override

        if not self.prompt_bank_path.exists():
            logger.warning("Prompt bank path does not exist: %s", self.prompt_bank_path)

        self.prompt_bank_cache = {}

    # ==============================
    # Public methods
    # ==============================
    def render_prompt(self, prompt_id: str, variables: dict[str, Any]) -> str:
        """
        Render prompt template with variables

        Args:
            prompt_id (str): ID of the prompt
            variables (dict[str, Any]): Variables to substitute in template

        Returns:
            str: Rendered prompt content

        Raises:
            ValueError: If prompt not found or template rendering fails
        """
        version = (
            self.version_override.get(prompt_id) if self.version_override else None
        )
        prompt = self._get_prompt(prompt_id, version)
        if not prompt:
            raise ValueError(f"Prompt {prompt_id} not found")

        # Check that all required prompt variables are provided (allow extra variables)
        missing_vars = set(prompt.variables) - set(variables.keys())
        if missing_vars:
            raise ValueError(
                f"Missing required variables {missing_vars} for prompt {prompt_id}"
            )

        try:
            return prompt.content.format(**variables)
        except KeyError as e:
            raise ValueError(
                f"Missing required variable {e} for prompt {prompt_id}"
            ) from e
        except Exception as e:
            raise ValueError(f"Error rendering prompt {prompt_id}: {e}") from e

    def list_versions(self, prompt_id: str) -> list[str]:
        """
        List all versions of a prompt

        Args:
            prompt_id (str): ID of the prompt

        Returns:
            list[str]: List of version strings
        """
        prompt_bank = self._get_prompt_bank(prompt_id)
        if prompt_bank:
            return list(prompt_bank.versions.keys())
        return []

    def get_active_version(self, prompt_id: str) -> str | None:
        """
        Get the active version for a prompt (considering overrides).

        Args:
            prompt_id (str): ID of the prompt

        Returns:
            Optional[str]: The active version string, or None if prompt not found
        """
        if self.version_override and prompt_id in self.version_override:
            return self.version_override[prompt_id]
        prompt_bank = self._get_prompt_bank(prompt_id)
        return prompt_bank.active_version if prompt_bank else None

    def get_all_prompt_ids(self) -> list[str]:
        """
        Get list of all available prompt IDs

        Returns:
            list[str]: List of prompt IDs
        """
        if not self.prompt_bank_path.exists():
            return []

        prompt_ids = []
        try:
            prompt_ids.extend(
                item.name
                for item in self.prompt_bank_path.iterdir()
                if item.is_dir() and (item / "metadata.json").exists()
            )
        except Exception as e:
            logger.error("Error listing prompt directories: %s", e)

        return prompt_ids

    # ==============================
    # Private methods
    # ==============================

    def _load_metadata_file(self, prompt_id: str) -> dict | None:
        """Load metadata.json for a prompt"""
        metadata_path = self.prompt_bank_path / prompt_id / "metadata.json"
        try:
            with metadata_path.open(encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(
                "Metadata file not found for prompt %s at %s", prompt_id, metadata_path
            )
            return None
        except json.JSONDecodeError as e:
            logger.error(
                "Invalid JSON in metadata file for prompt %s: %s", prompt_id, e
            )
            return None
        except Exception as e:
            logger.error("Error loading metadata for prompt %s: %s", prompt_id, e)
            return None

    def _load_prompt_content(self, prompt_id: str, version: str) -> str | None:
        """Load prompt content from versioned file"""
        prompt_path = self.prompt_bank_path / prompt_id / f"{version}.prompt"
        try:
            with prompt_path.open(encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(
                "Prompt file not found for %s version %s at %s",
                prompt_id,
                version,
                prompt_path,
            )
            return None
        except Exception as e:
            logger.error(
                "Error loading prompt content for %s version %s: %s",
                prompt_id,
                version,
                e,
            )
            return None

    def _build_prompt_bank(
        self, prompt_id: str, metadata_data: dict
    ) -> PromptBank | None:
        """Build PromptBank from metadata and prompt files"""
        try:
            # Build versions with actual prompt content
            versions = {}
            for version_key, version_info in metadata_data.get("versions", {}).items():
                # Load the actual prompt content
                content = self._load_prompt_content(prompt_id, version_key)
                if content is None:
                    logger.warning(
                        "Skipping version %s for prompt %s - content not found",
                        version_key,
                        prompt_id,
                    )
                    continue

                # Create prompt with content and variables
                prompt = Prompt(
                    created_at=version_info.get("created_at", 0),
                    content=content,
                    variables=version_info.get("variables", []),
                )

                versions[version_key] = prompt

            if not versions:
                logger.warning("No valid versions found for prompt %s", prompt_id)
                return None

            # Create PromptBank with simplified schema (description at top level)
            return PromptBank(
                prompt_id=metadata_data.get("prompt_id", prompt_id),
                active_version=metadata_data.get("active_version", "1.0.0"),
                created_at=metadata_data.get("created_at", 0),
                last_updated=metadata_data.get("last_updated", 0),
                description=metadata_data.get("description", ""),
                versions=versions,
            )

        except Exception as e:
            logger.error("Failed to build prompt bank for %s: %s", prompt_id, e)
            return None

    def _get_prompt(self, prompt_id: str, version: str | None = None) -> Prompt | None:
        """
        Get active prompt with validation

        Args:
            prompt_id (str): ID of the prompt
            version (str, optional): Version of the prompt to get. If not provided, the active version is used.

        Returns:
            Optional[Prompt]: Validated prompt or None if not found
        """
        prompt_bank = self._get_prompt_bank(prompt_id)
        if not prompt_bank:
            return None

        chosen_version = version or prompt_bank.active_version
        version_data = prompt_bank.versions.get(chosen_version)

        if not version_data:
            logger.warning(
                "Version %s not found for prompt %s", chosen_version, prompt_id
            )
            return None

        return version_data

    def _get_prompt_bank(self, prompt_id: str) -> PromptBank | None:
        """
        Get complete prompt bank data with validation

        Args:
            prompt_id (str): ID of the prompt

        Returns:
            Optional[PromptBank]: Validated prompt bank or None if not found
        """
        if prompt_id in self.prompt_bank_cache:
            return self.prompt_bank_cache[prompt_id]

        metadata_data = self._load_metadata_file(prompt_id)
        if not metadata_data:
            return None

        prompt_bank = self._build_prompt_bank(prompt_id, metadata_data)
        self.prompt_bank_cache[prompt_id] = prompt_bank
        return prompt_bank
