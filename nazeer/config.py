"""Runtime configuration: the secret key and the no-network guards.

The key is read from the NAZEER_KEY environment variable only. It is never
written to disk, logged, or included in any output.
"""
from __future__ import annotations

import os

KEY_ENV = "NAZEER_KEY"
MIN_KEY_LEN = 32

# Runtime must never reach the network with data. Model files are fetched once
# by scripts/download_models.py; after that everything loads from local cache.
OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}


class KeyConfigError(RuntimeError):
    """NAZEER_KEY is missing or too weak."""


def load_key() -> bytes:
    raw = os.environ.get(KEY_ENV, "")
    if not raw.strip():
        raise KeyConfigError(
            f"{KEY_ENV} is not set. In PowerShell: "
            f"$env:{KEY_ENV} = '<at least {MIN_KEY_LEN} random characters>'"
        )
    if len(raw) < MIN_KEY_LEN:
        raise KeyConfigError(f"{KEY_ENV} is too short; use at least {MIN_KEY_LEN} characters.")
    return raw.encode("utf-8")


def enforce_offline() -> None:
    """Force offline mode for Hugging Face libraries in this process."""
    os.environ.update(OFFLINE_ENV)
