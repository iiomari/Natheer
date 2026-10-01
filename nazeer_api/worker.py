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


def run_one(sessionmaker, settings: Settings, worker_id: str) -> bool:
    """Recover stale jobs, then claim and run at most one. Returns True if a job was run."""
    db: DbSession = sessionmaker()
    try:
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
            jobs.fail(db, db.get(Job, job.id), type(exc).__name__)
        else:
            jobs.finish(db, job, result)
            log.info("job %s kind=%s succeeded", job.id, job.kind)
        return True
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m nazeer_api.worker")
    ap.add_argument("--poll", type=float, default=1.0, help="seconds between polls when idle")
    ap.add_argument("--once", action="store_true", help="run at most one job and exit")
    args = ap.parse_args(argv)
    configure_logging()
    enforce_offline()
    settings = get_settings()
    sessionmaker = make_sessionmaker(make_engine(settings.database_url))
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
