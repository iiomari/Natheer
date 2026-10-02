"""Production entrypoint, one image for every backend service:

    NAZEER_ROLE=api     python -m nazeer_api.serve   # migrations, then the API on $PORT
    NAZEER_ROLE=worker  python -m nazeer_api.serve   # the background worker
    NAZEER_ROLE=all     python -m nazeer_api.serve   # both in one container (single-service hosts)

On Railway the API and the worker are separate services, so each gets its own memory budget
(twin generation runs in the worker). Storage is in MySQL, so no shared volume is needed.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time

from nazeer.safe_log import configure_logging

log = logging.getLogger("nazeer_api.serve")


def _api_cmd() -> list[str]:
    # "*" goes through the environment: as an argument, Windows Python expands it like a file glob.
    os.environ.setdefault("FORWARDED_ALLOW_IPS", "*")
    return [sys.executable, "-m", "uvicorn", "nazeer_api.main:app", "--host", "0.0.0.0",
            "--port", os.environ.get("PORT", "8000"), "--proxy-headers", "--no-server-header"]


def _worker_cmd() -> list[str]:
    return [sys.executable, "-m", "nazeer_api.worker", "--poll", os.environ.get("NAZEER_WORKER_POLL", "3")]


def migrate() -> int:
    return subprocess.run([sys.executable, "-m", "alembic", "-c", "nazeer_api/alembic.ini", "upgrade", "head"]).returncode


def supervise(cmds: dict[str, list[str]]) -> int:
    procs = {name: subprocess.Popen(cmd) for name, cmd in cmds.items()}
    stopping = False

    def stop(*_):  # noqa: ANN002
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    code = 0
    while not stopping:
        for name, p in procs.items():
            rc = p.poll()
            if rc is not None:
                log.error("%s exited with %d; stopping", name, rc)
                code, stopping = rc or 1, True
                break
        time.sleep(1)
    for p in procs.values():
        if p.poll() is None:
            p.terminate()
    for p in procs.values():
        try:
            p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            p.kill()
    return code


def main() -> int:
    configure_logging()
    role = os.environ.get("NAZEER_ROLE", "all").strip().lower()
    if role in ("api", "all"):
        rc = migrate()
        if rc != 0:
            log.error("migrations failed (exit %d); not starting", rc)
            return rc
    if role == "api":
        return supervise({"api": _api_cmd()})
    if role == "worker":
        return supervise({"worker": _worker_cmd()})
    return supervise({"api": _api_cmd(), "worker": _worker_cmd()})


if __name__ == "__main__":
    raise SystemExit(main())
