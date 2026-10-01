"""Score free-text detection against the demo golden labels: Nazeer vs naive baseline.

    python scripts\score_detection.py --data data\demo
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nazeer import detect  # noqa: E402
from nazeer.evaluate import score_detection  # noqa: E402
from nazeer.tableio import load_csv_folder, read_csv  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data") / "demo")
    ap.add_argument("--json", type=Path, default=None, help="optional path to write the scores")
    args = ap.parse_args()
    tables = load_csv_folder(args.data, ["customers", "claims"])
    golden = read_csv(args.data / "golden_labels.csv")
    negatives = read_csv(args.data / "hard_negatives.csv")
    cols = [("claims", "notes")]
    results = {
        "nazeer": score_detection(detect.detect_free_text(tables, cols), golden, negatives),
        "baseline": score_detection(detect.baseline_free_text(tables, cols), golden, negatives),
    }
    print(f"{'type':12} {'gold':>6} | {'nazeer R':>8} {'P':>6} | {'baseline R':>10} {'P':>6}")
    for t in ("SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME"):
        n, b = results["nazeer"]["per_type"][t], results["baseline"]["per_type"][t]
        fmt = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
        print(f"{t:12} {n['golden']:>6} | {fmt(n['recall']):>8} {fmt(n['precision']):>6} | "
              f"{fmt(b['recall']):>10} {fmt(b['precision']):>6}")
    for who in ("nazeer", "baseline"):
        r = results[who]
        print(f"{who:8} overall recall={r['overall_recall']} precision={r['overall_precision']} "
              f"structured-id recall={r['structured_id_recall']} hard-negative hits={r['hard_negative_hits']}/{r['hard_negatives']}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
