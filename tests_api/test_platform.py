"""Org keys, jobs/worker, migrations, logging hygiene, configuration."""
import io
import logging
import os
from datetime import timedelta

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, update

from nazeer.safe_log import configure_logging
from nazeer_api import jobs
from nazeer_api.config import ConfigError, ROOT, decode_master_key, load_settings
from nazeer_api.db import utcnow
from nazeer_api.models import Base, Job, Organization
from nazeer_api.security import KeyDecryptionError, decrypt_org_key, encrypt_org_key
from nazeer_api.worker import HANDLERS, handler, run_one
from tests_api.conftest import MASTER_KEY, PASSWORD, link_token, new_client, signup


# ---------------------------------------------------------------- org keys

def test_org_key_created_encrypted_and_bound_to_its_org(app):
    signup(app, "k1@a.example.com", org="منشأة أ")
    signup(app, "k2@b.example.com", org="منشأة ب")
    with app.state.sessionmaker() as db:
        o1, o2 = db.query(Organization).all()
    k1 = decrypt_org_key(MASTER_KEY, o1.id, o1.key_version, o1.enc_key)
    k2 = decrypt_org_key(MASTER_KEY, o2.id, o2.key_version, o2.enc_key)
    assert len(k1) == 32 and k1 != k2 and k1 not in o1.enc_key
    with pytest.raises(KeyDecryptionError):
        decrypt_org_key(os.urandom(32), o1.id, o1.key_version, o1.enc_key)  # wrong master key
    with pytest.raises(KeyDecryptionError):
        decrypt_org_key(MASTER_KEY, o2.id, o1.key_version, o1.enc_key)  # row copied to another org
    blob = encrypt_org_key(MASTER_KEY, "x", 2, k1)
    with pytest.raises(KeyDecryptionError):
        decrypt_org_key(MASTER_KEY, "x", 1, blob)  # key version is bound too


def test_master_key_config():
    assert len(decode_master_key("A" * 43)) == 32
    with pytest.raises(ConfigError):
        decode_master_key("dG9vLXNob3J0")
    with pytest.raises(ConfigError):
        decode_master_key("not base64 !!!")


def test_settings_fail_fast_without_required_env(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("NAZEER_MASTER_KEY", raising=False)
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        load_settings(tmp_path / "missing.env")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    with pytest.raises(ConfigError, match="NAZEER_MASTER_KEY"):
        load_settings(tmp_path / "missing.env")


# ---------------------------------------------------------------- jobs and worker

def _admin(app):
    c, me = signup(app, "jobs@a.example.com")
    return c, me["memberships"][0]["org_id"]


def test_ping_job_runs_through_the_worker(app):
    c, org = _admin(app)
    job = c.post(f"/api/orgs/{org}/jobs/ping").json()
    assert job["status"] == "queued"
    assert run_one(app.state.sessionmaker, app.state.settings, "w1") is True
    done = c.get(f"/api/orgs/{org}/jobs/{job['id']}").json()
    assert done["status"] == "succeeded" and done["progress"] == 100 and done["result"] == {"pong": True}
    assert run_one(app.state.sessionmaker, app.state.settings, "w1") is False  # queue empty


def test_failed_job_stores_error_type_not_message(app):
    @handler("boom")
    def _boom(ctx):
        raise ValueError("could not convert '1110704341'")

    try:
        c, org = _admin(app)
        with app.state.sessionmaker() as db:
            jid = jobs.enqueue(db, org, "boom").id
            db.commit()
        run_one(app.state.sessionmaker, app.state.settings, "w1")
        j = c.get(f"/api/orgs/{org}/jobs/{jid}").json()
        assert j["status"] == "failed" and j["error_code"] == "ValueError"
        assert "1110704341" not in str(j)
    finally:
        HANDLERS.pop("boom", None)


def test_claim_is_exclusive(app):
    _, org = _admin(app)
    with app.state.sessionmaker() as db:
        jobs.enqueue(db, org, "ping")
        db.commit()
    with app.state.sessionmaker() as db1, app.state.sessionmaker() as db2:
        first = jobs.claim_next(db1, "w1")
        second = jobs.claim_next(db2, "w2")
    assert first is not None and second is None


def test_stale_job_requeued_then_failed_after_max_attempts(app):
    _, org = _admin(app)
    s = app.state.settings
    with app.state.sessionmaker() as db:
        jid = jobs.enqueue(db, org, "ping").id
        db.commit()
        for attempt in range(1, s.job_max_attempts + 1):
            job = jobs.claim_next(db, "dead-worker")
            assert job is not None and job.attempts == attempt
            db.execute(update(Job).where(Job.id == jid).values(
                heartbeat_at=utcnow() - timedelta(seconds=s.job_stale_seconds + 5)))
            db.commit()
            assert jobs.recover_stale(db, s.job_stale_seconds, s.job_max_attempts) == 1
        job = db.get(Job, jid)
        db.refresh(job)
        assert job.status == "failed" and job.error_code == "stale_worker"


# ---------------------------------------------------------------- migrations

def test_migrations_match_models(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = Config(str(ROOT / "nazeer_api" / "alembic.ini"))
    cfg.cmd_opts = type("o", (), {"x": [f"url={url}"]})()
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == [], diff
    command.downgrade(cfg, "base")


# ---------------------------------------------------------------- logging hygiene

def test_no_secret_token_or_password_in_logs(app, mailer):
    buf = io.StringIO()
    configure_logging(level=logging.DEBUG, stream=buf)
    try:
        c, me = signup(app, "logs@a.example.com")
        org = me["memberships"][0]["org_id"]
        c.post(f"/api/orgs/{org}/invitations", json={"email": "new@a.example.com"})
        anon = new_client(app)
        anon.post("/api/auth/login", json={"email": "logs@a.example.com", "password": "wrong-password!"})
        anon.post("/api/auth/forgot-password", json={"email": "logs@a.example.com"})
        c.post(f"/api/orgs/{org}/jobs/ping")
        run_one(app.state.sessionmaker, app.state.settings, "w1")
    finally:
        configure_logging()
    out = buf.getvalue()
    secrets_seen = [link_token(m) for m in mailer.outbox] + [PASSWORD, c.cookies.get("__Host-nz_session"),
                                                             MASTER_KEY.hex()]
    assert out and not [s for s in secrets_seen if s and s in out]
    assert "logs@a.example.com" not in out and "new@a.example.com" not in out
