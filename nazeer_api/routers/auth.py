"""Sign up (organization or individual), login, logout, me, email verification, password reset."""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Literal

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from nazeer_api import audit, mail
from nazeer_api.config import Settings
from nazeer_api.db import utcnow
from nazeer_api.deps import api_error, check_csrf, client_ip, current_user, get_db, get_settings_dep
from nazeer_api.models import EmailToken, Membership, Organization, Session, User, new_id
from nazeer_api.security import (PASSWORD_MAX, PASSWORD_MIN, encrypt_org_key, hash_password, needs_rehash,
                                 new_org_key, new_token, token_hash, verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])
VERIFY_TTL = timedelta(hours=48)
RESET_TTL = timedelta(hours=1)


# ---------------------------------------------------------------- helpers

def normalize_email(raw: str) -> str:
    try:
        return validate_email(raw.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise api_error(422, "invalid_email") from None


def check_password(password: str) -> None:
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise api_error(422, "weak_password")


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return f"{base or 'org'}-{new_id()[:6]}"


def limit(request: Request, key: str, n: int, window_s: int) -> None:
    wait = request.app.state.limiter.hit(key, n, window_s)
    if wait is not None:
        raise api_error(429, "rate_limited")


def set_csrf_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(settings.csrf_cookie, token, httponly=False, secure=settings.cookie_secure,
                        samesite="lax", path="/", domain=settings.cookie_domain,
                        max_age=settings.session_max_days * 86400)


def start_session(db: DbSession, response: Response, settings: Settings, user: User) -> None:
    token = new_token()
    now = utcnow()
    db.add(Session(token_hash=token_hash(token), user_id=user.id, last_seen_at=now,
                   expires_at=now + timedelta(days=settings.session_max_days)))
    response.set_cookie(settings.session_cookie, token, httponly=True, secure=settings.cookie_secure,
                        samesite="lax", path="/", domain=settings.cookie_domain,
                        max_age=settings.session_max_days * 86400)
    set_csrf_cookie(response, settings, new_token())  # rotate CSRF on login


def clear_session_cookies(response: Response, settings: Settings) -> None:
    # The CSRF cookie is not tied to a session; it stays so the next form still works.
    response.delete_cookie(settings.session_cookie, path="/", domain=settings.cookie_domain,
                           secure=settings.cookie_secure, samesite="lax")


def issue_email_token(db: DbSession, user: User, purpose: str, ttl: timedelta) -> str:
    db.execute(delete(EmailToken).where(EmailToken.user_id == user.id, EmailToken.purpose == purpose,
                                        EmailToken.used_at.is_(None)))
    token = new_token()
    db.add(EmailToken(user_id=user.id, purpose=purpose, token_hash=token_hash(token), expires_at=utcnow() + ttl))
    return token


def consume_email_token(db: DbSession, token: str, purpose: str) -> EmailToken:
    row = db.execute(select(EmailToken).where(EmailToken.token_hash == token_hash(token),
                                              EmailToken.purpose == purpose)).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        raise api_error(400, "invalid_or_expired_token")
    row.used_at = utcnow()
    return row


def me_payload(user: User) -> dict:
    return {
        "id": user.id, "email": user.email, "full_name": user.full_name, "email_verified": user.email_verified,
        "memberships": [{"org_id": m.org_id, "org_name": m.org.name, "role": m.role,
                         "data_manager": m.data_manager} for m in user.memberships],
    }


# ---------------------------------------------------------------- schemas

class SignupIn(BaseModel):
    account_type: Literal["organization", "individual"]
    email: str = Field(max_length=254)
    password: str = Field(max_length=PASSWORD_MAX)
    full_name: str = Field(min_length=2, max_length=120)
    org_name: str | None = Field(default=None, min_length=2, max_length=160)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=PASSWORD_MAX)


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class EmailIn(BaseModel):
    email: str = Field(max_length=254)


class ResetIn(TokenIn):
    password: str = Field(max_length=PASSWORD_MAX)


# ---------------------------------------------------------------- routes

@router.get("/csrf")
def csrf(request: Request, response: Response, settings: Settings = Depends(get_settings_dep)) -> dict:
    """Issues the CSRF cookie (the web app calls this once before its first form)."""
    token = request.cookies.get(settings.csrf_cookie) or new_token()
    set_csrf_cookie(response, settings, token)
    return {"csrf_token": token}


@router.post("/signup", status_code=201, dependencies=[Depends(check_csrf)])
def signup(body: SignupIn, request: Request, response: Response, db: DbSession = Depends(get_db),
           settings: Settings = Depends(get_settings_dep)) -> dict:
    limit(request, f"signup:ip:{client_ip(request)}", 10, 3600)
    email = normalize_email(body.email)
    check_password(body.password)
    if body.account_type == "organization" and not body.org_name:
        raise api_error(422, "org_name_required")
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name.strip())
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise api_error(409, "email_taken") from None
    if body.account_type == "organization":
        org = Organization(id=new_id(), name=body.org_name.strip(), slug=slugify(body.org_name), key_version=1)
        org.enc_key = encrypt_org_key(settings.master_key, org.id, 1, new_org_key())
        db.add(org)
        db.add(Membership(org_id=org.id, user_id=user.id, role="admin"))
        db.flush()
        audit.record(db, "org.created", org_id=org.id, actor_user_id=user.id, target_type="org", target_id=org.id)
    token = issue_email_token(db, user, "verify", VERIFY_TTL)
    start_session(db, response, settings, user)
    db.commit()
    request.app.state.mailer.send(mail.verify_email(settings.app_base_url, user.email, token))
    db.refresh(user)
    return me_payload(user)


@router.post("/login", dependencies=[Depends(check_csrf)])
def login(body: LoginIn, request: Request, response: Response, db: DbSession = Depends(get_db),
          settings: Settings = Depends(get_settings_dep)) -> dict:
    email = body.email.strip().lower()
    limit(request, f"login:ip:{client_ip(request)}", 20, 300)
    limit(request, f"login:email:{token_hash(email)}", 8, 300)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not verify_password(user.password_hash if user else None, body.password) or not user.is_active:
        raise api_error(401, "invalid_credentials")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    start_session(db, response, settings, user)
    audit.record(db, "auth.login", actor_user_id=user.id, target_type="user", target_id=user.id)
    db.commit()
    return me_payload(user)


@router.post("/logout", dependencies=[Depends(check_csrf)])
def logout(request: Request, response: Response, db: DbSession = Depends(get_db),
           settings: Settings = Depends(get_settings_dep)) -> dict:
    raw = request.cookies.get(settings.session_cookie)
    if raw:
        db.execute(delete(Session).where(Session.token_hash == token_hash(raw)))
        db.commit()
    clear_session_cookies(response, settings)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return me_payload(user)


@router.post("/verify-email", dependencies=[Depends(check_csrf)])
def verify_email(body: TokenIn, db: DbSession = Depends(get_db)) -> dict:
    row = consume_email_token(db, body.token, "verify")
    user = db.get(User, row.user_id)
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    audit.record(db, "auth.email_verified", actor_user_id=user.id, target_type="user", target_id=user.id)
    db.commit()
    return {"ok": True}


@router.post("/resend-verification", dependencies=[Depends(check_csrf)])
def resend_verification(request: Request, user: User = Depends(current_user), db: DbSession = Depends(get_db),
                        settings: Settings = Depends(get_settings_dep)) -> dict:
    limit(request, f"resend:{user.id}", 3, 3600)
    if user.email_verified:
        return {"ok": True}
    token = issue_email_token(db, user, "verify", VERIFY_TTL)
    db.commit()
    request.app.state.mailer.send(mail.verify_email(settings.app_base_url, user.email, token))
    return {"ok": True}


@router.post("/forgot-password", status_code=202, dependencies=[Depends(check_csrf)])
def forgot_password(body: EmailIn, request: Request, db: DbSession = Depends(get_db),
                    settings: Settings = Depends(get_settings_dep)) -> dict:
    """Always 202: the answer never reveals whether an account exists."""
    email = body.email.strip().lower()
    limit(request, f"forgot:ip:{client_ip(request)}", 10, 3600)
    if request.app.state.limiter.hit(f"forgot:email:{token_hash(email)}", 3, 3600) is not None:
        return {"ok": True}
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None and user.is_active:
        token = issue_email_token(db, user, "reset", RESET_TTL)
        db.commit()
        request.app.state.mailer.send(mail.reset_password(settings.app_base_url, user.email, token))
    return {"ok": True}


@router.post("/reset-password", dependencies=[Depends(check_csrf)])
def reset_password(body: ResetIn, response: Response, db: DbSession = Depends(get_db),
                   settings: Settings = Depends(get_settings_dep)) -> dict:
    check_password(body.password)
    row = consume_email_token(db, body.token, "reset")
    user = db.get(User, row.user_id)
    user.password_hash = hash_password(body.password)
    # The reset link proves control of the mailbox.
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    db.execute(delete(Session).where(Session.user_id == user.id))  # sign out everywhere
    audit.record(db, "auth.password_reset", actor_user_id=user.id, target_type="user", target_id=user.id)
    db.commit()
    clear_session_cookies(response, settings)
    return {"ok": True}
