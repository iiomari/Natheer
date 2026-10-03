"""Seed the demo database tables (patients, appointments) at a given admin URL.

    python scripts\seed_demo_db.py --url <admin database URL>

The hosted API does this itself at startup when DEMO_DB_RO_PASSWORD is set (nazeer_api/demo_seed.py).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nazeer_api.demo_seed import DDL, build, write  # noqa: E402,F401


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("DEMO_DB_ADMIN_URL", ""))
    a = ap.parse_args(argv)
    if not a.url:
        raise SystemExit("set --url or DEMO_DB_ADMIN_URL")
    t = build()
    write(a.url, t)
    print({k: len(v) for k, v in t.items()})


if __name__ == "__main__":
    main()
