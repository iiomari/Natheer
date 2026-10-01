"""API settings, read from the environment (or a local .env; real environment variables win).

Required: DATABASE_URL and NAZEER_MASTER_KEY. The app refuses to start without them.
Secrets are never logged and never included in responses or reports.
"""
from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ConfigError(RuntimeError):
    """A required setting is missing or malformed (message names the setting, never its value)."""


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name, "")
    items = [x.strip().rstrip("/") for x in raw.split(",") if x.strip()]
    return items or default


def decode_master_key(raw: str) -> bytes:
    """NAZEER_MASTER_KEY: 32 random bytes, base64 (urlsafe or standard) encoded."""
    raw = raw.strip()
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (binascii.Error, ValueError):
        raise ConfigError("NAZEER_MASTER_KEY is not valid base64") from None
    if len(key) != 32:
        raise ConfigError("NAZEER_MASTER_KEY must decode to exactly 32 bytes")
    return key


@dataclass(frozen=True)
class Settings:
    database_url: str
    master_key: bytes = field(repr=False)
    app_base_url: str = "http://localhost:3000"
    allowed_origins: tuple[str, ...] = ("http://localhost:3000",)
    # Optional: this project's Vercel preview URLs, e.g. ^https://nazeer-[a-z0-9-]+-myteam\.vercel\.app$
    allowed_origin_regex: str | None = None
    # Same-origin deployment: the browser talks only to the web origin, which proxies /api/* to this
    # API (Next.js rewrites). Cookies are therefore host-only (no Domain) and first-party.
    cookie_secure: bool = True
    cookie_domain: str | None = None
    trust_proxy: bool = False
    session_idle_days: int = 7
    session_max_days: int = 30
    mail_backend: str = "smtp"  # smtp | memory | console
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = field(default=None, repr=False)
    smtp_from: str = "Nazeer <no-reply@localhost>"
    smtp_starttls: bool = False
    # PEM text of the database server's CA (managed MySQL with TLS). Never logged.
    database_ca_pem: str | None = field(default=None, repr=False)
    # Persistent storage for encrypted twins and returned files (a mounted volume in production).
    storage_dir: str = "storage"
    job_stale_seconds: int = 300
    job_max_attempts: int = 3

    @property
    def cookie_prefix(self) -> str:
        # __Host- cookies must be Secure, Path=/ and carry no Domain: the strongest binding to one host.
        return "__Host-" if self.cookie_secure and not self.cookie_domain else ""

    @property
    def session_cookie(self) -> str:
        return f"{self.cookie_prefix}nz_session"

    @property
    def csrf_cookie(self) -> str:
        return f"{self.cookie_prefix}nz_csrf"


def load_settings(env_file: Path | None = None) -> Settings:
    from dotenv import load_dotenv

    load_dotenv(env_file or ROOT / ".env", override=False)
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise ConfigError("DATABASE_URL is not set")
    raw_key = os.environ.get("NAZEER_MASTER_KEY", "")
    if not raw_key.strip():
        raise ConfigError("NAZEER_MASTER_KEY is not set (32 random bytes, base64)")
    base = os.environ.get("APP_BASE_URL", "http://localhost:3000").rstrip("/")
    return Settings(
        database_url=url,
        master_key=decode_master_key(raw_key),
        app_base_url=base,
        allowed_origins=tuple(_list("ALLOWED_ORIGINS", [base])),
        allowed_origin_regex=os.environ.get("ALLOWED_ORIGIN_REGEX", "").strip() or None,
        cookie_secure=_flag("COOKIE_SECURE", True),
        cookie_domain=os.environ.get("COOKIE_DOMAIN", "").strip() or None,
        trust_proxy=_flag("TRUST_PROXY", False),
        mail_backend=os.environ.get("MAIL_BACKEND", "smtp").strip().lower(),
        smtp_host=os.environ.get("SMTP_HOST", "localhost"),
        smtp_port=int(os.environ.get("SMTP_PORT", "1025")),
        smtp_user=os.environ.get("SMTP_USER") or None,
        smtp_password=os.environ.get("SMTP_PASSWORD") or None,
        smtp_from=os.environ.get("SMTP_FROM", "Nazeer <no-reply@localhost>"),
        smtp_starttls=_flag("SMTP_STARTTLS", False),
        database_ca_pem=os.environ.get("DATABASE_CA_PEM") or None,
        storage_dir=os.environ.get("NAZEER_STORAGE_DIR", "storage"),
    )


def origin_allowed(settings: Settings, origin: str) -> bool:
    import re

    origin = origin.rstrip("/")
    if origin in settings.allowed_origins:
        return True
    return bool(settings.allowed_origin_regex and re.fullmatch(settings.allowed_origin_regex, origin))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
