"""Per-row verification token ("رمز التحقق").

Every row of a shared masked twin carries a token in the column رمز_التحقق:

    NZ- + base32( header(4) || AES-SIV(org token key, plaintext, AD) )

    header     key version (1 byte) + share fingerprint (3 bytes, HMAC of the share id): lets a token
               from another share or organization be told apart from a damaged one. Reveals nothing
               about the row.
    plaintext  table index (1 byte, high bit = numeric key) + the original row's key: the primary
               key value of the original table, or, if the table has none, the row's position (1-based)
               after cleaning. Numeric keys are packed as integers to keep the token short.
    AD         share id | dataset id | key version. No row values are bound.

Recipients can neither read the key nor forge a token (AES-SIV under the organization's key).
Length: NZ- + about 40-60 characters (40 for a 6-digit key, 56 for a 10-character text key).
Excel-safe: letters A-Z and digits 2-7 after a letter prefix, never all digits, never e-notation.

Before a share exists the same reference is sealed WITHOUT the share binding (AD: dataset id | key
version) and kept inside the encrypted twin, in the internal column INTERNAL_COLUMN; exports
replace it with the share-bound token. This is the token itself, not a lookup table: without the
organization key it opens nothing, and no pseudonym -> real key pair is ever stored.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

TOKEN_COLUMN = "رمز_التحقق"
INTERNAL_COLUMN = "__nazeer_row_ref"
PREFIX = "NZ-"
HEADER = 4
_TOKEN_RE = re.compile(r"^NZ-[A-Z2-7]+$")
STATUSES = ("verified", "invalid", "missing", "foreign", "old_key", "duplicate")


def _siv(org_key: bytes) -> AESSIV:
    return AESSIV(HKDF(algorithm=hashes.SHA256(), length=64, salt=None, info=b"nazeer-row-token-v1").derive(org_key))


def share_fingerprint(master_key: bytes, share_id: str) -> bytes:
    """Stable across organization key rotation (master-key based), so old tokens are still recognised."""
    return hmac.new(master_key, b"nazeer-share-tag:" + share_id.encode(), hashlib.sha256).digest()[:3]


def _b32(data: bytes) -> str:
    return base64.b32encode(data).decode("ascii").rstrip("=")


def _unb32(text: str) -> bytes:
    return base64.b32decode(text + "=" * (-len(text) % 8))


def pack(table_idx: int, key: str) -> bytes:
    key = str(key)
    if not 0 <= table_idx < 128:
        raise ValueError("too many tables")
    if key.isdigit() and not (len(key) > 1 and key.startswith("0")) and len(key) <= 38:
        n = int(key)
        return bytes([table_idx | 0x80]) + n.to_bytes(max(1, (n.bit_length() + 7) // 8), "big")
    return bytes([table_idx]) + key.encode("utf-8")


def unpack(pt: bytes) -> tuple[int, str]:
    if not pt:
        raise ValueError("empty")
    head, body = pt[0], pt[1:]
    if head & 0x80:
        return head & 0x7F, str(int.from_bytes(body, "big"))
    return head, body.decode("utf-8")


def _ad(*parts) -> list[bytes]:
    return ["|".join(str(p) for p in parts).encode("utf-8")]


# ---------------------------------------------------------------- inside the twin (no share yet)

def seal_internal(org_key: bytes, dataset_id: str, key_version: int, table_idx: int, key: str) -> str:
    return _b32(_siv(org_key).encrypt(pack(table_idx, key), _ad("twin", dataset_id, key_version)))


class Sealer:
    """Re-seals internal references into share-bound tokens (one cipher setup per export)."""

    def __init__(self, org_key: bytes | None, master_key: bytes, dataset_id: str, key_version: int, share_id: str):
        """org_key None: the twin was made with a key the organization has since rotated."""
        self.siv = _siv(org_key) if org_key is not None else None
        self.dataset_id, self.key_version, self.share_id = dataset_id, key_version, share_id
        self.header = bytes([key_version % 256]) + share_fingerprint(master_key, share_id)

    def open_internal(self, ref: str) -> bytes:
        return self.siv.decrypt(_unb32(ref), _ad("twin", self.dataset_id, self.key_version))

    def token_for(self, pt: bytes) -> str:
        return PREFIX + _b32(self.header + self.siv.encrypt(pt, _ad(self.share_id, self.dataset_id, self.key_version)))

    def token_from_internal(self, ref: str) -> str:
        return self.token_for(self.open_internal(ref))

    # ---------------------------------------------------------------- verification

    def classify(self, raw, seen: set) -> tuple[str, bytes | None]:
        """(status, plaintext) for one returned cell. `seen` collects verified plaintexts (duplicates)."""
        if raw is None:
            return "missing", None
        text = str(raw).strip().upper().replace(" ", "")
        if text in ("", "NAN", "NONE"):
            return "missing", None
        if not _TOKEN_RE.match(text):
            return "invalid", None
        try:
            data = _unb32(text[len(PREFIX):])
        except (ValueError, base64.binascii.Error):
            return "invalid", None
        if _b32(data) != text[len(PREFIX):]:  # strict: the unused bits of the last character must be zero
            return "invalid", None
        if len(data) < HEADER + 16 + 2:
            return "invalid", None
        if data[1:HEADER] != self.header[1:]:
            return "foreign", None
        if data[0] != self.header[0]:
            return "invalid", None
        if self.siv is None:
            return "old_key", None
        try:
            pt = self.siv.decrypt(data[HEADER:], _ad(self.share_id, self.dataset_id, self.key_version))
        except InvalidTag:
            return "invalid", None
        if pt in seen:
            return "duplicate", pt
        seen.add(pt)
        return "verified", pt

    def open_token(self, token: str) -> bytes:
        """Plaintext of a share-bound token (raises on anything that does not verify)."""
        text = str(token).strip().upper().replace(" ", "")
        if not _TOKEN_RE.match(text) or self.siv is None:
            raise ValueError("token")
        data = _unb32(text[len(PREFIX):])
        if _b32(data) != text[len(PREFIX):] or data[:HEADER] != self.header:
            raise ValueError("token")
        return self.siv.decrypt(data[HEADER:], _ad(self.share_id, self.dataset_id, self.key_version))
