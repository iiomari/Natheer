"""Organization workspace: profile, members, invitations, jobs, audit log.

Every route is scoped to /api/orgs/{org_id} and guarded by member()/admin() from deps.py.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from nazeer_api import audit, jobs, mail
from nazeer_api.config import Settings
from nazeer_api.db import utcnow
from nazeer_api.deps import admin, api_error, check_csrf, get_db, get_settings_dep, member, scoped
from nazeer_api.models import AuditEvent, Invitation, Job, Membership, Organization, User
from nazeer_api.routers.auth import limit, normalize_email
from nazeer_api.security import new_token, token_hash

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["orgs"], dependencies=[Depends(check_csrf)])
INVITE_TTL = timedelta(days=7)


class OrgPatch(BaseModel):
    name: str = Field(min_length=2, max_length=160)


class InviteIn(BaseModel):
    email: str = Field(max_length=254)
    role: Literal["admin", "member"] = "member"
    data_manager: bool = False


class MemberPatch(BaseModel):
    role: Literal["admin", "member"] | None = None
    data_manager: bool | None = None


def org_payload(org: Organization, m: Membership) -> dict:
    return {"id": org.id, "name": org.name, "slug": org.slug, "key_version": org.key_version,
            "my_role": m.role, "my_data_manager": m.data_manager}


def member_payload(m: Membership) -> dict:
    return {"id": m.id, "user_id": m.user_id, "full_name": m.user.full_name, "email": m.user.email,
            "role": m.role, "data_manager": m.data_manager, "email_verified": m.user.email_verified,
            "joined_at": m.created_at.isoformat()}


def job_payload(j: Job) -> dict:
    return {"id": j.id, "kind": j.kind, "status": j.status, "stage": j.stage, "progress": j.progress,
            "result": j.result, "error_code": j.error_code, "created_at": j.created_at.isoformat(),
            "finished_at": j.finished_at.isoformat() if j.finished_at else None}


def _admin_count(db: DbSession, org_id: str) -> int:
    return db.execute(select(func.count()).select_from(Membership).where(
        Membership.org_id == org_id, Membership.role == "admin")).scalar_one()


def _membership(db: DbSession, org_id: str, membership_id: str) -> Membership:
    m = db.execute(scoped(select(Membership).where(Membership.id == membership_id), Membership, org_id)
                   ).scalar_one_or_none()
    if m is None:
        raise api_error(404, "not_found")
    return m


# ---------------------------------------------------------------- organization

@router.get("")
def get_org(org_id: str, m: Membership = Depends(member)) -> dict:
    return org_payload(m.org, m)


@router.patch("")
def update_org(org_id: str, body: OrgPatch, m: Membership = Depends(admin), db: DbSession = Depends(get_db)) -> dict:
    m.org.name = body.name.strip()
    audit.record(db, "org.updated", org_id=org_id, actor_user_id=m.user_id, target_type="org", target_id=org_id)
    db.commit()
    return org_payload(m.org, m)


# ---------------------------------------------------------------- members

@router.get("/members")
def list_members(org_id: str, m: Membership = Depends(admin), db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(scoped(select(Membership), Membership, org_id).order_by(Membership.created_at)).scalars()
    return [member_payload(x) for x in rows]


@router.patch("/members/{membership_id}")
def update_member(org_id: str, membership_id: str, body: MemberPatch, m: Membership = Depends(admin),
                  db: DbSession = Depends(get_db)) -> dict:
    target = _membership(db, org_id, membership_id)
    if body.role is not None and body.role != target.role:
        if target.role == "admin" and _admin_count(db, org_id) <= 1:
            raise api_error(409, "last_admin")
        audit.record(db, "member.role_changed", org_id=org_id, actor_user_id=m.user_id, target_type="membership",
                     target_id=target.id, old=target.role, new=body.role)
        target.role = body.role
    if body.data_manager is not None and body.data_manager != target.data_manager:
        audit.record(db, "member.data_manager_changed", org_id=org_id, actor_user_id=m.user_id,
                     target_type="membership", target_id=target.id, new=body.data_manager)
        target.data_manager = body.data_manager
    db.commit()
    return member_payload(target)


@router.delete("/members/{membership_id}")
def remove_member(org_id: str, membership_id: str, m: Membership = Depends(admin),
                  db: DbSession = Depends(get_db)) -> dict:
    target = _membership(db, org_id, membership_id)
    if target.role == "admin" and _admin_count(db, org_id) <= 1:
        raise api_error(409, "last_admin")
    audit.record(db, "member.removed", org_id=org_id, actor_user_id=m.user_id, target_type="membership",
                 target_id=target.id)
    db.delete(target)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- invitations

@router.get("/invitations")
def list_invitations(org_id: str, m: Membership = Depends(admin), db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(scoped(select(Invitation), Invitation, org_id).where(
        Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None)).order_by(Invitation.created_at)).scalars()
    now = utcnow()
    return [{"id": i.id, "email": i.email, "role": i.role, "data_manager": i.data_manager,
             "expires_at": i.expires_at.isoformat(), "expired": i.expires_at <= now} for i in rows]


@router.post("/invitations", status_code=201)
def invite(org_id: str, body: InviteIn, request: Request, m: Membership = Depends(admin),
           db: DbSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    limit(request, f"invite:{org_id}", 50, 3600)
    email = normalize_email(body.email)
    if db.execute(select(Membership.id).join(Membership.user).where(
            Membership.org_id == org_id, User.email == email)).first() is not None:
        raise api_error(409, "already_member")
    # One open invitation per email: a new one replaces the old link.
    for old in db.execute(scoped(select(Invitation), Invitation, org_id).where(
            Invitation.email == email, Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None))).scalars():
        old.revoked_at = utcnow()
    token = new_token()
    inv = Invitation(org_id=org_id, email=email, role=body.role, data_manager=body.data_manager,
                     token_hash=token_hash(token), invited_by=m.user_id, expires_at=utcnow() + INVITE_TTL)
    db.add(inv)
    db.flush()
    audit.record(db, "member.invited", org_id=org_id, actor_user_id=m.user_id, target_type="invitation",
                 target_id=inv.id, role=body.role, data_manager=body.data_manager)
    db.commit()
    request.app.state.mailer.send(mail.invitation(settings.app_base_url, email, m.org.name, token))
    return {"id": inv.id, "email": email, "role": inv.role, "expires_at": inv.expires_at.isoformat()}


@router.delete("/invitations/{invitation_id}")
def revoke_invitation(org_id: str, invitation_id: str, m: Membership = Depends(admin),
                      db: DbSession = Depends(get_db)) -> dict:
    inv = db.execute(scoped(select(Invitation).where(Invitation.id == invitation_id), Invitation, org_id)
                     ).scalar_one_or_none()
    if inv is None:
        raise api_error(404, "not_found")
    inv.revoked_at = utcnow()
    audit.record(db, "member.invitation_revoked", org_id=org_id, actor_user_id=m.user_id,
                 target_type="invitation", target_id=inv.id)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- jobs

@router.get("/jobs/{job_id}")
def get_job(org_id: str, job_id: str, m: Membership = Depends(member), db: DbSession = Depends(get_db)) -> dict:
    j = db.execute(scoped(select(Job).where(Job.id == job_id), Job, org_id)).scalar_one_or_none()
    if j is None:
        raise api_error(404, "not_found")
    return job_payload(j)


@router.post("/jobs/ping", status_code=202)
def ping_job(org_id: str, m: Membership = Depends(admin), db: DbSession = Depends(get_db)) -> dict:
    """Diagnostic: proves the worker is alive end to end."""
    j = jobs.enqueue(db, org_id, "ping", {}, created_by=m.user_id)
    db.commit()
    return job_payload(j)


# ---------------------------------------------------------------- audit

@router.get("/audit")
def audit_log(org_id: str, n: int = 100, m: Membership = Depends(admin),
              db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(scoped(select(AuditEvent), AuditEvent, org_id).order_by(AuditEvent.created_at.desc())
                      .limit(max(1, min(n, 500)))).scalars()
    return [{"id": e.id, "action": e.action, "actor_user_id": e.actor_user_id, "target_type": e.target_type,
             "target_id": e.target_id, "meta": e.meta, "at": e.created_at.isoformat()} for e in rows]
