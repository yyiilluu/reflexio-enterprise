import json

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from reflexio.utils.s3_utils import S3Utils

TEST_BUCKET = "test-bucket"
TEST_REGION = "us-east-1"
TEST_ACCESS_TEST = "my_access_key"
TEST_SECRET_KEY = "my_very_secret_key"  # noqa: S105
TEST_FILE_KEY = "test/file.json"
TEST_DATA = {"key": "value", "nested": {"data": [1, 2, 3]}}


@pytest.fixture
def s3_client():
    """Create a mock S3 client using moto."""
    with mock_aws():
        s3 = boto3.client("s3", region_name=TEST_REGION)
        s3.create_bucket(Bucket=TEST_BUCKET)
        yield s3


@pytest.fixture
def s3_utils(s3_client):
    """Create an S3Utils instance with mocked S3 client."""
    return S3Utils(
        s3_path=TEST_BUCKET,
        aws_region=TEST_REGION,
        aws_access_key=TEST_ACCESS_TEST,
        aws_secret_key=TEST_SECRET_KEY,
    )


class TestS3Utils:
    def test_init(self):
        """Test S3Utils initialization."""
        s3_utils = S3Utils(
            s3_path=TEST_BUCKET,
            aws_region=TEST_REGION,
            aws_access_key=TEST_ACCESS_TEST,
            aws_secret_key=TEST_SECRET_KEY,
        )
        assert s3_utils.s3_path == TEST_BUCKET
        assert s3_utils.s3_client.meta.region_name == TEST_REGION

    def test_read_json_success(self, s3_client, s3_utils):
        """Test successful JSON read from S3."""
        # Setup: Upload test data to mock S3
        s3_client.put_object(
            Bucket=TEST_BUCKET, Key=TEST_FILE_KEY, Body=json.dumps(TEST_DATA)
        )

        # Test
        result = s3_utils.read_json(TEST_FILE_KEY)
        assert result == TEST_DATA

    def test_read_json_nonexistent_file(self, s3_utils):
        """Test reading non-existent JSON file returns empty dict."""
        result = s3_utils.read_json("nonexistent.json")
        assert result == {}

    def test_read_json_invalid_json(self, s3_client, s3_utils):
        """Test reading invalid JSON file raises JSONDecodeError."""
        # Setup: Upload invalid JSON
        s3_client.put_object(Bucket=TEST_BUCKET, Key=TEST_FILE_KEY, Body="invalid json")

        # Test
        with pytest.raises(json.JSONDecodeError):
            s3_utils.read_json(TEST_FILE_KEY)

    def test_write_json_success(self, s3_utils):
        """Test successful JSON write to S3."""
        # Test
        result = s3_utils.write_json(TEST_FILE_KEY, TEST_DATA)
        assert result is True

        # Verify
        written_data = json.loads(
            s3_utils.s3_client.get_object(Bucket=TEST_BUCKET, Key=TEST_FILE_KEY)["Body"]
            .read()
            .decode("utf-8")
        )
        assert written_data == TEST_DATA

    def test_write_json_invalid_data(self, s3_utils):
        """Test writing non-serializable data raises TypeError."""
        with pytest.raises(TypeError):
            s3_utils.write_json(TEST_FILE_KEY, set())  # sets are not JSON serializable

    def test_file_exists_true(self, s3_client, s3_utils):
        """Test file_exists returns True for existing file."""
        # Setup
        s3_client.put_object(Bucket=TEST_BUCKET, Key=TEST_FILE_KEY, Body="test content")

        # Test
        assert s3_utils.file_exists(TEST_FILE_KEY) is True

    def test_file_exists_false(self, s3_utils):
        """Test file_exists returns False for non-existent file."""
        assert s3_utils.file_exists("nonexistent.json") is False

    def test_delete_file_success(self, s3_client, s3_utils):
        """Test successful file deletion."""
        # Setup
        s3_client.put_object(Bucket=TEST_BUCKET, Key=TEST_FILE_KEY, Body="test content")

        # Test
        result = s3_utils.delete_file(TEST_FILE_KEY)
        assert result is True

        # Verify
        with pytest.raises(ClientError) as exc_info:
            s3_client.head_object(Bucket=TEST_BUCKET, Key=TEST_FILE_KEY)
        assert exc_info.value.response["Error"]["Code"] == "404"

    def test_delete_nonexistent_file(self, s3_utils):
        """Test deleting non-existent file succeeds (idempotent operation)."""
        result = s3_utils.delete_file("nonexistent.json")
        assert result is True

    def test_list_files_empty(self, s3_utils):
        """Test listing files in empty bucket."""
        files = s3_utils.list_files()
        assert files == []

    def test_list_files_with_prefix(self, s3_client, s3_utils):
        """Test listing files with prefix filter."""
        # Setup: Create test files
        test_files = ["test/file1.json", "test/file2.json", "other/file3.json"]
        for file_key in test_files:
            s3_client.put_object(Bucket=TEST_BUCKET, Key=file_key, Body="test content")

        # Test
        files = s3_utils.list_files(prefix="test/")
        assert len(files) == 2
        assert all(f.startswith("test/") for f in files)
        assert "other/file3.json" not in files

    def test_get_file_metadata_success(self, s3_client, s3_utils):
        """Test getting file metadata."""
        # Setup
        test_content = "test content"
        s3_client.put_object(
            Bucket=TEST_BUCKET,
            Key=TEST_FILE_KEY,
            Body=test_content,
            ContentType="application/json",
            Metadata={"custom-key": "custom-value"},
        )

        # Test
        metadata = s3_utils.get_file_metadata(TEST_FILE_KEY)

        assert "last_modified" in metadata
        assert metadata["size"] == len(test_content)
        assert metadata["content_type"] == "application/json"
        assert metadata["metadata"] == {"custom-key": "custom-value"}

    def test_get_metadata_nonexistent_file(self, s3_utils):
        """Test getting metadata for non-existent file raises ClientError."""
        with pytest.raises(ClientError) as exc_info:
            s3_utils.get_file_metadata("nonexistent.json")
        assert exc_info.value.response["Error"]["Code"] == "404"


if __name__ == "__main__":
    pytest.main()
