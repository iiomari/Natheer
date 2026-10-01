"""Public side of invitations: preview a link, accept it (as a new or an existing user).

The emailed link proves control of the mailbox, so accepting it verifies the email.
An existing account must be signed in AS the invited address to accept.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from nazeer_api import audit
from nazeer_api.config import Settings
from nazeer_api.db import utcnow
from nazeer_api.deps import api_error, check_csrf, client_ip, get_db, get_settings_dep, optional_user
from nazeer_api.models import Invitation, Membership, User
from nazeer_api.routers.auth import check_password, limit, me_payload, start_session
from nazeer_api.security import PASSWORD_MAX, hash_password, token_hash

router = APIRouter(prefix="/api/invitations", tags=["invitations"])


class AcceptIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    password: str | None = Field(default=None, max_length=PASSWORD_MAX)


class PreviewIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


def _open_invitation(db: DbSession, token: str) -> Invitation:
    inv = db.execute(select(Invitation).where(Invitation.token_hash == token_hash(token))).scalar_one_or_none()
    if inv is None or inv.revoked_at is not None or inv.accepted_at is not None or inv.expires_at <= utcnow():
        raise api_error(400, "invalid_or_expired_token")
    return inv


@router.post("/preview", dependencies=[Depends(check_csrf)])
def preview(body: PreviewIn, request: Request, db: DbSession = Depends(get_db)) -> dict:
    """POST (not GET with the token in the URL) so tokens stay out of access logs."""
    limit(request, f"invite-preview:{client_ip(request)}", 30, 300)
    inv = _open_invitation(db, body.token)
    has_account = db.execute(select(User.id).where(User.email == inv.email)).first() is not None
    return {"org_name": inv.org.name, "email": inv.email, "role": inv.role, "has_account": has_account}


@router.post("/accept", dependencies=[Depends(check_csrf)])
def accept(body: AcceptIn, request: Request, response: Response, db: DbSession = Depends(get_db),
           user: User | None = Depends(optional_user), settings: Settings = Depends(get_settings_dep)) -> dict:
    limit(request, f"invite-accept:{client_ip(request)}", 30, 300)
    inv = _open_invitation(db, body.token)
    existing = db.execute(select(User).where(User.email == inv.email)).scalar_one_or_none()
    if user is not None:
        if user.email != inv.email:
            raise api_error(403, "invitation_for_other_email")
        target = user
    elif existing is not None:
        raise api_error(409, "login_required")
    else:
        if not body.full_name or not body.password:
            raise api_error(422, "name_and_password_required")
        check_password(body.password)
        target = User(email=inv.email, password_hash=hash_password(body.password), full_name=body.full_name.strip())
        db.add(target)
        db.flush()
        start_session(db, response, settings, target)
    if target.email_verified_at is None:
        target.email_verified_at = utcnow()
    already = db.execute(select(Membership).where(Membership.org_id == inv.org_id,
                                                  Membership.user_id == target.id)).scalar_one_or_none()
    if already is None:
        db.add(Membership(org_id=inv.org_id, user_id=target.id, role=inv.role, data_manager=inv.data_manager))
    inv.accepted_at = utcnow()
    audit.record(db, "member.joined", org_id=inv.org_id, actor_user_id=target.id, target_type="invitation",
                 target_id=inv.id, role=inv.role)
    db.commit()
    db.refresh(target)
    return me_payload(target)
