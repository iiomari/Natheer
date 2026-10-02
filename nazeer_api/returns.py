"""P5: results returned by recipients, and admin-only re-linking to the real records.

No mapping table, ever. Re-linking needs the organization's original files again: the worker
re-runs the exact steps that made the twin (same ingest, same cleaning options, same detection,
the organization's key, the same overrides and fix), checks that this reproduces the stored twin's
key column value for value, and only then joins the returned results to the real keys, in memory.
The organization key and the pseudonym -> real key dictionary live only inside that one job.

nazeer_ref: every masked twin export carries, next to the entity key, a reference
"NZ-" + base32(HMAC(share secret, pseudonym)). It detects edited or swapped KEYS (and files from
another share); it does not detect edits to the recipient's result values.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
from datetime import timedelta

import pandas as pd

from nazeer_api.config import Settings
from nazeer_api.db import utcnow

log = logging.getLogger("nazeer_api.returns")

REF_COLUMN = "nazeer_ref"
REF_PREFIX = "NZ-"
REF_LEN = 12                 # base32 characters: 60 bits
MAX_REF_MISMATCH = 0.01      # more than 1% of rows with a wrong reference: tampering or corruption
MAX_OTHER_ERRORS = 0.05      # more than 5% of rows unusable for any other reason
RELINK_KINDS = ("relink_upload", "relinked")
_EXCEL_INT = re.compile(r"^(\d+)\.0+$")
_EXCEL_SCI = re.compile(r"^\d(\.\d+)?[eE]\+?\d+$")


class ReturnError(Exception):
    """code maps to an Arabic message; counts are value-free."""

    def __init__(self, code: str, **counts):
        super().__init__(code)
        self.code = code
        self.counts = counts


# ---------------------------------------------------------------- references

def ref_key(master_key: bytes, share_id: str) -> bytes:
    return hmac.new(master_key, b"nazeer-ref:" + share_id.encode(), hashlib.sha256).digest()


def make_ref(key: bytes, pseudonym: str) -> str:
    """Letters and digits 2-7 after a letter prefix: never read as a number or a date by Excel."""
    digest = hmac.new(key, str(pseudonym).encode("utf-8"), hashlib.sha256).digest()
    return REF_PREFIX + base64.b32encode(digest).decode("ascii")[:REF_LEN]


def link_of(twin) -> dict | None:
    """The entity key of a masked twin that results can be returned against, or None."""
    if twin.mode != "masked":
        return None
    return ((twin.report or {}).get("generation") or {}).get("link")


def add_refs(tables: dict[str, pd.DataFrame], link: dict | None, key: bytes) -> dict[str, pd.DataFrame]:
    if not link or link["table"] not in tables or link["column"] not in tables[link["table"]].columns:
        return tables
    out = dict(tables)
    df = tables[link["table"]].copy()
    if REF_COLUMN in df.columns:
        return tables
    refs = [make_ref(key, v) if isinstance(v, str) and v else None for v in df[link["column"]].tolist()]
    df.insert(df.columns.get_loc(link["column"]) + 1, REF_COLUMN, refs)
    out[link["table"]] = df
    return out


# ---------------------------------------------------------------- checking a returned file

def _cell(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


class _KeyIndex:
    """Find twin keys from a returned cell, tolerating what Excel does to number-like keys:
    "751233.0", dropped leading zeros, and 1.23457E+11 (matched only together with the reference)."""

    def __init__(self, keys: list[str]):
        self.keys = set(keys)
        self.no_zeros: dict[str, set[str]] = {}
        for k in self.keys:
            if k.isdigit():
                self.no_zeros.setdefault(k.lstrip("0") or "0", set()).add(k)

    def candidates(self, cell: str) -> tuple[set[str], bool]:
        """(matching twin keys, repaired?)."""
        if cell in self.keys:
            return {cell}, False
        m = _EXCEL_INT.match(cell)
        text = m.group(1) if m else cell
        if text in self.keys:
            return {text}, True
        if text.isdigit() and (text.lstrip("0") or "0") in self.no_zeros:
            return set(self.no_zeros[text.lstrip("0") or "0"]), True
        if _EXCEL_SCI.match(cell):
            x = float(cell)
            return {k for k in self.keys if k.isdigit() and abs(float(k) - x) <= abs(x) * 5e-6}, True
        return set(), False


def _find_column(df: pd.DataFrame, name: str) -> str | None:
    want = name.strip().lower()
    return next((c for c in df.columns if str(c).strip().lower() == want), None)


def check_return(twin_tables: dict[str, pd.DataFrame], link: dict, key: bytes,
                 files: list[tuple[str, bytes]]) -> tuple[pd.DataFrame, dict]:
    """Validate a returned results file against the shared twin. Returns (accepted rows with the
    twin key restored exactly, value-free stats) or raises ReturnError."""
    from nazeer.ingest import IngestError, read_files

    try:
        tables = read_files(files).tables
    except IngestError as e:
        raise ReturnError(f"ingest:{e.code}") from None
    table = next((df for df in tables.values() if _find_column(df, REF_COLUMN)), None)
    if table is None:
        raise ReturnError("return_missing_ref_column")
    key_col = _find_column(table, link["column"])
    if key_col is None:
        raise ReturnError("return_missing_key_column")
    ref_col = _find_column(table, REF_COLUMN)

    twin_keys = [k for k in twin_tables[link["table"]][link["column"]].tolist() if isinstance(k, str) and k]
    by_ref = {make_ref(key, k): k for k in twin_keys}
    index = _KeyIndex(twin_keys)

    rows = [(_cell(k), _cell(r)) for k, r in zip(table[key_col].tolist(), table[ref_col].tolist())]
    counts = {"ref_mismatch": 0, "unknown_key": 0, "missing_key": 0, "duplicate_key": 0}
    keep, restored, seen, repaired = [], [], set(), 0
    for i, (cell, ref) in enumerate(rows):
        if not cell:
            counts["missing_key"] += 1
            continue
        cands, fixed = index.candidates(cell)
        if not cands:
            counts["unknown_key"] += 1
            continue
        pseudonym = by_ref.get(ref.upper())
        if pseudonym is None or pseudonym not in cands:
            counts["ref_mismatch"] += 1
            continue
        if pseudonym in seen:
            counts["duplicate_key"] += 1
            continue
        seen.add(pseudonym)
        repaired += fixed
        keep.append(i)
        restored.append(pseudonym)
    total = len(rows)
    other = counts["unknown_key"] + counts["missing_key"] + counts["duplicate_key"]
    stats = {"rows_total": total, "rows_accepted": len(keep), "rejected": counts, "excel_repaired": repaired}
    if total == 0:
        raise ReturnError("return_empty", **stats)
    if counts["ref_mismatch"] > total * MAX_REF_MISMATCH:
        raise ReturnError("return_tampered", **stats)
    if other > total * MAX_OTHER_ERRORS:
        raise ReturnError("return_too_many_errors", **stats)
    if not keep:
        raise ReturnError("return_no_valid_rows", **stats)
    out = table.iloc[keep].drop(columns=[ref_col]).reset_index(drop=True)
    out[key_col] = restored
    if key_col != link["column"]:
        out = out.rename(columns={key_col: link["column"]})
    stats["columns"] = [str(c) for c in out.columns]
    return out, stats


# ---------------------------------------------------------------- re-linking (worker only)

def relink(db, settings: Settings, ret) -> dict:
    """Recompute the twin from the admin's original files, verify it, join, store the output for
    the session window. Raises ReturnError with a stable code on any mismatch."""
    from nazeer import pipeline
    from nazeer.cleaning import CleanOptions, clean
    from nazeer.ingest import IngestError, read_files
    from nazeer.policy import load_policy
    from nazeer_api.models import Blob, Organization
    from nazeer_api.processing import _upload_files, org_key
    from nazeer_api.storage import put_blob, read_blob, tables_to_zip, zip_to_tables

    twin = ret.twin
    gen = (twin.report or {}).get("generation") or {}
    link = gen.get("link")
    org = db.get(Organization, ret.org_id)
    if not link:
        raise ReturnError("relink_not_supported")
    if twin.key_version != org.key_version:
        raise ReturnError("relink_key_rotated")
    if twin.blob_id is None:
        raise ReturnError("relink_twin_purged")
    upload = db.get(Blob, ret.relink_upload_id) if ret.relink_upload_id else None
    if upload is None or upload.expires_at <= utcnow():
        raise ReturnError("relink_upload_expired")

    try:
        parsed = read_files(_upload_files(read_blob(settings.master_key, upload)))
    except IngestError as e:
        raise ReturnError(f"ingest:{e.code}") from None
    # Same files, same names, same rows: any other set changes detection and pseudonyms.
    expected = {s["table"]: s["rows"] for s in gen.get("source", [])}
    got = {n["table"]: n["rows"] for n in parsed.report()}
    if set(got) != set(expected):
        raise ReturnError("relink_tables_differ", tables_expected=len(expected), tables_uploaded=len(got))
    if got != expected:
        raise ReturnError("relink_rows_differ", rows_expected=sum(expected.values()), rows_uploaded=sum(got.values()))

    cleaned, _ = clean(parsed.tables, CleanOptions.from_dict(gen.get("cleaning")))
    del parsed
    an = pipeline.analyze(cleaned, gen.get("dataset_name", ""))
    key = org_key(settings, org)
    try:
        res = pipeline.run_masked(an, load_policy(pipeline.DEFAULT_POLICY), key, gen.get("overrides") or {},
                                  apply_fix=gen.get("apply_fix"))
    finally:
        del key
    t, c = link["table"], link["column"]
    stored = zip_to_tables(read_blob(settings.master_key, db.get(Blob, twin.blob_id)))
    if t not in res.twin or c not in res.twin[t].columns or t not in stored:
        raise ReturnError("relink_mismatch")
    recomputed = [_cell(v) for v in res.twin[t][c].tolist()]
    if recomputed != [_cell(v) for v in stored[t][c].tolist()]:
        raise ReturnError("relink_mismatch")

    real = an.tables[t][c].tolist()
    mapping = {p: r for p, r in zip(recomputed, real) if p}
    del an, res, cleaned, stored, recomputed, real

    returned = zip_to_tables(read_blob(settings.master_key, db.get(Blob, ret.blob_id)))["results"]
    linked = returned[c].map(mapping)
    matched = int(linked.notna().sum())
    out = returned.drop(columns=[c])
    out.insert(0, c, linked)
    del mapping, returned, linked

    old = db.get(Blob, ret.relinked_blob_id) if ret.relinked_blob_id else None
    if old is not None:
        db.delete(old)
    expires = utcnow() + timedelta(minutes=settings.session_minutes)
    blob = put_blob(db, settings.master_key, ret.org_id, "relinked", tables_to_zip({"results": out}), expires_at=expires)
    db.delete(upload)
    db.flush()
    ret.relink_upload_id, ret.relinked_blob_id, ret.relink_expires_at = None, blob.id, expires
    ret.relink_status, ret.relink_error, ret.relink_matched = "ready", None, matched
    ret.relink_downloads = 0
    return {"rows": len(out), "matched": matched, "unmatched": len(out) - matched}
