"""Passwords, tokens, org-key encryption, CSRF, rate limiting and secure headers."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ---------------------------------------------------------------- passwords (Argon2id)

_hasher = PasswordHasher()  # argon2-cffi defaults: Argon2id, RFC 9106 low-memory profile
# Verified against when the email is unknown, so login time does not reveal whether an account exists.
_DUMMY_HASH = _hasher.hash("nazeer-dummy-password-for-timing")
PASSWORD_MIN, PASSWORD_MAX = 10, 128


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# ---------------------------------------------------------------- opaque tokens

def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """Only this goes into the database; a leaked table does not yield usable tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- organization keys

ORG_KEY_BYTES = 32


class KeyDecryptionError(RuntimeError):
    """The org key could not be decrypted (wrong master key or tampered row)."""


def new_org_key() -> bytes:
    return os.urandom(ORG_KEY_BYTES)


def _aad(org_id: str, key_version: int) -> bytes:
    # Binds the ciphertext to its row: a key copied to another organization does not decrypt.
    return f"nazeer-org-key:{org_id}:v{key_version}".encode("utf-8")


def encrypt_org_key(master_key: bytes, org_id: str, key_version: int, org_key: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(master_key).encrypt(nonce, org_key, _aad(org_id, key_version))


def decrypt_org_key(master_key: bytes, org_id: str, key_version: int, blob: bytes) -> bytes:
    try:
        return AESGCM(master_key).decrypt(blob[:12], blob[12:], _aad(org_id, key_version))
    except (InvalidTag, ValueError):
        raise KeyDecryptionError("organization key could not be decrypted") from None


# ---------------------------------------------------------------- CSRF (double submit)

CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def csrf_ok(cookie_value: str | None, header_value: str | None) -> bool:
    return bool(cookie_value) and bool(header_value) and hmac.compare_digest(cookie_value, header_value)


# ---------------------------------------------------------------- rate limiting

class RateLimiter:
    """In-process sliding window. Enough for one API instance; with several instances it must
    move to the database or a shared store (documented in docs/PROGRESS.md)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: float) -> float | None:
        """Record one attempt. Returns None if allowed, else seconds until the next allowed attempt."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_s:
                q.popleft()
            if len(q) >= limit:
                return max(1.0, q[0] + window_s - now)
            q.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# ---------------------------------------------------------------- secure headers

API_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}
HSTS = "max-age=31536000; includeSubDomains"
