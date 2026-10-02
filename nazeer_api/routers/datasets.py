"""Datasets and twins (organization side): upload, review detection, generate, preview, report.

Upload / review / generate need the data-manager right (admins have it). The before/after preview
shows original values and is for admins only, and only while the processing session is open.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from nazeer_api import audit, jobs
from nazeer_api.config import Settings
from nazeer_api.db import utcnow
from nazeer_api.deps import admin, api_error, check_csrf, data_manager, get_db, get_settings_dep, member, scoped
from nazeer_api.models import Blob, Dataset, Job, Membership, Share, Twin
from nazeer_api.processing import ProcessingError, end_session, load_tables, pack_upload
from nazeer_api.storage import org_usage_bytes, put_blob, read_blob, zip_to_tables

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["datasets"], dependencies=[Depends(check_csrf)])


def _dataset(db: DbSession, org_id: str, dataset_id: str) -> Dataset:
    ds = db.execute(scoped(select(Dataset).where(Dataset.id == dataset_id), Dataset, org_id)).scalar_one_or_none()
    if ds is None:
        raise api_error(404, "not_found")
    return ds


def _twin(db: DbSession, org_id: str, twin_id: str) -> Twin:
    t = db.execute(scoped(select(Twin).where(Twin.id == twin_id), Twin, org_id)).scalar_one_or_none()
    if t is None:
        raise api_error(404, "not_found")
    return t


def session_open(ds: Dataset) -> bool:
    return ds.originals_deleted_at is None and ds.session_expires_at > utcnow()


def _job_state(db: DbSession, org_id: str, dataset_id: str, kind: str) -> dict | None:
    rows = db.execute(scoped(select(Job), Job, org_id).where(Job.kind == kind).order_by(Job.created_at.desc())
                      .limit(20)).scalars()
    j = next((j for j in rows if j.payload.get("dataset_id") == dataset_id), None)
    return None if j is None else {"id": j.id, "status": j.status, "progress": j.progress, "stage": j.stage,
                                   "error_code": j.error_code, "result": j.result}


def dataset_payload(db: DbSession, ds: Dataset, detail: bool = False) -> dict:
    twins = db.execute(select(Twin).where(Twin.dataset_id == ds.id).order_by(Twin.created_at.desc())).scalars().all()
    out = {"id": ds.id, "name": ds.name, "status": ds.status, "error_code": ds.error_code,
           "created_at": ds.created_at.isoformat(), "session_open": session_open(ds),
           "session_expires_at": ds.session_expires_at.isoformat(),
           "originals_deleted_at": ds.originals_deleted_at.isoformat() if ds.originals_deleted_at else None,
           "tables": [{"name": t["name"], "rows": t["rows"], "columns": len(t["columns"])}
                      for t in (ds.summary or {}).get("tables", [])],
           "twins": [{"id": t.id, "mode": t.mode, "verdict": t.verdict, "created_at": t.created_at.isoformat(),
                      "purged": t.purged_at is not None} for t in twins]}
    if detail:
        out["summary"] = ds.summary
        out["process_job"] = _job_state(db, ds.org_id, ds.id, "process")
        out["generate_job"] = _job_state(db, ds.org_id, ds.id, "generate")
    return out


# ---------------------------------------------------------------- dashboard

@router.get("/stats")
def stats(org_id: str, m: Membership = Depends(member), db: DbSession = Depends(get_db)) -> dict:
    from sqlalchemy import func

    from nazeer_api.storage import org_usage_bytes

    now = utcnow()
    count = lambda stmt: int(db.execute(stmt).scalar_one())  # noqa: E731
    recent = db.execute(scoped(select(Twin), Twin, org_id).order_by(Twin.created_at.desc()).limit(5)).scalars()
    return {
        "datasets": count(scoped(select(func.count()).select_from(Dataset), Dataset, org_id)),
        "twins": count(scoped(select(func.count()).select_from(Twin), Twin, org_id)),
        "active_shares": count(scoped(select(func.count()).select_from(Share), Share, org_id)
                               .where(Share.revoked_at.is_(None), Share.expires_at > now)),
        "pending_returns": 0,
        "storage_mb": round(org_usage_bytes(db, org_id) / 2**20, 1),
        "recent_twins": [{"id": t.id, "dataset_name": t.dataset.name, "mode": t.mode, "verdict": t.verdict,
                          "created_at": t.created_at.isoformat()} for t in recent],
    }


# ---------------------------------------------------------------- datasets

@router.get("/datasets")
def list_datasets(org_id: str, m: Membership = Depends(data_manager), db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(scoped(select(Dataset), Dataset, org_id).order_by(Dataset.created_at.desc())).scalars()
    return [dataset_payload(db, ds) for ds in rows]


@router.post("/datasets", status_code=201)
async def upload(org_id: str, request: Request, files: list[UploadFile] = File(...), name: str = Form(""),
                 m: Membership = Depends(data_manager), db: DbSession = Depends(get_db),
                 settings: Settings = Depends(get_settings_dep)) -> dict:
    from nazeer.ingest import LIMITS

    if not files or len(files) > LIMITS["max_files"]:
        raise api_error(422, "ingest:too_many_files" if files else "ingest:no_files")
    payload, total = [], 0
    for f in files:
        data = await f.read(LIMITS["max_file_bytes"] + 1)
        if len(data) > LIMITS["max_file_bytes"]:
            raise api_error(413, "ingest:file_too_large")
        total += len(data)
        if total > LIMITS["max_total_bytes"]:
            raise api_error(413, "ingest:total_too_large")
        payload.append(((f.filename or "file.csv")[:200], data))
    if org_usage_bytes(db, org_id) + total > settings.org_quota_mb * 1024 * 1024:
        raise api_error(413, "quota_exceeded")
    title = (name or "").strip()[:160] or payload[0][0].rsplit(".", 1)[0][:160] or "مجموعة بيانات"
    ds = Dataset(org_id=org_id, name=title, status="processing", created_by=m.user_id,
                 session_expires_at=utcnow() + timedelta(minutes=settings.session_minutes))
    db.add(ds)
    db.flush()
    put_blob(db, settings.master_key, org_id, "upload", pack_upload(payload), expires_at=ds.session_expires_at,
             dataset_id=ds.id)
    jobs.enqueue(db, org_id, "process", {"dataset_id": ds.id}, created_by=m.user_id)
    audit.record(db, "dataset.uploaded", org_id=org_id, actor_user_id=m.user_id, target_type="dataset",
                 target_id=ds.id, files=len(payload))
    db.commit()
    return dataset_payload(db, ds, detail=True)


@router.get("/datasets/{dataset_id}")
def get_dataset(org_id: str, dataset_id: str, m: Membership = Depends(data_manager),
                db: DbSession = Depends(get_db)) -> dict:
    return dataset_payload(db, _dataset(db, org_id, dataset_id), detail=True)


@router.get("/datasets/{dataset_id}/notes/{index}")
def note(org_id: str, dataset_id: str, index: int, m: Membership = Depends(data_manager),
         db: DbSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    """One highlighted note (original text) for the review screen: only while the session is open."""
    ds = _dataset(db, org_id, dataset_id)
    notes = (ds.summary or {}).get("notes", [])
    if not 0 <= index < len(notes):
        raise api_error(404, "not_found")
    try:
        tables = load_tables(db, settings, ds)
    except ProcessingError as e:
        raise api_error(410, e.code) from None
    n = notes[index]
    text = tables[n["table"]][n["column"]].iat[n["row"]]
    return {"index": index, "count": len(notes), "table": n["table"], "column": n["column"], "text": text,
            "baseline": n["baseline"], "nazeer": n["nazeer"]}


class CleanIn(BaseModel):
    trim: bool = True
    nulls: bool = True
    numbers: bool = True
    dates: bool = True
    dedupe: bool = True
    arabic: bool = False
    phones: bool = False
    merges: list[str] = Field(default_factory=list, max_length=500)  # suggestion keys only, never values


CLEAN_RULES = ("trim", "nulls", "numbers", "dates", "dedupe", "arabic", "phones")


@router.post("/datasets/{dataset_id}/clean", status_code=202)
def reclean(org_id: str, dataset_id: str, body: CleanIn, m: Membership = Depends(data_manager),
            db: DbSession = Depends(get_db)) -> dict:
    """Re-run cleaning + detection on the session's raw tables with new options."""
    ds = _dataset(db, org_id, dataset_id)
    if ds.status not in ("ready", "failed") or not (ds.summary or {}).get("cleaning"):
        raise api_error(409, "dataset_not_ready")
    if not session_open(ds):
        raise api_error(410, "session_expired")
    if any(len(k) > 600 or "#" not in k for k in body.merges):
        raise api_error(422, "invalid_merge_key")
    ds.status, ds.error_code = "processing", None
    j = jobs.enqueue(db, org_id, "process", {"dataset_id": ds.id, "cleaning": body.model_dump()}, created_by=m.user_id)
    audit.record(db, "dataset.cleaning_changed", org_id=org_id, actor_user_id=m.user_id, target_type="dataset",
                 target_id=ds.id, on=sorted(r for r in CLEAN_RULES if getattr(body, r)), merges=len(body.merges))
    db.commit()
    return {"job_id": j.id}


def _raw_tables(db: DbSession, settings: Settings, ds: Dataset) -> dict:
    try:
        return load_tables(db, settings, ds, kind="tables")
    except ProcessingError as e:
        raise api_error(410, e.code) from None


@router.get("/datasets/{dataset_id}/cleaning/examples/{rule}")
def cleaning_examples(org_id: str, dataset_id: str, rule: str, m: Membership = Depends(data_manager),
                      db: DbSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    """Before/after values for one rule. Original values: only while the session is open, never stored."""
    from nazeer.cleaning import examples

    if rule not in CLEAN_RULES:
        raise api_error(404, "not_found")
    ds = _dataset(db, org_id, dataset_id)
    return {"rule": rule, "examples": examples(_raw_tables(db, settings, ds), rule, n=6)}


@router.get("/datasets/{dataset_id}/cleaning/suggestions")
def cleaning_suggestions(org_id: str, dataset_id: str, m: Membership = Depends(data_manager),
                         db: DbSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> list[dict]:
    """Category spelling groups with their values (session-only); approvals are sent back as keys."""
    from nazeer.cleaning import category_suggestions

    ds = _dataset(db, org_id, dataset_id)
    return category_suggestions(_raw_tables(db, settings, ds))


REVIEW_EXAMPLES = 12


@router.get("/datasets/{dataset_id}/review")
def review_examples(org_id: str, dataset_id: str, m: Membership = Depends(data_manager),
                    db: DbSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    """Free-text values the detector is unsure of, in their sentence (original text: session only)."""
    from nazeer import pipeline
    from nazeer.detect import SPAN_REVIEW_BELOW

    ds = _dataset(db, org_id, dataset_id)
    try:
        tables = load_tables(db, settings, ds)
    except ProcessingError as e:
        raise api_error(410, e.code) from None
    an = pipeline.analyze(tables, ds.name)
    pending = [sp for sp in an.spans if sp.confidence < SPAN_REVIEW_BELOW]
    items = []
    for sp in pending[:REVIEW_EXAMPLES]:
        text = an.tables[sp.table][sp.column].iat[sp.row]
        items.append({"table": sp.table, "column": sp.column, "row": sp.row + 1, "kind": sp.type,
                      "text": text, "start": sp.start, "end": sp.end})
    return {"total": len(pending), "items": items}


@router.post("/datasets/{dataset_id}/answer-key")
async def answer_key_check(org_id: str, dataset_id: str, file: UploadFile = File(...),
                           m: Membership = Depends(data_manager), db: DbSession = Depends(get_db),
                           settings: Settings = Depends(get_settings_dep)) -> dict:
    """Optional, independent proof: compare detection with an answer key the user brings.
    Counts only in the response; the key itself is never stored."""
    from nazeer import pipeline
    from nazeer.answer_key import AnswerKeyError, evaluate, load_key

    ds = _dataset(db, org_id, dataset_id)
    data = await file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise api_error(413, "answer_key_too_large")
    try:
        entries = load_key(data)
    except AnswerKeyError as e:
        raise api_error(422, e.code) from None
    if (ds.summary or {}).get("total_rows", 0) > 50_000:
        raise api_error(413, "answer_key_dataset_too_large")
    try:
        tables = load_tables(db, settings, ds)
    except ProcessingError as e:
        raise api_error(410, e.code) from None
    an = pipeline.analyze(tables, ds.name)
    out = evaluate(an.tables, an.detections, an.spans, entries)
    audit.record(db, "dataset.answer_key_checked", org_id=org_id, actor_user_id=m.user_id, target_type="dataset",
                 target_id=ds.id, entries=len(entries))
    db.commit()
    return out


class GenerateIn(BaseModel):
    mode: Literal["masked", "synthetic"] = "masked"
    overrides: dict = Field(default_factory=dict)
    approve_review: bool = False  # also replace the free-text values the detector is unsure of
    cleared_columns: list[str] = Field(default_factory=list, max_length=200)  # "table.column": confirmed not identifiers
    target: str | None = Field(default=None, max_length=200)


@router.post("/datasets/{dataset_id}/generate", status_code=202)
def generate(org_id: str, dataset_id: str, body: GenerateIn, m: Membership = Depends(data_manager),
             db: DbSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    ds = _dataset(db, org_id, dataset_id)
    if ds.status != "ready":
        raise api_error(409, "dataset_not_ready")
    if not session_open(ds):
        raise api_error(410, "session_expired")
    total = (ds.summary or {}).get("total_rows", 0)
    if body.mode == "synthetic" and total > settings.max_rows_synthetic:
        raise api_error(422, "synthetic_too_large")
    j = jobs.enqueue(db, org_id, "generate", {"dataset_id": ds.id, **body.model_dump()}, created_by=m.user_id)
    audit.record(db, "twin.generate_requested", org_id=org_id, actor_user_id=m.user_id, target_type="dataset",
                 target_id=ds.id, mode=body.mode, overrides=len(body.overrides), approve_review=body.approve_review,
                 cleared_columns=len(body.cleared_columns))
    db.commit()
    return {"job_id": j.id}


@router.post("/datasets/{dataset_id}/end-session")
def end(org_id: str, dataset_id: str, m: Membership = Depends(data_manager), db: DbSession = Depends(get_db)) -> dict:
    ds = _dataset(db, org_id, dataset_id)
    end_session(db, ds)
    audit.record(db, "dataset.originals_deleted", org_id=org_id, actor_user_id=m.user_id, target_type="dataset",
                 target_id=ds.id)
    db.commit()
    return dataset_payload(db, ds)


@router.delete("/datasets/{dataset_id}")
def delete_dataset(org_id: str, dataset_id: str, m: Membership = Depends(data_manager),
                   db: DbSession = Depends(get_db)) -> dict:
    ds = _dataset(db, org_id, dataset_id)
    audit.record(db, "dataset.deleted", org_id=org_id, actor_user_id=m.user_id, target_type="dataset", target_id=ds.id)
    db.delete(ds)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- twins

def _limitations_ar() -> list[str]:
    from nazeer.report import LIMITATIONS_AR

    return LIMITATIONS_AR


def _plain_summary(t: Twin) -> dict:
    from nazeer_api.report_pdf import summary

    return summary(t)


def twin_payload(t: Twin) -> dict:
    rep = t.report
    return {"id": t.id, "dataset_id": t.dataset_id, "dataset_name": t.dataset.name, "mode": t.mode,
            "verdict": t.verdict, "created_at": t.created_at.isoformat(), "purged": t.purged_at is not None,
            "withheld": t.blob_id is None and t.purged_at is None, "proof": t.proof,
            "checks": [{k_: c.get(k_) for k_ in ("name", "status", "blocking", "detail", "value", "threshold")}
                       for c in rep.get("checks", [])],
            "failed_checks": rep.get("failed_checks", []), "limitations": rep.get("limitations", []),
            "limitations_ar": rep.get("limitations_ar") or _limitations_ar(),
            "token": (rep.get("generation") or {}).get("token"),
            "options": {k_: (rep.get("generation") or {}).get(k_) for k_ in ("approve_review", "cleared_columns", "overrides")},
            "summary": _plain_summary(t),
            "review": (rep.get("free_text") or {}).get("review"), "residual": rep.get("residual_scan"),
            "utility": rep.get("utility"), "synthetic": rep.get("synthetic"),
            "privacy": rep.get("privacy")}


@router.get("/twins")
def list_twins(org_id: str, m: Membership = Depends(data_manager), db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(scoped(select(Twin), Twin, org_id).order_by(Twin.created_at.desc()).limit(200)).scalars()
    return [twin_payload(t) for t in rows]


@router.get("/twins/{twin_id}")
def get_twin(org_id: str, twin_id: str, m: Membership = Depends(data_manager), db: DbSession = Depends(get_db)) -> dict:
    t = _twin(db, org_id, twin_id)
    out = twin_payload(t)
    out["session_open"] = session_open(t.dataset)
    out["shares"] = db.execute(select(Share.id).where(Share.twin_id == t.id)).scalars().all()
    return out


def _view_sealer(settings: Settings, db: DbSession, t: Twin):
    """Tokens shown in the organization's own view and downloads (each share gets its own tokens)."""
    from nazeer_api.models import Organization
    from nazeer_api.processing import org_key
    from nazeer_api.tokens import Sealer

    org = db.get(Organization, t.org_id)
    key = org_key(settings, org) if t.key_version == org.key_version else None
    return Sealer(key, settings.master_key, t.dataset_id, t.key_version, f"view-{t.id}")


def _twin_blob(db: DbSession, t: Twin) -> Blob:
    if t.blob_id is None:
        raise api_error(410, "twin_purged" if t.purged_at else "twin_withheld")
    return db.get(Blob, t.blob_id)


@router.get("/twins/{twin_id}/rows")
def twin_rows(org_id: str, twin_id: str, table: str | None = None, page: int = 1, size: int = 50, q: str = "",
              sort: str | None = None, desc: bool = False, m: Membership = Depends(data_manager),
              db: DbSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    """One page of the twin (no original value), with replaced / review marks."""
    from nazeer_api import twin_view

    t = _twin(db, org_id, twin_id)
    tables, marks = twin_view.load(settings.master_key, _twin_blob(db, t))
    return twin_view.page(tables, marks, table, page, size, q[:100], sort, desc, _view_sealer(settings, db, t))


@router.get("/twins/{twin_id}/download.{fmt}")
def twin_download(org_id: str, twin_id: str, fmt: Literal["csv", "xlsx"], m: Membership = Depends(data_manager),
                  db: DbSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)):
    from nazeer_api.returns import tables_for_share
    from nazeer_api.storage import export_csv_zip, export_xlsx

    t = _twin(db, org_id, twin_id)
    tables = tables_for_share(zip_to_tables(read_blob(settings.master_key, _twin_blob(db, t))), _view_sealer(settings, db, t))
    audit.record(db, "twin.downloaded", org_id=org_id, actor_user_id=m.user_id, target_type="twin", target_id=t.id,
                 format=fmt)
    db.commit()
    if fmt == "xlsx":
        data, media, ext = export_xlsx(tables), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    else:
        data, media, ext = export_csv_zip(tables), "application/zip", "zip"
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="nazeer-twin-{t.id[:8]}.{ext}"'})


@router.get("/twins/{twin_id}/report.pdf")
def twin_report_pdf(org_id: str, twin_id: str, m: Membership = Depends(data_manager), db: DbSession = Depends(get_db)):
    from nazeer_api.models import Organization
    from nazeer_api.report_pdf import build

    t = _twin(db, org_id, twin_id)
    pdf = build(t, db.get(Organization, t.org_id).name)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="nazeer-report-{t.id[:8]}.pdf"'})


@router.get("/twins/{twin_id}/report.json")
def twin_report(org_id: str, twin_id: str, m: Membership = Depends(data_manager), db: DbSession = Depends(get_db)):
    import json

    t = _twin(db, org_id, twin_id)
    return Response(json.dumps(t.report, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="nazeer-report-{t.id[:8]}.json"'})


@router.get("/twins/{twin_id}/preview")
def twin_preview(org_id: str, twin_id: str, m: Membership = Depends(admin), db: DbSession = Depends(get_db),
                 settings: Settings = Depends(get_settings_dep)) -> dict:
    """Before/after of the tracked record and its related rows. Admins only; needs the open session."""
    from nazeer import ui_logic as ui

    t = _twin(db, org_id, twin_id)
    if t.mode != "masked" or t.blob_id is None:
        raise api_error(409, "preview_unavailable")
    try:
        original = load_tables(db, settings, t.dataset)
    except ProcessingError as e:
        raise api_error(410, e.code) from None
    from nazeer_api.returns import strip_internal

    twin = strip_internal(zip_to_tables(read_blob(settings.master_key, db.get(Blob, t.blob_id))))
    entity = (t.dataset.summary or {}).get("entity")
    out_tables = []
    rows_by_table = entity["rows"] if entity else {name: list(range(min(3, len(df)))) for name, df in original.items()}
    for table, rows in rows_by_table.items():
        if table not in twin:
            continue
        rows = rows[:5]
        comp = ui.compare_rows(original[table], twin[table], rows)
        cols = [c for c in original[table].columns if c in twin[table].columns]
        out_tables.append({"table": table, "columns": cols,
                           "rows": [{c: [ui._show(r[c][0]), ui._show(r[c][1]), bool(r[c][2])] for c in cols} for r in comp]})
    actions = {f"{c['table']}.{c['column']}": c["action"] for c in t.report.get("columns", [])}
    audit.record(db, "twin.preview_viewed", org_id=org_id, actor_user_id=m.user_id, target_type="twin", target_id=t.id)
    db.commit()
    return {"entity_table": entity["table"] if entity else None, "tables": out_tables, "actions": actions}
