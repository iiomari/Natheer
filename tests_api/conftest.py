"""API test fixtures: a fresh SQLite database per test, an in-memory mailer, HTTPS test client
(so Secure / __Host- cookies behave as in production)."""
from __future__ import annotations

import os
import re

import pytest
from fastapi.testclient import TestClient

from nazeer_api.config import Settings
from nazeer_api.mail import MemoryMailer
from nazeer_api.main import create_app
from nazeer_api.models import Base

MASTER_KEY = os.urandom(32)
ORIGIN = "https://nazeer.test"
PASSWORD = "correct-horse-battery"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(database_url=f"sqlite:///{(tmp_path / 'api.db').as_posix()}", master_key=MASTER_KEY,
                    app_base_url=ORIGIN, allowed_origins=(ORIGIN,), cookie_secure=True, mail_backend="memory")


@pytest.fixture
def app(settings):
    mailer = MemoryMailer()
    application = create_app(settings, mailer=mailer)
    Base.metadata.create_all(application.state.engine)
    yield application
    application.state.engine.dispose()


@pytest.fixture
def mailer(app) -> MemoryMailer:
    return app.state.mailer


def new_client(app) -> TestClient:
    """Behaves like the web app: reads the (rotating) CSRF cookie and echoes it in the header."""
    c = TestClient(app, base_url="https://testserver")
    c.get("/api/auth/csrf")

    def echo_csrf(request) -> None:
        # "auto" = use the current cookie; tests that remove or forge the header are left alone.
        if request.headers.get("X-CSRF-Token") == "auto":
            request.headers["X-CSRF-Token"] = c.cookies.get("__Host-nz_csrf") or ""

    c.headers["X-CSRF-Token"] = "auto"
    c.event_hooks["request"].append(echo_csrf)
    return c


@pytest.fixture
def client(app) -> TestClient:
    return new_client(app)


def link_token(mail) -> str:
    return re.search(r"token=([\w-]+)", mail.text).group(1)


def signup(app, email: str, *, org: str | None = "منشأة الاختبار", name: str = "مستخدم تجريبي",
           verify: bool = True) -> tuple[TestClient, dict]:
    """Returns (logged-in client, /me payload)."""
    c = new_client(app)
    body = {"account_type": "organization" if org else "individual", "email": email, "password": PASSWORD,
            "full_name": name}
    if org:
        body["org_name"] = org
    r = c.post("/api/auth/signup", json=body)
    assert r.status_code == 201, r.text
    if verify:
        mail = next(m for m in reversed(app.state.mailer.outbox) if m.to == email and m.kind == "verify_email")
        assert c.post("/api/auth/verify-email", json={"token": link_token(mail)}).status_code == 200
    return c, c.get("/api/auth/me").json()


def invite_and_join(app, admin_client: TestClient, org_id: str, email: str, role: str = "member",
                    data_manager: bool = False) -> tuple[TestClient, dict]:
    r = admin_client.post(f"/api/orgs/{org_id}/invitations", json={"email": email, "role": role,
                                                                   "data_manager": data_manager})
    assert r.status_code == 201, r.text
    mail = next(m for m in reversed(app.state.mailer.outbox) if m.to == email and m.kind == "invitation")
    c = new_client(app)
    r = c.post("/api/invitations/accept", json={"token": link_token(mail), "full_name": "موظف", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return c, r.json()
