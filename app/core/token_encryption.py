"""Encrypt/decrypt social OAuth tokens at rest using Fernet (secret_key derived)."""

import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import get_settings

_FERNET: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    settings = get_settings()
    key_material = hashlib.sha256(settings.secret_key.encode()).digest()
    # Fernet needs 32 url-safe base64-encoded bytes
    derived = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"auto_viral_oauth_tokens",
        iterations=100000,
    ).derive(key_material)
    key = base64.urlsafe_b64encode(derived)
    _FERNET = Fernet(key)
    return _FERNET


def encrypt_token(plain: str) -> str:
    if not plain:
        return ""
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    if not encrypted:
        return ""
    return _get_fernet().decrypt(encrypted.encode()).decode()
