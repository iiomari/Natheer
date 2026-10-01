"""Request dependencies: DB session, current user, CSRF, tenancy and role checks.

Tenant rule: every organization route is /api/orgs/{org_id}/...; require_member() resolves the
caller's membership in THAT organization and answers 404 (not 403) when there is none, so an
outsider cannot even learn that the organization exists. Data queries go through scoped().
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import Select, select
from sqlalchemy.orm import Session as DbSession

from nazeer_api.config import Settings
from nazeer_api.db import utcnow
from nazeer_api.models import Membership, Session, User
from nazeer_api.security import CSRF_HEADER, UNSAFE_METHODS, csrf_ok, token_hash

SESSION_TOUCH_SECONDS = 60


def api_error(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[DbSession]:
    db = request.app.state.sessionmaker()
    try:
        yield db
    finally:
        db.close()


def client_ip(request: Request) -> str:
    if request.app.state.settings.trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_csrf(request: Request) -> None:
    """Double-submit check for every unsafe method, plus an Origin allow-list when the browser sends one."""
    if request.method not in UNSAFE_METHODS:
        return
    settings: Settings = request.app.state.settings
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in settings.allowed_origins:
        raise api_error(403, "origin_not_allowed")
    if not csrf_ok(request.cookies.get(settings.csrf_cookie), request.headers.get(CSRF_HEADER)):
        raise api_error(403, "csrf_failed")


def _load_session(request: Request, db: DbSession) -> Session | None:
    settings: Settings = request.app.state.settings
    raw = request.cookies.get(settings.session_cookie)
    if not raw:
        return None
    sess = db.execute(select(Session).where(Session.token_hash == token_hash(raw))).scalar_one_or_none()
    if sess is None:
        return None
    now = utcnow()
    idle_limit = sess.last_seen_at + timedelta(days=settings.session_idle_days)
    if now >= sess.expires_at or now >= idle_limit or not sess.user.is_active:
        db.delete(sess)
        db.commit()
        return None
    if (now - sess.last_seen_at).total_seconds() > SESSION_TOUCH_SECONDS:
        sess.last_seen_at = now
        db.commit()
    return sess


def optional_user(request: Request, db: DbSession = Depends(get_db)) -> User | None:
    sess = _load_session(request, db)
    return sess.user if sess else None


def current_user(request: Request, db: DbSession = Depends(get_db)) -> User:
    sess = _load_session(request, db)
    if sess is None:
        raise api_error(401, "not_authenticated")
    request.state.session_id = sess.id
    return sess.user


def verified_user(user: User = Depends(current_user)) -> User:
    """Shared data (received twins, downloads, returns) requires a verified email: an account that
    merely registered with someone's address must not see what was shared to that address."""
    if not user.email_verified:
        raise api_error(403, "email_not_verified")
    return user


def require_member(org_id: str, user: User, db: DbSession, role: str | None = None) -> Membership:
    m = db.execute(select(Membership).where(Membership.org_id == org_id, Membership.user_id == user.id)
                   ).scalar_one_or_none()
    if m is None:
        raise api_error(404, "not_found")
    if role == "admin" and m.role != "admin":
        raise api_error(403, "admin_only")
    if role == "data_manager" and not m.can_manage_data:
        raise api_error(403, "data_manager_only")
    return m


def member(org_id: str, user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> Membership:
    return require_member(org_id, user, db)


def admin(org_id: str, user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> Membership:
    return require_member(org_id, user, db, "admin")


def data_manager(org_id: str, user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> Membership:
    return require_member(org_id, user, db, "data_manager")


def scoped(stmt: Select, model, org_id: str) -> Select:
    """Every tenant-owned query passes through here: the org filter cannot be forgotten at a call site."""
    return stmt.where(model.org_id == org_id)
