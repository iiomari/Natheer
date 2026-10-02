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


ORIGINAL_KINDS = ("upload", "tables", "clean")


def load_tables(db: DbSession, settings: Settings, ds: Dataset, kind: str = "clean") -> dict:
    """The cleaned tables (what detection and generation use); kind="tables" gives the raw parse."""
    blob = originals_blob(db, ds.id, kind) or (originals_blob(db, ds.id, "tables") if kind == "clean" else None)
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
        "found_by_type": _found_by_type(an),
        "review": _review_counts(an),
    }


def _found_by_type(an) -> dict:
    """Identifier values found, per type: values in identifier columns + values inside free text."""
    from collections import Counter

    out: Counter = Counter()
    for d in an.detections:
        if d.tag == "DIRECT_ID" and d.kind:
            out[d.kind] += int(an.tables[d.table][d.column].notna().sum())
    for sp in an.spans:
        out[sp.type] += 1
    return dict(out)


def _review_counts(an) -> dict:
    from collections import Counter

    from nazeer.detect import SPAN_REVIEW_BELOW

    c = Counter(sp.type for sp in an.spans if sp.confidence < SPAN_REVIEW_BELOW)
    return {"by_type": dict(c), "total": int(sum(c.values()))}


def process_upload(db: DbSession, settings: Settings, ds: Dataset, cleaning: dict | None = None) -> dict:
    """upload -> raw tables (the upload blob is deleted) -> cleaning -> detection summary.

    Called again with new cleaning options: then the raw tables blob is reused."""
    from nazeer import cleaning as cl
    from nazeer import pipeline
    from nazeer.ingest import IngestError, read_files

    upload = originals_blob(db, ds.id, "upload")
    if upload is not None:
        try:
            res = read_files(_upload_files(read_blob(settings.master_key, upload)))
        except IngestError as e:
            raise ProcessingError(f"ingest:{e.code}") from None
        raw, ingest_notes = res.tables, res.report()
        put_blob(db, settings.master_key, ds.org_id, "tables", tables_to_zip(raw),
                 expires_at=ds.session_expires_at, dataset_id=ds.id)
        db.delete(upload)
    else:
        raw = load_tables(db, settings, ds, kind="tables")
        ingest_notes = (ds.summary or {}).get("ingest", [])
    total = sum(len(df) for df in raw.values())
    if total > settings.max_rows_masked:
        raise ProcessingError("too_many_rows_hosted")
    opts = cl.CleanOptions.from_dict(cleaning)
    cleaned, report = cl.clean(raw, opts)
    old = originals_blob(db, ds.id, "clean")
    if old is not None:
        db.delete(old)
    put_blob(db, settings.master_key, ds.org_id, "clean", tables_to_zip(cleaned),
             expires_at=ds.session_expires_at, dataset_id=ds.id)
    an = pipeline.analyze(cleaned, ds.name)
    summary = detection_summary(an, ingest_notes)
    suggestions = cl.category_suggestions(raw)
    summary["cleaning"] = {
        "report": report,
        "potential": cl.potential(raw),
        "suggestions": [{"key": g["key"], "table": g["table"], "column": g["column"], "variants": len(g["from"]) + 1,
                         "rows": g["rows"], "approved": g["key"] in opts.merges} for g in suggestions],
        "report_only": cl.report_only(raw),
        "rows_before": int(total),
    }
    ds.summary = summary
    ds.status = "ready"
    db.commit()
    return {"tables": len(cleaned), "rows": summary["total_rows"]}


# ---------------------------------------------------------------- twin generation

def org_key(settings: Settings, org: Organization) -> bytes:
    return decrypt_org_key(settings.master_key, org.id, org.key_version, org.enc_key)


def _json_safe(obj):
    return json.loads(json.dumps(obj, default=str))


def add_row_refs(twin: dict, an, key: bytes, dataset_id: str, key_version: int) -> dict:
    """Seal each twin row's original reference (primary key value, else row position after cleaning)
    under the organization key and keep it inside the (encrypted) twin. Exports turn it into the
    share-bound verification token. Returns value-free information for the report."""
    from nazeer_api.tokens import INTERNAL_COLUMN, TOKEN_COLUMN, seal_internal

    tables = []
    for idx, (name, df) in enumerate(twin.items()):
        pk = an.profile.tables[name].primary_key if name in an.profile.tables else None
        orig = an.tables[name]
        if pk and pk in orig.columns and orig[pk].notna().all() and orig[pk].is_unique:
            keys = [str(v).strip() for v in orig[pk].tolist()]
        else:
            pk, keys = None, [str(i + 1) for i in range(len(orig))]
        df[INTERNAL_COLUMN] = [seal_internal(key, dataset_id, key_version, idx, k) for k in keys]
        tables.append({"name": name, "key_column": pk, "rows": len(df)})
    return {"column": TOKEN_COLUMN, "tables": tables, "length": "NZ- + 40-60"}


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
        res = pipeline.run_masked(an, policy, org_key(settings, org), overrides,
                                  approve_review=bool(payload.get("approve_review")),
                                  cleared_columns=payload.get("cleared_columns") or [])
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
    token_info = None
    if mode == "masked" and not res.twin_withheld:
        token_info = add_row_refs(res.twin, an, org_key(settings, org), ds.id, org.key_version)
    if not res.twin_withheld:
        blob = put_blob(db, settings.master_key, ds.org_id, "twin", tables_to_zip(res.twin), dataset_id=ds.id)
        db.flush()
    report = _json_safe(res.report)
    summary = ds.summary or {}
    cleaning = summary.get("cleaning") or {}
    report["cleaning"] = cleaning.get("report")  # what was cleaned (counts only)
    # Everything needed to rebuild this twin from the same original files at re-link time.
    # Names, options and counts only: no data value.
    key = ui.entity_key(an.profile) if mode == "masked" else None
    opts = dict((cleaning.get("report") or {}).get("options") or {})
    opts["merges"] = [g["key"] for g in cleaning.get("suggestions", []) if g.get("approved")]
    report["generation"] = _json_safe({
        "dataset_name": ds.name, "cleaning": opts, "overrides": overrides, "approve_review": bool(payload.get("approve_review")),
        "cleared_columns": payload.get("cleared_columns") or [],
        "link": {"table": key[0], "column": key[1]} if key else None,
        "source": [{"table": n["table"], "rows": n["rows"]} for n in summary.get("ingest", [])],
        "token": token_info,
    })
    twin = Twin(org_id=ds.org_id, dataset_id=ds.id, blob_id=blob.id if blob else None, mode=mode,
                verdict=res.report["verdict"], report=report, proof=_json_safe(proof),
                key_version=org.key_version, created_by=created_by)
    db.add(twin)
    db.commit()
    return twin


# ---------------------------------------------------------------- retention sweep

def sweep(db: DbSession, settings: Settings) -> dict:
    """Delete expired originals; purge old twins no active share needs. Counts only."""
    now = utcnow()
    expired = db.execute(select(Blob).where(Blob.kind.in_(ORIGINAL_KINDS), Blob.expires_at <= now)).scalars().all()
    ds_ids = {b.dataset_id for b in expired}
    for b in expired:
        db.delete(b)
    for ds in db.execute(select(Dataset).where(Dataset.id.in_(ds_ids))).scalars() if ds_ids else []:
        ds.originals_deleted_at = ds.originals_deleted_at or now
        if ds.status == "processing":
            ds.status, ds.error_code = "failed", "session_expired"
    from nazeer_api.models import Return
    from nazeer_api.returns import RELINK_KINDS

    relink_blobs = db.execute(select(Blob).where(Blob.kind.in_(RELINK_KINDS), Blob.expires_at <= now)).scalars().all()
    for b in relink_blobs:
        for r in db.execute(select(Return).where((Return.relinked_blob_id == b.id) | (Return.relink_upload_id == b.id))).scalars():
            if r.relinked_blob_id == b.id:
                r.relinked_blob_id, r.relink_status = None, "expired"
            else:
                r.relink_upload_id = None
                if r.relink_status == "running":
                    r.relink_status, r.relink_error = "failed", "relink_upload_expired"
        db.delete(b)
    cutoff = now - timedelta(days=settings.twin_retention_days)
    purged = 0
    for twin in db.execute(select(Twin).where(Twin.purged_at.is_(None), Twin.created_at <= cutoff)).scalars():
        active = db.execute(select(Share.id).where(Share.twin_id == twin.id, Share.revoked_at.is_(None),
                                                   Share.expires_at > now)).first()
        if active is None:
            if twin.blob_id:
                db.execute(delete(Blob).where(Blob.id == twin.blob_id))
            for r in db.execute(select(Return).where(Return.twin_id == twin.id, Return.blob_id.is_not(None))).scalars():
                db.execute(delete(Blob).where(Blob.id == r.blob_id))
                r.blob_id = None
            twin.blob_id, twin.purged_at = None, now
            purged += 1
    db.commit()
    return {"originals_deleted": len(expired), "twins_purged": purged, "relink_files_deleted": len(relink_blobs)}


def end_session(db: DbSession, ds: Dataset) -> None:
    """The user's "delete originals now": both original blobs go, immediately."""
    db.execute(delete(Blob).where(Blob.dataset_id == ds.id, Blob.kind.in_(ORIGINAL_KINDS)))
    ds.originals_deleted_at = utcnow()
    ds.session_expires_at = min(ds.session_expires_at, utcnow())
    db.commit()
