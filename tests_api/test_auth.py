from datetime import timedelta

from sqlalchemy import select, update

from nazeer_api.db import utcnow
from nazeer_api.models import EmailToken, Session
from tests_api.conftest import PASSWORD, invite, invite_and_join, new_client, signup, token_of


def test_signup_organization_creates_admin_and_session(app):
    c, me = signup(app, "admin@alwaha.example.com")
    assert me["email"] == "admin@alwaha.example.com"
    assert len(me["memberships"]) == 1 and me["memberships"][0]["role"] == "admin"
    cookies = {ck.name: ck for ck in c.cookies.jar}
    sess = cookies["__Host-nz_session"]
    assert sess.secure and sess.path == "/" and not sess.domain_specified
    assert sess.has_nonstandard_attr("HttpOnly")
    assert not cookies["__Host-nz_csrf"].has_nonstandard_attr("HttpOnly")  # readable by the web app


def test_signup_individual_has_no_org(app):
    _, me = signup(app, "person@example.com", org=None)
    assert me["memberships"] == []


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


def _member_reset_path(admin, org_id: str, email: str) -> str:
    row = next(m for m in admin.get(f"/api/orgs/{org_id}/members").json() if m["email"] == email)
    r = admin.post(f"/api/orgs/{org_id}/members/{row['id']}/reset-link")
    assert r.status_code == 201, r.text
    return r.json()["link_path"]


def test_admin_reset_link_flow(app):
    admin, me = signup(app, "boss@example.com")
    org = me["memberships"][0]["org_id"]
    emp, _ = invite_and_join(app, admin, org, "forgetful@example.com")
    token = token_of(_member_reset_path(admin, org, "forgetful@example.com"))
    c = new_client(app)
    assert c.post("/api/auth/reset-password", json={"token": token, "password": "a-brand-new-password"}).status_code == 200
    assert emp.get("/api/auth/me").status_code == 401  # every session ended
    again = c.post("/api/auth/reset-password", json={"token": token, "password": "another-password-1"})
    assert again.status_code == 400  # single use
    assert c.post("/api/auth/login", json={"email": "forgetful@example.com",
                                           "password": "a-brand-new-password"}).status_code == 200
    with app.state.sessionmaker() as db:
        assert token not in [t.token_hash for t in db.execute(select(EmailToken)).scalars()]  # only the hash


def test_reset_link_expires(app):
    admin, me = signup(app, "boss2@example.com")
    org = me["memberships"][0]["org_id"]
    invite_and_join(app, admin, org, "late@example.com")
    token = token_of(_member_reset_path(admin, org, "late@example.com"))
    with app.state.sessionmaker() as db:
        db.execute(update(EmailToken).where(EmailToken.purpose == "reset").values(expires_at=utcnow()))
        db.commit()
    c = new_client(app)
    assert c.post("/api/auth/reset-password", json={"token": token, "password": "a-brand-new-password"}).status_code == 400


def test_reset_link_refused_for_accounts_in_another_org(app):
    """Org A's admin must not be able to take over an account that also belongs to org B."""
    a, me_a = signup(app, "a-admin@example.com", org="منشأة أ")
    b, me_b = signup(app, "b-admin@example.com", org="منشأة ب")
    org_a, org_b = me_a["memberships"][0]["org_id"], me_b["memberships"][0]["org_id"]
    shared, _ = invite_and_join(app, b, org_b, "both@example.com")
    token = invite(a, org_a, "both@example.com")
    assert shared.post("/api/invitations/accept", json={"token": token}).status_code == 200
    row = next(m for m in a.get(f"/api/orgs/{org_a}/members").json() if m["email"] == "both@example.com")
    r = a.post(f"/api/orgs/{org_a}/members/{row['id']}/reset-link")
    assert r.status_code == 409 and r.json()["code"] == "member_of_other_org"


def test_reset_link_is_admin_only(app):
    admin, me = signup(app, "boss3@example.com")
    org = me["memberships"][0]["org_id"]
    emp, _ = invite_and_join(app, admin, org, "plain@example.com")
    row = next(m for m in admin.get(f"/api/orgs/{org}/members").json() if m["email"] == "boss3@example.com")
    assert emp.post(f"/api/orgs/{org}/members/{row['id']}/reset-link").json()["code"] == "admin_only"


def test_forgot_password_and_verification_endpoints_are_gone(client):
    assert client.post("/api/auth/forgot-password", json={"email": "x@example.com"}).status_code in (404, 405)
    assert client.post("/api/auth/verify-email", json={"token": "x" * 20}).status_code in (404, 405)


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


def test_preview_origin_regex(app):
    from dataclasses import replace

    app.state.settings = replace(app.state.settings, allowed_origin_regex=r"https://nazeer-[a-z0-9-]+-team\.vercel\.app")
    c = new_client(app)
    ok = c.post("/api/auth/login", json={"email": "a@b.example.com", "password": PASSWORD},
                headers={"Origin": "https://nazeer-git-main-team.vercel.app"})
    assert ok.status_code == 401  # passed the origin check, failed on credentials
    bad = c.post("/api/auth/login", json={"email": "a@b.example.com", "password": PASSWORD},
                 headers={"Origin": "https://nazeer-git-main-team.vercel.app.evil.example"})
    assert bad.json()["code"] == "origin_not_allowed"
