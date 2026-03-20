from unittest.mock import patch

from cryptography.fernet import Fernet

from reflexio.utils.encrypt_manager import EncryptManager

# ── Init tests ───────────────────────────────────────────────────────────────


def test_init_valid_single_key():
    key = Fernet.generate_key().decode()
    em = EncryptManager(key)
    assert em.multi_fernet is not None


def test_init_multiple_keys():
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()
    em = EncryptManager(f"{key1},{key2}")
    assert em.multi_fernet is not None


def test_init_empty_string():
    em = EncryptManager("")
    assert em.multi_fernet is None


def test_init_invalid_key():
    em = EncryptManager("invalid_key")
    assert em.multi_fernet is None


def test_init_mixed_valid_invalid():
    valid_key = Fernet.generate_key().decode()
    em = EncryptManager(f"{valid_key},invalid_key")
    assert em.multi_fernet is not None


# ── Encrypt tests ────────────────────────────────────────────────────────────


def test_encrypt_success():
    key = Fernet.generate_key().decode()
    em = EncryptManager(key)
    result = em.encrypt("secret")
    assert result is not None
    assert result != "secret"


def test_encrypt_no_fernet_passthrough():
    em = EncryptManager("")
    result = em.encrypt("secret")
    assert result == "secret"


def test_encrypt_exception():
    key = Fernet.generate_key().decode()
    em = EncryptManager(key)
    with patch.object(em.multi_fernet, "encrypt", side_effect=Exception("boom")):
        result = em.encrypt("secret")
    assert result is None


# ── Decrypt tests ────────────────────────────────────────────────────────────


def test_decrypt_success_roundtrip():
    key = Fernet.generate_key().decode()
    em = EncryptManager(key)
    encrypted = em.encrypt("hello world")
    assert encrypted is not None
    decrypted = em.decrypt(encrypted)
    assert decrypted == "hello world"


def test_decrypt_no_fernet_passthrough():
    em = EncryptManager("")
    result = em.decrypt("anything")
    assert result == "anything"


def test_decrypt_invalid_token():
    key = Fernet.generate_key().decode()
    em = EncryptManager(key)
    result = em.decrypt("not-a-valid-token")
    assert result is None


def test_decrypt_with_ttl():
    key = Fernet.generate_key().decode()
    em = EncryptManager(key)
    encrypted = em.encrypt("ttl_test")
    assert encrypted is not None
    decrypted = em.decrypt(encrypted, ttl=300)
    assert decrypted == "ttl_test"


# ── Rotate tests ─────────────────────────────────────────────────────────────


def test_rotate_success():
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()
    em = EncryptManager(f"{key1},{key2}")
    encrypted = em.encrypt("rotate me")
    assert encrypted is not None
    rotated = em.rotate(encrypted)
    assert rotated is not None
    decrypted = em.decrypt(rotated)
    assert decrypted == "rotate me"


def test_rotate_no_fernet_passthrough():
    em = EncryptManager("")
    result = em.rotate("anything")
    assert result == "anything"


def test_rotate_invalid_token():
    key = Fernet.generate_key().decode()
    em = EncryptManager(key)
    result = em.rotate("garbage-data")
    assert result is None
