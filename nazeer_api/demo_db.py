"""Demo only: read a few tables from a read-only database of fictional data.

The connection URL comes from the server environment (DEMO_DB_URL) and never leaves it: it is not
logged, not stored and not returned. Access is read-only twice over: the database user has SELECT
only, and this module issues nothing but SELECT on table names taken from the database's own catalog.
In real use Nazeer connects to the organization's databases from inside the organization.
"""
from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import create_engine, inspect, text

log = logging.getLogger("nazeer_api.demo_db")
MAX_ROWS = 20_000


class DemoDbError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _engine(url: str):
    return create_engine(url, pool_pre_ping=True, pool_recycle=300, connect_args={"connect_timeout": 10}
                         if url.startswith("mysql") else {})


def _quote(conn, name: str) -> str:
    return conn.dialect.identifier_preparer.quote(name)


def list_tables(url: str | None) -> list[dict]:
    if not url:
        raise DemoDbError("demo_db_unavailable")
    try:
        eng = _engine(url)
        with eng.connect() as conn:
            names = sorted(inspect(conn).get_table_names())
            out = [{"name": n, "rows": int(conn.execute(text(f"SELECT COUNT(*) FROM {_quote(conn, n)}")).scalar_one())}
                   for n in names]
        eng.dispose()
        return out
    except DemoDbError:
        raise
    except Exception as e:  # noqa: BLE001 - never echo the URL or the driver's message
        log.warning("demo database unreachable (%s)", type(e).__name__)
        raise DemoDbError("demo_db_unreachable") from None


def read_tables(url: str | None, wanted: list[str]) -> list[tuple[str, bytes]]:
    """Selected tables as CSV files, ready for the normal upload flow."""
    if not url:
        raise DemoDbError("demo_db_unavailable")
    try:
        eng = _engine(url)
        with eng.connect() as conn:
            known = set(inspect(conn).get_table_names())
            if not wanted or any(t not in known for t in wanted):
                raise DemoDbError("demo_db_unknown_table")
            files = []
            for t in wanted:
                df = pd.read_sql_query(text(f"SELECT * FROM {_quote(conn, t)} LIMIT {MAX_ROWS}"), conn)
                files.append((f"{t}.csv", df.astype(object).where(df.notna(), None).to_csv(index=False).encode("utf-8")))
        eng.dispose()
        return files
    except DemoDbError:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("demo database read failed (%s)", type(e).__name__)
        raise DemoDbError("demo_db_unreachable") from None
