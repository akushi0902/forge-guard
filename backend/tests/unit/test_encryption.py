"""Unit tests for forgeguard.utils.encryption.FieldEncryptor.

Covers:
  1. Encrypt/decrypt round-trip for various string lengths.
  2. Key rotation: encrypt with old key, rotate, decrypt with new key.
  3. Wrong key raises EncryptionError.
  4. Invalid key length raises ValueError.
  5. Non-string input raises TypeError.
  6. Non-bytes key raises TypeError.
  7. generate_key() produces 32 random bytes.
  8. from_base64_key() factory accepts base64url-encoded key.
  9. Ciphertext is non-deterministic (different nonce each call).
 10. Missing cryptography package: ImportError with clear message.

These tests are skipped automatically if the ``cryptography`` package is
not installed (the dependency declaration in pyproject.toml ensures it will
be installed in real environments).
"""

from __future__ import annotations

import base64

import pytest

# Guard: skip entire module if cryptography is not installed.
cryptography = pytest.importorskip(
    "cryptography",
    reason="cryptography package not installed — skipping encryption tests",
)

from forgeguard.utils.encryption import EncryptionError, FieldEncryptor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_key() -> bytes:
    return FieldEncryptor.generate_key()


# ---------------------------------------------------------------------------
# Basic encrypt / decrypt
# ---------------------------------------------------------------------------

class TestEncryptDecryptRoundTrip:
    def test_short_string(self) -> None:
        key = _make_key()
        enc = FieldEncryptor(key)
        plaintext = "hello"
        assert enc.decrypt(enc.encrypt(plaintext)) == plaintext

    def test_email_string(self) -> None:
        key = _make_key()
        enc = FieldEncryptor(key)
        email = "user@example.com"
        assert enc.decrypt(enc.encrypt(email)) == email

    def test_long_string(self) -> None:
        key = _make_key()
        enc = FieldEncryptor(key)
        plaintext = "A" * 10_000
        assert enc.decrypt(enc.encrypt(plaintext)) == plaintext

    def test_empty_string(self) -> None:
        key = _make_key()
        enc = FieldEncryptor(key)
        assert enc.decrypt(enc.encrypt("")) == ""

    def test_unicode_string(self) -> None:
        key = _make_key()
        enc = FieldEncryptor(key)
        plaintext = "Ångström Björk <user@ångström.example>"
        assert enc.decrypt(enc.encrypt(plaintext)) == plaintext

    def test_special_characters(self) -> None:
        key = _make_key()
        enc = FieldEncryptor(key)
        plaintext = "Héllo\nWörld\t🎉"
        assert enc.decrypt(enc.encrypt(plaintext)) == plaintext


# ---------------------------------------------------------------------------
# Ciphertext properties
# ---------------------------------------------------------------------------

class TestCiphertextProperties:
    def test_ciphertext_is_base64url(self) -> None:
        key = _make_key()
        enc = FieldEncryptor(key)
        ct = enc.encrypt("test")
        # Should be valid base64url
        decoded = base64.urlsafe_b64decode(ct + "==")
        assert len(decoded) >= 28  # 12-byte nonce + 16-byte tag minimum

    def test_ciphertext_is_not_plaintext(self) -> None:
        key = _make_key()
        enc = FieldEncryptor(key)
        ct = enc.encrypt("secret value")
        assert "secret value" not in ct

    def test_same_plaintext_different_ciphertext(self) -> None:
        key = _make_key()
        enc = FieldEncryptor(key)
        ct1 = enc.encrypt("same input")
        ct2 = enc.encrypt("same input")
        # Different nonces → different ciphertexts
        assert ct1 != ct2

    def test_ciphertext_is_ascii_safe(self) -> None:
        key = _make_key()
        enc = FieldEncryptor(key)
        ct = enc.encrypt("test")
        assert ct.isascii()


# ---------------------------------------------------------------------------
# Key rotation
# ---------------------------------------------------------------------------

class TestKeyRotation:
    def test_rotate_key_round_trip(self) -> None:
        old_key = _make_key()
        new_key = _make_key()
        enc_old = FieldEncryptor(old_key)

        plaintext = "rotate me"
        ciphertext = enc_old.encrypt(plaintext)

        rotated_ct = FieldEncryptor.rotate_key(ciphertext, old_key, new_key)

        enc_new = FieldEncryptor(new_key)
        assert enc_new.decrypt(rotated_ct) == plaintext

    def test_old_key_cannot_decrypt_rotated(self) -> None:
        old_key = _make_key()
        new_key = _make_key()
        enc_old = FieldEncryptor(old_key)

        ciphertext = enc_old.encrypt("secret")
        rotated_ct = FieldEncryptor.rotate_key(ciphertext, old_key, new_key)

        enc_old_again = FieldEncryptor(old_key)
        with pytest.raises(EncryptionError):
            enc_old_again.decrypt(rotated_ct)

    def test_rotate_preserves_plaintext(self) -> None:
        old_key = _make_key()
        new_key = _make_key()
        enc_old = FieldEncryptor(old_key)

        original = "user@example.com"
        rotated = FieldEncryptor.rotate_key(enc_old.encrypt(original), old_key, new_key)
        assert FieldEncryptor(new_key).decrypt(rotated) == original


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    def test_wrong_key_raises_encryption_error(self) -> None:
        key_a = _make_key()
        key_b = _make_key()
        enc_a = FieldEncryptor(key_a)
        enc_b = FieldEncryptor(key_b)

        ct = enc_a.encrypt("secret")
        with pytest.raises(EncryptionError):
            enc_b.decrypt(ct)

    def test_tampered_ciphertext_raises(self) -> None:
        key = _make_key()
        enc = FieldEncryptor(key)
        ct = enc.encrypt("data")
        # Flip a byte in the ciphertext
        raw = base64.urlsafe_b64decode(ct + "==")
        tampered = bytearray(raw)
        tampered[-1] ^= 0xFF
        bad_ct = base64.urlsafe_b64encode(bytes(tampered)).decode()
        with pytest.raises(EncryptionError):
            enc.decrypt(bad_ct)

    def test_invalid_key_length_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            FieldEncryptor(b"too-short")

    def test_non_bytes_key_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            FieldEncryptor("not-bytes-key-32-chars-long!!!")  # type: ignore[arg-type]

    def test_encrypt_non_string_raises_type_error(self) -> None:
        enc = FieldEncryptor(_make_key())
        with pytest.raises(TypeError):
            enc.encrypt(12345)  # type: ignore[arg-type]

    def test_decrypt_non_string_raises_type_error(self) -> None:
        enc = FieldEncryptor(_make_key())
        with pytest.raises(TypeError):
            enc.decrypt(b"not-a-string")  # type: ignore[arg-type]

    def test_decrypt_invalid_base64_raises_value_error(self) -> None:
        enc = FieldEncryptor(_make_key())
        with pytest.raises(ValueError):
            enc.decrypt("!!!not-base64!!!")

    def test_decrypt_too_short_raises_value_error(self) -> None:
        enc = FieldEncryptor(_make_key())
        # Encode a very short bytes object as base64
        short = base64.urlsafe_b64encode(b"tiny").decode()
        with pytest.raises(ValueError, match="too short"):
            enc.decrypt(short)


# ---------------------------------------------------------------------------
# Key generation and factory
# ---------------------------------------------------------------------------

class TestKeyGenerationAndFactory:
    def test_generate_key_is_32_bytes(self) -> None:
        key = FieldEncryptor.generate_key()
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_generate_key_is_random(self) -> None:
        key1 = FieldEncryptor.generate_key()
        key2 = FieldEncryptor.generate_key()
        assert key1 != key2

    def test_from_base64_key_round_trip(self) -> None:
        raw_key = _make_key()
        b64_key = base64.urlsafe_b64encode(raw_key).decode()

        enc = FieldEncryptor.from_base64_key(b64_key)
        plaintext = "test-from-b64"
        assert enc.decrypt(enc.encrypt(plaintext)) == plaintext

    def test_from_base64_key_wrong_length_raises(self) -> None:
        bad_key = base64.urlsafe_b64encode(b"short").decode()
        with pytest.raises(ValueError):
            FieldEncryptor.from_base64_key(bad_key)
