"""
Tests for EncryptManager in reflexio.utils.encrypt_manager.

Covers:
1. Encrypt/decrypt roundtrip with valid Fernet keys
2. Initialization with empty, invalid, and mixed keys
3. Passthrough behavior when multi_fernet is None
4. Key rotation with valid and invalid tokens
5. Exception handling paths (InvalidToken, generic Exception)
6. TTL-based decryption
"""

import time
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from reflexio.utils.encrypt_manager import EncryptManager

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def fernet_key() -> str:
    """Generate a single valid Fernet key."""
    return Fernet.generate_key().decode("utf-8")


@pytest.fixture
def second_fernet_key() -> str:
    """Generate a second valid Fernet key for multi-key tests."""
    return Fernet.generate_key().decode("utf-8")


@pytest.fixture
def manager(fernet_key: str) -> EncryptManager:
    """Create an EncryptManager with a single valid key."""
    return EncryptManager(fernet_key)


@pytest.fixture
def multi_key_manager(fernet_key: str, second_fernet_key: str) -> EncryptManager:
    """Create an EncryptManager with two valid keys."""
    return EncryptManager(f"{fernet_key},{second_fernet_key}")


@pytest.fixture
def null_manager() -> EncryptManager:
    """Create an EncryptManager with no valid keys (multi_fernet is None)."""
    return EncryptManager("")


# =============================================================================
# Initialization Tests
# =============================================================================


class TestEncryptManagerInit:
    """Tests for EncryptManager initialization with various key configurations."""

    def test_init_with_valid_key(self, fernet_key: str):
        """Single valid key initializes multi_fernet successfully."""
        mgr = EncryptManager(fernet_key)
        assert mgr.multi_fernet is not None

    def test_init_with_multiple_valid_keys(self, fernet_key: str, second_fernet_key: str):
        """Comma-separated valid keys all get loaded."""
        mgr = EncryptManager(f"{fernet_key},{second_fernet_key}")
        assert mgr.multi_fernet is not None

    def test_init_with_empty_string(self):
        """Empty string leaves multi_fernet as None."""
        mgr = EncryptManager("")
        assert mgr.multi_fernet is None

    def test_init_with_only_whitespace(self):
        """Whitespace-only string leaves multi_fernet as None."""
        mgr = EncryptManager("   ")
        assert mgr.multi_fernet is None

    def test_init_with_invalid_key(self):
        """Invalid (non-base64) key is silently skipped; multi_fernet stays None."""
        mgr = EncryptManager("not-a-valid-fernet-key")
        assert mgr.multi_fernet is None

    def test_init_with_mixed_valid_and_invalid_keys(self, fernet_key: str):
        """Valid keys are kept and invalid keys are silently skipped."""
        mgr = EncryptManager(f"{fernet_key},bad-key,also-bad")
        assert mgr.multi_fernet is not None

    def test_init_with_mixed_valid_and_empty_keys(self, fernet_key: str):
        """Empty segments between commas are skipped; valid keys still work."""
        mgr = EncryptManager(f",, {fernet_key} ,,")
        assert mgr.multi_fernet is not None

    def test_init_with_all_invalid_keys(self):
        """All invalid keys leaves multi_fernet as None."""
        mgr = EncryptManager("bad1,bad2,bad3")
        assert mgr.multi_fernet is None

    def test_init_keys_stripped_of_whitespace(self, fernet_key: str):
        """Keys with surrounding whitespace are stripped and still work."""
        mgr = EncryptManager(f"  {fernet_key}  ")
        assert mgr.multi_fernet is not None


# =============================================================================
# Encrypt / Decrypt Roundtrip Tests
# =============================================================================


class TestEncryptDecryptRoundtrip:
    """Tests for encrypt/decrypt roundtrip fidelity."""

    def test_basic_roundtrip(self, manager: EncryptManager):
        """Encrypting then decrypting returns the original plaintext."""
        plaintext = "hello world"
        encrypted = manager.encrypt(plaintext)
        assert encrypted is not None
        assert encrypted != plaintext
        decrypted = manager.decrypt(encrypted)
        assert decrypted == plaintext

    def test_roundtrip_with_unicode(self, manager: EncryptManager):
        """Unicode strings survive the encrypt/decrypt roundtrip."""
        plaintext = "prix: 42 euros"
        encrypted = manager.encrypt(plaintext)
        assert encrypted is not None
        decrypted = manager.decrypt(encrypted)
        assert decrypted == plaintext

    def test_roundtrip_with_empty_string(self, manager: EncryptManager):
        """Empty string can be encrypted and decrypted."""
        encrypted = manager.encrypt("")
        assert encrypted is not None
        decrypted = manager.decrypt(encrypted)
        assert decrypted == ""

    def test_roundtrip_with_multi_key_manager(self, multi_key_manager: EncryptManager):
        """Multi-key manager encrypts with the first key and decrypts with any."""
        plaintext = "secret data"
        encrypted = multi_key_manager.encrypt(plaintext)
        assert encrypted is not None
        decrypted = multi_key_manager.decrypt(encrypted)
        assert decrypted == plaintext


# =============================================================================
# Null Manager (multi_fernet is None) Tests
# =============================================================================


class TestNullManager:
    """Tests for EncryptManager behavior when multi_fernet is None."""

    def test_encrypt_returns_value_as_is(self, null_manager: EncryptManager):
        """When multi_fernet is None, encrypt returns the plaintext unchanged."""
        assert null_manager.encrypt("hello") == "hello"

    def test_decrypt_returns_value_as_is(self, null_manager: EncryptManager):
        """When multi_fernet is None, decrypt returns the value unchanged."""
        assert null_manager.decrypt("hello") == "hello"

    def test_rotate_returns_value_as_is(self, null_manager: EncryptManager):
        """When multi_fernet is None, rotate returns the value unchanged."""
        assert null_manager.rotate("hello") == "hello"


# =============================================================================
# Key Rotation Tests
# =============================================================================


class TestRotate:
    """Tests for Fernet key rotation."""

    def test_rotate_valid_token(self, fernet_key: str, second_fernet_key: str):
        """Rotating a token encrypted with an old key re-encrypts with the primary key."""
        old_manager = EncryptManager(fernet_key)
        encrypted = old_manager.encrypt("rotate me")
        assert encrypted is not None

        # New manager with second key as primary, old key as fallback
        new_manager = EncryptManager(f"{second_fernet_key},{fernet_key}")
        rotated = new_manager.rotate(encrypted)
        assert rotated is not None
        assert rotated != encrypted

        # The rotated token should decrypt with the new manager
        decrypted = new_manager.decrypt(rotated)
        assert decrypted == "rotate me"

    def test_rotate_invalid_token_returns_none(self, manager: EncryptManager):
        """Rotating an invalid token returns None (InvalidToken path)."""
        result = manager.rotate("not-a-valid-fernet-token")
        assert result is None

    def test_rotate_token_from_unknown_key_returns_none(self, second_fernet_key: str):
        """Rotating a token from an unknown key returns None."""
        unknown_manager = EncryptManager(Fernet.generate_key().decode("utf-8"))
        encrypted = unknown_manager.encrypt("secret")
        assert encrypted is not None

        other_manager = EncryptManager(second_fernet_key)
        result = other_manager.rotate(encrypted)
        assert result is None


# =============================================================================
# TTL-Based Decryption Tests
# =============================================================================


class TestTTLDecryption:
    """Tests for TTL-based decryption."""

    def test_decrypt_within_ttl_succeeds(self, manager: EncryptManager):
        """Decrypting within the TTL window succeeds."""
        encrypted = manager.encrypt("ttl-test")
        assert encrypted is not None
        decrypted = manager.decrypt(encrypted, ttl=60)
        assert decrypted == "ttl-test"

    def test_decrypt_expired_ttl_returns_none(self, manager: EncryptManager):
        """Decrypting after TTL expiration returns None (InvalidToken path)."""
        encrypted = manager.encrypt("expired")
        assert encrypted is not None
        # Sleep long enough to guarantee the 1-second TTL has elapsed
        time.sleep(2)
        result = manager.decrypt(encrypted, ttl=1)
        assert result is None


# =============================================================================
# Exception Handling Tests
# =============================================================================


class TestExceptionHandling:
    """Tests for encrypt/decrypt error paths."""

    def test_decrypt_with_invalid_token_returns_none(self, manager: EncryptManager):
        """Decrypting a non-Fernet string returns None via InvalidToken."""
        result = manager.decrypt("garbage-token")
        assert result is None

    def test_decrypt_with_wrong_key_returns_none(self, fernet_key: str):
        """Decrypting with a different key returns None via InvalidToken."""
        mgr1 = EncryptManager(fernet_key)
        encrypted = mgr1.encrypt("secret")
        assert encrypted is not None

        mgr2 = EncryptManager(Fernet.generate_key().decode("utf-8"))
        result = mgr2.decrypt(encrypted)
        assert result is None

    def test_encrypt_exception_returns_none(self, manager: EncryptManager):
        """Encrypt returns None when an unexpected exception occurs."""
        with patch.object(
            manager.multi_fernet, "encrypt", side_effect=RuntimeError("boom")
        ):
            result = manager.encrypt("test")
        assert result is None

    def test_decrypt_generic_exception_returns_none(self, manager: EncryptManager):
        """Decrypt returns None when a generic (non-InvalidToken) exception occurs."""
        with patch.object(
            manager.multi_fernet, "decrypt", side_effect=RuntimeError("boom")
        ):
            result = manager.decrypt("anything")
        assert result is None

    def test_rotate_generic_exception_returns_none(self, manager: EncryptManager):
        """Rotate returns None when a generic (non-InvalidToken) exception occurs."""
        with patch.object(
            manager.multi_fernet, "rotate", side_effect=RuntimeError("boom")
        ):
            result = manager.rotate("anything")
        assert result is None
