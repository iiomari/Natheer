"""Reading and writing table folders. MVP input: a folder of CSV files.

Everything is read as text: identifiers such as mobiles keep their leading zero,
and type inference happens in profiling.py, not in the CSV parser.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_csv_folder(folder: Path, names: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Load every *.csv in `folder` (or only `names`) as all-string DataFrames.

    The table name is the file stem. `utf-8-sig` also accepts files saved by Excel with a BOM.
    """
    folder = Path(folder)
    paths = sorted(folder.glob("*.csv")) if names is None else [folder / f"{n}.csv" for n in names]
    if not paths:
        raise FileNotFoundError(f"no CSV files in {folder}")
    return {p.stem: read_csv(p) for p in paths}


def read_csv(path_or_buffer) -> pd.DataFrame:
    return pd.read_csv(
        path_or_buffer, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8-sig"
    )


def write_csv_folder(tables: dict[str, pd.DataFrame], folder: Path) -> list[Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, df in tables.items():
        path = folder / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
        written.append(path)
    return written
