"""Load the demo dataset into a MySQL "production" database (utf8mb4, PK/FK constraints).

    python -m data_gen.load_mysql                 # creates nazeer_prod_demo
    python -m data_gen.load_mysql --replace       # drop and recreate it

Credentials: NAZEER_MYSQL_* environment variables or .env (see .env.example).
This only ever creates/replaces the one demo database named on the command line.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

from nazeer import mysqlio
from nazeer.tableio import load_csv_folder

ROOT = Path(__file__).resolve().parents[1]

DDL = [
    """CREATE TABLE customers (
        customer_id INT NOT NULL,
        full_name   VARCHAR(100) NOT NULL,
        national_id VARCHAR(20)  NOT NULL,
        mobile      VARCHAR(20)  NOT NULL,
        city        VARCHAR(50)  NOT NULL,
        age         INT          NOT NULL,
        gender      VARCHAR(10)  NOT NULL,
        PRIMARY KEY (customer_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE claims (
        claim_id    INT NOT NULL,
        customer_id INT NOT NULL,
        claim_date  DATE NOT NULL,
        claim_type  VARCHAR(50) NOT NULL,
        amount      DECIMAL(12,2) NOT NULL,
        notes       TEXT,
        PRIMARY KEY (claim_id),
        CONSTRAINT fk_claims_customer FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
]


def load(database: str, demo_dir: Path, replace: bool) -> dict[str, int]:
    settings = mysqlio.load_settings()
    mysqlio.check_target(None, database)
    if not (demo_dir / "customers.csv").exists():
        from data_gen import make_demo_data
        make_demo_data.main(["--seed", "42", "--n", "3000", "--out", str(demo_dir)])
    tables = load_csv_folder(demo_dir, ["customers", "claims"])

    with mysqlio.engine(settings).begin() as conn:
        exists = conn.execute(text("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = :d"),
                              {"d": database}).scalar()
        if exists and not replace:
            raise SystemExit(f"database {database} already exists; use --replace to recreate it")
        if exists:
            conn.execute(text(f"DROP DATABASE {mysqlio._q(database)}"))
        conn.execute(text(f"CREATE DATABASE {mysqlio._q(database)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    with mysqlio.engine(settings, database).begin() as conn:
        for ddl in DDL:
            conn.execute(text(ddl))
        for name in ("customers", "claims"):  # parents first: FK checks stay on
            df = tables[name]
            cols = list(df.columns)
            stmt = text(f"INSERT INTO {name} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})")
            records = df.where(df.notna(), None).to_dict("records")
            for start in range(0, len(records), 1000):
                conn.execute(stmt, records[start:start + 1000])
    return {n: len(df) for n, df in tables.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--database", default="nazeer_prod_demo")
    ap.add_argument("--demo", type=Path, default=ROOT / "data" / "demo")
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args(argv)
    try:
        counts = load(args.database, args.demo, args.replace)
    except mysqlio.MySQLError as e:
        print(f"MySQL: {e}", file=sys.stderr)
        return 1
    print(f"loaded {args.database}: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
