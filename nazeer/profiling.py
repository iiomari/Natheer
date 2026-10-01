"""Module 0: schema profiling. Infers column types, primary keys and foreign keys.

Input tables are all-string DataFrames (see tableio.py). Nothing here logs values.
"""
from __future__ import annotations

import difflib
import logging
import re

import pandas as pd

from nazeer.models import ColumnProfile, ColType, DatasetProfile, ForeignKey, TableProfile

log = logging.getLogger(__name__)

_ARABIC_LETTER = re.compile(r"[ء-يٱ-ۓ]")
_DATE_SHAPE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}([ T]\d{1,2}:\d{2}(:\d{2})?)?$")
_PK_NAME = re.compile(r"(^|_)id$", re.IGNORECASE)
_IDENTIFIER_NAME = re.compile(r"national|iqama|hawiya|mobile|phone|jawal|iban|email|هوية|جوال|اقامة|إقامة", re.IGNORECASE)

FREE_TEXT_MIN_MEAN_LEN = 30
FREE_TEXT_MIN_ARABIC_RATIO = 0.4
NUMERIC_MIN_PARSE_RATIO = 0.98
FK_MIN_CONTAINMENT = 0.99
FK_MIN_NAME_SIMILARITY = 0.5


def _arabic_ratio(values: pd.Series) -> float:
    text = "".join(values.astype(str))
    letters = sum(1 for ch in text if not ch.isspace())
    return len(_ARABIC_LETTER.findall(text)) / letters if letters else 0.0


def infer_dtype(values: pd.Series) -> tuple[ColType, float, float]:
    """(dtype, mean_len, arabic_ratio) for the non-null string values of one column."""
    if values.empty:
        return "short_text", 0.0, 0.0
    mean_len = float(values.str.len().mean())
    arabic = _arabic_ratio(values.head(2000))
    if pd.to_numeric(values, errors="coerce").notna().mean() >= NUMERIC_MIN_PARSE_RATIO:
        return "numeric", mean_len, arabic
    if values.head(500).str.match(_DATE_SHAPE).mean() >= 0.95:
        return "date", mean_len, arabic
    if mean_len > FREE_TEXT_MIN_MEAN_LEN and arabic >= FREE_TEXT_MIN_ARABIC_RATIO:
        return "free_text", mean_len, arabic
    n_unique = values.nunique()
    if n_unique <= max(20, int(0.05 * len(values))):
        return "categorical", mean_len, arabic
    return "short_text", mean_len, arabic


def _choose_primary_key(df: pd.DataFrame, table: str) -> str | None:
    """Among unique, non-null columns prefer an `id`-named, non-identifier, early column."""
    candidates = []
    for pos, col in enumerate(df.columns):
        s = df[col]
        if s.isna().any() or not s.is_unique:
            continue
        score = 0
        if _PK_NAME.search(col):
            score += 2
        if table.rstrip("s").lower() in col.lower():
            score += 1
        if pos == 0:
            score += 1
        if _IDENTIFIER_NAME.search(col):
            score -= 3  # a national ID can be unique, but it is personal data, not a surrogate key
        candidates.append((score, -pos, col))
    if not candidates:
        return None
    best = max(candidates)
    return best[2] if best[0] > 0 else None


def _name_similarity(child_col: str, parent_table: str, parent_col: str) -> float:
    a = child_col.lower()
    targets = [parent_col.lower(), f"{parent_table.rstrip('s').lower()}_{parent_col.lower()}",
               f"{parent_table.rstrip('s').lower()}_id"]
    return max(difflib.SequenceMatcher(None, a, t).ratio() for t in targets)


def infer_foreign_keys(tables: dict[str, pd.DataFrame], pks: dict[str, str | None]) -> list[ForeignKey]:
    fks = []
    for parent, pk in pks.items():
        if pk is None:
            continue
        parent_values = set(tables[parent][pk].dropna())
        for child, df in tables.items():
            if child == parent:
                continue
            for col in df.columns:
                if col == pks.get(child):
                    continue
                values = df[col].dropna()
                if values.empty:
                    continue
                containment = float(values.isin(parent_values).mean())
                if containment < FK_MIN_CONTAINMENT:
                    continue
                if _name_similarity(col, parent, pk) < FK_MIN_NAME_SIMILARITY:
                    continue
                fks.append(ForeignKey(child, col, parent, pk, round(containment, 4)))
    return fks


def profile_dataset(tables: dict[str, pd.DataFrame], db_fks: list[ForeignKey] | None = None) -> DatasetProfile:
    """Profile every table. `db_fks` (e.g. from a database catalog) override inference."""
    profiles: dict[str, TableProfile] = {}
    pks: dict[str, str | None] = {}
    for name, df in tables.items():
        pk = _choose_primary_key(df, name)
        pks[name] = pk
        cols = {}
        for col in df.columns:
            s = df[col]
            non_null = s.dropna()
            dtype, mean_len, arabic = infer_dtype(non_null)
            cols[col] = ColumnProfile(
                table=name, column=col, dtype=dtype, n_rows=len(s), n_null=int(s.isna().sum()),
                n_unique=int(non_null.nunique()), mean_len=round(mean_len, 2),
                arabic_ratio=round(arabic, 3), is_primary_key=(col == pk),
            )
        profiles[name] = TableProfile(name=name, n_rows=len(df), columns=cols, primary_key=pk)
    fks = db_fks if db_fks is not None else infer_foreign_keys(tables, pks)
    log.info("profiled %d tables, %d columns, %d foreign keys",
             len(profiles), sum(len(t.columns) for t in profiles.values()), len(fks))
    return DatasetProfile(tables=profiles, foreign_keys=fks)


def typed(df: pd.DataFrame, table: TableProfile, keep_as_text: set[str] = frozenset()) -> pd.DataFrame:
    """Convert numeric and date columns to real dtypes (identifier columns stay text)."""
    out = df.copy()
    for col, cp in table.columns.items():
        if col in keep_as_text:
            continue
        if cp.dtype == "numeric":
            out[col] = pd.to_numeric(out[col], errors="coerce")
        elif cp.dtype == "date":
            out[col] = pd.to_datetime(out[col], errors="coerce")
    return out
