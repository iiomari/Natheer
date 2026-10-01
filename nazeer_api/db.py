"""Database engine and sessions (MySQL in production and locally, SQLite in tests)."""
from __future__ import annotations

import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


def utcnow() -> datetime:
    """Naive UTC: MySQL DATETIME and SQLite both store it without surprises."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ca_file(pem: str) -> str:
    """PyMySQL wants a CA *file*; the platform gives the PEM as an env var. Content-addressed path."""
    path = Path(tempfile.gettempdir()) / f"nazeer-db-ca-{hashlib.sha256(pem.encode()).hexdigest()[:16]}.pem"
    if not path.exists():
        # Dashboards often store multi-line values with literal "\n" sequences.
        path.write_text(pem.replace("\\n", "\n"), encoding="utf-8")
    return str(path)


def make_engine(url: str, ca_pem: str | None = None) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_fk(dbapi_conn, _):  # noqa: ANN001
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    connect_args = {"ssl": {"ca": _ca_file(ca_pem)}} if ca_pem and url.startswith("mysql") else {}
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800, connect_args=connect_args)
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
