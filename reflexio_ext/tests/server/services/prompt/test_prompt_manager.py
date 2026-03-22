"""
Unit tests for PromptManager

Tests the file-system-based prompt bank using metadata.json + {version}.prompt files.
"""

import json
import tempfile
from pathlib import Path

import pytest
import reflexio.server.prompt as prompt
from reflexio.server.prompt.prompt_manager import PromptManager
from reflexio.server.prompt.prompt_schema import Prompt


def _write_prompt_bank(
    prompt_dir: Path,
    versions: dict[str, dict],
    *,
    active_version: str = "1.0.0",
    description: str | None = None,
) -> None:
    """Helper to write metadata.json and {version}.prompt files.

    Args:
        prompt_dir: Directory for this prompt (e.g. prompt_bank/test_prompt).
        versions: Mapping of version string to dict with 'content' and 'variables' keys.
        active_version: Which version is active.
        description: Optional description for the prompt.
    """
    prompt_dir.mkdir(exist_ok=True)

    metadata = {
        "prompt_id": prompt_dir.name,
        "active_version": active_version,
        "created_at": 1700000000,
        "last_updated": 1700000000,
        "description": description or "",
        "versions": {},
    }
    for ver, info in versions.items():
        metadata["versions"][ver] = {
            "created_at": 1700000000,
            "variables": info.get("variables", []),
        }
        # Write the .prompt file
        (prompt_dir / f"{ver}.prompt").write_text(info["content"])

    (prompt_dir / "metadata.json").write_text(json.dumps(metadata, indent=4))


class TestPromptManager:
    """Test cases for PromptManager"""

    @pytest.fixture
    def temp_prompt_bank(self):
        """Create a temporary prompt bank directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank_path = Path(temp_dir) / "prompt_bank"
            prompt_bank_path.mkdir()

            # Create test prompt directory with two versions
            test_dir = prompt_bank_path / "test_prompt"
            _write_prompt_bank(
                test_dir,
                {
                    "1.0.0": {
                        "content": "This is a test prompt with {variable1} and {variable2}",
                        "variables": ["variable1", "variable2"],
                    },
                    "0.9.0": {
                        "content": "Old test prompt with {variable1}",
                        "variables": ["variable1"],
                    },
                },
                active_version="1.0.0",
                description="Test prompt for unit testing",
            )

            yield str(prompt_bank_path)

    @pytest.fixture
    def prompt_manager(self, temp_prompt_bank):
        """Create a PromptManager instance for testing."""
        return PromptManager(temp_prompt_bank)

    def test_get_prompt_success(self, prompt_manager):
        """Test successful retrieval of active prompt."""
        result = prompt_manager._get_prompt("test_prompt")
        assert result is not None
        assert isinstance(result, Prompt)
        assert (
            result.content == "This is a test prompt with {variable1} and {variable2}"
        )

    def test_get_prompt_specific_version(self, prompt_manager):
        """Test retrieval of specific prompt version."""
        result = prompt_manager._get_prompt("test_prompt", "0.9.0")
        assert result is not None
        assert result.content == "Old test prompt with {variable1}"

    def test_get_prompt_not_found(self, prompt_manager):
        """Test get_prompt when prompt doesn't exist."""
        assert prompt_manager._get_prompt("nonexistent_prompt") is None

    def test_get_prompt_no_active_version(self, temp_prompt_bank):
        """Test get_prompt when active_version points to a missing .prompt file."""
        no_active_dir = Path(temp_prompt_bank) / "no_active"
        no_active_dir.mkdir()
        # metadata.json references version 2.0.0 but no 2.0.0.prompt file exists
        metadata = {
            "prompt_id": "no_active",
            "active_version": "2.0.0",
            "created_at": 0,
            "last_updated": 0,
            "description": "",
            "versions": {
                "1.0.0": {"created_at": 0, "variables": ["x"]},
            },
        }
        (no_active_dir / "metadata.json").write_text(json.dumps(metadata))
        (no_active_dir / "1.0.0.prompt").write_text("Content")

        pm = PromptManager(temp_prompt_bank)
        assert pm._get_prompt("no_active") is None

    def test_render_prompt_success(self, prompt_manager):
        """Test successful prompt rendering."""
        result = prompt_manager.render_prompt(
            "test_prompt", {"variable1": "value1", "variable2": "value2"}
        )
        assert result == "This is a test prompt with value1 and value2"

    def test_render_prompt_missing_variable(self, prompt_manager):
        """Test render_prompt with missing template variable."""
        with pytest.raises(ValueError, match="Missing required variable"):
            prompt_manager.render_prompt("test_prompt", {"variable2": "value2"})

    def test_render_prompt_not_found(self, prompt_manager):
        """Test render_prompt when prompt doesn't exist."""
        with pytest.raises(ValueError, match="Prompt nonexistent_prompt not found"):
            prompt_manager.render_prompt("nonexistent_prompt", {})

    def test_render_prompt_missing_another_variable(self, prompt_manager):
        """Test render_prompt fails when any template variable is missing."""
        with pytest.raises(ValueError, match="Missing required variable"):
            prompt_manager.render_prompt("test_prompt", {"variable1": "value1"})

    def test_list_versions(self, prompt_manager):
        """Test listing prompt versions."""
        result = prompt_manager.list_versions("test_prompt")
        assert set(result) == {"1.0.0", "0.9.0"}

    def test_list_versions_not_found(self, prompt_manager):
        """Test list_versions when prompt doesn't exist."""
        assert prompt_manager.list_versions("nonexistent_prompt") == []

    def test_get_active_version(self, prompt_manager):
        """Test getting the active version."""
        assert prompt_manager.get_active_version("test_prompt") == "1.0.0"

    def test_get_active_version_with_override(self, temp_prompt_bank):
        """Test version override takes precedence."""
        pm = PromptManager(temp_prompt_bank, version_override={"test_prompt": "0.9.0"})
        assert pm.get_active_version("test_prompt") == "0.9.0"

    def test_get_all_prompt_ids(self, temp_prompt_bank):
        """Test retrieval of all prompt IDs."""
        another_dir = Path(temp_prompt_bank) / "another_prompt"
        _write_prompt_bank(
            another_dir,
            {"1.0.0": {"content": "Content", "variables": ["x"]}},
            active_version="1.0.0",
        )

        pm = PromptManager(temp_prompt_bank)
        assert set(pm.get_all_prompt_ids()) == {"test_prompt", "another_prompt"}

    def test_get_all_prompt_ids_empty(self):
        """Test get_all_prompt_ids when no prompts exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            empty = Path(temp_dir) / "empty"
            empty.mkdir()
            assert PromptManager(str(empty)).get_all_prompt_ids() == []

    def test_caching_behavior(self, prompt_manager):
        """Test that prompt bank caching works correctly."""
        result1 = prompt_manager._get_prompt("test_prompt")
        result2 = prompt_manager._get_prompt("test_prompt")
        assert result1 is result2

    def test_version_override_bypasses_cache(self, temp_prompt_bank):
        """Test that explicit version requests bypass the cache."""
        pm = PromptManager(temp_prompt_bank, version_override={"test_prompt": "0.9.0"})
        result = pm.render_prompt("test_prompt", {"variable1": "val"})
        assert result == "Old test prompt with val"

    def test_integration_render_multiple_prompts(self, prompt_manager):
        """Integration test: render multiple prompts with caching."""
        variables = {"variable1": "test_value", "variable2": "another_value"}
        result1 = prompt_manager.render_prompt("test_prompt", variables)
        result2 = prompt_manager.render_prompt("test_prompt", variables)
        assert result1 == result2
        assert result1 == "This is a test prompt with test_value and another_value"

    def test_all_prompt_files_valid(self):
        """Test that all .prompt files in prompt_bank have corresponding metadata."""
        current_dir = Path(prompt.__file__).parent
        prompt_bank_path = (current_dir / "prompt_bank").resolve()

        if not prompt_bank_path.exists():
            pytest.skip("prompt_bank directory not found")

        metadata_files = list(prompt_bank_path.rglob("metadata.json"))
        assert metadata_files, "No metadata.json files found in prompt_bank"

        errors = []
        for metadata_file in metadata_files:
            prompt_dir = metadata_file.parent
            try:
                with metadata_file.open(encoding="utf-8") as f:
                    metadata = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                errors.append(
                    f"{prompt_dir.relative_to(prompt_bank_path)}: invalid metadata.json: {e}"
                )
                continue

            if "versions" not in metadata:
                errors.append(
                    f"{prompt_dir.relative_to(prompt_bank_path)}: missing 'versions'"
                )
                continue

            for version_key, version_info in metadata["versions"].items():
                prompt_file = prompt_dir / f"{version_key}.prompt"
                if not prompt_file.exists():
                    errors.append(
                        f"{prompt_dir.relative_to(prompt_bank_path)}: missing {version_key}.prompt"
                    )
                elif not prompt_file.read_text(encoding="utf-8").strip():
                    errors.append(
                        f"{prompt_dir.relative_to(prompt_bank_path)}: empty {version_key}.prompt"
                    )

                if "variables" not in version_info:
                    errors.append(
                        f"{prompt_dir.relative_to(prompt_bank_path)}/{version_key}: missing 'variables'"
                    )
                elif not isinstance(version_info["variables"], list):
                    errors.append(
                        f"{prompt_dir.relative_to(prompt_bank_path)}/{version_key}: 'variables' must be a list"
                    )

        if errors:
            pytest.fail("Validation errors:\n" + "\n".join(errors))

    def test_exactly_one_active_per_prompt(self):
        """Test that each prompt directory has an active_version defined in metadata."""
        current_dir = Path(prompt.__file__).parent
        prompt_bank_path = (current_dir / "prompt_bank").resolve()

        if not prompt_bank_path.exists():
            pytest.skip("prompt_bank directory not found")

        errors = []
        for prompt_dir in sorted(prompt_bank_path.iterdir()):
            if not prompt_dir.is_dir():
                continue
            metadata_file = prompt_dir / "metadata.json"
            if not metadata_file.exists():
                continue

            try:
                with metadata_file.open(encoding="utf-8") as f:
                    metadata = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            active_version = metadata.get("active_version")
            if not active_version:
                errors.append(f"{prompt_dir.name}: no active_version defined")
            elif active_version not in metadata.get("versions", {}):
                errors.append(
                    f"{prompt_dir.name}: active_version '{active_version}' not in versions"
                )

        if errors:
            pytest.fail("Active version errors:\n" + "\n".join(errors))


class TestRenderPromptErrors:
    """Tests for render_prompt error cases."""

    def test_missing_variable_raises_key_error_as_value_error(self):
        """Test that a KeyError from format() is wrapped in ValueError."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()
            prompt_dir = prompt_bank / "key_err"

            # Template uses {a} and {b}, but metadata only declares {a}
            # This means the variables check passes for {a},
            # but format() will raise KeyError for {b} not supplied
            _write_prompt_bank(
                prompt_dir,
                {"1.0.0": {"content": "Hello {a} and {b}", "variables": ["a"]}},
                active_version="1.0.0",
            )

            pm = PromptManager(str(prompt_bank))
            # Providing only 'a' but template needs 'b' => KeyError from format()
            with pytest.raises(ValueError, match="Missing required variable"):
                pm.render_prompt("key_err", {"a": "val_a"})

    def test_general_format_error_raises_value_error(self):
        """Test that a general formatting error raises ValueError."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()
            prompt_dir = prompt_bank / "fmt_err"

            # Bad format string with invalid conversion spec
            _write_prompt_bank(
                prompt_dir,
                {"1.0.0": {"content": "Hello {x!z}", "variables": ["x"]}},
                active_version="1.0.0",
            )

            pm = PromptManager(str(prompt_bank))
            with pytest.raises(ValueError, match="Error rendering prompt"):
                pm.render_prompt("fmt_err", {"x": "val"})


class TestLoadPromptContentEdgeCases:
    """Tests for _load_prompt_content edge cases."""

    def test_nonexistent_version_file_returns_none(self):
        """Test that requesting a non-existent version file returns None."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()
            prompt_dir = prompt_bank / "my_prompt"

            _write_prompt_bank(
                prompt_dir,
                {"1.0.0": {"content": "Content", "variables": ["x"]}},
                active_version="1.0.0",
            )

            pm = PromptManager(str(prompt_bank))
            result = pm._load_prompt_content("my_prompt", "99.99.99")
            assert result is None

    def test_nonexistent_prompt_dir_returns_none(self):
        """Test that _load_prompt_content returns None for non-existent prompt dir."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()

            pm = PromptManager(str(prompt_bank))
            result = pm._load_prompt_content("nonexistent_prompt", "1.0.0")
            assert result is None


class TestGetActiveVersionCacheBehavior:
    """Tests for get_active_version and _get_prompt cache behavior."""

    def test_no_active_version_match_returns_none(self):
        """Test that when active_version points to missing version, _get_prompt returns None."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()
            prompt_dir = prompt_bank / "inactive"
            prompt_dir.mkdir()

            # metadata references 2.0.0 as active but only 1.0.0 content exists
            metadata = {
                "prompt_id": "inactive",
                "active_version": "2.0.0",
                "created_at": 0,
                "last_updated": 0,
                "description": "",
                "versions": {"1.0.0": {"created_at": 0, "variables": ["x"]}},
            }
            (prompt_dir / "metadata.json").write_text(json.dumps(metadata))
            (prompt_dir / "1.0.0.prompt").write_text("Content")

            pm = PromptManager(str(prompt_bank))
            result = pm._get_prompt("inactive")
            assert result is None

    def test_active_version_gets_cached(self):
        """Test that a found prompt bank gets cached."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()
            prompt_dir = prompt_bank / "cached_prompt"

            _write_prompt_bank(
                prompt_dir,
                {"1.0.0": {"content": "Content", "variables": ["x"]}},
                active_version="1.0.0",
            )

            pm = PromptManager(str(prompt_bank))
            result1 = pm._get_prompt("cached_prompt")
            assert result1 is not None
            assert "cached_prompt" in pm.prompt_bank_cache
            # Second call should return same cached instance
            result2 = pm._get_prompt("cached_prompt")
            assert result1 is result2

    def test_nonexistent_prompt_dir_returns_none(self):
        """Test that get_active_version returns None for non-existent prompt dir."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()

            pm = PromptManager(str(prompt_bank))
            assert pm.get_active_version("does_not_exist") is None


class TestGetActiveVersionWithInvalidMetadata:
    """Tests for get_active_version when a prompt has invalid metadata."""

    def test_invalid_metadata_returns_none(self):
        """Test that invalid metadata.json causes get_active_version to return None."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank_path = Path(temp_dir) / "prompt_bank"
            prompt_bank_path.mkdir()
            prompt_dir = prompt_bank_path / "bad_prompt"
            prompt_dir.mkdir()

            # Write invalid JSON in metadata.json
            (prompt_dir / "metadata.json").write_text("Not valid JSON")

            pm = PromptManager(str(prompt_bank_path))
            assert pm.get_active_version("bad_prompt") is None

    def test_valid_metadata_returns_active_version(self):
        """Test that valid metadata returns the active version."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank_path = Path(temp_dir) / "prompt_bank"
            prompt_bank_path.mkdir()
            prompt_dir = prompt_bank_path / "good_prompt"

            _write_prompt_bank(
                prompt_dir,
                {
                    "1.0.0": {"content": "Old content", "variables": ["x"]},
                    "2.0.0": {"content": "New content", "variables": ["x"]},
                },
                active_version="2.0.0",
            )

            pm = PromptManager(str(prompt_bank_path))
            version = pm.get_active_version("good_prompt")
            assert version == "2.0.0"


class TestConstructorNonExistentPath:
    """Tests for PromptManager constructor with non-existent path."""

    def test_non_existent_path_no_raise(self):
        """Test that constructor with non-existent path does not raise."""
        pm = PromptManager("/this/path/does/not/exist")
        assert pm.prompt_bank_cache == {}

    def test_non_existent_path_empty_prompts(self):
        """Test that non-existent path results in empty prompt IDs."""
        pm = PromptManager("/this/path/does/not/exist")
        assert pm.get_all_prompt_ids() == []

    def test_non_existent_path_list_versions_empty(self):
        """Test that list_versions returns empty for non-existent path."""
        pm = PromptManager("/this/path/does/not/exist")
        assert pm.list_versions("any_prompt") == []

    def test_non_existent_path_get_active_version_none(self):
        """Test that get_active_version returns None for non-existent path."""
        pm = PromptManager("/this/path/does/not/exist")
        assert pm.get_active_version("any_prompt") is None
