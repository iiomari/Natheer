"""Results returned by recipients, verified per row by the verification token, and admin-only
re-linking to the organization's own original data.

Principle: from a returned row Nazeer trusts only two things, the token (رمز_التحقق) and the columns
the recipient ADDED. Every original value in the re-linked output comes from the original file the
admin uploads at re-link time; the recipient's copy of the twin columns is ignored (it is only
compared, for information, to count rows the recipient changed).

No mapping table, ever: a verified token decrypts (org key, in memory) to its original row key,
which is joined with the uploaded original and then discarded. Reports hold row numbers, counts,
percentages and column names only.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta

import pandas as pd

from nazeer_api.config import Settings
from nazeer_api.db import utcnow
from nazeer_api.tokens import INTERNAL_COLUMN, STATUSES, TOKEN_COLUMN, Sealer, unpack

log = logging.getLogger("nazeer_api.returns")

ROW_LIST_CAP = 200          # row numbers listed per status in a report
STATUS_COLUMN = "حالة_الربط"
LINKED = "مرتبط"
NOT_IN_UPLOAD = "غير موجود في الملف الأصلي المرفوع"
RELINK_KINDS = ("relink_upload", "relinked")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


class ReturnError(Exception):
    """code maps to an Arabic message; counts are value-free."""

    def __init__(self, code: str, **counts):
        super().__init__(code)
        self.code = code
        self.counts = counts


# ---------------------------------------------------------------- tokens on the shared twin

def token_info(twin) -> dict | None:
    """Value-free token description of a masked twin (None for synthetic or pre-token twins)."""
    if twin.mode != "masked":
        return None
    return ((twin.report or {}).get("generation") or {}).get("token")


def sealer_for(settings: Settings, share) -> Sealer:
    from nazeer_api.processing import org_key

    twin, org = share.twin, share.org
    key = org_key(settings, org) if twin.key_version == org.key_version else None
    return Sealer(key, settings.master_key, twin.dataset_id, twin.key_version, share.id)


def strip_internal(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {n: (df.drop(columns=[INTERNAL_COLUMN]) if INTERNAL_COLUMN in df.columns else df) for n, df in tables.items()}


def tables_for_share(tables: dict[str, pd.DataFrame], sealer: Sealer) -> dict[str, pd.DataFrame]:
    """The twin as a recipient gets it: the internal reference becomes the share-bound token, first column."""
    out = {}
    for name, df in tables.items():
        if INTERNAL_COLUMN not in df.columns:
            out[name] = df
            continue
        df = df.copy()
        refs = df.pop(INTERNAL_COLUMN).tolist()
        if sealer.siv is not None:
            df.insert(0, TOKEN_COLUMN, [sealer.token_from_internal(r) for r in refs])
        out[name] = df
    return out


# ---------------------------------------------------------------- verifying a returned file

def _norm_name(c) -> str:
    return re.sub(r"[\s_]+", "_", str(c).strip())


def _token_col(df: pd.DataFrame) -> str | None:
    want = _norm_name(TOKEN_COLUMN)
    return next((c for c in df.columns if _norm_name(c) == want), None)


def _cell_text(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    t = str(v).strip().translate(_AR_DIGITS)
    m = re.fullmatch(r"(-?\d+)\.0+", t)
    return m.group(1) if m else t


def verify_return(settings: Settings, share, twin_tables: dict[str, pd.DataFrame],
                  files: list[tuple[str, bytes]]) -> tuple[dict[str, pd.DataFrame], dict]:
    """Classify every returned row. Returns (verified rows to keep: token + added columns, per
    twin table; value-free report). Raises ReturnError when nothing can be verified at all."""
    from nazeer.ingest import IngestError, read_files

    try:
        returned = read_files(files).tables
    except IngestError as e:
        raise ReturnError(f"ingest:{e.code}") from None
    sheets = [(n, df, _token_col(df)) for n, df in returned.items()]
    total_rows = int(sum(len(df) for _, df, _ in sheets))
    if not any(tc for _, _, tc in sheets):
        raise ReturnError("token_column_missing", rows_returned=total_rows)

    info = token_info(share.twin) or {}
    names = [t["name"] for t in info.get("tables", [])]
    sealer = sealer_for(settings, share)
    counts = {s: 0 for s in STATUSES}
    rows_by_status: dict[str, list[int]] = {s: [] for s in STATUSES if s != "verified"}
    seen: set[bytes] = set()
    kept: dict[str, list[dict]] = {}
    added: dict[str, list[str]] = {}
    verified_pts: dict[int, list[tuple[bytes, dict]]] = {}
    row_no = 0
    for _, df, tc in sheets:
        if tc is None:  # a sheet without tokens: all its rows count as missing
            for _ in range(len(df)):
                row_no += 1
                counts["missing"] += 1
                if len(rows_by_status["missing"]) < ROW_LIST_CAP:
                    rows_by_status["missing"].append(row_no)
            continue
        records = df.to_dict("records")
        for rec in records:
            row_no += 1
            status, pt = sealer.classify(rec.get(tc), seen)
            if status != "verified":
                counts[status] += 1
                if len(rows_by_status[status]) < ROW_LIST_CAP:
                    rows_by_status[status].append(row_no)
                continue
            idx, _ = unpack(pt)
            if idx >= len(names):
                counts["invalid"] += 1
                if len(rows_by_status["invalid"]) < ROW_LIST_CAP:
                    rows_by_status["invalid"].append(row_no)
                continue
            counts["verified"] += 1
            verified_pts.setdefault(idx, []).append((pt, {"__row": row_no, "__token": str(rec.get(tc)).strip().upper(), **rec}))

    differs = 0
    for idx, items in verified_pts.items():
        name = names[idx]
        twin_df = twin_tables.get(name)
        twin_cols = set(twin_df.columns) - {INTERNAL_COLUMN} if twin_df is not None else set()
        sample = items[0][1]
        extra = [c for c in sample if c not in ("__row", "__token") and _norm_name(c) != _norm_name(TOKEN_COLUMN)
                 and c not in twin_cols]
        added[name] = [str(c) for c in extra]
        # informational: rows whose copy of the twin columns differs from what was shared
        pos = {}
        if twin_df is not None and sealer.siv is not None and INTERNAL_COLUMN in twin_df.columns:
            for i, ref in enumerate(twin_df[INTERNAL_COLUMN].tolist()):
                try:
                    pos[sealer.open_internal(ref)] = i
                except Exception:  # noqa: BLE001
                    continue
        common = [c for c in sample if c in twin_cols]
        for pt, rec in items:
            i = pos.get(pt)
            if i is not None and any(_cell_text(rec.get(c)) != _cell_text(twin_df[c].iat[i]) for c in common):
                differs += 1
            kept.setdefault(name, []).append({"__row": rec["__row"], "__token": rec["__token"],
                                              **{c: rec.get(c) for c in extra}})
        del pos

    shared = sum(int(len(twin_tables[names[i]])) for i in verified_pts if names[i] in twin_tables) or \
        sum(int(t.get("rows", 0)) for t in info.get("tables", []))
    report = {
        "rows_returned": row_no,
        "rows_shared": shared,
        "coverage": round(row_no / shared, 4) if shared else None,
        "counts": counts,
        "integrity": round(counts["verified"] / row_no, 4) if row_no else 0.0,
        "rows_by_status": rows_by_status,
        "added_columns": added,
        "rows_changed_in_twin_columns": differs,
        "tables": [names[i] for i in sorted(verified_pts)],
    }
    tables = {n: pd.DataFrame(rows).astype(object) for n, rows in kept.items()}
    return tables, report


# ---------------------------------------------------------------- re-linking (worker only)

def _norm_key(v) -> str:
    t = _cell_text(v)
    t = re.sub(r"\s+", " ", t)
    if re.fullmatch(r"[\d,٬ ]+", t):
        t = re.sub(r"[,٬ ]", "", t)
    return t


def relink(db, settings: Settings, ret) -> dict:
    """Verified tokens -> original row keys (in memory) -> join with the uploaded original rows."""
    from nazeer.cleaning import CleanOptions, clean
    from nazeer.ingest import IngestError, read_files
    from nazeer_api.models import Blob
    from nazeer_api.processing import _upload_files
    from nazeer_api.storage import put_blob, read_blob, tables_to_zip, zip_to_tables

    share = ret.share
    info = token_info(share.twin)
    if not info:
        raise ReturnError("relink_not_supported")
    sealer = sealer_for(settings, share)
    if sealer.siv is None:
        raise ReturnError("relink_key_rotated")
    if not (ret.report or {}).get("counts", {}).get("verified"):
        raise ReturnError("relink_no_verified")
    upload = db.get(Blob, ret.relink_upload_id) if ret.relink_upload_id else None
    if upload is None or upload.expires_at <= utcnow():
        raise ReturnError("relink_upload_expired")
    try:
        originals = read_files(_upload_files(read_blob(settings.master_key, upload))).tables
    except IngestError as e:
        raise ReturnError(f"ingest:{e.code}") from None
    kept = zip_to_tables(read_blob(settings.master_key, db.get(Blob, ret.blob_id)))
    gen = (share.twin.report or {}).get("generation") or {}
    by_name = {t["name"]: t for t in info["tables"]}

    out_tables, matched, missing = {}, 0, 0
    for name, rows in kept.items():
        meta = by_name.get(name)
        if meta is None:
            continue
        org_df = originals.get(name)
        if org_df is None and len(originals) == 1:
            org_df = next(iter(originals.values()))
        if org_df is None:
            raise ReturnError("relink_table_missing", tables_expected=len(kept))
        key_col = meta.get("key_column")
        if key_col:
            col = next((c for c in org_df.columns if _norm_name(c) == _norm_name(key_col)), None)
            if col is None:
                raise ReturnError("relink_key_column_missing")
            index: dict[str, int] = {}
            for i, v in enumerate(org_df[col].tolist()):
                index.setdefault(_norm_key(v), i)
        else:
            # no key column: the reference is the row position after the twin's own cleaning
            cleaned, _ = clean({name: org_df}, CleanOptions.from_dict(gen.get("cleaning")))
            org_df = cleaned[name]
            index = {str(i + 1): i for i in range(len(org_df))}
        added = [c for c in rows.columns if c not in ("__row", "__token")]
        out_rows = []
        for rec in rows.to_dict("records"):
            try:
                _, key = unpack(sealer.open_token(rec["__token"]))
            except Exception:  # noqa: BLE001 - verified at return time; a later failure is excluded
                continue
            i = index.get(_norm_key(key) if key_col else key)
            row = {c: (org_df[c].iat[i] if i is not None else None) for c in org_df.columns}
            for c in added:
                row[c if c not in row else f"{c} (المستلم)"] = rec[c]
            row[STATUS_COLUMN] = LINKED if i is not None else NOT_IN_UPLOAD
            matched += i is not None
            missing += i is None
            out_rows.append(row)
        out_tables[name] = pd.DataFrame(out_rows).astype(object)
        del index
    del originals, kept

    old = db.get(Blob, ret.relinked_blob_id) if ret.relinked_blob_id else None
    if old is not None:
        db.delete(old)
    expires = utcnow() + timedelta(minutes=settings.session_minutes)
    blob = put_blob(db, settings.master_key, ret.org_id, "relinked", tables_to_zip(out_tables), expires_at=expires)
    db.delete(upload)
    db.flush()
    ret.relink_upload_id, ret.relinked_blob_id, ret.relink_expires_at = None, blob.id, expires
    ret.relink_status, ret.relink_error, ret.relink_matched = "ready", None, matched
    ret.relink_downloads = 0
    return {"rows": matched + missing, "matched": matched, "not_in_upload": missing}
