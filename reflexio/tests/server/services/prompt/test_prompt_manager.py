"""
Unit tests for PromptManager
"""

import tempfile
from pathlib import Path

import pytest

import reflexio.server.prompt as prompt
from reflexio.server.prompt.prompt_manager import PromptManager, _parse_frontmatter
from reflexio.server.prompt.prompt_schema import Prompt


def _write_prompt_md(
    directory: Path,
    version: str,
    content: str,
    variables: list[str],
    *,
    active: bool = False,
    description: str | None = None,
) -> None:
    """Helper to write a v{version}.prompt.md file with frontmatter."""
    lines = ["---"]
    if active:
        lines.append("active: true")
    if description:
        lines.append(f'description: "{description}"')
    lines.append("variables:")
    lines.extend(f"  - {v}" for v in variables)
    lines.append("---")
    lines.append("")
    (directory / f"v{version}.prompt.md").write_text("\n".join(lines) + content)


class TestParseFrontmatter:
    """Tests for the standalone _parse_frontmatter helper."""

    def test_basic(self):
        raw = "---\nactive: true\nvariables:\n  - a\n  - b\n---\nHello {a} {b}"
        meta, body = _parse_frontmatter(raw)
        assert meta["active"] is True
        assert meta["variables"] == ["a", "b"]
        assert body == "Hello {a} {b}"

    def test_missing_frontmatter(self):
        with pytest.raises(ValueError, match="Missing or malformed"):
            _parse_frontmatter("No frontmatter here")

    def test_description_field(self):
        raw = (
            '---\nactive: false\ndescription: "Some desc"\nvariables:\n  - x\n---\nBody'
        )
        meta, _ = _parse_frontmatter(raw)
        assert meta["description"] == "Some desc"
        assert meta["active"] is False


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
            test_dir.mkdir()

            _write_prompt_md(
                test_dir,
                "1.0.0",
                "This is a test prompt with {variable1} and {variable2}",
                ["variable1", "variable2"],
                active=True,
                description="Test prompt for unit testing",
            )
            _write_prompt_md(
                test_dir,
                "0.9.0",
                "Old test prompt with {variable1}",
                ["variable1"],
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
        assert result.active is True

    def test_get_prompt_specific_version(self, prompt_manager):
        """Test retrieval of specific prompt version."""
        result = prompt_manager._get_prompt("test_prompt", "0.9.0")
        assert result is not None
        assert result.content == "Old test prompt with {variable1}"

    def test_get_prompt_not_found(self, prompt_manager):
        """Test get_prompt when prompt doesn't exist."""
        assert prompt_manager._get_prompt("nonexistent_prompt") is None

    def test_get_prompt_no_active_version(self, temp_prompt_bank):
        """Test get_prompt when no version has active: true."""
        no_active_dir = Path(temp_prompt_bank) / "no_active"
        no_active_dir.mkdir()
        _write_prompt_md(no_active_dir, "1.0.0", "Content", ["x"])

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
        another_dir.mkdir()
        _write_prompt_md(another_dir, "1.0.0", "Content", ["x"], active=True)

        pm = PromptManager(temp_prompt_bank)
        assert set(pm.get_all_prompt_ids()) == {"test_prompt", "another_prompt"}

    def test_get_all_prompt_ids_empty(self):
        """Test get_all_prompt_ids when no prompts exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            empty = Path(temp_dir) / "empty"
            empty.mkdir()
            assert PromptManager(str(empty)).get_all_prompt_ids() == []

    def test_caching_behavior(self, prompt_manager):
        """Test that active prompt caching works correctly."""
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

    def test_all_prompt_md_files_valid(self):
        """Test that all .prompt.md files in prompt_bank have valid frontmatter."""
        current_dir = Path(prompt.__file__).parent
        prompt_bank_path = (current_dir / "prompt_bank").resolve()

        if not prompt_bank_path.exists():
            pytest.skip("prompt_bank directory not found")

        md_files = list(prompt_bank_path.rglob("v*.prompt.md"))
        assert md_files, "No .prompt.md files found in prompt_bank"

        errors = []
        for md_file in md_files:
            raw = md_file.read_text(encoding="utf-8")
            try:
                meta, content = _parse_frontmatter(raw)
            except ValueError as e:
                errors.append(f"{md_file.relative_to(prompt_bank_path)}: {e}")
                continue

            if "variables" not in meta:
                errors.append(
                    f"{md_file.relative_to(prompt_bank_path)}: missing 'variables'"
                )
            elif not isinstance(meta["variables"], list):
                errors.append(
                    f"{md_file.relative_to(prompt_bank_path)}: 'variables' must be a list"
                )

            if not content.strip():
                errors.append(
                    f"{md_file.relative_to(prompt_bank_path)}: empty prompt content"
                )

        if errors:
            pytest.fail("Validation errors:\n" + "\n".join(errors))

    def test_exactly_one_active_per_prompt(self):
        """Test that each prompt directory has exactly one active version."""
        current_dir = Path(prompt.__file__).parent
        prompt_bank_path = (current_dir / "prompt_bank").resolve()

        if not prompt_bank_path.exists():
            pytest.skip("prompt_bank directory not found")

        errors = []
        for prompt_dir in sorted(prompt_bank_path.iterdir()):
            if not prompt_dir.is_dir():
                continue
            md_files = list(prompt_dir.glob("v*.prompt.md"))
            if not md_files:
                continue

            active_count = 0
            for md_file in md_files:
                raw = md_file.read_text(encoding="utf-8")
                try:
                    meta, _ = _parse_frontmatter(raw)
                    if meta.get("active"):
                        active_count += 1
                except ValueError:
                    pass

            if active_count != 1:
                errors.append(
                    f"{prompt_dir.name}: {active_count} active versions (expected 1)"
                )

        if errors:
            pytest.fail("Active version errors:\n" + "\n".join(errors))


class TestParseFrontmatterExtended:
    """Extended tests for _parse_frontmatter covering edge cases."""

    def test_block_style_list(self):
        """Test parsing block-style YAML lists (- item per line)."""
        raw = "---\nactive: true\nvariables:\n  - foo\n  - bar\n  - baz\n---\nBody"
        meta, body = _parse_frontmatter(raw)
        assert meta["variables"] == ["foo", "bar", "baz"]
        assert body == "Body"

    def test_null_value(self):
        """Test that 'null' values are parsed as None."""
        raw = "---\nactive: false\ndescription: null\nvariables:\n  - x\n---\nBody"
        meta, _ = _parse_frontmatter(raw)
        assert meta["description"] is None

    def test_empty_value(self):
        """Test that empty values are parsed as None."""
        raw = "---\nactive: false\ndescription:\nvariables:\n  - x\n---\nBody"
        meta, _ = _parse_frontmatter(raw)
        assert meta["description"] is None

    def test_malformed_no_closing_delimiter(self):
        """Test that missing closing --- raises ValueError."""
        raw = "---\nactive: true\nvariables:\n  - x\nBody without closing"
        with pytest.raises(ValueError, match="Missing or malformed"):
            _parse_frontmatter(raw)

    def test_malformed_no_opening_delimiter(self):
        """Test that missing opening --- raises ValueError."""
        raw = "active: true\nvariables:\n  - x\n---\nBody"
        with pytest.raises(ValueError, match="Missing or malformed"):
            _parse_frontmatter(raw)

    def test_inline_list_syntax(self):
        """Test parsing inline list [a, b, c] syntax."""
        raw = "---\nactive: true\nvariables: [a, b, c]\n---\nBody"
        meta, _ = _parse_frontmatter(raw)
        assert meta["variables"] == ["a", "b", "c"]

    def test_changelog_field(self):
        """Test parsing a changelog field as a string."""
        raw = '---\nactive: true\nchangelog: "Added new feature"\nvariables:\n  - x\n---\nBody'
        meta, _ = _parse_frontmatter(raw)
        assert meta["changelog"] == "Added new feature"


class TestParseFrontmatterDeepEdgeCases:
    """Deep edge cases for _parse_frontmatter."""

    def test_first_item_block_list_on_same_line(self):
        """Test that '- value' on the same line as key is parsed as a list."""
        raw = "---\nitems: - first_item\n---\nBody"
        meta, body = _parse_frontmatter(raw)
        assert meta["items"] == ["first_item"]
        assert body == "Body"

    def test_block_list_continuation_after_key(self):
        """Test block-style list with items on subsequent lines (continuation)."""
        raw = "---\nactive: true\ntags:\n  - alpha\n  - beta\n  - gamma\n---\nContent"
        meta, body = _parse_frontmatter(raw)
        assert meta["tags"] == ["alpha", "beta", "gamma"]
        assert body == "Content"

    def test_block_list_replaces_inline_value(self):
        """Test that block-style list items override any inline value for the key."""
        # The key has a value that gets parsed first pass, then block items override it
        raw = "---\nactive: true\ndata: initial_value\n  - item_a\n  - item_b\n---\nBody"
        meta, _ = _parse_frontmatter(raw)
        # The block list parser should convert data to a list
        assert meta["data"] == ["item_a", "item_b"]

    def test_empty_key_line_skipped(self):
        """Test that lines with empty keys (after strip) are skipped."""
        raw = "---\nactive: true\n: only_value\nvariables:\n  - x\n---\nBody"
        meta, _ = _parse_frontmatter(raw)
        assert "" not in meta
        assert meta["active"] is True

    def test_line_without_colon_skipped(self):
        """Test that lines without a colon are skipped in parsing."""
        raw = "---\nactive: true\nno-colon-here\nvariables:\n  - x\n---\nBody"
        meta, _ = _parse_frontmatter(raw)
        assert meta["active"] is True
        assert "no-colon-here" not in meta

    def test_quoted_string_value(self):
        """Test that quoted string values have quotes stripped."""
        raw = "---\nactive: true\ndescription: 'my prompt description'\nvariables:\n  - x\n---\nBody"
        meta, _ = _parse_frontmatter(raw)
        assert meta["description"] == "my prompt description"

    def test_inline_list_with_quoted_items(self):
        """Test parsing inline list with quoted items."""
        raw = "---\nvariables: ['foo', \"bar\", baz]\n---\nBody"
        meta, _ = _parse_frontmatter(raw)
        assert meta["variables"] == ["foo", "bar", "baz"]

    def test_boolean_true(self):
        """Test true boolean parsing."""
        raw = "---\nactive: true\nvariables:\n  - x\n---\nBody"
        meta, _ = _parse_frontmatter(raw)
        assert meta["active"] is True

    def test_boolean_false(self):
        """Test false boolean parsing."""
        raw = "---\nactive: false\nvariables:\n  - x\n---\nBody"
        meta, _ = _parse_frontmatter(raw)
        assert meta["active"] is False


class TestRenderPromptErrors:
    """Tests for render_prompt error cases."""

    def test_missing_variable_raises_key_error_as_value_error(self):
        """Test that a KeyError from format() is wrapped in ValueError."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()
            prompt_dir = prompt_bank / "key_err"
            prompt_dir.mkdir()

            # Template uses {a} and {b}, but frontmatter only declares {a}
            # This means the frontmatter variables check passes for {a},
            # but format() will raise KeyError for {b} not supplied
            _write_prompt_md(
                prompt_dir,
                "1.0.0",
                "Hello {a} and {b}",
                ["a"],
                active=True,
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
            prompt_dir.mkdir()

            # Bad format string with incomplete brace
            (prompt_dir / "v1.0.0.prompt.md").write_text(
                "---\nactive: true\nvariables:\n  - x\n---\nHello {x!z}"
            )

            pm = PromptManager(str(prompt_bank))
            with pytest.raises(ValueError, match="Error rendering prompt"):
                pm.render_prompt("fmt_err", {"x": "val"})


class TestLoadPromptEdgeCases:
    """Tests for _load_prompt edge cases."""

    def test_nonexistent_version_file_returns_none(self):
        """Test that requesting a non-existent version file returns None."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()
            prompt_dir = prompt_bank / "my_prompt"
            prompt_dir.mkdir()

            _write_prompt_md(prompt_dir, "1.0.0", "Content", ["x"], active=True)

            pm = PromptManager(str(prompt_bank))
            result = pm._load_prompt("my_prompt", "99.99.99")
            assert result is None

    def test_malformed_frontmatter_returns_none(self):
        """Test that a prompt file with malformed frontmatter returns None."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()
            prompt_dir = prompt_bank / "bad_prompt"
            prompt_dir.mkdir()

            (prompt_dir / "v1.0.0.prompt.md").write_text("No frontmatter here")

            pm = PromptManager(str(prompt_bank))
            result = pm._load_prompt("bad_prompt", "1.0.0")
            assert result is None

    def test_read_error_returns_none(self):
        """Test that a file read error returns None."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()

            pm = PromptManager(str(prompt_bank))
            # Prompt directory doesn't exist at all
            result = pm._load_prompt("nonexistent_prompt", "1.0.0")
            assert result is None


class TestFindActiveVersionCacheMiss:
    """Tests for _find_active_version and _get_prompt cache behavior."""

    def test_no_active_version_returns_none(self):
        """Test that when no version has active: true, _get_prompt returns None."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()
            prompt_dir = prompt_bank / "inactive"
            prompt_dir.mkdir()

            # Write a version with active: false
            _write_prompt_md(prompt_dir, "1.0.0", "Content", ["x"])

            pm = PromptManager(str(prompt_bank))
            result = pm._get_prompt("inactive")
            assert result is None
            # Should not be cached since it wasn't found
            assert "inactive" not in pm._cache

    def test_active_version_gets_cached(self):
        """Test that a found active prompt gets cached."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()
            prompt_dir = prompt_bank / "cached_prompt"
            prompt_dir.mkdir()

            _write_prompt_md(prompt_dir, "1.0.0", "Content", ["x"], active=True)

            pm = PromptManager(str(prompt_bank))
            result1 = pm._get_prompt("cached_prompt")
            assert result1 is not None
            assert "cached_prompt" in pm._cache
            # Second call should return same cached instance
            result2 = pm._get_prompt("cached_prompt")
            assert result1 is result2

    def test_nonexistent_prompt_dir_returns_none(self):
        """Test that _find_active_version returns None for non-existent prompt dir."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank = Path(temp_dir) / "prompt_bank"
            prompt_bank.mkdir()

            pm = PromptManager(str(prompt_bank))
            assert pm._find_active_version("does_not_exist") is None


class TestFindActiveVersionWithException:
    """Tests for _find_active_version when a prompt file has invalid content."""

    def test_exception_in_one_file_continues(self):
        """Test that an exception in one prompt file skips it and finds active in another."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank_path = Path(temp_dir) / "prompt_bank"
            prompt_bank_path.mkdir()
            prompt_dir = prompt_bank_path / "flaky_prompt"
            prompt_dir.mkdir()

            # Write a bad file (no frontmatter)
            (prompt_dir / "v1.0.0.prompt.md").write_text("No frontmatter here at all")

            # Write a good active file
            _write_prompt_md(prompt_dir, "2.0.0", "Good content", ["x"], active=True)

            pm = PromptManager(str(prompt_bank_path))
            version = pm._find_active_version("flaky_prompt")
            assert version == "2.0.0"

    def test_all_files_invalid_returns_none(self):
        """Test that when all prompt files are invalid, None is returned."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_bank_path = Path(temp_dir) / "prompt_bank"
            prompt_bank_path.mkdir()
            prompt_dir = prompt_bank_path / "bad_prompt"
            prompt_dir.mkdir()

            (prompt_dir / "v1.0.0.prompt.md").write_text("No frontmatter")
            (prompt_dir / "v2.0.0.prompt.md").write_text("Also no frontmatter")

            pm = PromptManager(str(prompt_bank_path))
            assert pm._find_active_version("bad_prompt") is None


class TestConstructorNonExistentPath:
    """Tests for PromptManager constructor with non-existent path."""

    def test_non_existent_path_no_raise(self):
        """Test that constructor with non-existent path does not raise."""
        pm = PromptManager("/this/path/does/not/exist")
        assert pm._cache == {}

    def test_non_existent_path_empty_prompts(self):
        """Test that non-existent path results in empty prompt IDs."""
        pm = PromptManager("/this/path/does/not/exist")
        assert pm.get_all_prompt_ids() == []

    def test_non_existent_path_list_versions_empty(self):
        """Test that list_versions returns empty for non-existent path."""
        pm = PromptManager("/this/path/does/not/exist")
        assert pm.list_versions("any_prompt") == []

    def test_non_existent_path_find_active_version_none(self):
        """Test that _find_active_version returns None for non-existent path."""
        pm = PromptManager("/this/path/does/not/exist")
        assert pm._find_active_version("any_prompt") is None
