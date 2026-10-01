from datetime import timedelta

from fastapi import Depends
from sqlalchemy import select, update

from nazeer_api.db import utcnow
from nazeer_api.deps import verified_user
from nazeer_api.models import Session
from tests_api.conftest import PASSWORD, link_token, new_client, signup


def test_signup_organization_creates_admin_and_session(app, mailer):
    c, me = signup(app, "admin@alwaha.example.com", verify=False)
    assert me["email"] == "admin@alwaha.example.com" and not me["email_verified"]
    assert len(me["memberships"]) == 1 and me["memberships"][0]["role"] == "admin"
    assert mailer.outbox[-1].kind == "verify_email" and "token=" in mailer.outbox[-1].text
    cookies = {ck.name: ck for ck in c.cookies.jar}
    sess = cookies["__Host-nz_session"]
    assert sess.secure and sess.path == "/" and not sess.domain_specified
    assert sess.has_nonstandard_attr("HttpOnly")
    assert not cookies["__Host-nz_csrf"].has_nonstandard_attr("HttpOnly")  # readable by the web app


def test_signup_individual_has_no_org(app):
    _, me = signup(app, "person@example.com", org=None)
    assert me["memberships"] == [] and me["email_verified"]


def test_duplicate_email_and_weak_password_rejected(app, client):
    signup(app, "dup@example.com", org=None)
    r = client.post("/api/auth/signup", json={"account_type": "individual", "email": "DUP@example.com",
                                              "password": PASSWORD, "full_name": "x y"})
    assert r.status_code == 409 and r.json()["code"] == "email_taken"
    r = client.post("/api/auth/signup", json={"account_type": "individual", "email": "new@example.com",
                                              "password": "short", "full_name": "x y"})
    assert r.status_code == 422 and r.json()["code"] == "weak_password"


def test_login_logout_and_wrong_password(app):
    signup(app, "u@example.com", org=None)
    c = new_client(app)
    assert c.post("/api/auth/login", json={"email": "u@example.com", "password": "wrong-password!"}).json() == \
        {"code": "invalid_credentials"}
    assert c.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}).json() == \
        {"code": "invalid_credentials"}  # same answer: no account enumeration
    assert c.post("/api/auth/login", json={"email": "U@example.com", "password": PASSWORD}).status_code == 200
    assert c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").status_code == 401


def test_csrf_required_on_unsafe_methods(app):
    c = new_client(app)
    del c.headers["X-CSRF-Token"]
    r = c.post("/api/auth/login", json={"email": "a@b.example.com", "password": PASSWORD})
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
    c.headers["X-CSRF-Token"] = "forged-token-value"
    assert c.post("/api/auth/login", json={"email": "a@b.example.com", "password": PASSWORD}).status_code == 403


def test_foreign_origin_rejected(app, client):
    r = client.post("/api/auth/login", json={"email": "a@b.example.com", "password": PASSWORD},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "origin_not_allowed"


def test_session_idle_and_absolute_expiry(app):
    c, _ = signup(app, "exp@example.com", org=None)
    with app.state.sessionmaker() as db:
        db.execute(update(Session).values(last_seen_at=utcnow() - timedelta(days=8)))
        db.commit()
    assert c.get("/api/auth/me").status_code == 401
    c2 = new_client(app)
    c2.post("/api/auth/login", json={"email": "exp@example.com", "password": PASSWORD})
    with app.state.sessionmaker() as db:
        db.execute(update(Session).values(expires_at=utcnow() - timedelta(seconds=1)))
        db.commit()
    assert c2.get("/api/auth/me").status_code == 401


def test_login_rate_limited(app):
    signup(app, "rl@example.com", org=None)
    c = new_client(app)
    codes = [c.post("/api/auth/login", json={"email": "rl@example.com", "password": "wrong-password!"}).status_code
             for _ in range(10)]
    assert codes[:8] == [401] * 8 and codes[8:] == [429, 429]


def test_verify_email_token_is_single_use(app, mailer):
    c, _ = signup(app, "v@example.com", org=None, verify=False)
    token = link_token(mailer.outbox[-1])
    assert c.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    assert c.get("/api/auth/me").json()["email_verified"]
    r = c.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 400 and r.json()["code"] == "invalid_or_expired_token"


def test_password_reset_flow(app, mailer):
    old, _ = signup(app, "r@example.com", org=None)
    c = new_client(app)
    assert c.post("/api/auth/forgot-password", json={"email": "r@example.com"}).status_code == 202
    assert c.post("/api/auth/forgot-password", json={"email": "ghost@example.com"}).status_code == 202
    resets = [m for m in mailer.outbox if m.kind == "reset_password"]
    assert [m.to for m in resets] == ["r@example.com"]
    token = link_token(resets[0])
    assert c.post("/api/auth/reset-password", json={"token": token, "password": "a-brand-new-password"}).status_code == 200
    assert old.get("/api/auth/me").status_code == 401  # every session ended
    assert c.post("/api/auth/reset-password", json={"token": token, "password": "another-password-1"}).status_code == 400
    assert c.post("/api/auth/login", json={"email": "r@example.com", "password": "a-brand-new-password"}).status_code == 200


def test_reset_token_expires(app, mailer):
    signup(app, "e@example.com", org=None)
    c = new_client(app)
    c.post("/api/auth/forgot-password", json={"email": "e@example.com"})
    from nazeer_api.models import EmailToken
    with app.state.sessionmaker() as db:
        db.execute(update(EmailToken).where(EmailToken.purpose == "reset").values(expires_at=utcnow()))
        db.commit()
    token = link_token(mailer.outbox[-1])
    assert c.post("/api/auth/reset-password", json={"token": token, "password": "a-brand-new-password"}).status_code == 400


def test_unverified_user_blocked_from_verified_only_routes(app):
    """Shared data (P2) uses verified_user: an unverified account registered with someone's address
    gets 403 email_not_verified."""
    @app.get("/api/_test/shared")
    def shared(user=Depends(verified_user)):
        return {"ok": True}

    unverified, _ = signup(app, "squatter@example.com", org=None, verify=False)
    r = unverified.get("/api/_test/shared")
    assert r.status_code == 403 and r.json()["code"] == "email_not_verified"
    verified, _ = signup(app, "owner@example.com", org=None)
    assert verified.get("/api/_test/shared").status_code == 200


def test_session_token_stored_hashed(app):
    c, _ = signup(app, "h@example.com", org=None)
    raw = c.cookies.get("__Host-nz_session")
    with app.state.sessionmaker() as db:
        hashes = db.execute(select(Session.token_hash)).scalars().all()
    assert raw not in hashes and len(hashes[0]) == 64


def test_secure_headers_and_errors_carry_codes_only(app, client):
    r = client.get("/api/health")
    assert r.headers["X-Frame-Options"] == "DENY" and "Strict-Transport-Security" in r.headers
    assert r.headers["Cache-Control"] == "no-store"
    r = client.post("/api/auth/signup", json={"account_type": "individual", "email": "x@y.example.com",
                                              "password": "1110704341-secret", "full_name": 5})
    assert r.status_code == 422 and "1110704341" not in r.text and r.json()["code"] == "invalid_request"
