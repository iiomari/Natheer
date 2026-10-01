"""Database engine and sessions (MySQL in production and locally, SQLite in tests)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


def utcnow() -> datetime:
    """Naive UTC: MySQL DATETIME and SQLite both store it without surprises."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_fk(dbapi_conn, _):  # noqa: ANN001
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800)
    if engine.dialect.name == "mysql":
        @event.listens_for(engine, "connect")
        def _mysql_strict(dbapi_conn, _):  # noqa: ANN001
            # Same rule as nazeer.mysqlio: fail loudly instead of silently truncating.
            with dbapi_conn.cursor() as cur:
                cur.execute("SET SESSION sql_mode = 'STRICT_ALL_TABLES,NO_ENGINE_SUBSTITUTION'")
                cur.execute("SET time_zone = '+00:00'")
    return engine


def make_sessionmaker(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
