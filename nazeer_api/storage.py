"""Encrypted storage in the database, table (de)serialization, and safe exports.

Every stored byte (uploaded originals, parsed tables, twins) is zlib-compressed and then
AES-256-GCM encrypted with a per-organization storage key derived from NAZEER_MASTER_KEY (HKDF),
bound to the blob ID. Storage keys are separate from the organization's pseudonymization key.

Storage lives in MySQL (LONGBLOB) rather than on a disk: the API and the worker run as
separate services, and a volume can only attach to one of them.
"""
from __future__ import annotations

import io
import os
import re
import zipfile
import zlib
from datetime import datetime

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from nazeer_api.models import Blob, new_id


def _storage_key(master_key: bytes, org_id: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=f"nazeer-storage:{org_id}".encode()).derive(master_key)


def put_blob(db: DbSession, master_key: bytes, org_id: str, kind: str, data: bytes,
             expires_at: datetime | None = None, dataset_id: str | None = None) -> Blob:
    blob_id = new_id()
    nonce = os.urandom(12)
    sealed = nonce + AESGCM(_storage_key(master_key, org_id)).encrypt(nonce, zlib.compress(data, 6), blob_id.encode())
    blob = Blob(id=blob_id, org_id=org_id, dataset_id=dataset_id, kind=kind, size=len(sealed), data=sealed,
                expires_at=expires_at)
    db.add(blob)
    return blob


def read_blob(master_key: bytes, blob: Blob) -> bytes:
    raw = AESGCM(_storage_key(master_key, blob.org_id)).decrypt(blob.data[:12], blob.data[12:], blob.id.encode())
    return zlib.decompress(raw)


def org_usage_bytes(db: DbSession, org_id: str) -> int:
    return int(db.execute(select(func.coalesce(func.sum(Blob.size), 0)).where(Blob.org_id == org_id)).scalar_one())


# ---------------------------------------------------------------- tables <-> bytes

def tables_to_zip(tables: dict, meta: dict | None = None) -> bytes:
    """All-text tables as UTF-8 CSVs in a zip (table order and names kept). `meta`: value-free JSON
    stored next to them (e.g. the twin viewer's cell marks)."""
    import json

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("_order.txt", "\n".join(tables))
        if meta is not None:
            z.writestr("_meta.json", json.dumps(meta, ensure_ascii=False))
        for name, df in tables.items():
            z.writestr(f"{name}.csv", df.to_csv(index=False, lineterminator="\n"))
    return buf.getvalue()


def zip_meta(data: bytes) -> dict:
    import json

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return json.loads(z.read("_meta.json")) if "_meta.json" in z.namelist() else {}


def zip_to_tables(data: bytes) -> dict:
    import pandas as pd

    out = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.read("_order.txt").decode("utf-8").split("\n"):
            if name:
                with z.open(f"{name}.csv") as f:
                    out[name] = pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8")
    return out


# ---------------------------------------------------------------- exports (formula-injection safe)

_NUMBER = re.compile(r"^[+-]?(\d+([.,]\d+)?|\d{1,3}(,\d{3})+(\.\d+)?)$")
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value) -> str:
    """Neutralize spreadsheet formulas (CSV/Excel injection): a text cell that starts with
    = + - @ TAB or CR gets a leading apostrophe. Plain numbers such as -12.5 are left alone."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(_DANGEROUS) and not _NUMBER.match(text):
        return "'" + text
    return text


def export_csv_zip(tables: dict) -> bytes:
    import csv

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, df in tables.items():
            s = io.StringIO()
            w = csv.writer(s, lineterminator="\n")
            w.writerow([safe_cell(c) for c in df.columns])
            for row in df.itertuples(index=False, name=None):
                w.writerow([safe_cell(v) for v in row])
            z.writestr(f"{name}.csv", "﻿" + s.getvalue())  # BOM: Excel opens Arabic correctly
    return buf.getvalue()


def export_xlsx(tables: dict) -> bytes:
    from openpyxl import Workbook

    wb = Workbook(write_only=True)
    for name, df in tables.items():
        ws = wb.create_sheet(title=re.sub(r"[\[\]:*?/\\]", "_", name)[:31] or "sheet")
        ws.append([safe_cell(c) for c in df.columns])
        for row in df.itertuples(index=False, name=None):
            # Every value is written as text (data_type "s"), never as a formula.
            ws.append([safe_cell(v) for v in row])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
