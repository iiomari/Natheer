"""Alembic environment. The URL comes from DATABASE_URL (environment or .env), or from
`config.attributes["connection"]` / `-x url=...` (tests). It is never printed."""
from __future__ import annotations

import os

from alembic import context

from nazeer_api.config import ROOT, normalize_database_url
from nazeer_api.db import make_engine
from nazeer_api.models import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    from dotenv import load_dotenv

    x = context.get_x_argument(as_dictionary=True)
    if x.get("url"):
        return x["url"]
    load_dotenv(ROOT / ".env", override=False)
    url = normalize_database_url(os.environ.get("DATABASE_URL", ""))
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = make_engine(_url(), os.environ.get("DATABASE_CA_PEM") or None)
    try:
        with engine.connect() as conn:
            context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
