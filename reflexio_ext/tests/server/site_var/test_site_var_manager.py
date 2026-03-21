import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

import redis
from reflexio.server.site_var.site_var_manager import SiteVarManager


class TestSiteVarManager(unittest.TestCase):
    """
    Unit tests for SiteVarManager class.
    Tests all methods with proper mocking of Redis and file system operations.
    """

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.temp_dir = tempfile.mkdtemp()
        # Create mock redis client
        self.mock_redis = Mock()

        # Create SiteVarManager with Redis enabled
        with patch("redis.Redis", return_value=self.mock_redis):
            self.site_var_manager = SiteVarManager(
                source_dir=self.temp_dir, enable_redis=True
            )

    def tearDown(self):
        """Clean up after each test method."""
        # Clean up temporary directory
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

        # Clean up nonexistent directory if it was created during tests
        nonexistent_path = "./nonexistent"
        if os.path.exists(nonexistent_path):
            shutil.rmtree(nonexistent_path)

    def test_init_with_default_source_dir(self):
        """Test initialization with default source directory."""
        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.mkdir") as mock_mkdir,
        ):
            manager = SiteVarManager()
            mock_mkdir.assert_called_once()
            # Default enable_redis is False
            self.assertFalse(manager.enable_redis)

    def test_init_with_redis_disabled(self):
        """Test initialization with Redis disabled."""
        manager = SiteVarManager(enable_redis=False)
        self.assertFalse(manager.enable_redis)
        self.assertIsNone(manager.redis)

    @patch("os.path.exists", return_value=True)
    def test_get_site_var_from_redis_cache(self, mock_exists):
        """Test getting site variable from Redis cache."""
        cached_value = b'{"key": "value"}'
        self.mock_redis.get.return_value = cached_value

        result = self.site_var_manager.get_site_var("test_var")

        self.assertEqual(result, {"key": "value"})  # Expect parsed JSON object
        self.mock_redis.get.assert_called_once_with("test_var")

    @patch("os.path.exists", return_value=True)
    def test_get_site_var_from_file_when_not_in_cache(self, mock_exists):
        """Test getting site variable from file when not in Redis cache."""
        # Mock Redis to return None (not in cache)
        self.mock_redis.get.return_value = None

        # Mock file content
        json_content = '{"test": "data"}'
        expected_data = json.loads(json_content)

        with patch.object(
            self.site_var_manager, "_load_from_file", return_value=expected_data
        ):
            result = self.site_var_manager.get_site_var("test_var")

            self.assertEqual(result, expected_data)
            # Should cache in Redis as JSON string (dicts are converted via json.dumps)
            self.mock_redis.set.assert_called_once_with("test_var", json_content)

    def test_get_site_var_not_found(self):
        """Test getting site variable that doesn't exist."""
        self.mock_redis.get.return_value = None

        with patch.object(self.site_var_manager, "_load_from_file", return_value=None):
            result = self.site_var_manager.get_site_var("nonexistent")

            self.assertIsNone(result)

    def test_get_site_var_redis_error_fallback(self):
        """Test fallback to file loading when Redis error occurs."""
        self.mock_redis.get.side_effect = redis.RedisError("Connection failed")

        json_content = '{"fallback": "data"}'
        with patch.object(
            self.site_var_manager, "_load_from_file", return_value=json_content
        ):
            result = self.site_var_manager.get_site_var("test_var")

            self.assertEqual(result, json_content)

    def test_get_site_var_with_redis_disabled(self):
        """Test getting site variable when Redis is disabled."""
        manager = SiteVarManager(source_dir=self.temp_dir, enable_redis=False)
        json_content = '{"no_redis": "data"}'

        with patch.object(manager, "_load_from_file", return_value=json_content):
            result = manager.get_site_var("test_var")

            self.assertEqual(result, json_content)

    def test_load_all_site_vars(self):
        """Test loading all site variables from directory."""
        # Create test files
        test_files = {
            "var1.json": '{"key1": "value1"}',
            "var2.txt": "plain text content",
            "var3.json": '{"key3": "value3"}',
        }

        for filename, content in test_files.items():
            filepath = os.path.join(self.temp_dir, filename)
            with open(filepath, "w") as f:
                f.write(content)

        # Mock Redis to return None for all gets
        self.mock_redis.get.return_value = None

        result = self.site_var_manager.load_all_site_vars()

        # The actual implementation returns parsed JSON objects for .json files
        expected = {
            "var1": {"key1": "value1"},
            "var2": "plain text content",
            "var3": {"key3": "value3"},
        }
        self.assertEqual(result, expected)
        # Should cache all variables in Redis
        self.assertEqual(self.mock_redis.set.call_count, 3)

    def test_load_all_site_vars_empty_directory(self):
        """Test loading all site variables from empty directory."""
        result = self.site_var_manager.load_all_site_vars()
        self.assertEqual(result, {})

    def test_load_all_site_vars_nonexistent_directory(self):
        """Test loading all site variables from nonexistent directory."""
        manager = SiteVarManager(source_dir="./nonexistent/path")
        result = manager.load_all_site_vars()
        self.assertEqual(result, {})

    def test_list_site_vars(self):
        """Test listing all available site variable names."""
        # Create test files
        test_files = ["var1.json", "var2.txt", "var3.json", "ignore.py"]

        for filename in test_files:
            filepath = os.path.join(self.temp_dir, filename)
            with open(filepath, "w") as f:
                f.write("content")

        result = self.site_var_manager.list_site_vars()

        expected = ["var1", "var2", "var3"]
        self.assertEqual(sorted(result), sorted(expected))

    def test_list_site_vars_empty_directory(self):
        """Test listing site variables from empty directory."""
        result = self.site_var_manager.list_site_vars()
        self.assertEqual(result, [])

    def test_list_site_vars_nonexistent_directory(self):
        """Test listing site variables from nonexistent directory."""
        manager = SiteVarManager(source_dir="./nonexistent/path")
        result = manager.list_site_vars()
        self.assertEqual(result, [])

    def test_find_file_path_json_exists(self):
        """Test finding file path when JSON file exists."""
        json_path = os.path.join(self.temp_dir, "test_var.json")
        with open(json_path, "w") as f:
            f.write("{}")

        result = self.site_var_manager._find_file_path("test_var")
        self.assertEqual(result, json_path)

    def test_find_file_path_txt_exists(self):
        """Test finding file path when TXT file exists."""
        txt_path = os.path.join(self.temp_dir, "test_var.txt")
        with open(txt_path, "w") as f:
            f.write("content")

        result = self.site_var_manager._find_file_path("test_var")
        self.assertEqual(result, txt_path)

    def test_find_file_path_json_precedence(self):
        """Test that JSON files take precedence over TXT files."""
        json_path = os.path.join(self.temp_dir, "test_var.json")
        txt_path = os.path.join(self.temp_dir, "test_var.txt")

        with open(txt_path, "w") as f:
            f.write("txt content")
        with open(json_path, "w") as f:
            f.write("{}")

        result = self.site_var_manager._find_file_path("test_var")
        self.assertEqual(result, json_path)

    def test_find_file_path_not_found(self):
        """Test finding file path when no file exists."""
        result = self.site_var_manager._find_file_path("nonexistent")
        self.assertIsNone(result)

    def test_load_file_content_txt_file(self):
        """Test loading content from TXT file."""
        txt_path = os.path.join(self.temp_dir, "test.txt")
        content = "This is plain text content"

        with open(txt_path, "w") as f:
            f.write(content)

        result = self.site_var_manager._load_file_content(txt_path)
        self.assertEqual(result, content)

    def test_load_file_content_json_file(self):
        """Test loading content from valid JSON file."""
        json_path = os.path.join(self.temp_dir, "test.json")
        content = '{"key": "value", "number": 42}'

        with open(json_path, "w") as f:
            f.write(content)

        result = self.site_var_manager._load_file_content(json_path)
        # The actual implementation returns parsed JSON object, not string
        expected = {"key": "value", "number": 42}
        self.assertEqual(result, expected)

    def test_load_file_content_invalid_json(self):
        """Test loading content from invalid JSON file."""
        json_path = os.path.join(self.temp_dir, "test.json")
        invalid_content = '{"key": "value", "unclosed": }'

        with open(json_path, "w") as f:
            f.write(invalid_content)

        result = self.site_var_manager._load_file_content(json_path)
        self.assertIsNone(result)

    def test_load_file_content_unsupported_file_type(self):
        """Test loading content from unsupported file type."""
        result = self.site_var_manager._load_file_content("test.py")
        self.assertIsNone(result)

    def test_load_file_content_file_not_found(self):
        """Test loading content from nonexistent file."""
        result = self.site_var_manager._load_file_content("./nonexistent/file.txt")
        self.assertIsNone(result)

    def test_load_from_file_success(self):
        """Test loading site variable from file successfully."""
        json_path = os.path.join(self.temp_dir, "test_var.json")
        content = {"test": "data"}

        with open(json_path, "w") as f:
            json.dump(content, f)

        result = self.site_var_manager._load_from_file("test_var")
        # The actual implementation returns parsed JSON object for .json files
        self.assertEqual(result, content)

    def test_load_from_file_not_found(self):
        """Test loading site variable from file when file doesn't exist."""
        result = self.site_var_manager._load_from_file("nonexistent")
        self.assertIsNone(result)

    def test_get_name_from_filename(self):
        """Test extracting name from filename."""
        test_cases = [
            ("test.json", "test"),
            ("test.txt", "test"),
            ("test.py", "test.py"),  # Unsupported extension
            ("no_extension", "no_extension"),
        ]

        for filename, expected in test_cases:
            result = self.site_var_manager._get_name_from_filename(filename)
            self.assertEqual(result, expected)

    def test_get_site_var_with_redis_connection_error(self):
        """Test handling of Redis connection error during get operation."""
        self.mock_redis.get.side_effect = redis.ConnectionError("Connection failed")

        json_content = '{"fallback": "data"}'
        with patch.object(
            self.site_var_manager, "_load_from_file", return_value=json_content
        ):
            result = self.site_var_manager.get_site_var("test_var")

            self.assertEqual(result, json_content)

    def test_get_site_var_with_redis_set_error(self):
        """Test handling of Redis set error during caching."""
        self.mock_redis.get.return_value = None
        self.mock_redis.set.side_effect = redis.RedisError("Set failed")

        json_content = '{"data": "value"}'
        with patch.object(
            self.site_var_manager, "_load_from_file", return_value=json_content
        ):
            result = self.site_var_manager.get_site_var("test_var")

            # Should still return the content even if caching fails
            self.assertEqual(result, json_content)

    def test_load_all_site_vars_with_redis_errors(self):
        """Test loading all site variables with Redis errors."""
        # Create test files
        test_files = {
            "var1.json": '{"key1": "value1"}',
            "var2.txt": "plain text content",
        }

        for filename, content in test_files.items():
            filepath = os.path.join(self.temp_dir, filename)
            with open(filepath, "w") as f:
                f.write(content)

        # Mock Redis to fail on get but succeed on set
        self.mock_redis.get.side_effect = redis.RedisError("Get failed")

        result = self.site_var_manager.load_all_site_vars()

        # The actual implementation returns parsed JSON objects for .json files
        expected = {"var1": {"key1": "value1"}, "var2": "plain text content"}
        self.assertEqual(result, expected)

    # ── Redis cache hit returning JSON value ──

    def test_redis_cache_hit_returns_parsed_json(self):
        """Test that a Redis cache hit with valid JSON returns the parsed dict."""
        cached_json = b'{"nested": {"key": "value"}, "count": 5}'
        self.mock_redis.get.return_value = cached_json

        result = self.site_var_manager.get_site_var("json_var")

        self.assertEqual(result, {"nested": {"key": "value"}, "count": 5})
        # Should also populate in-memory cache
        self.assertIn("json_var", self.site_var_manager._cache)
        self.assertEqual(
            self.site_var_manager._cache["json_var"],
            {"nested": {"key": "value"}, "count": 5},
        )

    # ── Redis cache hit returning plain text ──

    def test_redis_cache_hit_returns_plain_text(self):
        """Test that a Redis cache hit with non-JSON content returns the decoded string."""
        cached_text = b"This is plain text, not JSON"
        self.mock_redis.get.return_value = cached_text

        result = self.site_var_manager.get_site_var("text_var")

        self.assertEqual(result, "This is plain text, not JSON")
        # Should also populate in-memory cache
        self.assertIn("text_var", self.site_var_manager._cache)
        self.assertEqual(
            self.site_var_manager._cache["text_var"],
            "This is plain text, not JSON",
        )

    # ── Redis cache miss with file fallback ──

    def test_redis_cache_miss_falls_back_to_file(self):
        """Test that a Redis miss triggers file loading and caches the result."""
        self.mock_redis.get.return_value = None

        # Create a real file to load from
        json_path = os.path.join(self.temp_dir, "fallback_var.json")
        with open(json_path, "w") as f:
            json.dump({"from": "file"}, f)

        result = self.site_var_manager.get_site_var("fallback_var")

        self.assertEqual(result, {"from": "file"})
        # Should cache in Redis
        self.mock_redis.set.assert_called_once_with("fallback_var", '{"from": "file"}')
        # Should cache in memory
        self.assertIn("fallback_var", self.site_var_manager._cache)

    # ── Directory creation when source_dir doesn't exist ──

    def test_init_creates_source_dir_when_missing(self):
        """Test that __init__ creates the source directory if it doesn't exist."""
        nonexistent_dir = os.path.join(self.temp_dir, "new_subdir", "site_vars")
        self.assertFalse(os.path.exists(nonexistent_dir))

        SiteVarManager(source_dir=nonexistent_dir, enable_redis=False)

        self.assertTrue(os.path.exists(nonexistent_dir))
        # Clean up the created directory
        shutil.rmtree(os.path.join(self.temp_dir, "new_subdir"))

    # ── _load_from_file with .txt file extension ──

    def test_load_from_file_with_txt_extension(self):
        """Test that _load_from_file correctly loads and strips .txt file content."""
        txt_path = os.path.join(self.temp_dir, "my_text_var.txt")
        with open(txt_path, "w") as f:
            f.write("  some prompt text with whitespace  \n")

        result = self.site_var_manager._load_from_file("my_text_var")

        self.assertEqual(result, "some prompt text with whitespace")

    def test_load_from_file_returns_none_when_no_file(self):
        """Test that _load_from_file returns None when neither .json nor .txt exists."""
        result = self.site_var_manager._load_from_file("does_not_exist")
        self.assertIsNone(result)

    # ── evict_cache and get_cache_stats ──

    def test_evict_cache_clears_memory_cache(self):
        """Test that evict_cache clears the in-memory cache completely."""
        # Pre-populate the in-memory cache
        self.site_var_manager._cache["var_a"] = "value_a"
        self.site_var_manager._cache["var_b"] = {"key": "value_b"}

        self.site_var_manager.evict_cache()

        self.assertEqual(len(self.site_var_manager._cache), 0)

    def test_get_cache_stats_reflects_cache_size(self):
        """Test that get_cache_stats returns correct counts."""
        self.site_var_manager._cache["x"] = "1"
        self.site_var_manager._cache["y"] = "2"

        stats = self.site_var_manager.get_cache_stats()

        self.assertEqual(stats["cache_size"], 2)
        self.assertEqual(stats["cached_keys"], 2)

    # ── In-memory cache takes priority ──

    def test_in_memory_cache_hit_skips_redis_and_file(self):
        """Test that a value already in in-memory cache is returned without hitting Redis."""
        self.site_var_manager._cache["cached_var"] = {"already": "cached"}

        result = self.site_var_manager.get_site_var("cached_var")

        self.assertEqual(result, {"already": "cached"})
        # Redis should never be queried
        self.mock_redis.get.assert_not_called()

    # ── get_site_var generic exception path (lines 99-101) ──

    def test_get_site_var_generic_exception_returns_none(self):
        """Test that a non-Redis exception in get_site_var returns None."""
        # Force redis.get to raise a generic exception (not RedisError)
        self.mock_redis.get.side_effect = RuntimeError("unexpected failure")

        result = self.site_var_manager.get_site_var("test_var")

        self.assertIsNone(result)

    def test_get_site_var_generic_exception_does_not_cache(self):
        """Test that a generic exception does not populate the in-memory cache."""
        self.mock_redis.get.side_effect = RuntimeError("unexpected failure")

        self.site_var_manager.get_site_var("test_var")

        self.assertNotIn("test_var", self.site_var_manager._cache)

    # ── load_all_site_vars with inaccessible directory (lines 136-137, 153-155) ──

    def test_load_all_site_vars_permission_error(self):
        """Test load_all_site_vars handles exception when iterating directory."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.iterdir", side_effect=PermissionError("access denied")),
        ):
            result = self.site_var_manager.load_all_site_vars()

        self.assertEqual(result, {})

    # ── list_site_vars exception handling (lines 167, 175-177) ──

    def test_list_site_vars_exception_returns_empty(self):
        """Test that list_site_vars returns empty list on exception."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.iterdir", side_effect=OSError("cannot read directory")),
        ):
            result = self.site_var_manager.list_site_vars()

        self.assertEqual(result, [])

    # ── _load_file_content: unsupported file type (lines 225-228) ──

    def test_load_file_content_unsupported_extension_yaml(self):
        """Test that _load_file_content returns None for .yaml files."""
        yaml_path = os.path.join(self.temp_dir, "config.yaml")
        with open(yaml_path, "w") as f:
            f.write("key: value")

        result = self.site_var_manager._load_file_content(yaml_path)

        self.assertIsNone(result)

    def test_load_file_content_unsupported_extension_csv(self):
        """Test that _load_file_content returns None for .csv files."""
        csv_path = os.path.join(self.temp_dir, "data.csv")
        with open(csv_path, "w") as f:
            f.write("a,b,c")

        result = self.site_var_manager._load_file_content(csv_path)

        self.assertIsNone(result)

    # ── _load_file_content: OSError during read (lines 230-232) ──

    def test_load_file_content_os_error_on_txt_read(self):
        """Test that _load_file_content returns None when OSError occurs reading a .txt file."""
        txt_path = os.path.join(self.temp_dir, "broken.txt")
        with open(txt_path, "w") as f:
            f.write("content")

        with patch("pathlib.Path.open", side_effect=OSError("disk error")):
            result = self.site_var_manager._load_file_content(txt_path)

        self.assertIsNone(result)

    def test_load_file_content_os_error_on_json_read(self):
        """Test that _load_file_content returns None when OSError occurs reading a .json file."""
        json_path = os.path.join(self.temp_dir, "broken.json")
        with open(json_path, "w") as f:
            f.write('{"key": "val"}')

        with patch("pathlib.Path.open", side_effect=OSError("disk error")):
            result = self.site_var_manager._load_file_content(json_path)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
