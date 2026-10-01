"""Peak memory (RSS) of the engine on the demo data, to size the backend host.

    python scripts\\measure_memory.py --csv data\\demo --mode masked
    python scripts\\measure_memory.py --csv data\\demo --mode synthetic

Prints JSON with peak RSS in MB and wall time. Needs psutil (dev tool, not a dependency).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    import psutil

    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--mode", choices=["masked", "synthetic"], default="masked")
    ap.add_argument("--rows", type=int, default=0, help="keep only the first N customers (0 = all)")
    args = ap.parse_args()

    proc = psutil.Process(os.getpid())
    peak = {"rss": proc.memory_info().rss}
    stop = threading.Event()

    def sample() -> None:
        while not stop.is_set():
            peak["rss"] = max(peak["rss"], proc.memory_info().rss)
            time.sleep(0.05)

    threading.Thread(target=sample, daemon=True).start()
    t0 = time.perf_counter()
    from nazeer import pipeline
    from nazeer.policy import load_policy
    from nazeer.tableio import load_csv_folder

    baseline = proc.memory_info().rss
    tables = load_csv_folder(args.csv)
    an = pipeline.analyze(tables, "measure")
    policy = load_policy(pipeline.DEFAULT_POLICY)
    if args.mode == "masked":
        res = pipeline.run_masked(an, policy, os.urandom(32), apply_fix="auto")
    else:
        res = pipeline.run_synthetic(an, policy, target="is_large_claim=amount>p90")
    stop.set()
    print(json.dumps({"mode": args.mode, "rows": {n: len(df) for n, df in tables.items()},
                      "verdict": res.report["verdict"], "peak_rss_mb": round(peak["rss"] / 2**20),
                      "after_imports_mb": round(baseline / 2**20), "seconds": round(time.perf_counter() - t0, 1)}))


if __name__ == "__main__":
    main()
