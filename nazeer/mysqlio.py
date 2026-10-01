"""MySQL input (read-only source) and output (a SEPARATE target database).

* Driver: SQLAlchemy + PyMySQL, always `charset=utf8mb4`.
* Credentials: environment variables NAZEER_MYSQL_HOST / _PORT / _USER / _PASSWORD,
  or a local `.env` (python-dotenv). Real environment variables win over `.env`.
  Credentials are never printed, logged or written to reports.
* Source: every session is a READ ONLY transaction and only SELECT is issued.
* Target: refused if it equals the source (case-insensitive) or is a system schema.
  Tables are created with the source's primary and foreign keys, utf8mb4 and
  utf8mb4_unicode_ci. Our sessions use STRICT_ALL_TABLES so a value that does not fit
  fails loudly instead of being truncated (the server itself may run non-strict).
"""
from __future__ import annotations

import datetime as _dt
import decimal
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from nazeer.models import ForeignKey

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER_PASSWORD = "CHANGE_ME"
SYSTEM_SCHEMAS = {"mysql", "information_schema", "performance_schema", "sys"}
_DB_NAME = re.compile(r"^[A-Za-z0-9_]{1,64}$")
SESSION_SQL_MODE = "STRICT_ALL_TABLES,NO_ENGINE_SUBSTITUTION"
CHARSET, COLLATION = "utf8mb4", "utf8mb4_unicode_ci"


class MySQLError(RuntimeError):
    """Base class; messages never contain credentials or data values."""


class CredentialsPending(MySQLError):
    """The password is still the CHANGE_ME placeholder."""


class UnsafeTarget(MySQLError):
    """Target database equals the source, is a system schema, or has an invalid name."""


@dataclass(frozen=True)
class MySQLSettings:
    host: str
    port: int
    user: str
    password: str = field(repr=False)

    def __str__(self) -> str:  # never reveal credentials
        return "MySQLSettings(<from environment>)"

    __repr__ = __str__


def load_settings(env_file: Path | None = None) -> MySQLSettings:
    from dotenv import load_dotenv

    load_dotenv(env_file or ROOT / ".env", override=False)  # real environment variables win
    password = os.environ.get("NAZEER_MYSQL_PASSWORD")
    if password is None or password == PLACEHOLDER_PASSWORD:
        raise CredentialsPending(
            "waiting for credentials: set NAZEER_MYSQL_PASSWORD in .env (or the environment); "
            "it is still the CHANGE_ME placeholder")
    return MySQLSettings(
        host=os.environ.get("NAZEER_MYSQL_HOST", "localhost"),
        port=int(os.environ.get("NAZEER_MYSQL_PORT", "3306")),
        user=os.environ.get("NAZEER_MYSQL_USER", "root"),
        password=password,  # an empty password is allowed (WAMP's default root account)
    )


def check_db_name(name: str) -> str:
    if not _DB_NAME.match(name or ""):
        raise UnsafeTarget("database names may contain only letters, digits and underscores (max 64)")
    return name


def check_target(source_db: str | None, target_db: str) -> str:
    check_db_name(target_db)
    if target_db.casefold() in SYSTEM_SCHEMAS:
        raise UnsafeTarget(f"refusing to write into the system schema {target_db!r}")
    if source_db is not None and target_db.casefold() == source_db.casefold():
        raise UnsafeTarget("refusing to write the twin into the SOURCE database; choose a separate target database")
    return target_db


def _q(identifier: str) -> str:
    return "`" + identifier.replace("`", "``") + "`"


def engine(settings: MySQLSettings, database: str | None = None):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    url = URL.create("mysql+pymysql", username=settings.user, password=settings.password, host=settings.host,
                     port=settings.port, database=database, query={"charset": CHARSET})
    return create_engine(url, pool_pre_ping=True, hide_parameters=True,
                         connect_args={"init_command": f"SET SESSION sql_mode='{SESSION_SQL_MODE}'"})


def ping(settings: MySQLSettings) -> str:
    """Server version string; raises MySQLError with a credential-free message."""
    from sqlalchemy import text

    try:
        with engine(settings).connect() as conn:
            return str(conn.execute(text("SELECT VERSION()")).scalar())
    except Exception as e:  # noqa: BLE001 - translate to a safe message
        raise MySQLError(f"cannot connect to MySQL ({type(e).__name__}); is the server running and are the "
                         "credentials in .env correct?") from None


# ---------------------------------------------------------------- read (source)

@dataclass
class SourceSchema:
    database: str
    columns: dict[str, list[tuple[str, str, bool]]]  # table -> [(column, COLUMN_TYPE, nullable)]
    primary_keys: dict[str, list[str]]
    foreign_keys: list[ForeignKey]


def _to_text(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, decimal.Decimal):
        return format(v, "f")
    if isinstance(v, _dt.datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, _dt.date):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def load_mysql(settings: MySQLSettings, database: str) -> tuple[dict[str, pd.DataFrame], SourceSchema]:
    """Read every base table as all-text DataFrames (same convention as CSV input). SELECT only."""
    from sqlalchemy import text

    check_db_name(database)
    with engine(settings, database).connect() as conn:
        conn.execute(text("SET SESSION TRANSACTION READ ONLY"))
        params = {"db": database}
        names = [r[0] for r in conn.execute(text(
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = :db AND TABLE_TYPE = 'BASE TABLE' "
            "ORDER BY TABLE_NAME"), params)]
        cols: dict[str, list[tuple[str, str, bool]]] = {n: [] for n in names}
        for t, c, ctype, nullable in conn.execute(text(
                "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :db ORDER BY TABLE_NAME, ORDINAL_POSITION"), params):
            if t in cols:
                cols[t].append((c, ctype, nullable == "YES"))
        pks: dict[str, list[str]] = {n: [] for n in names}
        fks: list[ForeignKey] = []
        for t, c, rt, rc, cname in conn.execute(text(
                "SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME, CONSTRAINT_NAME "
                "FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = :db "
                "ORDER BY TABLE_NAME, ORDINAL_POSITION"), params):
            if cname == "PRIMARY" and t in pks:
                pks[t].append(c)
            elif rt is not None:
                fks.append(ForeignKey(t, c, rt, rc, 1.0))
        tables = {}
        for n in names:
            rows = conn.execute(text(f"SELECT * FROM {_q(n)}"))
            df = pd.DataFrame(rows.fetchall(), columns=list(rows.keys()))
            tables[n] = df.apply(lambda s: s.map(_to_text)).astype(object) if len(df) else df.astype(object)
        conn.rollback()
    log.info("read %d tables (%d foreign keys) from MySQL database %s", len(tables), len(fks), database)
    return tables, SourceSchema(database, cols, pks, fks)


# ---------------------------------------------------------------- write (target)

_INT = re.compile(r"^(tinyint|smallint|mediumint|int|integer|bigint)\b", re.I)
_NUM = re.compile(r"^(decimal|numeric|float|double|real)\b", re.I)
_DATE = re.compile(r"^date$", re.I)
_DATETIME = re.compile(r"^(datetime|timestamp)\b", re.I)


def _fits(values: pd.Series, column_type: str) -> bool:
    vals = values.dropna().astype(str)
    if vals.empty:
        return True
    if _INT.match(column_type):
        return bool(vals.str.fullmatch(r"-?\d+").all())
    if _NUM.match(column_type):
        return bool(pd.to_numeric(vals, errors="coerce").notna().all())
    if _DATE.match(column_type):
        return bool(vals.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all())
    if _DATETIME.match(column_type):
        return bool(pd.to_datetime(vals, errors="coerce").notna().all())
    m = re.match(r"^(var)?char\((\d+)\)", column_type, re.I)
    if m:
        return int(vals.str.len().max()) <= int(m.group(2))
    return True  # text/blob/json etc.


def _infer_type(values: pd.Series) -> str:
    vals = values.dropna().astype(str)
    if vals.empty:
        return "VARCHAR(255)"
    if vals.str.fullmatch(r"-?\d{1,18}").all():
        return "BIGINT"
    if pd.to_numeric(vals, errors="coerce").notna().all():
        return "DOUBLE"
    if vals.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        return "DATE"
    longest = int(vals.str.len().max())
    return f"VARCHAR({max(32, min(255, longest * 2))})" if longest <= 255 else "TEXT"


def target_column_type(values: pd.Series, source_type: str | None) -> str:
    """Keep the source type when every twin value fits it (e.g. generalized ages no longer fit INT)."""
    if source_type and _fits(values, source_type):
        return source_type
    return _infer_type(values)


def _create_order(tables: list[str], fks: list[ForeignKey]) -> list[str]:
    order, pending = [], list(tables)
    while pending:
        ready = [t for t in pending if all(fk.parent_table in order or fk.parent_table not in tables
                                           for fk in fks if fk.child_table == t and fk.parent_table != t)]
        if not ready:  # cycle: keep remaining order, FKs are added afterwards anyway
            ready = pending[:]
        for t in ready:
            order.append(t)
            pending.remove(t)
    return order


def write_twin(settings: MySQLSettings, twin: dict[str, pd.DataFrame], target_db: str,
               source_db: str | None = None, source: SourceSchema | None = None,
               primary_keys: dict[str, str | None] | None = None,
               foreign_keys: list[ForeignKey] | None = None) -> dict:
    """Create `target_db` (utf8mb4/utf8mb4_unicode_ci), (re)create the twin tables with the same
    PKs/FKs and insert the rows. Refuses to touch the source database."""
    from sqlalchemy import text

    check_target(source_db or (source.database if source else None), target_db)
    pks = {t: (source.primary_keys.get(t) if source else None) or ([primary_keys[t]] if primary_keys and primary_keys.get(t) else [])
           for t in twin}
    fks = [fk for fk in (source.foreign_keys if source else (foreign_keys or []))
           if fk.child_table in twin and fk.parent_table in twin
           and fk.child_column in twin[fk.child_table].columns and fk.parent_column in twin[fk.parent_table].columns]
    src_types = {t: {c: ct for c, ct, _ in cols} for t, cols in (source.columns.items() if source else [])}

    with engine(settings).begin() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {_q(target_db)} CHARACTER SET {CHARSET} COLLATE {COLLATION}"))
    order = _create_order(list(twin), fks)
    summary = {"database": target_db, "tables": {}}
    with engine(settings, target_db).begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for t in reversed(order):
            conn.execute(text(f"DROP TABLE IF EXISTS {_q(t)}"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        for t in order:
            df = twin[t]
            defs = []
            for c in df.columns:
                ctype = target_column_type(df[c], src_types.get(t, {}).get(c))
                if c in pks[t] and re.match(r"^(text|blob)", ctype, re.I):
                    ctype = "VARCHAR(191)"
                defs.append(f"{_q(c)} {ctype}{' NOT NULL' if c in pks[t] else ''}")
            if pks[t]:
                defs.append("PRIMARY KEY (" + ", ".join(_q(c) for c in pks[t]) + ")")
            for i, fk in enumerate(f for f in fks if f.child_table == t):
                defs.append(f"CONSTRAINT {_q(f'fk_{t}_{fk.child_column}_{i}'[:64])} FOREIGN KEY ({_q(fk.child_column)}) "
                            f"REFERENCES {_q(fk.parent_table)} ({_q(fk.parent_column)})")
            conn.execute(text(f"CREATE TABLE {_q(t)} ({', '.join(defs)}) ENGINE=InnoDB "
                              f"DEFAULT CHARSET={CHARSET} COLLATE={COLLATION}"))
            if len(df):
                cols = list(df.columns)
                stmt = text(f"INSERT INTO {_q(t)} ({', '.join(_q(c) for c in cols)}) VALUES "
                            f"({', '.join(':p' + str(i) for i in range(len(cols)))})")
                records = [{f"p{i}": (None if pd.isna(v) else v) for i, v in enumerate(row)}
                           for row in df.itertuples(index=False, name=None)]
                for start in range(0, len(records), 1000):
                    conn.execute(stmt, records[start:start + 1000])
            summary["tables"][t] = {"rows": int(len(df)), "primary_key": pks[t],
                                    "foreign_keys": [f"{fk.child_column} -> {fk.parent_table}.{fk.parent_column}"
                                                     for fk in fks if fk.child_table == t]}
    log.info("wrote %d twin tables to MySQL database %s", len(twin), target_db)
    return summary
