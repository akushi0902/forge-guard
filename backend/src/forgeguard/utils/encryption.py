"""AES-256-GCM field-level encryption utility for ForgeGuard.

Provides the :class:`FieldEncryptor` class for encrypting and decrypting
individual string fields (email, name) before persisting them to the
database.  Key rotation is supported to enable periodic key cycling without
data loss.

Encryption scheme:
  - Algorithm: AES-256-GCM (authenticated encryption with associated data)
  - Key length: 32 bytes (256 bits)
  - Nonce: 12 bytes, randomly generated per encrypt() call
  - Output: ``base64url(nonce || ciphertext || tag)``
  - Key format: raw 32 bytes; loaded from base64-encoded environment variable

Security properties:
  - Each encryption call produces a different ciphertext (random nonce).
  - Authentication tag prevents tampering — decryption raises on modification.
  - Keys are never hardcoded; loaded from ``FIELD_ENCRYPTION_KEY`` env var.

Dependencies:
  cryptography >= 42.0 (``pip install cryptography``)

Usage::

    from forgeguard.utils.encryption import FieldEncryptor
    import base64, os

    key = base64.urlsafe_b64encode(os.urandom(32))  # generate once, store securely
    enc = FieldEncryptor(key)

    ciphertext = enc.encrypt("user@example.com")
    plaintext  = enc.decrypt(ciphertext)            # "user@example.com"

Key rotation::

    rotated = FieldEncryptor.rotate_key(ciphertext, old_key_bytes, new_key_bytes)
"""

from __future__ import annotations

import base64
import os
from typing import TYPE_CHECKING

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _CRYPTOGRAPHY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CRYPTOGRAPHY_AVAILABLE = False

_NONCE_SIZE = 12  # bytes — 96-bit nonce for AES-GCM
_KEY_SIZE = 32    # bytes — 256-bit key for AES-256


class EncryptionError(Exception):
    """Raised when decryption fails (wrong key, tampered ciphertext)."""


class FieldEncryptor:
    """AES-256-GCM symmetric encryptor for individual string fields.

    Args:
        key: Raw 32-byte encryption key.  Pass ``bytes`` directly.

    Raises:
        ImportError:  If the ``cryptography`` package is not installed.
        ValueError:   If the key is not exactly 32 bytes.
        TypeError:    If the key is not ``bytes``.
    """

    def __init__(self, key: bytes) -> None:
        if not _CRYPTOGRAPHY_AVAILABLE:
            raise ImportError(
                "The 'cryptography' package is required for FieldEncryptor. "
                "Install it with: pip install 'cryptography>=42.0'"
            )
        if not isinstance(key, bytes):
            raise TypeError(f"Encryption key must be bytes, got {type(key).__name__}")
        if len(key) != _KEY_SIZE:
            raise ValueError(
                f"Encryption key must be exactly {_KEY_SIZE} bytes ({_KEY_SIZE * 8} bits) "
                f"for AES-256-GCM.  Got {len(key)} bytes."
            )
        self._aesgcm = AESGCM(key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string to a base64url-encoded ciphertext.

        A fresh 12-byte nonce is generated for every call so the same
        plaintext produces different ciphertext each time.

        Args:
            plaintext: The string value to encrypt.

        Returns:
            Base64url-encoded string of ``nonce || ciphertext || tag``.

        Raises:
            TypeError: If ``plaintext`` is not a string.
        """
        if not isinstance(plaintext, str):
            raise TypeError(f"plaintext must be str, got {type(plaintext).__name__}")

        nonce = os.urandom(_NONCE_SIZE)
        data = plaintext.encode("utf-8")
        ciphertext_and_tag = self._aesgcm.encrypt(nonce, data, None)
        # Output: nonce (12 B) + ciphertext + authentication tag (16 B)
        return base64.urlsafe_b64encode(nonce + ciphertext_and_tag).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64url-encoded ciphertext back to the original string.

        Args:
            ciphertext: Base64url-encoded string produced by :meth:`encrypt`.

        Returns:
            The original plaintext string.

        Raises:
            TypeError:        If ``ciphertext`` is not a string.
            ValueError:       If the ciphertext is too short or malformed.
            EncryptionError:  If the authentication tag fails (wrong key or
                              data tampering).
        """
        if not isinstance(ciphertext, str):
            raise TypeError(f"ciphertext must be str, got {type(ciphertext).__name__}")

        try:
            raw = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        except Exception as exc:
            raise ValueError(f"ciphertext is not valid base64url: {exc}") from exc

        min_size = _NONCE_SIZE + 16  # nonce + AES-GCM tag (no payload)
        if len(raw) < min_size:
            raise ValueError(
                f"ciphertext is too short ({len(raw)} bytes); "
                f"expected at least {min_size} bytes."
            )

        nonce = raw[:_NONCE_SIZE]
        payload = raw[_NONCE_SIZE:]

        try:
            plaintext_bytes = self._aesgcm.decrypt(nonce, payload, None)
        except InvalidTag as exc:
            raise EncryptionError(
                "Decryption failed: authentication tag is invalid. "
                "The ciphertext may have been encrypted with a different key or tampered with."
            ) from exc

        return plaintext_bytes.decode("utf-8")

    @staticmethod
    def rotate_key(ciphertext: str, old_key: bytes, new_key: bytes) -> str:
        """Decrypt with the old key and re-encrypt with the new key.

        Used during key rotation to re-encrypt stored ciphertext without
        persisting the plaintext value.

        Args:
            ciphertext: Base64url-encoded ciphertext (encrypted with ``old_key``).
            old_key:    The 32-byte key used to encrypt ``ciphertext``.
            new_key:    The new 32-byte key to encrypt with.

        Returns:
            New base64url-encoded ciphertext (encrypted with ``new_key``).

        Raises:
            ValueError:      If either key is not 32 bytes.
            EncryptionError: If decryption with ``old_key`` fails.
        """
        old_encryptor = FieldEncryptor(old_key)
        new_encryptor = FieldEncryptor(new_key)
        plaintext = old_encryptor.decrypt(ciphertext)
        return new_encryptor.encrypt(plaintext)

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_base64_key(cls, b64_key: str) -> "FieldEncryptor":
        """Create a :class:`FieldEncryptor` from a base64-encoded key string.

        Args:
            b64_key: Base64url or standard base64 encoded 32-byte key.

        Returns:
            Configured :class:`FieldEncryptor` instance.

        Raises:
            ValueError: If the decoded key is not 32 bytes.
        """
        try:
            key_bytes = base64.urlsafe_b64decode(b64_key + "==")  # pad if needed
        except Exception as exc:
            raise ValueError(f"FIELD_ENCRYPTION_KEY is not valid base64: {exc}") from exc

        return cls(key_bytes)

    @classmethod
    def generate_key(cls) -> bytes:
        """Generate a cryptographically random 32-byte key.

        Returns:
            32 random bytes suitable for AES-256-GCM.

        Note:
            Store this key securely and never commit it to source control.
            Encode for environment variable storage::

                import base64
                key = FieldEncryptor.generate_key()
                print(base64.urlsafe_b64encode(key).decode())
        """
        return os.urandom(_KEY_SIZE)
