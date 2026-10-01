"""DB-backed job queue.

Why a table and not Redis/Celery: the product already needs one managed MySQL; a jobs table
adds no service to pay for or operate, survives restarts, and is easy to inspect. Workers claim
with SELECT ... FOR UPDATE SKIP LOCKED on MySQL (ignored by SQLite, where the conditional
UPDATE below is what makes the claim atomic). A running job heartbeats; one that stops is
requeued (or failed after job_max_attempts).
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from nazeer_api.db import utcnow
from nazeer_api.models import Job


def enqueue(db: DbSession, org_id: str, kind: str, payload: dict | None = None,
            created_by: str | None = None) -> Job:
    job = Job(org_id=org_id, kind=kind, payload=payload or {}, created_by=created_by, status="queued")
    db.add(job)
    db.flush()
    return job


def claim_next(db: DbSession, worker_id: str, kinds: list[str] | None = None) -> Job | None:
    stmt = select(Job.id).where(Job.status == "queued")
    if kinds:
        stmt = stmt.where(Job.kind.in_(kinds))
    stmt = stmt.order_by(Job.created_at).limit(1).with_for_update(skip_locked=True)
    job_id = db.execute(stmt).scalar_one_or_none()
    if job_id is None:
        db.rollback()
        return None
    now = utcnow()
    res = db.execute(update(Job).where(Job.id == job_id, Job.status == "queued").values(
        status="running", locked_by=worker_id, started_at=now, heartbeat_at=now, attempts=Job.attempts + 1))
    db.commit()
    if res.rowcount != 1:
        return None  # another worker won the race
    return db.get(Job, job_id)


def heartbeat(db: DbSession, job: Job, stage: str | None = None, progress: int | None = None) -> None:
    if stage is not None:
        job.stage = stage[:64]
    if progress is not None:
        job.progress = max(0, min(100, int(progress)))
    job.heartbeat_at = utcnow()
    db.commit()


def finish(db: DbSession, job: Job, result: dict | None = None) -> None:
    job.status, job.progress, job.result, job.finished_at = "succeeded", 100, result or {}, utcnow()
    job.locked_by = None
    db.commit()


def fail(db: DbSession, job: Job, error_code: str) -> None:
    job.status, job.error_code, job.finished_at, job.locked_by = "failed", error_code[:64], utcnow(), None
    db.commit()


def recover_stale(db: DbSession, stale_seconds: int, max_attempts: int) -> int:
    """Requeue (or fail) running jobs whose worker stopped heartbeating. Returns the count."""
    cutoff = utcnow() - timedelta(seconds=stale_seconds)
    stale = db.execute(select(Job).where(Job.status == "running", Job.heartbeat_at < cutoff)).scalars().all()
    for job in stale:
        if job.attempts >= max_attempts:
            job.status, job.error_code, job.finished_at = "failed", "stale_worker", utcnow()
        else:
            job.status, job.stage = "queued", "requeued"
        job.locked_by = None
    db.commit()
    return len(stale)
