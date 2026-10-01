"""Orchestration and CLI.

    $env:NAZEER_KEY = "<at least 32 random characters>"
    python -m nazeer.pipeline --csv data\\demo --mode masked --out out\\masked --apply-fix auto

Steps (also used by the Streamlit app): analyze() -> run_masked() / run_synthetic()
-> write_outputs(). If the leak scan fails, the twin is withheld: only the report
is written. Exit code: 0 = PASS, 2 = FAIL.
"""
from __future__ import annotations

import argparse
import json
import logging
import secrets
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nazeer import __version__, detect, evaluate, kanon, transform
from nazeer import report as rpt
from nazeer.config import load_key
from nazeer.models import ColumnDetection, DatasetProfile, Span
from nazeer.policy import Decision, Policy, apply_overrides, inactive_rules, load_policy, resolve
from nazeer.profiling import profile_dataset
from nazeer.safe_log import configure_logging, install_excepthook
from nazeer.tableio import load_csv_folder, read_csv, write_csv_folder

log = logging.getLogger("nazeer.pipeline")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config" / "policy.yaml"


@dataclass
class Analysis:
    tables: dict[str, pd.DataFrame]
    profile: DatasetProfile
    detections: list[ColumnDetection]
    spans: list[Span]
    baseline_spans: list[Span]
    source: str
    seconds: float


@dataclass
class RunResult:
    run_id: str
    mode: str
    report: dict
    twin: dict[str, pd.DataFrame]
    twin_withheld: bool
    decisions: list[Decision] = field(default_factory=list)
    extras: dict = field(default_factory=dict)


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)


def analyze(tables: dict[str, pd.DataFrame], source: str = "<upload>", ner=None) -> Analysis:
    t0 = time.perf_counter()
    prof = profile_dataset(tables)
    dets = detect.detect_columns(tables, prof)
    cols = detect.free_text_columns(dets)
    spans = detect.detect_free_text(tables, cols, ner)
    base = detect.baseline_free_text(tables, cols)
    return Analysis(tables, prof, dets, spans, base, source, round(time.perf_counter() - t0, 2))


# ---------------------------------------------------------------- shared report parts

def _column_entries(analysis: Analysis, dets: list[ColumnDetection], decisions: list[Decision]) -> list[dict]:
    dec = {(d.table, d.column): d for d in decisions}
    out = []
    for d in dets:
        cp = analysis.profile.column(d.table, d.column)
        dc = dec.get((d.table, d.column))
        out.append({
            "table": d.table, "column": d.column, "dtype": cp.dtype, "tag": d.tag, "kind": d.kind,
            "confidence": round(d.score, 3), "valid_ratio": round(d.valid_ratio, 3), "name_hint": d.name_hint,
            "needs_review": d.needs_review, "human_reviewed": d.human_override,
            "action": dc.action if dc else "n/a", "rule": dc.rule if dc else "", "params": dc.params if dc else {},
            "reason": d.reason,
        })
    return out


def _base_report(analysis: Analysis, run_id: str, mode: str, policy: Policy, decisions: list[Decision],
                 dets: list[ColumnDetection]) -> dict:
    return {
        "nazeer_version": __version__,
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "input": {
            "source": analysis.source,
            "tables": {n: {"rows": int(len(df)), "columns": int(df.shape[1])} for n, df in analysis.tables.items()},
            "primary_keys": {n: t.primary_key for n, t in analysis.profile.tables.items()},
            "foreign_keys": [f"{f.child_table}.{f.child_column} -> {f.parent_table}.{f.parent_column}"
                             for f in analysis.profile.foreign_keys],
        },
        "policy": {"source": policy.source, "hash": policy.hash, "thresholds": policy.thresholds,
                   "inactive_rules": inactive_rules(policy, decisions)},
        "key": {"source": "environment variable NAZEER_KEY (never stored or logged)"} if mode == "masked" else {},
        "columns": _column_entries(analysis, dets, decisions),
        "free_text": {
            "columns": [f"{t}.{c}" for t, c in detect.free_text_columns(dets)],
            "spans_by_type": dict(Counter(sp.type for sp in analysis.spans)),
            "baseline_spans_by_type": dict(Counter(sp.type for sp in analysis.baseline_spans)),
        },
        "outputs": {"twin_written": False, "files": [], "note": "filled in when outputs are written"},
    }


def _golden_scores(analysis: Analysis, golden_dir: Path | None) -> dict | None:
    if not golden_dir or not (Path(golden_dir) / "golden_labels.csv").exists():
        return None
    golden = read_csv(Path(golden_dir) / "golden_labels.csv")
    negatives = read_csv(Path(golden_dir) / "hard_negatives.csv")
    return {
        "nazeer": evaluate.score_detection(analysis.spans, golden, negatives),
        "baseline": evaluate.score_detection(analysis.baseline_spans, golden, negatives),
        "note": "demo answer key; measures planted formats only",
    }


def _review_check(builder: rpt.ReportBuilder, dets: list[ColumnDetection]) -> None:
    pending = [f"{d.table}.{d.column}" for d in dets if d.needs_review and not d.human_override]
    builder.add("human_review", "INFO", False,
                f"{len(pending)} borderline column(s) not reviewed by a human; treated as identifiers"
                if pending else "no borderline columns pending review", value=pending)


# ---------------------------------------------------------------- k-anonymity step

def kanon_step(twin: dict[str, pd.DataFrame], dets: list[ColumnDetection], k_min: int,
               apply_fix: str | None) -> dict:
    quasi: dict[str, list[str]] = defaultdict(list)
    for d in dets:
        if d.tag == "QUASI_ID" and d.column in twin[d.table].columns:
            quasi[d.table].append(d.column)
    result = {}
    for t, cols in quasi.items():
        before = kanon.k_anonymity(twin[t], cols, k_min)
        entry = {"quasi_columns": cols, "k_min": k_min, "k_before": before.k, "classes_before": before.n_classes,
                 "rows_in_small_classes_before": before.rows_in_small_classes, "passed_before": before.passed,
                 "suggestions": [], "applied_fix": None, "k_after": before.k, "passed_after": before.passed}
        if not before.passed:
            fixes = kanon.suggest_fixes(twin[t], cols, k_min)
            entry["suggestions"] = [f.to_dict() for f in fixes[:8]]
            chosen = None
            if apply_fix == "auto":
                chosen = next((f for f in fixes if f.reaches_k_min), None)
            elif apply_fix:
                chosen = next((f for f in fixes if f.name == apply_fix), None)
                if chosen is None:
                    entry["fix_error"] = f"no suggested fix named {apply_fix!r} for table {t}"
            if chosen is not None:
                twin[t] = kanon.apply_fix(twin[t], chosen, cols, k_min)
                after = kanon.k_anonymity(twin[t], cols, k_min)
                entry.update(applied_fix=chosen.to_dict(), k_after=after.k, passed_after=after.passed,
                             classes_after=after.n_classes, rows_in_small_classes_after=after.rows_in_small_classes)
        result[t] = entry
        log.info("k-anonymity %s: k_before=%d k_after=%d", t, entry["k_before"], entry["k_after"])
    return result


def _kanon_checks(builder: rpt.ReportBuilder, kan: dict) -> None:
    for t, e in kan.items():
        if not e["passed_before"]:
            builder.add(f"k_anonymity_before_fix[{t}]", "FAIL", False,
                        f"k={e['k_before']} < {e['k_min']} over {', '.join(e['quasi_columns'])}; "
                        f"{e['rows_in_small_classes_before']} rows in small classes",
                        value=e["k_before"], threshold=e["k_min"])
        fix = e["applied_fix"]["name"] if e["applied_fix"] else None
        builder.add(f"k_anonymity[{t}]", "PASS" if e["passed_after"] else "FAIL", True,
                    (f"after fix '{fix}': " if fix else "no fix applied: ") + f"k={e['k_after']} (min {e['k_min']})",
                    value=e["k_after"], threshold=e["k_min"])


def _leak_check(builder: rpt.ReportBuilder, leak: dict) -> None:
    total = sum(leak["leaked_by_kind"].values())
    names = leak["names"].get("rows_keeping_original_full_name")
    detail = f"{total} original identifier occurrence(s) found in the twin across {leak['cells_scanned']} cells"
    if names is not None:
        detail += f"; {names} row(s) keep their original full name"
    builder.add("leak_scan", leak["verdict"], True, detail, value=leak["leaked_by_kind"])


# ---------------------------------------------------------------- masked mode (5a)

def run_masked(analysis: Analysis, policy: Policy, key: bytes, overrides: dict | None = None,
               apply_fix: str | None = None, golden_dir: Path | None = None) -> RunResult:
    run_id = new_run_id()
    overrides = overrides or {}
    dets = apply_overrides(analysis.detections, overrides)
    decisions = resolve(policy, analysis.profile, analysis.detections, overrides)
    pseudo = transform.Pseudonymizer(key, keep_first_digit=policy.rules.get("SAUDI_ID", {}).get("keep_first_digit", True))
    twin, tstats = transform.apply(analysis.tables, analysis.profile, decisions, analysis.spans, pseudo,
                                   policy.thresholds["min_span_confidence"])

    kan = kanon_step(twin, dets, int(policy.thresholds["k_anonymity_min"]), apply_fix)
    originals = evaluate.original_identifier_values(analysis.tables, dets, analysis.spans)
    name_cols = [(d.table, d.column) for d in dets if d.tag == "DIRECT_ID" and d.kind == "PERSON_NAME"]
    leak = evaluate.leak_scan(originals, twin, "masked", analysis.tables, name_cols)
    copies = {t: evaluate.exact_copies(analysis.tables[t], twin[t]) for t in twin}

    base = _base_report(analysis, run_id, "masked", policy, decisions, dets)
    base["free_text"]["spans_replaced_by_type"] = tstats["spans_replaced"]
    base["transform"] = {"pseudonym_collisions_resolved": tstats["collisions"]}
    base["k_anonymity"] = kan
    base["privacy"] = {"exact_copies": copies,
                       "note": "masked twin: rows correspond to real people; DCR is not meaningful in this mode"}
    base["leak_scan"] = leak
    golden = _golden_scores(analysis, golden_dir)
    if golden:
        base["detection_vs_golden"] = golden

    b = rpt.ReportBuilder(base)
    _leak_check(b, leak)
    n_copies = sum(copies.values())
    b.add("exact_copies", "PASS" if n_copies == 0 else "FAIL", True,
          f"{n_copies} twin row(s) identical to an original row", value=copies, threshold=0)
    _kanon_checks(b, kan)
    _review_check(b, dets)
    b.add("free_text_replacement", "INFO", False,
          f"{sum(tstats['spans_replaced'].values())} identifier spans replaced in free text",
          value=tstats["spans_replaced"])
    if golden:
        b.add("detection_vs_golden", "INFO", False,
              f"Nazeer recall {golden['nazeer']['overall_recall']} vs baseline {golden['baseline']['overall_recall']} "
              "(demo answer key)", value={"nazeer": golden["nazeer"]["overall_recall"],
                                          "baseline": golden["baseline"]["overall_recall"]})
    report = b.build()
    return RunResult(run_id, "masked", report, twin, twin_withheld=leak["hard_fail"], decisions=decisions,
                     extras={"kanon": kan, "transform": tstats})


# ---------------------------------------------------------------- synthetic mode (5b)

def run_synthetic(analysis: Analysis, policy: Policy, overrides: dict | None = None,
                  target: str | None = None, golden_dir: Path | None = None) -> RunResult:
    raise NotImplementedError("synthetic mode is built in milestone M7")


# ---------------------------------------------------------------- outputs

def write_outputs(result: RunResult, out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    files = []
    result.report["outputs"] = {"twin_written": not result.twin_withheld, "files": []}
    if not result.twin_withheld:
        files += write_csv_folder(result.twin, out_dir / "twin")
    else:
        log.error("leak scan failed: twin withheld, only the report is written")
    result.report["outputs"]["files"] = [str(p.relative_to(out_dir)) for p in files] + ["report.json"]
    rpt.validate(result.report)
    files.append(rpt.write_json(result.report, out_dir))
    return files


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m nazeer.pipeline", description="Nazeer: Saudi-aware masked/synthetic twin")
    ap.add_argument("--csv", type=Path, required=True, help="folder of CSV files (one table per file)")
    ap.add_argument("--mode", choices=["masked", "synthetic"], default="masked")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    ap.add_argument("--overrides", type=Path, help='JSON: {"table.column": {"tag": ..., "kind": ..., "action": {...}}}')
    ap.add_argument("--apply-fix", default=None, help='k-anonymity fix to apply: a suggested fix name, or "auto"')
    ap.add_argument("--target", default=None, help="synthetic mode: target column for the utility test")
    ap.add_argument("--golden", type=Path, default=None, help="demo answer key folder (default: <csv>\\_golden if present)")
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    configure_logging(log_file=args.out / "nazeer.log")
    install_excepthook()

    tables = load_csv_folder(args.csv)
    log.info("loaded %d tables from folder %s", len(tables), args.csv.name)
    analysis = analyze(tables, source=f"csv folder: {args.csv.name}")
    policy = load_policy(args.policy)
    overrides = json.loads(args.overrides.read_text(encoding="utf-8")) if args.overrides else {}
    golden = args.golden or (args.csv / "_golden")

    if args.mode == "masked":
        result = run_masked(analysis, policy, load_key(), overrides, args.apply_fix, golden)
    else:
        result = run_synthetic(analysis, policy, overrides, target=args.target, golden_dir=golden)

    write_outputs(result, args.out)
    rep = result.report
    print(f"run {rep['run_id']} mode={rep['mode']} verdict={rep['verdict']}")
    for c in rep["checks"]:
        print(f"  [{c['status']:7}] {'*' if c['blocking'] else ' '} {c['name']}: {c['detail']}")
    print(f"report: {args.out / 'report.json'}" + ("" if not result.twin_withheld else "  (twin WITHHELD)"))
    return 0 if rep["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
