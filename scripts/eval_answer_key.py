"""Recall per type against an answer key, through the same steps as the website:
ingest -> default cleaning -> detection -> masked twin.

    python scripts\\eval_answer_key.py --data FILE [FILE ...] --key KEY.csv [--json out.json]

Prints counts only (no values). Uses a fixed throwaway key: the numbers do not depend on it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run(paths: list[Path], key_path: Path, cleaning: bool = True) -> dict:
    from nazeer import pipeline
    from nazeer.answer_key import evaluate, load_key
    from nazeer.cleaning import clean
    from nazeer.ingest import read_files
    from nazeer.policy import load_policy

    tables = read_files([(p.name, p.read_bytes()) for p in paths]).tables
    cleaned = clean(tables)[0] if cleaning else tables  # the site: «نظّف» or «تخطَّ»
    an = pipeline.analyze(cleaned, paths[0].stem)
    res = pipeline.run_masked(an, load_policy(pipeline.DEFAULT_POLICY), b"eval-key-" + b"x" * 32)
    entries = load_key(key_path.read_bytes())
    out = evaluate(an.tables, an.detections, an.spans, entries, twin=res.twin)
    out["verdict"] = res.report["verdict"]
    out["failed_checks"] = res.report.get("failed_checks", [])
    out["spans_by_type"] = res.report.get("free_text", {}).get("spans_by_type", {})
    out["review_totals"] = (res.report.get("free_text", {}).get("review") or {}).get("totals", {})
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, nargs="+", required=True)
    ap.add_argument("--key", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--no-clean", action="store_true", help="as if the user chose «تخطَّ» (no cleaning)")
    a = ap.parse_args(argv)
    out = run(a.data, a.key, cleaning=not a.no_clean)
    print(f"verdict {out['verdict']}  failed {out['failed_checks']}")
    print(f"{'type':<12}{'planted':>8}{'found':>8}{'replaced':>9}{'missed':>8}{'recall':>8}")
    for k, v in out["types"].items():
        print(f"{k:<12}{v['planted']:>8}{v['found']:>8}{v['replaced']:>9}{v['missed']:>8}{v['recall']:>8.1%}")
    lk = out["look_alikes"]
    print(f"look-alikes {lk['total']}: ignored {lk['ignored']}, decided with evidence {lk['review']} "
          f"(kept {lk['review_kept']}, replaced {lk['review_replaced']}), wrongly replaced {lk['wrong']}")
    t = out.get("review_totals", {})
    print(f"uncertain values: decided by Nazeer {t.get('auto', 0)}, waiting for the admin {t.get('pending', 0)}")
    if a.json:
        a.json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
