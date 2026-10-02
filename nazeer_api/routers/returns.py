"""Returned results (recipient side) and admin-only re-linking (organization side).

* a recipient returns any subset of rows through their own grant on an active share of a masked twin;
* every row is verified by its رمز_التحقق: verified / invalid / missing / foreign / old key / duplicate;
* only verified rows are kept (token + the columns the recipient added), encrypted;
* re-linking is for organization admins only: verified tokens -> original keys (in memory) -> joined
  with the original file uploaded at re-link time. Below 100% integrity the admin must confirm.
Reports and audit entries hold row numbers, counts, percentages and column names: never a value.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from nazeer_api import audit, jobs
from nazeer_api.config import Settings
from nazeer_api.db import utcnow
from nazeer_api.deps import admin, api_error, check_csrf, current_user, data_manager, get_db, get_settings_dep, scoped
from nazeer_api.models import Blob, Membership, Return, ShareGrant, ShareLink, User
from nazeer_api.processing import pack_upload
from nazeer_api.returns import ReturnError, token_info, verify_return
from nazeer_api.routers.shares import _grant, share_status
from nazeer_api.storage import export_csv_zip, export_xlsx, org_usage_bytes, put_blob, read_blob, tables_to_zip, zip_to_tables

router = APIRouter(prefix="/api", tags=["returns"], dependencies=[Depends(check_csrf)])
org_router = APIRouter(prefix="/api/orgs/{org_id}", tags=["returns"], dependencies=[Depends(check_csrf)])


async def _read_files(files: list[UploadFile], max_files: int) -> list[tuple[str, bytes]]:
    from nazeer.ingest import LIMITS

    if not files or len(files) > max_files:
        raise api_error(422, "ingest:too_many_files" if files else "ingest:no_files")
    out, total = [], 0
    for f in files:
        data = await f.read(LIMITS["max_file_bytes"] + 1)
        if len(data) > LIMITS["max_file_bytes"]:
            raise api_error(413, "ingest:file_too_large")
        total += len(data)
        if total > LIMITS["max_total_bytes"]:
            raise api_error(413, "ingest:total_too_large")
        out.append(((f.filename or "file.csv")[:200], data))
    return out


def _audit_counts(report: dict) -> dict:
    c = report.get("counts", {})
    return {"rows": report.get("rows_returned"), "verified": c.get("verified"), "invalid": c.get("invalid"),
            "missing": c.get("missing"), "foreign": c.get("foreign"), "old_key": c.get("old_key"),
            "duplicate": c.get("duplicate"), "integrity": report.get("integrity")}


def return_payload(r: Return) -> dict:
    live = r.relink_status == "ready" and r.relink_expires_at is not None and r.relink_expires_at > utcnow()
    status = "expired" if r.relink_status == "ready" and not live else r.relink_status
    rep = r.report or {}
    return {"id": r.id, "share_id": r.share_id, "twin_id": r.twin_id, "dataset_name": r.twin.dataset.name,
            "file_name": r.file_name, "created_at": r.created_at.isoformat(), "report": rep,
            "rows_returned": rep.get("rows_returned", r.rows_total), "verified": r.rows_accepted,
            "added_columns": r.columns, "available": r.blob_id is not None,
            "relinkable": bool(r.blob_id and rep.get("counts", {}).get("verified")),
            "relink": {"status": status, "error_code": r.relink_error, "matched": r.relink_matched,
                       "expires_at": r.relink_expires_at.isoformat() if live else None,
                       "downloads": r.relink_downloads}}


# ---------------------------------------------------------------- recipient side

@router.post("/received/{share_id}/returns", status_code=201)
async def submit_return(share_id: str, files: list[UploadFile] = File(...), user: User = Depends(current_user),
                        db: DbSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    s = _grant(db, user, share_id)
    if share_status(s) != "active":
        raise api_error(410, f"share_{share_status(s)}")
    if not token_info(s.twin):
        raise api_error(422, "returns_not_supported")
    if s.twin.blob_id is None:
        raise api_error(410, "share_expired")
    payload = await _read_files(files, 1)
    twin_tables = zip_to_tables(read_blob(settings.master_key, db.get(Blob, s.twin.blob_id)))
    try:
        kept, report = verify_return(settings, s, twin_tables, payload)
    except ReturnError as e:
        audit.record(db, "return.rejected", org_id=s.org_id, actor_user_id=user.id, target_type="share",
                     target_id=s.id, reason=e.code, rows=e.counts.get("rows_returned"))
        db.commit()
        raise HTTPException(422, detail={"code": e.code, **e.counts}) from None
    blob = None
    if kept:
        data = tables_to_zip(kept)
        if org_usage_bytes(db, s.org_id) + len(data) > settings.org_quota_mb * 1024 * 1024:
            raise api_error(413, "quota_exceeded")
        blob = put_blob(db, settings.master_key, s.org_id, "return", data)
        db.flush()
    added = sorted({c for cols in report["added_columns"].values() for c in cols})
    r = Return(org_id=s.org_id, share_id=s.id, twin_id=s.twin_id, submitted_by=user.id, file_name=payload[0][0],
               rows_total=report["rows_returned"], rows_accepted=report["counts"]["verified"],
               rejected={k: v for k, v in report["counts"].items() if k != "verified"}, columns=added,
               blob_id=blob.id if blob else None, report=report)
    db.add(r)
    db.flush()
    audit.record(db, "return.submitted", org_id=s.org_id, actor_user_id=user.id, target_type="return", target_id=r.id,
                 share=s.id, added_columns=len(added), **_audit_counts(report))
    db.commit()
    out = return_payload(r)
    out.pop("relink")
    return out


@router.get("/received/{share_id}/returns")
def my_returns(share_id: str, user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> list[dict]:
    s = _grant(db, user, share_id)
    rows = db.execute(select(Return).where(Return.share_id == s.id, Return.submitted_by == user.id)
                      .order_by(Return.created_at.desc())).scalars()
    out = []
    for r in rows:
        p = return_payload(r)
        p.pop("relink")  # the organization's business
        out.append(p)
    return out


# ---------------------------------------------------------------- organization side

def _return(db: DbSession, org_id: str, return_id: str) -> Return:
    r = db.execute(scoped(select(Return).where(Return.id == return_id), Return, org_id)).scalar_one_or_none()
    if r is None:
        raise api_error(404, "not_found")
    return r


def _recipient_label(db: DbSession, r: Return) -> str:
    u = db.get(User, r.submitted_by) if r.submitted_by else None
    if u is None:
        return ""
    g = db.execute(select(ShareGrant).where(ShareGrant.share_id == r.share_id, ShareGrant.user_id == u.id)).scalar_one_or_none()
    link = db.get(ShareLink, g.link_id) if g is not None and g.link_id else None
    return f"{u.full_name} · {link.label}" if link else u.full_name


@org_router.get("/returns")
def list_returns(org_id: str, m: Membership = Depends(data_manager), db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(scoped(select(Return), Return, org_id).order_by(Return.created_at.desc()).limit(200)).scalars()
    return [{**return_payload(r), "recipient": _recipient_label(db, r)} for r in rows]


@org_router.get("/returns/{return_id}")
def get_return(org_id: str, return_id: str, m: Membership = Depends(data_manager),
               db: DbSession = Depends(get_db)) -> dict:
    r = _return(db, org_id, return_id)
    out = {**return_payload(r), "recipient": _recipient_label(db, r)}
    out["relink"]["mine"] = r.relink_by == m.user_id
    info = token_info(r.twin) or {}
    out["source_tables"] = [{"name": t["name"], "key_column": t.get("key_column")} for t in info.get("tables", [])]
    return out


@org_router.post("/returns/{return_id}/relink", status_code=202)
async def start_relink(org_id: str, return_id: str, files: list[UploadFile] = File(...),
                       confirm_partial: bool = Form(False), m: Membership = Depends(admin),
                       db: DbSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    from nazeer.ingest import LIMITS

    r = _return(db, org_id, return_id)
    rep = r.report or {}
    if not token_info(r.twin):
        raise api_error(422, "relink_not_supported")
    if r.blob_id is None or not rep.get("counts", {}).get("verified"):
        raise api_error(422, "relink_no_verified")
    if r.relink_status == "running":
        raise api_error(409, "relink_running")
    partial = (rep.get("integrity") or 0) < 1
    if partial and not confirm_partial:
        raise api_error(409, "relink_confirm_partial")
    payload = await _read_files(files, LIMITS["max_files"])
    for old_id in (r.relink_upload_id, r.relinked_blob_id):
        old = db.get(Blob, old_id) if old_id else None
        if old is not None:
            db.delete(old)
    upload = put_blob(db, settings.master_key, org_id, "relink_upload", pack_upload(payload),
                      expires_at=utcnow() + timedelta(minutes=settings.session_minutes))
    db.flush()
    r.relink_upload_id, r.relinked_blob_id, r.relink_expires_at = upload.id, None, None
    r.relink_status, r.relink_error, r.relink_by = "running", None, m.user_id
    r.relink_matched, r.relink_downloads = None, 0
    j = jobs.enqueue(db, org_id, "relink", {"return_id": r.id}, created_by=m.user_id)
    if partial:
        audit.record(db, "relink.partial_confirmed", org_id=org_id, actor_user_id=m.user_id, target_type="return",
                     target_id=r.id, integrity=rep.get("integrity"), verified=rep.get("counts", {}).get("verified"))
    audit.record(db, "relink.requested", org_id=org_id, actor_user_id=m.user_id, target_type="return", target_id=r.id,
                 files=len(payload))
    db.commit()
    return {"job_id": j.id}


@org_router.get("/returns/{return_id}/relinked.{fmt}")
def download_relinked(org_id: str, return_id: str, fmt: Literal["csv", "xlsx"], m: Membership = Depends(admin),
                      db: DbSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)):
    r = _return(db, org_id, return_id)
    if r.relink_by != m.user_id:
        raise api_error(403, "relink_not_yours")
    blob = db.get(Blob, r.relinked_blob_id) if r.relinked_blob_id else None
    if r.relink_status != "ready" or blob is None or blob.expires_at is None or blob.expires_at <= utcnow():
        raise api_error(410, "relink_expired")
    tables = zip_to_tables(read_blob(settings.master_key, blob))
    if fmt == "xlsx":
        data, media, ext = export_xlsx(tables), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    else:
        data, media, ext = export_csv_zip(tables), "application/zip", "zip"
    r.relink_downloads += 1
    audit.record(db, "relink.downloaded", org_id=org_id, actor_user_id=m.user_id, target_type="return", target_id=r.id,
                 format=fmt, rows=sum(len(df) for df in tables.values()), download=r.relink_downloads)
    db.commit()
    return Response(data, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="nazeer-relinked-{r.id[:8]}.{ext}"', "Cache-Control": "no-store"})
