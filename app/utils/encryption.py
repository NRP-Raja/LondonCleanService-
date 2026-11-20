"""CleanLondon Encryption Utilities — AES-256 Fernet for sensitive access data at rest."""

import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import JWT_SECRET_KEY


# ---------------------------------------------------------------------------
# Encryption Key Setup
# ---------------------------------------------------------------------------
_DATA_ENCRYPTION_KEY = os.getenv("DATA_ENCRYPTION_KEY")
if not _DATA_ENCRYPTION_KEY:
    # Deterministically derive 32-byte urlsafe base64 key from JWT_SECRET_KEY as fallback
    derived = hashlib.sha256(JWT_SECRET_KEY.encode("utf-8")).digest()
    _DATA_ENCRYPTION_KEY = base64.urlsafe_b64encode(derived).decode("utf-8")

_cipher_suite = Fernet(
    _DATA_ENCRYPTION_KEY.encode("utf-8")
    if isinstance(_DATA_ENCRYPTION_KEY, str)
    else _DATA_ENCRYPTION_KEY
)


# ---------------------------------------------------------------------------
# Encrypt / Decrypt
# ---------------------------------------------------------------------------
def encrypt_sensitive_data(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt sensitive customer access notes & PIN codes at rest (AES-256 Fernet)."""
    if not plaintext or not plaintext.strip():
        return plaintext
    try:
        return _cipher_suite.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        raise RuntimeError("Unable to encrypt sensitive access data") from exc


def decrypt_sensitive_data(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt sensitive customer access notes at rest."""
    if not ciphertext or not ciphertext.strip():
        return ciphertext
    try:
        return _cipher_suite.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Stored sensitive access data is not a valid encrypted value") from exc


# ---------------------------------------------------------------------------
# Staff Access Masking
# ---------------------------------------------------------------------------
def mask_access_notes_for_staff(
    status_val: str,
    encrypted_or_plain_notes: Optional[str],
) -> Optional[str]:
    """
    UK GDPR access-code masking:
    - While booking is SCHEDULED: cleaner sees masked notes (no PIN/key-safe code)
    - Once EN_ROUTE: full access notes revealed to assigned cleaner
    """
    if not encrypted_or_plain_notes:
        return None

    decrypted = decrypt_sensitive_data(encrypted_or_plain_notes)

    if status_val == "SCHEDULED":
        # Mask sensitive details: only show generic entry instructions
        masked_lines = []
        for line in decrypted.splitlines():
            line_lower = line.lower()
            if any(kw in line_lower for kw in ["pin", "code", "key safe", "keysafe", "door code"]):
                masked_lines.append("[Access code masked - revealed once cleaner is EN_ROUTE]")
            else:
                masked_lines.append(line)
        return "\n".join(masked_lines)

    return decrypted
