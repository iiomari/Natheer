"""Production entrypoint: migrations, then the API and the worker in one container.

    python -m nazeer_api.serve            # PORT from the environment (Railway sets it)

Why one container: twins and returned files live on one persistent volume, and a volume
attaches to a single service on the chosen host. Running the API and the worker side by side
keeps both on that volume. If either process exits, the other is stopped and the container
exits non-zero, so the platform restarts the whole unit.
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


def main() -> int:
    configure_logging()
    port = os.environ.get("PORT", "8000")
    migrate = subprocess.run([sys.executable, "-m", "alembic", "-c", "nazeer_api/alembic.ini", "upgrade", "head"])
    if migrate.returncode != 0:
        log.error("migrations failed (exit %d); not starting", migrate.returncode)
        return migrate.returncode
    procs = {
        "api": subprocess.Popen([sys.executable, "-m", "uvicorn", "nazeer_api.main:app", "--host", "0.0.0.0",
                                 "--port", port, "--proxy-headers", "--forwarded-allow-ips", "*",
                                 "--no-server-header"]),
        "worker": subprocess.Popen([sys.executable, "-m", "nazeer_api.worker"]),
    }
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
                log.error("%s exited with %d; stopping the container", name, rc)
                code = rc or 1
                stopping = True
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


if __name__ == "__main__":
    raise SystemExit(main())
