import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3Utils:
    def __init__(
        self, s3_path: str, aws_region: str, aws_access_key: str, aws_secret_key: str
    ):
        """Initialize S3 utility class.

        Args:
            s3_path (str): Name of the S3 bucket and (optionally) paths under the bucket.
            aws_region (str): AWS region.
            aws_access_key (str): AWS access key.
            aws_secret_key (str): AWS secret key.
        """
        self.s3_path = s3_path
        self.s3_client = boto3.client(
            "s3",
            region_name=aws_region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
        )

    def read_json(self, file_key: str) -> dict:
        """Read JSON data from S3.

        Args:
            file_key (str): S3 object key for the JSON file

        Returns:
            dict: Parsed JSON data

        Raises:
            ClientError: If S3 operations fail
            json.JSONDecodeError: If JSON parsing fails
        """
        try:
            response = self.s3_client.get_object(Bucket=self.s3_path, Key=file_key)
            json_content = response["Body"].read().decode("utf-8")
            return json.loads(json_content)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.warning("File %s not found in bucket %s", file_key, self.s3_path)
                return {}
            logger.error("Error reading from S3: %s", str(e))
            raise
        except json.JSONDecodeError as e:
            logger.error("Error parsing JSON from %s: %s", file_key, str(e))
            raise

    def write_json(self, file_key: str, data: Any) -> bool:
        """Write JSON data to S3.

        Args:
            file_key (str): S3 object key for the JSON file
            data (Any): Data to be written as JSON

        Returns:
            bool: True if successful, False otherwise

        Raises:
            ClientError: If S3 operations fail
        """
        try:
            json_data = json.dumps(data)
            self.s3_client.put_object(
                Bucket=self.s3_path,
                Key=file_key,
                Body=json_data,
                ContentType="application/json",
            )
            return True
        except ClientError as e:
            logger.error("Error writing to S3: %s", str(e))
            raise
        except TypeError as e:
            logger.error("Error serializing JSON: %s", str(e))
            raise

    def file_exists(self, file_key: str) -> bool:
        """Check if a file exists in S3.

        Args:
            file_key (str): S3 object key to check

        Returns:
            bool: True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(Bucket=self.s3_path, Key=file_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            logger.error("Error checking file existence in S3: %s", str(e))
            raise

    def delete_file(self, file_key: str) -> bool:
        """Delete a file from S3.

        Args:
            file_key (str): S3 object key to delete

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=self.s3_path, Key=file_key)
            return True
        except ClientError as e:
            logger.error("Error deleting file from S3: %s", str(e))
            raise

    def list_files(self, prefix: str = "") -> list[str]:
        """List files in S3 bucket with given prefix.

        Args:
            prefix (str, optional): Prefix to filter objects. Defaults to ''.

        Returns:
            list[str]: List of file keys
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.s3_path, Prefix=prefix
            )
            if "Contents" not in response:
                return []
            return [obj["Key"] for obj in response["Contents"]]
        except ClientError as e:
            logger.error("Error listing files in S3: %s", str(e))
            raise

    def get_file_metadata(self, file_key: str) -> dict:
        """Get metadata for a file in S3.

        Args:
            file_key (str): S3 object key

        Returns:
            dict: File metadata
        """
        try:
            response = self.s3_client.head_object(Bucket=self.s3_path, Key=file_key)
            return {
                "last_modified": response["LastModified"],
                "size": response["ContentLength"],
                "content_type": response.get("ContentType", ""),
                "metadata": response.get("Metadata", {}),
            }
        except ClientError as e:
            logger.error("Error getting file metadata from S3: %s", str(e))
            raise
