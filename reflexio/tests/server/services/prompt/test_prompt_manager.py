"""
Unit tests for PromptManager
"""

import json
import tempfile
from pathlib import Path

import pytest

import reflexio.server.prompt as prompt
from reflexio.server.prompt.prompt_manager import PromptManager
from reflexio.server.prompt.prompt_schema import Prompt, PromptBank


class TestPromptManager:
    """Test cases for PromptManager"""

    @pytest.fixture
    def temp_prompt_bank(self):
        """Create a temporary prompt bank directory for testing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank_path = Path(temp_dir) / "prompt_bank"
            prompt_bank_path.mkdir()

            # Create test prompt directory
            test_prompt_dir = prompt_bank_path / "test_prompt"
            test_prompt_dir.mkdir()

            # Create metadata.json
            metadata = {
                "prompt_id": "test_prompt",
                "active_version": "1.0.0",
                "created_at": 1703123456,
                "last_updated": 1703123456,
                "description": "Test prompt for unit testing",
                "versions": {
                    "1.0.0": {
                        "created_at": 1703123456,
                        "variables": ["variable1", "variable2"],
                    },
                    "0.9.0": {
                        "created_at": 1703000000,
                        "variables": ["variable1"],
                    },
                },
            }

            with open(test_prompt_dir / "metadata.json", "w") as f:
                json.dump(metadata, f)

            # Create prompt files
            with open(test_prompt_dir / "1.0.0.prompt", "w") as f:
                f.write("This is a test prompt with {variable1} and {variable2}")

            with open(test_prompt_dir / "0.9.0.prompt", "w") as f:
                f.write("Old test prompt with {variable1}")

            yield str(prompt_bank_path)

    @pytest.fixture
    def prompt_manager(self, temp_prompt_bank):
        """Create a PromptManager instance for testing"""
        return PromptManager(temp_prompt_bank)

    @pytest.fixture
    def sample_prompt_data(self):
        """Sample prompt data that matches the new schema"""
        return {
            "prompt_id": "test_prompt",
            "active_version": "1.0.0",
            "created_at": 1703123456,
            "last_updated": 1703123456,
            "description": "Test prompt for unit testing",
            "versions": {
                "1.0.0": {
                    "created_at": 1703123456,
                    "variables": ["variable1", "variable2"],
                },
                "0.9.0": {
                    "created_at": 1703000000,
                    "variables": ["variable1"],
                },
            },
        }

    def test_get_prompt_bank_success(self, prompt_manager):
        """Test successful retrieval of prompt bank"""
        result = prompt_manager._get_prompt_bank("test_prompt")

        assert result is not None
        assert isinstance(result, PromptBank)
        assert result.prompt_id == "test_prompt"
        assert result.active_version == "1.0.0"
        assert result.description == "Test prompt for unit testing"
        assert len(result.versions) == 2

    def test_get_prompt_bank_not_found(self, prompt_manager):
        """Test when prompt bank is not found"""
        result = prompt_manager._get_prompt_bank("nonexistent_prompt")
        assert result is None

    def test_get_prompt_success(self, prompt_manager):
        """Test successful retrieval of active prompt"""
        result = prompt_manager._get_prompt("test_prompt")

        assert result is not None
        assert isinstance(result, Prompt)
        assert (
            result.content == "This is a test prompt with {variable1} and {variable2}"
        )

    def test_get_prompt_specific_version(self, prompt_manager):
        """Test retrieval of specific prompt version"""
        result = prompt_manager._get_prompt("test_prompt", "0.9.0")

        assert result is not None
        assert isinstance(result, Prompt)
        assert result.content == "Old test prompt with {variable1}"

    def test_get_prompt_no_prompt_bank(self, prompt_manager):
        """Test get_prompt when prompt bank doesn't exist"""
        result = prompt_manager._get_prompt("nonexistent_prompt")
        assert result is None

    def test_get_prompt_no_active_version(self, temp_prompt_bank):
        """Test get_prompt when active version doesn't exist in versions"""
        # Create prompt with invalid active version
        invalid_prompt_dir = Path(temp_prompt_bank) / "invalid_prompt"
        invalid_prompt_dir.mkdir()

        metadata = {
            "prompt_id": "invalid_prompt",
            "active_version": "2.0.0",  # Version that doesn't exist
            "created_at": 1703123456,
            "last_updated": 1703123456,
            "description": "Invalid prompt",
            "versions": {
                "1.0.0": {
                    "created_at": 1703123456,
                    "variables": ["variable1"],
                },
            },
        }

        with open(invalid_prompt_dir / "metadata.json", "w") as f:
            json.dump(metadata, f)

        with open(invalid_prompt_dir / "1.0.0.prompt", "w") as f:
            f.write("Test prompt with {variable1}")

        pm = PromptManager(temp_prompt_bank)
        result = pm._get_prompt("invalid_prompt")
        assert result is None

    def test_render_prompt_success(self, prompt_manager):
        """Test successful prompt rendering"""
        variables = {"variable1": "value1", "variable2": "value2"}
        result = prompt_manager.render_prompt("test_prompt", variables)
        assert result == "This is a test prompt with value1 and value2"

    def test_render_prompt_missing_template_variable(self, prompt_manager):
        """Test render_prompt with missing template variable"""
        variables = {"variable2": "value2"}  # Missing variable1 needed by template

        with pytest.raises(ValueError, match="Missing required variable"):
            prompt_manager.render_prompt("test_prompt", variables)

    def test_render_prompt_not_found(self, prompt_manager):
        """Test render_prompt when prompt doesn't exist"""
        with pytest.raises(ValueError, match="Prompt nonexistent_prompt not found"):
            prompt_manager.render_prompt("nonexistent_prompt", {})

    def test_render_prompt_missing_another_template_variable(self, prompt_manager):
        """Test render_prompt fails when any template variable is missing"""
        variables = {"variable1": "value1"}  # variable2 is missing from template

        with pytest.raises(ValueError, match="Missing required variable"):
            prompt_manager.render_prompt("test_prompt", variables)

    def test_list_versions_success(self, prompt_manager):
        """Test successful listing of prompt versions"""
        result = prompt_manager.list_versions("test_prompt")
        assert set(result) == {"1.0.0", "0.9.0"}

    def test_list_versions_not_found(self, prompt_manager):
        """Test list_versions when prompt doesn't exist"""
        result = prompt_manager.list_versions("nonexistent_prompt")
        assert result == []

    def test_get_all_prompt_ids_success(self, temp_prompt_bank):
        """Test successful retrieval of all prompt IDs"""
        # Create additional prompt
        another_prompt_dir = Path(temp_prompt_bank) / "another_prompt"
        another_prompt_dir.mkdir()

        metadata = {
            "prompt_id": "another_prompt",
            "active_version": "1.0.0",
            "created_at": 1703123456,
            "last_updated": 1703123456,
            "description": "Another test prompt",
            "versions": {
                "1.0.0": {
                    "created_at": 1703123456,
                    "variables": ["variable1"],
                },
            },
        }

        with open(another_prompt_dir / "metadata.json", "w") as f:
            json.dump(metadata, f)

        with open(another_prompt_dir / "1.0.0.prompt", "w") as f:
            f.write("Another test prompt with {variable1}")

        pm = PromptManager(temp_prompt_bank)
        result = pm.get_all_prompt_ids()
        assert set(result) == {"test_prompt", "another_prompt"}

    def test_get_all_prompt_ids_empty(self):
        """Test get_all_prompt_ids when no prompts exist"""
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_prompt_bank = Path(temp_dir) / "empty_prompt_bank"
            empty_prompt_bank.mkdir()

            pm = PromptManager(str(empty_prompt_bank))
            result = pm.get_all_prompt_ids()
            assert result == []

    def test_caching_behavior(self, prompt_manager):
        """Test that prompt bank caching works correctly"""
        # First call should load from file
        result1 = prompt_manager._get_prompt_bank("test_prompt")
        # Second call should use cache
        result2 = prompt_manager._get_prompt_bank("test_prompt")

        assert result1 is result2  # Should be the same object due to caching
        assert result1.prompt_id == "test_prompt"

    def test_missing_prompt_file(self, temp_prompt_bank):
        """Test behavior when prompt file is missing"""
        # Create prompt with metadata but no prompt file
        missing_file_dir = Path(temp_prompt_bank) / "missing_file_prompt"
        missing_file_dir.mkdir()

        metadata = {
            "prompt_id": "missing_file_prompt",
            "active_version": "1.0.0",
            "created_at": 1703123456,
            "last_updated": 1703123456,
            "description": "Prompt with missing file",
            "versions": {
                "1.0.0": {
                    "created_at": 1703123456,
                    "variables": ["variable1"],
                },
            },
        }

        with open(missing_file_dir / "metadata.json", "w") as f:
            json.dump(metadata, f)

        # Don't create the .prompt file

        pm = PromptManager(temp_prompt_bank)
        result = pm._get_prompt_bank("missing_file_prompt")
        assert result is None  # Should return None when no valid versions found

    def test_invalid_metadata_file(self, temp_prompt_bank):
        """Test behavior when metadata file has invalid JSON"""
        invalid_json_dir = Path(temp_prompt_bank) / "invalid_json_prompt"
        invalid_json_dir.mkdir()

        with open(invalid_json_dir / "metadata.json", "w") as f:
            f.write("invalid json content")

        pm = PromptManager(temp_prompt_bank)
        result = pm._get_prompt_bank("invalid_json_prompt")
        assert result is None

    def test_integration_render_multiple_prompts(self, prompt_manager):
        """Integration test: render multiple prompts with caching"""
        variables = {"variable1": "test_value", "variable2": "another_value"}

        # First render
        result1 = prompt_manager.render_prompt("test_prompt", variables)
        # Second render (should use cached data)
        result2 = prompt_manager.render_prompt("test_prompt", variables)

        assert result1 == result2
        assert result1 == "This is a test prompt with test_value and another_value"

    def test_all_metadata_files_schema_validation(self):
        """Test that all metadata.json files in prompt_bank conform to simplified schema"""
        # Get the path to the actual prompt_bank directory
        current_dir = Path(prompt.__file__).parent
        prompt_bank_path = current_dir / "prompt_bank"
        prompt_bank_path = prompt_bank_path.resolve()

        # Skip test if prompt_bank doesn't exist
        if not prompt_bank_path.exists():
            pytest.skip("prompt_bank directory not found")

        # Find all metadata.json files
        metadata_files = list(prompt_bank_path.glob("*/metadata.json"))
        assert len(metadata_files) > 0, "No metadata.json files found in prompt_bank"

        failed_files = []
        schema_errors = []

        for metadata_file in metadata_files:
            prompt_name = metadata_file.parent.name
            try:
                with open(metadata_file, encoding="utf-8") as f:
                    metadata = json.load(f)

                # Validate top-level structure
                required_top_level_fields = [
                    "prompt_id",
                    "active_version",
                    "created_at",
                    "last_updated",
                    "description",
                    "versions",
                ]
                schema_errors.extend(
                    f"{prompt_name}: Missing required field '{field}'"
                    for field in required_top_level_fields
                    if field not in metadata
                )

                # Validate versions structure
                if "versions" in metadata:
                    for version_key, version_data in metadata["versions"].items():
                        # Check that version has simplified structure (no nested template)
                        if "template" in version_data:
                            schema_errors.append(
                                f"{prompt_name} v{version_key}: Still uses deprecated 'template' structure"
                            )

                        # Check required version fields
                        required_version_fields = ["created_at", "variables"]
                        schema_errors.extend(
                            f"{prompt_name} v{version_key}: Missing required field '{field}'"
                            for field in required_version_fields
                            if field not in version_data
                        )

                        # Validate variables field
                        if "variables" in version_data:
                            if not isinstance(version_data["variables"], list):
                                schema_errors.append(
                                    f"{prompt_name} v{version_key}: 'variables' must be a list"
                                )
                            else:
                                schema_errors.extend(
                                    f"{prompt_name} v{version_key}: All variables must be strings"
                                    for var in version_data["variables"]
                                    if not isinstance(var, str)
                                )

            except json.JSONDecodeError as e:
                failed_files.append(f"{prompt_name}: Invalid JSON - {e}")
            except Exception as e:
                failed_files.append(f"{prompt_name}: Error reading file - {e}")

        # Report any failures
        if failed_files:
            pytest.fail(f"Failed to read metadata files: {failed_files}")

        if schema_errors:
            pytest.fail(f"Schema validation errors: {schema_errors}")

        print(
            f"✅ Validated {len(metadata_files)} metadata.json files - all conform to simplified schema"
        )

    def test_no_legacy_template_structure_in_real_files(self):
        """Test that no real metadata.json files contain legacy 'template' structure"""
        # Get the path to the actual prompt_bank directory

        current_dir = Path(prompt.__file__).parent
        prompt_bank_path = current_dir / "prompt_bank"
        prompt_bank_path = prompt_bank_path.resolve()

        # Skip test if prompt_bank doesn't exist
        if not prompt_bank_path.exists():
            pytest.skip("prompt_bank directory not found")

        # Find all metadata.json files
        metadata_files = list(prompt_bank_path.glob("*/metadata.json"))
        legacy_files = []

        for metadata_file in metadata_files:
            prompt_name = metadata_file.parent.name
            try:
                with open(metadata_file, encoding="utf-8") as f:
                    content = f.read()

                # Check if file contains legacy template structure
                if '"template"' in content:
                    legacy_files.append(prompt_name)

            except Exception as e:
                pytest.fail(f"Error reading {prompt_name}: {e}")

        if legacy_files:
            pytest.fail(
                f"Found metadata files with legacy 'template' structure: {legacy_files}"
            )

        print(
            f"✅ Verified {len(metadata_files)} files have no legacy template structure"
        )
