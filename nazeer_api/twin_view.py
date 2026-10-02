"""Twin viewer: one page of a twin table, server-side search / sort / pagination.

The twin holds no original value, so a short in-process cache of the decrypted twin (a few twins,
five minutes) keeps paging fast on large twins. Marks are cell positions only: replaced columns,
changed free-text cells, cells holding a value left for review.
"""
from __future__ import annotations

import threading
import time

import pandas as pd

from nazeer_api.storage import read_blob, zip_meta, zip_to_tables
from nazeer_api.tokens import INTERNAL_COLUMN, TOKEN_COLUMN

_CACHE: dict[str, tuple[float, dict, dict]] = {}
_LOCK = threading.Lock()
_TTL, _MAX = 300.0, 3
MAX_PAGE = 100


def load(master_key: bytes, blob) -> tuple[dict[str, pd.DataFrame], dict]:
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(blob.id)
        if hit and now - hit[0] < _TTL:
            return hit[1], hit[2]
    data = read_blob(master_key, blob)
    tables, meta = zip_to_tables(data), zip_meta(data)
    with _LOCK:
        _CACHE[blob.id] = (now, tables, meta.get("marks") or {})
        for k in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:-_MAX]:
            _CACHE.pop(k, None)
    return tables, meta.get("marks") or {}


def _numeric(s: pd.Series) -> pd.Series | None:
    n = pd.to_numeric(s.str.replace(",", "", regex=False), errors="coerce")
    return n if n.notna().mean() > 0.9 else None


def page(tables: dict[str, pd.DataFrame], marks: dict, table: str | None, page_no: int, size: int,
         q: str, sort: str | None, desc: bool, sealer=None) -> dict:
    names = list(tables)
    if not names:
        return {"tables": [], "table": None, "columns": [], "rows": [], "total": 0, "page": 1, "pages": 1}
    name = table if table in tables else names[0]
    df = tables[name]
    m = marks.get(name, {})
    view = df
    if q:
        needle = q.strip().lower()
        hay = df.drop(columns=[INTERNAL_COLUMN], errors="ignore").astype(str).apply(lambda col: col.str.lower())
        view = df[hay.apply(lambda col: col.str.contains(needle, regex=False)).any(axis=1)]
    if sort and sort in df.columns and sort != INTERNAL_COLUMN:
        col = view[sort].fillna("").astype(str)
        num = _numeric(col)
        order = (num if num is not None else col).sort_values(ascending=not desc, kind="stable").index
        view = view.loc[order]
    size = max(10, min(MAX_PAGE, size))
    total = len(view)
    pages = max(1, -(-total // size))
    page_no = min(max(1, page_no), pages)
    chunk = view.iloc[(page_no - 1) * size: page_no * size]
    cols = [c for c in df.columns if c != INTERNAL_COLUMN]
    has_token = INTERNAL_COLUMN in df.columns and sealer is not None and sealer.siv is not None
    replaced_cols = set(m.get("replaced_columns", []))
    changed = {c: set(rows) for c, rows in (m.get("changed_cells") or {}).items()}
    review = {c: set(rows) for c, rows in (m.get("review_cells") or {}).items()}
    out_rows = []
    for idx, rec in zip(chunk.index, chunk.to_dict("records")):
        row = int(idx)
        cells = {}
        for c in cols:
            v = rec.get(c)
            v = None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
            mark = "review" if row in review.get(c, ()) else (
                "replaced" if v is not None and (c in replaced_cols or row in changed.get(c, ())) else None)
            cells[c] = [v, mark]
        if has_token:
            cells[TOKEN_COLUMN] = [sealer.token_from_internal(rec[INTERNAL_COLUMN]), None]
        out_rows.append({"n": row + 1, "cells": cells})
    columns = ([TOKEN_COLUMN] if has_token else []) + cols
    return {"tables": [{"name": n, "rows": int(len(t))} for n, t in tables.items()], "table": name,
            "columns": columns, "replaced_columns": sorted(replaced_cols & set(cols)), "rows": out_rows,
            "total": total, "page": page_no, "pages": pages, "size": size}
