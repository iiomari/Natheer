"""Background worker: claims jobs from the jobs table and runs them.

    python -m nazeer_api.worker            # settings from the environment / .env

Handlers receive a JobContext and report progress through it. A handler error marks the job
failed with the exception TYPE as error code; messages are never stored (they can quote values).
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session as DbSession

from nazeer.config import enforce_offline
from nazeer.safe_log import configure_logging
from nazeer_api import jobs
from nazeer_api.config import Settings, get_settings
from nazeer_api.db import make_engine, make_sessionmaker
from nazeer_api.models import Job

log = logging.getLogger("nazeer_api.worker")


@dataclass
class JobContext:
    db: DbSession
    job: Job
    settings: Settings

    def progress(self, stage: str, percent: int) -> None:
        jobs.heartbeat(self.db, self.job, stage, percent)


Handler = Callable[[JobContext], dict]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn
    return register


@handler("ping")
def _ping(ctx: JobContext) -> dict:
    ctx.progress("pong", 50)
    return {"pong": True}


@handler("process")
def _process(ctx: JobContext) -> dict:
    from nazeer_api.models import Dataset
    from nazeer_api.processing import ProcessingError, process_upload

    ds = ctx.db.get(Dataset, ctx.job.payload["dataset_id"])
    ctx.progress("reading_files", 10)
    try:
        return process_upload(ctx.db, ctx.settings, ds, ctx.job.payload.get("cleaning"))
    except Exception as e:  # noqa: BLE001 - any failure must reach the user, not leave "processing"
        ctx.db.rollback()
        ds = ctx.db.get(Dataset, ctx.job.payload["dataset_id"])
        code = e.code if isinstance(e, ProcessingError) else "processing_failed"
        ds.status, ds.error_code = "failed", code[:64]
        ctx.db.commit()
        raise


@handler("generate")
def _generate(ctx: JobContext) -> dict:
    from nazeer_api.models import Dataset
    from nazeer_api.processing import generate_twin

    ds = ctx.db.get(Dataset, ctx.job.payload["dataset_id"])
    ctx.progress("generating", 20)
    twin = generate_twin(ctx.db, ctx.settings, ds, ctx.job.payload, ctx.job.created_by)
    return {"twin_id": twin.id, "verdict": twin.verdict}


_last_sweep = 0.0


def maybe_sweep(db: DbSession, settings: Settings, every_s: float = 60.0) -> None:
    global _last_sweep
    if time.monotonic() - _last_sweep < every_s:
        return
    _last_sweep = time.monotonic()
    from nazeer_api.processing import sweep

    counts = sweep(db, settings)
    if any(counts.values()):
        log.info("sweep: %s", counts)


def run_one(sessionmaker, settings: Settings, worker_id: str) -> bool:
    """Sweep, recover stale jobs, then claim and run at most one. Returns True if a job was run."""
    db: DbSession = sessionmaker()
    try:
        maybe_sweep(db, settings)
        jobs.recover_stale(db, settings.job_stale_seconds, settings.job_max_attempts)
        job = jobs.claim_next(db, worker_id, list(HANDLERS))
        if job is None:
            return False
        log.info("job %s kind=%s started (attempt %d)", job.id, job.kind, job.attempts)
        try:
            result = HANDLERS[job.kind](JobContext(db, job, settings))
        except Exception as exc:  # noqa: BLE001 - worker boundary
            db.rollback()
            log.error("job %s kind=%s failed", job.id, job.kind, exc_info=True)
            jobs.fail(db, db.get(Job, job.id), getattr(exc, "code", None) or type(exc).__name__)
        else:
            jobs.finish(db, job, result)
            log.info("job %s kind=%s succeeded", job.id, job.kind)
        return True
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m nazeer_api.worker")
    ap.add_argument("--poll", type=float, default=2.0, help="seconds between polls when idle")
    ap.add_argument("--once", action="store_true", help="run at most one job and exit")
    args = ap.parse_args(argv)
    configure_logging()
    enforce_offline()
    settings = get_settings()
    sessionmaker = make_sessionmaker(make_engine(settings.database_url, settings.database_ca_pem))
    worker_id = f"{socket.gethostname()}:{os.getpid()}"[:64]
    stopping = False

    def stop(*_):  # noqa: ANN002
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    log.info("worker %s started; handlers: %s", worker_id, ", ".join(sorted(HANDLERS)))
    while not stopping:
        ran = run_one(sessionmaker, settings, worker_id)
        if args.once:
            break
        if not ran:
            time.sleep(args.poll)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
