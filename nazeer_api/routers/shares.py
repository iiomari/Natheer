"""Sharing a twin (organization side) and receiving it (recipient side).

Rules enforced here, not only in the UI:
* a twin whose verdict is FAIL (or that was withheld/purged) cannot be shared;
* a recipient sees a share only through a ShareGrant: members chosen by the admin, or an account
  that accepted that share's single-use link (no email: the link is the proof);
* expired or revoked shares cannot be viewed or downloaded;
* downloads go through a signed URL valid for 5 minutes, bound to the user and the share;
* exports neutralize spreadsheet formulas.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from nazeer_api import audit
from nazeer_api.config import Settings
from nazeer_api.db import utcnow
from nazeer_api.deps import api_error, check_csrf, client_ip, current_user, data_manager, get_db, get_settings_dep, scoped
from nazeer_api.models import Blob, Membership, Share, ShareGrant, ShareLink, Twin, User
from nazeer_api.routers.auth import limit
from nazeer_api.security import new_token, token_hash
from nazeer_api.storage import export_csv_zip, export_xlsx, read_blob, zip_to_tables

org_router = APIRouter(prefix="/api/orgs/{org_id}", tags=["shares"], dependencies=[Depends(check_csrf)])
router = APIRouter(prefix="/api", tags=["received"], dependencies=[Depends(check_csrf)])
DOWNLOAD_TTL_S = 300
PREVIEW_ROWS = 20


def share_status(s: Share) -> str:
    if s.revoked_at is not None:
        return "revoked"
    if s.expires_at <= utcnow():
        return "expired"
    return "active"


def pending_decisions(t: Twin) -> int:
    return int((((t.report or {}).get("free_text") or {}).get("review") or {}).get("totals", {}).get("pending", 0))


def shareable(t: Twin) -> bool:
    return t.verdict == "PASS" and t.blob_id is not None and t.purged_at is None


# ---------------------------------------------------------------- organization side

class ShareIn(BaseModel):
    expires_in_days: int = Field(default=7, ge=1, le=30)
    formats: list[Literal["csv", "xlsx"]] = Field(default_factory=lambda: ["csv", "xlsx"], min_length=1)
    message: str | None = Field(default=None, max_length=500)
    member_ids: list[str] = Field(default_factory=list, max_length=200)
    external_labels: list[str] = Field(default_factory=list, max_length=50)


def org_share_payload(db: DbSession, s: Share) -> dict:
    grants = db.execute(select(ShareGrant).where(ShareGrant.share_id == s.id)).scalars().all()
    links = db.execute(select(ShareLink).where(ShareLink.share_id == s.id)).scalars().all()
    return {"id": s.id, "twin_id": s.twin_id, "dataset_name": s.twin.dataset.name, "mode": s.twin.mode,
            "status": share_status(s), "formats": s.formats, "message": s.message,
            "expires_at": s.expires_at.isoformat(), "created_at": s.created_at.isoformat(),
            "download_count": s.download_count, "recipients": len(grants),
            "links": [{"id": ln.id, "label": ln.label, "accepted": ln.accepted_at is not None} for ln in links]}


@org_router.post("/twins/{twin_id}/shares", status_code=201)
def create_share(org_id: str, twin_id: str, body: ShareIn, m: Membership = Depends(data_manager),
                 db: DbSession = Depends(get_db)) -> dict:
    twin = db.execute(scoped(select(Twin).where(Twin.id == twin_id), Twin, org_id)).scalar_one_or_none()
    if twin is None:
        raise api_error(404, "not_found")
    if not shareable(twin):
        raise api_error(409, "twin_not_shareable")
    if pending_decisions(twin):
        raise api_error(409, "decisions_pending")
    if not body.member_ids and not body.external_labels:
        raise api_error(422, "no_recipients")
    share = Share(org_id=org_id, twin_id=twin.id, formats=sorted(set(body.formats)), message=body.message,
                  expires_at=utcnow() + timedelta(days=body.expires_in_days), created_by=m.user_id)
    db.add(share)
    db.flush()
    members = db.execute(scoped(select(Membership), Membership, org_id).where(Membership.id.in_(body.member_ids))
                         ).scalars().all() if body.member_ids else []
    if len(members) != len(set(body.member_ids)):
        raise api_error(422, "unknown_member")
    for mem in members:
        db.add(ShareGrant(share_id=share.id, user_id=mem.user_id, via="member"))
    links = []
    for label in body.external_labels:
        label = label.strip()[:160] or "مستلم"
        token = new_token()
        link = ShareLink(share_id=share.id, label=label, token_hash=token_hash(token))
        db.add(link)
        links.append({"label": label, "link_path": f"/s?token={token}"})
    audit.record(db, "share.created", org_id=org_id, actor_user_id=m.user_id, target_type="share", target_id=share.id,
                 members=len(members), links=len(links), days=body.expires_in_days)
    db.commit()
    out = org_share_payload(db, share)
    out["new_links"] = links  # shown once; only hashes are stored
    return out


@org_router.get("/shares")
def list_shares(org_id: str, m: Membership = Depends(data_manager), db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(scoped(select(Share), Share, org_id).order_by(Share.created_at.desc()).limit(200)).scalars()
    return [org_share_payload(db, s) for s in rows]


@org_router.post("/shares/{share_id}/revoke")
def revoke_share(org_id: str, share_id: str, m: Membership = Depends(data_manager), db: DbSession = Depends(get_db)) -> dict:
    s = db.execute(scoped(select(Share).where(Share.id == share_id), Share, org_id)).scalar_one_or_none()
    if s is None:
        raise api_error(404, "not_found")
    if s.revoked_at is None:
        s.revoked_at = utcnow()
        audit.record(db, "share.revoked", org_id=org_id, actor_user_id=m.user_id, target_type="share", target_id=s.id)
        db.commit()
    return org_share_payload(db, s)


# ---------------------------------------------------------------- share links

class LinkIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


def _link(db: DbSession, token: str) -> ShareLink:
    link = db.execute(select(ShareLink).where(ShareLink.token_hash == token_hash(token))).scalar_one_or_none()
    if link is None:
        raise api_error(400, "invalid_or_expired_token")
    return link


@router.post("/share-links/preview")
def preview_link(body: LinkIn, request: Request, db: DbSession = Depends(get_db)) -> dict:
    limit(request, f"share-preview:{client_ip(request)}", 30, 300)
    link = _link(db, body.token)
    s = db.get(Share, link.share_id)
    return {"org_name": s.org.name, "dataset_name": s.twin.dataset.name, "status": share_status(s),
            "expires_at": s.expires_at.isoformat(), "accepted": link.accepted_at is not None}


@router.post("/share-links/accept")
def accept_link(body: LinkIn, request: Request, user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> dict:
    limit(request, f"share-accept:{client_ip(request)}", 30, 300)
    link = _link(db, body.token)
    s = db.get(Share, link.share_id)
    if link.accepted_by is not None and link.accepted_by != user.id:
        raise api_error(409, "link_already_used")
    if share_status(s) != "active":
        raise api_error(410, f"share_{share_status(s)}")
    if link.accepted_by is None:
        link.accepted_by, link.accepted_at = user.id, utcnow()
        if user.email_verified_at is None:
            user.email_verified_at = utcnow()  # opening the link and signing in is the verification
        exists = db.execute(select(ShareGrant).where(ShareGrant.share_id == s.id, ShareGrant.user_id == user.id)).first()
        if exists is None:
            db.add(ShareGrant(share_id=s.id, user_id=user.id, via="link", link_id=link.id))
        audit.record(db, "share.link_accepted", org_id=s.org_id, actor_user_id=user.id, target_type="share", target_id=s.id)
        db.commit()
    return {"share_id": s.id}


# ---------------------------------------------------------------- recipient side

def _grant(db: DbSession, user: User, share_id: str) -> Share:
    g = db.execute(select(ShareGrant).where(ShareGrant.share_id == share_id, ShareGrant.user_id == user.id)).scalar_one_or_none()
    if g is None:
        raise api_error(404, "not_found")
    return g.share


def cleaning_note(report: dict | None) -> dict | None:
    """What was cleaned before the twin was made: rules that ran and how many cells/rows each changed."""
    c = (report or {}).get("cleaning")
    if not c:
        return None
    on = [r for r, v in c.get("options", {}).items() if v and r != "merges"]
    if c.get("options", {}).get("merges"):
        on.append("merges")
    return {"rules": on, "changed": {r: v["total"] for r, v in c.get("applied", {}).items()}}


def received_payload(s: Share) -> dict:
    t = s.twin
    return {"id": s.id, "org_name": s.org.name, "dataset_name": t.dataset.name, "mode": t.mode, "verdict": t.verdict,
            "status": share_status(s), "formats": s.formats, "message": s.message,
            "created_at": s.created_at.isoformat(), "expires_at": s.expires_at.isoformat(),
            "tables": [{"name": tb["name"], "rows": tb["rows"]} for tb in (t.dataset.summary or {}).get("tables", [])],
            "cleaning": cleaning_note(t.report),
            "returns": _return_info(t)}


def _return_info(t: Twin) -> dict | None:
    from nazeer_api.returns import token_info

    info = token_info(t)
    return {"token_column": info["column"], "tables": [x["name"] for x in info["tables"]]} if info else None


@router.get("/received")
def received(user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> list[dict]:
    grants = db.execute(select(ShareGrant).where(ShareGrant.user_id == user.id).order_by(ShareGrant.created_at.desc())).scalars()
    return [received_payload(g.share) for g in grants]


def _active_share_tables(db: DbSession, settings: Settings, s: Share) -> dict:
    if share_status(s) != "active":
        raise api_error(410, f"share_{share_status(s)}")
    if s.twin.blob_id is None:
        raise api_error(410, "share_expired")
    from nazeer_api.returns import sealer_for, tables_for_share

    tables = zip_to_tables(read_blob(settings.master_key, db.get(Blob, s.twin.blob_id)))
    return tables_for_share(tables, sealer_for(settings, s))  # رمز_التحقق on every row


@router.get("/received/{share_id}")
def received_detail(share_id: str, user: User = Depends(current_user), db: DbSession = Depends(get_db),
                    settings: Settings = Depends(get_settings_dep)) -> dict:
    s = _grant(db, user, share_id)
    out = received_payload(s)
    proof = s.twin.proof or {}
    out["proof"] = proof
    if out["status"] == "active":
        tables = _active_share_tables(db, settings, s)
        out["preview"] = [{"table": n, "columns": list(df.columns),
                           "rows": df.head(PREVIEW_ROWS).astype(object).where(df.head(PREVIEW_ROWS).notna(), None).values.tolist()}
                          for n, df in tables.items()]
    return out


@router.get("/received/{share_id}/rows")
def received_rows(share_id: str, table: str | None = None, page: int = 1, size: int = 50, q: str = "",
                  sort: str | None = None, desc: bool = False, user: User = Depends(current_user),
                  db: DbSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    """The shared twin, page by page, with this share's verification tokens."""
    from nazeer_api import twin_view
    from nazeer_api.returns import sealer_for

    s = _grant(db, user, share_id)
    if share_status(s) != "active":
        raise api_error(410, f"share_{share_status(s)}")
    if s.twin.blob_id is None:
        raise api_error(410, "share_expired")
    tables, marks = twin_view.load(settings.master_key, db.get(Blob, s.twin.blob_id))
    return twin_view.page(tables, marks, table, page, size, q[:100], sort, desc, sealer_for(settings, s))


def _sign(settings: Settings, payload: str) -> str:
    key = hashlib.sha256(b"nazeer-download:" + settings.master_key).digest()
    return base64.urlsafe_b64encode(hmac.new(key, payload.encode(), hashlib.sha256).digest()).decode().rstrip("=")


class DownloadIn(BaseModel):
    format: Literal["csv", "xlsx"]


@router.post("/received/{share_id}/download")
def download_link(share_id: str, body: DownloadIn, user: User = Depends(current_user), db: DbSession = Depends(get_db),
                  settings: Settings = Depends(get_settings_dep)) -> dict:
    s = _grant(db, user, share_id)
    if share_status(s) != "active":
        raise api_error(410, f"share_{share_status(s)}")
    if body.format not in s.formats:
        raise api_error(422, "format_not_allowed")
    exp = int(time.time()) + DOWNLOAD_TTL_S
    payload = f"{s.id}.{user.id}.{body.format}.{exp}"
    return {"url": f"/api/downloads/{payload}.{_sign(settings, payload)}", "expires_in": DOWNLOAD_TTL_S}


@router.get("/downloads/{token}")
def download(token: str, user: User = Depends(current_user), db: DbSession = Depends(get_db),
             settings: Settings = Depends(get_settings_dep)):
    parts = token.split(".")
    if len(parts) != 5:
        raise api_error(404, "not_found")
    share_id, user_id, fmt, exp, sig = parts
    payload = ".".join(parts[:4])
    if not hmac.compare_digest(sig, _sign(settings, payload)) or user_id != user.id:
        raise api_error(403, "bad_download_link")
    if int(exp) < time.time():
        raise api_error(410, "download_link_expired")
    s = _grant(db, user, share_id)
    tables = _active_share_tables(db, settings, s)
    if fmt == "xlsx":
        data, media, ext = export_xlsx(tables), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    else:
        data, media, ext = export_csv_zip(tables), "application/zip", "zip"
    s.download_count += 1
    audit.record(db, "share.downloaded", org_id=s.org_id, actor_user_id=user.id, target_type="share", target_id=s.id,
                 format=fmt)
    db.commit()
    return Response(data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="nazeer-twin-{s.id[:8]}.{ext}"'})
