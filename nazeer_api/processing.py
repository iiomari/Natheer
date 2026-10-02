"""Worker-side processing: ingest + detect, generate a twin, and the retention sweep.

Originals principle: the uploaded files and the parsed tables exist only as encrypted blobs that
expire with the dataset's processing session (NAZEER_SESSION_MINUTES, 30 by default) or as soon as
the user ends the session. The sweep deletes them; nothing else ever holds them. What is kept is
value-free: structure, detection tags, counts and span offsets, and the twin.
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from nazeer_api.config import Settings
from nazeer_api.db import utcnow
from nazeer_api.models import Blob, Dataset, Organization, Share, Twin
from nazeer_api.security import decrypt_org_key
from nazeer_api.storage import put_blob, read_blob, tables_to_zip, zip_to_tables

log = logging.getLogger("nazeer_api.processing")
N_NOTES = 12


class ProcessingError(RuntimeError):
    """code is stable and maps to an Arabic message in the web app."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def originals_blob(db: DbSession, dataset_id: str, kind: str) -> Blob | None:
    return db.execute(select(Blob).where(Blob.dataset_id == dataset_id, Blob.kind == kind)).scalar_one_or_none()


def load_tables(db: DbSession, settings: Settings, ds: Dataset) -> dict:
    blob = originals_blob(db, ds.id, "tables")
    if blob is None or ds.originals_deleted_at is not None or ds.session_expires_at <= utcnow():
        raise ProcessingError("session_expired")
    return zip_to_tables(read_blob(settings.master_key, blob))


# ---------------------------------------------------------------- ingest + detect

def _upload_files(data: bytes) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = json.loads(z.read("_names.json"))
        return [(name, z.read(f"f{i}")) for i, name in enumerate(names)]


def pack_upload(files: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.writestr("_names.json", json.dumps([n for n, _ in files], ensure_ascii=False))
        for i, (_, data) in enumerate(files):
            z.writestr(f"f{i}", data)
    return buf.getvalue()


def detection_summary(an, ingest_notes: list[dict]) -> dict:
    """Everything the review screens need, without a single data value (names, tags, offsets)."""
    from collections import Counter

    from nazeer import ui_logic as ui

    cols_by_table: dict = {}
    for d in an.detections:
        cp = an.profile.column(d.table, d.column)
        cols_by_table.setdefault(d.table, []).append({
            "name": d.column, "dtype": cp.dtype, "tag": d.tag, "kind": d.kind, "confidence": round(d.score, 2),
            "needs_review": d.needs_review, "reason": d.reason, "nulls": cp.n_null, "unique": cp.n_unique})
    summary_counts = ui.detection_summary(an, None)
    cells = sorted({(s.table, s.column, s.row) for s in an.spans} | {(s.table, s.column, s.row) for s in an.baseline_spans})
    naz_idx, base_idx = ui._cell_spans(an.spans), ui._cell_spans(an.baseline_spans)
    ranked = sorted(cells, key=lambda c: (-ui.note_score(an, c, naz_idx, base_idx), c))[:N_NOTES]
    notes = []
    for cell in ranked:
        _, base, naz = ui.cell_marks(an, cell)
        notes.append({"table": cell[0], "column": cell[1], "row": cell[2],
                      "baseline": [list(m) for m in base], "nazeer": [list(m) for m in naz]})
    entity = None
    key = ui.entity_key(an.profile)
    if key:
        value = ui.default_entity(an)
        rows = ui.entity_rows(an, value) if value is not None else {}
        if rows.get(key[0]):
            entity = {"table": key[0], "column": key[1], "row": rows[key[0]][0], "rows": rows}
    return {
        "tables": [{"name": t, "rows": int(len(df)), "primary_key": an.profile.tables[t].primary_key,
                    "columns": cols_by_table.get(t, [])} for t, df in an.tables.items()],
        "relationships": [{"child_table": f.child_table, "child_column": f.child_column,
                           "parent_table": f.parent_table, "parent_column": f.parent_column} for f in an.profile.foreign_keys],
        "spans": {"nazeer": dict(Counter(s.type for s in an.spans)),
                  "baseline": dict(Counter(s.type for s in an.baseline_spans)),
                  "nazeer_found": summary_counts["nazeer"]["found"],
                  "baseline_found": summary_counts["baseline"]["found"],
                  "baseline_false_alarms": summary_counts["baseline"]["false_alarms"]},
        "notes": notes,
        "entity": entity,
        "ingest": ingest_notes,
        "total_rows": int(sum(len(df) for df in an.tables.values())),
    }


def process_upload(db: DbSession, settings: Settings, ds: Dataset) -> dict:
    """Upload blob -> clean tables blob (the upload blob is deleted) -> detection summary."""
    from nazeer import pipeline
    from nazeer.ingest import IngestError, read_files

    upload = originals_blob(db, ds.id, "upload")
    if upload is None:
        raise ProcessingError("session_expired")
    try:
        res = read_files(_upload_files(read_blob(settings.master_key, upload)))
    except IngestError as e:
        raise ProcessingError(f"ingest:{e.code}") from None
    total = sum(len(df) for df in res.tables.values())
    if total > settings.max_rows_masked:
        raise ProcessingError("too_many_rows_hosted")
    put_blob(db, settings.master_key, ds.org_id, "tables", tables_to_zip(res.tables),
             expires_at=ds.session_expires_at, dataset_id=ds.id)
    db.delete(upload)
    an = pipeline.analyze(res.tables, ds.name)
    ds.summary = detection_summary(an, res.report())
    ds.status = "ready"
    db.commit()
    return {"tables": len(res.tables), "rows": total}


# ---------------------------------------------------------------- twin generation

def org_key(settings: Settings, org: Organization) -> bytes:
    return decrypt_org_key(settings.master_key, org.id, org.key_version, org.enc_key)


def _json_safe(obj):
    return json.loads(json.dumps(obj, default=str))


def generate_twin(db: DbSession, settings: Settings, ds: Dataset, payload: dict, created_by: str | None) -> Twin:
    from nazeer import pipeline, ui_logic as ui
    from nazeer.policy import load_policy

    tables = load_tables(db, settings, ds)
    mode = payload.get("mode", "masked")
    total = sum(len(df) for df in tables.values())
    if mode == "synthetic" and total > settings.max_rows_synthetic:
        raise ProcessingError("synthetic_too_large")
    an = pipeline.analyze(tables, ds.name)
    policy = load_policy(pipeline.DEFAULT_POLICY)
    overrides = payload.get("overrides") or {}
    org = db.get(Organization, ds.org_id)
    if mode == "masked":
        res = pipeline.run_masked(an, policy, org_key(settings, org), overrides, apply_fix=payload.get("apply_fix"))
        proof = ui.proof(an, res)
    else:
        try:
            res = pipeline.run_synthetic(an, policy, overrides, target=payload.get("target") or None)
        except (ValueError, KeyError, ZeroDivisionError) as e:
            log.error("synthetic generation failed", exc_info=True)
            raise ProcessingError("synthetic_unsupported") from e
        proof = {"leak": {"status": res.report["leak_scan"]["verdict"],
                          "leaks": sum(res.report["leak_scan"]["leaked_by_kind"].values()),
                          "cells": res.report["leak_scan"]["cells_scanned"]}}
    blob = None
    if not res.twin_withheld:
        blob = put_blob(db, settings.master_key, ds.org_id, "twin", tables_to_zip(res.twin), dataset_id=ds.id)
        db.flush()
    twin = Twin(org_id=ds.org_id, dataset_id=ds.id, blob_id=blob.id if blob else None, mode=mode,
                verdict=res.report["verdict"], report=_json_safe(res.report), proof=_json_safe(proof),
                key_version=org.key_version, created_by=created_by)
    db.add(twin)
    db.commit()
    return twin


# ---------------------------------------------------------------- retention sweep

def sweep(db: DbSession, settings: Settings) -> dict:
    """Delete expired originals; purge old twins no active share needs. Counts only."""
    now = utcnow()
    expired = db.execute(select(Blob).where(Blob.kind.in_(("upload", "tables")), Blob.expires_at <= now)).scalars().all()
    ds_ids = {b.dataset_id for b in expired}
    for b in expired:
        db.delete(b)
    for ds in db.execute(select(Dataset).where(Dataset.id.in_(ds_ids))).scalars() if ds_ids else []:
        ds.originals_deleted_at = ds.originals_deleted_at or now
        if ds.status == "processing":
            ds.status, ds.error_code = "failed", "session_expired"
    cutoff = now - timedelta(days=settings.twin_retention_days)
    purged = 0
    for twin in db.execute(select(Twin).where(Twin.purged_at.is_(None), Twin.created_at <= cutoff)).scalars():
        active = db.execute(select(Share.id).where(Share.twin_id == twin.id, Share.revoked_at.is_(None),
                                                   Share.expires_at > now)).first()
        if active is None:
            if twin.blob_id:
                db.execute(delete(Blob).where(Blob.id == twin.blob_id))
            twin.blob_id, twin.purged_at = None, now
            purged += 1
    db.commit()
    return {"originals_deleted": len(expired), "twins_purged": purged}


def end_session(db: DbSession, ds: Dataset) -> None:
    """The user's "delete originals now": both original blobs go, immediately."""
    db.execute(delete(Blob).where(Blob.dataset_id == ds.id, Blob.kind.in_(("upload", "tables"))))
    ds.originals_deleted_at = utcnow()
    ds.session_expires_at = min(ds.session_expires_at, utcnow())
    db.commit()
