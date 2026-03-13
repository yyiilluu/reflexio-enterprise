"""
End-to-end tests for Claude client image encoding functionality.

These tests validate the image encoding and vision capabilities of the Claude client.
"""

import os
import struct
import tempfile
import zlib
from pathlib import Path

import pytest

from reflexio.server.llm.claude_client import (
    SUPPORTED_IMAGE_TYPES,
    ClaudeClient,
    ClaudeClientError,
    ClaudeConfig,
    create_image_content_block,
    encode_image_bytes_to_base64,
    encode_image_to_base64,
)
from reflexio.tests.server.test_utils import skip_in_precommit, skip_low_priority

# Skip all tests if ANTHROPIC_API_KEY is not set
pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY environment variable not set",
)


def _default_model() -> str:
    """Select a default test model that supports vision."""
    return os.getenv("ANTHROPIC_TEST_MODEL", "claude-3-5-haiku-20241022")


def create_minimal_png(
    width: int = 10, height: int = 10, color: tuple = (255, 0, 0)
) -> bytes:
    """
    Create a minimal valid PNG image in memory.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.
        color: RGB tuple for the fill color.

    Returns:
        PNG image as bytes.
    """

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk_len = struct.pack(">I", len(data))
        chunk_crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        return chunk_len + chunk_type + data + chunk_crc

    # PNG signature
    signature = b"\x89PNG\r\n\x1a\n"

    # IHDR chunk (image header)
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = png_chunk(b"IHDR", ihdr_data)

    # IDAT chunk (image data)
    # Create raw pixel data: filter byte (0) + RGB pixels for each row
    raw_data = b""
    for _ in range(height):
        raw_data += b"\x00"  # Filter byte (none)
        for _ in range(width):
            raw_data += bytes(color)

    compressed_data = zlib.compress(raw_data)
    idat = png_chunk(b"IDAT", compressed_data)

    # IEND chunk (image end)
    iend = png_chunk(b"IEND", b"")

    return signature + ihdr + idat + iend


@pytest.fixture
def claude_config() -> ClaudeConfig:
    """Create a basic Claude config for testing."""
    return ClaudeConfig(
        model=_default_model(),
        max_tokens=512,
        temperature=0.7,
        max_retries=2,
    )


@pytest.fixture
def claude_client(claude_config: ClaudeConfig) -> ClaudeClient:
    """Create a Claude client instance."""
    return ClaudeClient(claude_config)


@pytest.fixture
def test_image_bytes() -> bytes:
    """Create a test PNG image as bytes."""
    return create_minimal_png(width=50, height=50, color=(255, 0, 0))


@pytest.fixture
def test_image_file(test_image_bytes: bytes) -> str:
    """Create a temporary PNG image file."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(test_image_bytes)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestImageEncodingUtilities:
    """Test image encoding utility functions."""

    def test_encode_image_to_base64_from_file(self, test_image_file: str):
        """Test encoding an image file to base64."""
        base64_data, media_type = encode_image_to_base64(test_image_file)

        assert isinstance(base64_data, str)
        assert len(base64_data) > 0
        assert media_type == "image/png"

    def test_encode_image_to_base64_nonexistent_file(self):
        """Test that encoding a nonexistent file raises error."""
        with pytest.raises(ClaudeClientError, match="Image file not found"):
            encode_image_to_base64("/nonexistent/path/image.png")

    def test_encode_image_to_base64_unsupported_format(self, tmp_path: Path):
        """Test that unsupported format raises error."""
        unsupported_file = tmp_path / "test.bmp"
        unsupported_file.write_bytes(b"fake image data")

        with pytest.raises(ClaudeClientError, match="Unsupported image format"):
            encode_image_to_base64(str(unsupported_file))

    def test_encode_image_bytes_to_base64(self, test_image_bytes: bytes):
        """Test encoding image bytes to base64."""
        base64_data = encode_image_bytes_to_base64(test_image_bytes)

        assert isinstance(base64_data, str)
        assert len(base64_data) > 0

    def test_create_image_content_block_from_file(self, test_image_file: str):
        """Test creating an image content block from file."""
        content_block = create_image_content_block(test_image_file)

        assert content_block["type"] == "image"
        assert content_block["source"]["type"] == "base64"
        assert content_block["source"]["media_type"] == "image/png"
        assert len(content_block["source"]["data"]) > 0

    def test_create_image_content_block_from_bytes(self, test_image_bytes: bytes):
        """Test creating an image content block from bytes."""
        content_block = create_image_content_block(
            test_image_bytes, media_type="image/png"
        )

        assert content_block["type"] == "image"
        assert content_block["source"]["type"] == "base64"
        assert content_block["source"]["media_type"] == "image/png"
        assert len(content_block["source"]["data"]) > 0

    def test_create_image_content_block_bytes_without_media_type(
        self, test_image_bytes: bytes
    ):
        """Test that bytes without media_type raises error."""
        with pytest.raises(ClaudeClientError, match="media_type is required"):
            create_image_content_block(test_image_bytes)

    def test_supported_image_types(self):
        """Test that supported image types are correctly defined."""
        assert ".jpg" in SUPPORTED_IMAGE_TYPES
        assert ".jpeg" in SUPPORTED_IMAGE_TYPES
        assert ".png" in SUPPORTED_IMAGE_TYPES
        assert ".gif" in SUPPORTED_IMAGE_TYPES
        assert ".webp" in SUPPORTED_IMAGE_TYPES

        # Verify MIME types
        assert SUPPORTED_IMAGE_TYPES[".jpg"] == "image/jpeg"
        assert SUPPORTED_IMAGE_TYPES[".png"] == "image/png"


class TestClaudeClientImageVision:
    """Test Claude client image vision capabilities with real API calls."""

    @skip_in_precommit
    @skip_low_priority
    def test_generate_response_with_image_file(
        self, claude_client: ClaudeClient, test_image_file: str
    ):
        """Test generate_response with an image file."""
        prompt = (
            "Describe what you see in this image. Keep your response to one sentence."
        )

        response = claude_client.generate_response(
            prompt=prompt,
            images=[test_image_file],
        )

        assert isinstance(response, str)
        assert len(response) > 0
        # The image is a solid red square, expect some mention of color or simple shape
        response_lower = response.lower()
        assert any(
            word in response_lower
            for word in ["red", "color", "square", "image", "solid", "block", "pixel"]
        )

    @skip_in_precommit
    @skip_low_priority
    def test_generate_response_with_image_bytes(
        self, claude_client: ClaudeClient, test_image_bytes: bytes
    ):
        """Test generate_response with image bytes."""
        prompt = "What color is this image? Answer in one word."

        response = claude_client.generate_response(
            prompt=prompt,
            images=[test_image_bytes],
            image_media_type="image/png",
        )

        assert isinstance(response, str)
        assert len(response) > 0
        # Expect "red" or similar color description
        assert "red" in response.lower()

    @skip_in_precommit
    @skip_low_priority
    def test_generate_response_with_preformatted_image_block(
        self, claude_client: ClaudeClient, test_image_file: str
    ):
        """Test generate_response with a pre-formatted image content block."""
        image_block = create_image_content_block(test_image_file)
        prompt = "Is this image mostly one color? Answer yes or no."

        response = claude_client.generate_response(
            prompt=prompt,
            images=[image_block],
        )

        assert isinstance(response, str)
        assert "yes" in response.lower()

    @skip_in_precommit
    @skip_low_priority
    def test_generate_response_with_multiple_images(self, claude_client: ClaudeClient):
        """Test generate_response with multiple images."""
        # Create two different colored images
        red_image = create_minimal_png(20, 20, (255, 0, 0))
        blue_image = create_minimal_png(20, 20, (0, 0, 255))

        prompt = (
            "You are looking at two images. What colors are they? List both colors."
        )

        response = claude_client.generate_response(
            prompt=prompt,
            images=[red_image, blue_image],
            image_media_type="image/png",
        )

        assert isinstance(response, str)
        response_lower = response.lower()
        assert "red" in response_lower
        assert "blue" in response_lower

    @skip_in_precommit
    @skip_low_priority
    def test_generate_chat_response_with_image_content(
        self, claude_client: ClaudeClient, test_image_bytes: bytes
    ):
        """Test generate_chat_response with image content blocks."""
        image_block = create_image_content_block(
            test_image_bytes, media_type="image/png"
        )

        messages = [
            {
                "role": "user",
                "content": [
                    image_block,
                    {
                        "type": "text",
                        "text": "What color is this image? One word answer.",
                    },
                ],
            }
        ]

        response = claude_client.generate_chat_response(messages)

        assert isinstance(response, str)
        assert "red" in response.lower()

    @skip_in_precommit
    @skip_low_priority
    def test_generate_chat_response_multi_turn_with_image(
        self, claude_client: ClaudeClient, test_image_bytes: bytes
    ):
        """Test multi-turn conversation starting with an image."""
        image_block = create_image_content_block(
            test_image_bytes, media_type="image/png"
        )

        # First turn: describe the image
        messages = [
            {
                "role": "user",
                "content": [
                    image_block,
                    {"type": "text", "text": "Remember this image. What color is it?"},
                ],
            }
        ]

        response1 = claude_client.generate_chat_response(messages)
        assert isinstance(response1, str)
        assert "red" in response1.lower()

        # Second turn: follow-up question (without image)
        messages.append({"role": "assistant", "content": response1})
        messages.append(
            {
                "role": "user",
                "content": "What is the RGB value for that color? Give approximate values.",
            }
        )

        response2 = claude_client.generate_chat_response(messages)
        assert isinstance(response2, str)
        # Expect some mention of RGB values
        assert any(char.isdigit() for char in response2)

    @skip_in_precommit
    @skip_low_priority
    def test_generate_response_with_system_message_and_image(
        self, claude_client: ClaudeClient, test_image_bytes: bytes
    ):
        """Test generate_response with both system message and image."""
        prompt = "What do you see?"
        system_message = (
            "You are a color expert. Always respond with the exact color name."
        )

        response = claude_client.generate_response(
            prompt=prompt,
            system_message=system_message,
            images=[test_image_bytes],
            image_media_type="image/png",
        )

        assert isinstance(response, str)
        assert len(response) > 0

    @skip_in_precommit
    @skip_low_priority
    def test_image_with_json_response_format(
        self, claude_client: ClaudeClient, test_image_bytes: bytes
    ):
        """Test image analysis with structured JSON output."""
        prompt = """Analyze this image and return JSON with:
        - primary_color: the main color name
        - is_solid: true if the image is a solid color, false otherwise
        """

        response = claude_client.generate_response(
            prompt=prompt,
            system_message="Respond only with valid JSON.",
            images=[test_image_bytes],
            image_media_type="image/png",
            response_format={"type": "json_object"},
            parse_structured_output=True,
        )

        assert isinstance(response, dict)
        assert "primary_color" in response
        assert "red" in response["primary_color"].lower()
        assert response.get("is_solid") is True


class TestImageEncodingEdgeCases:
    """Test edge cases and error handling for image encoding."""

    def test_generate_response_empty_images_list(self, claude_client: ClaudeClient):
        """Test that empty images list behaves like no images."""
        prompt = "Say hello."

        # Empty list should be treated as no images
        response = claude_client.generate_response(prompt=prompt, images=[])

        assert isinstance(response, str)
        # With empty list, this falls through to text-only path
        # Empty list is falsy in Python, so images parameter is effectively None

    @skip_in_precommit
    @skip_low_priority
    def test_generate_response_mixed_image_types(self, claude_client: ClaudeClient):
        """Test generate_response with mixed image input types."""
        # Create images in different formats
        bytes_image = create_minimal_png(10, 10, (0, 255, 0))  # Green
        preformatted = create_image_content_block(
            create_minimal_png(10, 10, (0, 0, 255)),  # Blue
            media_type="image/png",
        )

        # Create a temp file for file-based image
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(create_minimal_png(10, 10, (255, 255, 0)))  # Yellow
            temp_path = f.name

        try:
            prompt = "List all the colors you see in these images."

            response = claude_client.generate_response(
                prompt=prompt,
                images=[bytes_image, preformatted, temp_path],
                image_media_type="image/png",
            )

            assert isinstance(response, str)
            response_lower = response.lower()
            # Should identify all three colors
            assert "green" in response_lower
            assert "blue" in response_lower
            assert "yellow" in response_lower
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_path_object_support(self, test_image_file: str):
        """Test that Path objects work for image encoding."""
        path_obj = Path(test_image_file)
        base64_data, media_type = encode_image_to_base64(path_obj)

        assert isinstance(base64_data, str)
        assert len(base64_data) > 0
        assert media_type == "image/png"

    def test_jpeg_extension_variants(self, tmp_path: Path):
        """Test both .jpg and .jpeg extensions are supported."""
        # Create fake JPEG files (just for extension testing, not valid JPEGs)
        jpg_file = tmp_path / "test.jpg"
        jpeg_file = tmp_path / "test.jpeg"

        # Write minimal valid JPEG (SOI and EOI markers)
        minimal_jpeg = bytes(
            [
                0xFF,
                0xD8,
                0xFF,
                0xE0,
                0x00,
                0x10,
                0x4A,
                0x46,
                0x49,
                0x46,
                0x00,
                0x01,
                0x01,
                0x00,
                0x00,
                0x01,
                0x00,
                0x01,
                0x00,
                0x00,
                0xFF,
                0xD9,
            ]
        )

        jpg_file.write_bytes(minimal_jpeg)
        jpeg_file.write_bytes(minimal_jpeg)

        # Both should be recognized as image/jpeg
        _, media_type_jpg = encode_image_to_base64(str(jpg_file))
        _, media_type_jpeg = encode_image_to_base64(str(jpeg_file))

        assert media_type_jpg == "image/jpeg"
        assert media_type_jpeg == "image/jpeg"
