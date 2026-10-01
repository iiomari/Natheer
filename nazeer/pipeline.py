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


def spans_for(analysis: Analysis, dets: list[ColumnDetection]) -> tuple[list[Span], list[Span]]:
    """(spans to replace, all known spans) after overrides: columns a reviewer newly tagged
    FREE_TEXT are scanned now; spans in columns no longer tagged FREE_TEXT are not replaced."""
    cols = set(detect.free_text_columns(dets))
    scanned = set(detect.free_text_columns(analysis.detections))
    missing = sorted(c for c in cols if c not in scanned)
    extra = detect.detect_free_text(analysis.tables, missing) if missing else []
    all_spans = analysis.spans + extra
    return [sp for sp in all_spans if (sp.table, sp.column) in cols], all_spans


# ---------------------------------------------------------------- masked mode (5a)

def run_masked(analysis: Analysis, policy: Policy, key: bytes, overrides: dict | None = None,
               apply_fix: str | None = None, golden_dir: Path | None = None) -> RunResult:
    run_id = new_run_id()
    overrides = overrides or {}
    dets = apply_overrides(analysis.detections, overrides)
    decisions = resolve(policy, analysis.profile, analysis.detections, overrides)
    spans, all_spans = spans_for(analysis, dets)
    pseudo = transform.Pseudonymizer(key, keep_first_digit=policy.rules.get("SAUDI_ID", {}).get("keep_first_digit", True))
    twin, tstats = transform.apply(analysis.tables, analysis.profile, decisions, spans, pseudo,
                                   policy.thresholds["min_span_confidence"])

    kan = kanon_step(twin, dets, int(policy.thresholds["k_anonymity_min"]), apply_fix)
    # The leak scan looks for EVERY identifier ever detected, including in columns a reviewer
    # un-tagged: an override can never hide an identifier from the scan.
    originals = evaluate.original_identifier_values(analysis.tables, dets, all_spans)
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

def fit_synthetic_view(analysis: Analysis, dets: list[ColumnDetection], seed: int, method: str) -> dict:
    """Split (before any fitting), build the flat view, fit on real-train, sample."""
    from nazeer import synth

    prof = analysis.profile
    train_t, hold_t, split = synth.split_holdout(analysis.tables, prof, frac=0.2, seed=seed)
    view_train, view_hold = synth.build_view(train_t, prof), synth.build_view(hold_t, prof)
    modelled, excluded = synth.view_plan(view_train, prof, dets)
    x_train = synth.typed_view(view_train.df, modelled)
    x_hold = synth.typed_view(view_hold.df, modelled)
    t0 = time.perf_counter()
    model = synth.make_synthesizer(method)
    model.fit({"view": x_train}, synth.SynthSchema(tables={"view": modelled}))
    sampled = model.sample(1.0, seed)["view"][list(modelled)]
    return {"split": split, "view_train": view_train, "modelled": modelled, "excluded": excluded,
            "x_train": x_train, "x_hold": x_hold, "model": model, "sampled": sampled,
            "seconds": round(time.perf_counter() - t0, 2)}


def dcr_robustness(analysis: Analysis, dets: list[ColumnDetection], method: str, seeds: int = 5) -> dict:
    """Repeat split -> fit -> sample -> DCR for several seeds. Each seed is a different
    holdout split and therefore a different fit. Reports mean and spread; the PASS rule
    itself is unchanged and is applied to the main run only."""
    import numpy as np

    runs = []
    for seed in range(seeds):
        f = fit_synthetic_view(analysis, dets, seed, method)
        x_twin = f["sampled"]
        d = evaluate.dcr(f["x_train"], x_twin, f["x_hold"], f["modelled"], seed)
        runs.append({"seed": seed, "median_dcr_twin_to_train": d["median_dcr_twin_to_train"],
                     "median_dcr_holdout_to_train": d["median_dcr_holdout_to_train"],
                     "share_twin_closer_to_train_than_holdout": d["share_twin_closer_to_train_than_holdout"],
                     "passed": d["passed"]})

    def stats(key: str) -> dict:
        v = np.array([r[key] for r in runs], dtype=float)
        return {"mean": round(float(v.mean()), 5), "std": round(float(v.std(ddof=1)) if len(v) > 1 else 0.0, 5),
                "min": round(float(v.min()), 5), "max": round(float(v.max()), 5)}

    margins = np.array([r["median_dcr_twin_to_train"] - r["median_dcr_holdout_to_train"] for r in runs])
    return {"seeds": seeds, "runs": runs, "passed_runs": int(sum(r["passed"] for r in runs)),
            "median_dcr_twin_to_train": stats("median_dcr_twin_to_train"),
            "median_dcr_holdout_to_train": stats("median_dcr_holdout_to_train"),
            "share_twin_closer_to_train_than_holdout": stats("share_twin_closer_to_train_than_holdout"),
            "margin": {"mean": round(float(margins.mean()), 5), "min": round(float(margins.min()), 5),
                       "max": round(float(margins.max()), 5)},
            "note": "information only; the PASS rule is applied to the main run"}


def run_synthetic(analysis: Analysis, policy: Policy, overrides: dict | None = None,
                  target: str | None = None, golden_dir: Path | None = None,
                  method: str = "stratified_copula", seed: int = 0, robustness_seeds: int = 0) -> RunResult:
    from nazeer import synth
    from nazeer import saudi_ids as s

    run_id = new_run_id()
    overrides = overrides or {}
    prof = analysis.profile
    dets = apply_overrides(analysis.detections, overrides)
    decisions = resolve(policy, prof, analysis.detections, overrides)

    # 1-2. split BEFORE anything is fitted, then fit on real-train only
    fitted = fit_synthetic_view(analysis, dets, seed, method)
    split, view_train = fitted["split"], fitted["view_train"]
    modelled, excluded = fitted["modelled"], fitted["excluded"]
    x_train, x_hold, model, sampled = fitted["x_train"], fitted["x_hold"], fitted["model"], fitted["sampled"]
    fit_seconds = fitted["seconds"]

    # 3. fill identifiers / keys / text with Nazeer's generators (never equal to an original)
    originals = evaluate.original_identifier_values(analysis.tables, dets, analysis.spans)
    twin_view = synth.fill_synthetic(sampled, view_train, view_train.df.reset_index(drop=True),
                                     excluded, dets, originals, seed)
    twin_name = f"{view_train.base_table}_synthetic"
    twin = {twin_name: twin_view}
    x_twin = synth.typed_view(twin_view, modelled)

    # 4. measure
    fid = evaluate.fidelity(x_train, x_twin, modelled)
    fid["sdmetrics_quality_score"] = evaluate.sdmetrics_quality(x_train, x_twin, modelled)
    util = evaluate.utility_tstr(x_train, x_twin, x_hold, modelled, target, seed) if target else None
    strat = getattr(model, "details", {}).get("stratified_by")
    dcr = evaluate.dcr(x_train, x_twin, x_hold, modelled, seed, strata=strat)
    robustness = dcr_robustness(analysis, dets, method, robustness_seeds) if robustness_seeds else None
    copies = evaluate.exact_copies(x_train, x_twin, list(modelled))
    leak = evaluate.leak_scan(originals, twin, "synthetic")
    by_col = {(d.table, d.column): d for d in dets}
    name_cols = [c for c, (t, oc) in view_train.origin.items()
                 if t != "<derived>" and by_col[(t, oc)].kind == "PERSON_NAME" and by_col[(t, oc)].tag == "DIRECT_ID"]
    orig_names = {s.normalize_name(v) for c in name_cols for v in view_train.df[c].dropna()}
    twin_names = {s.normalize_name(v) for c in name_cols for v in twin_view[c].dropna()}
    leak["names"] = {"columns": [f"{twin_name}.{c}" for c in name_cols],
                     "full_name_overlap_rate": round(len(twin_names & orig_names) / len(twin_names), 4) if twin_names else 0.0,
                     "note": "information only: generated from the same name lists, so common full names recur by chance"}

    # 5. report
    base = _base_report(analysis, run_id, "synthetic", policy, decisions, dets)
    view_action = {c: ("synthesized" if c in modelled else f"not trained on: {excluded[c]}") for c in view_train.origin}
    for entry in base["columns"]:
        col = next((vc for vc, (t, oc) in view_train.origin.items() if (t, oc) == (entry["table"], entry["column"])), None)
        entry["action"] = view_action.get(col, "not part of the synthetic view")
        entry["rule"] = "synthetic mode"
    base["synthetic"] = {
        "synthesizer": model.name, "license": model.license, "seed": model.seed_note, "fit_and_sample_seconds": fit_seconds,
        "synthesizer_details": getattr(model, "details", {}),
        "split": split, "twin_table": twin_name, "view_base_table": view_train.base_table,
        "rows": {"real_train": int(len(x_train)), "holdout": int(len(x_hold)), "twin": int(len(twin_view))},
        "modelled_columns": modelled, "excluded_columns": excluded,
        "derived_columns": {c: o[1] for c, o in view_train.origin.items() if o[0] == "<derived>"},
    }
    base["fidelity"] = fid
    base["utility"] = util or {"note": "no target given; utility not measured"}
    base["privacy"] = {"exact_copies": {twin_name: copies}, "dcr": dcr, "dcr_robustness": robustness}
    base["leak_scan"] = leak
    golden = _golden_scores(analysis, golden_dir)
    if golden:
        base["detection_vs_golden"] = golden

    b = rpt.ReportBuilder(base)
    b.add("holdout_split", "PASS", True,
          f"{split['holdout_fraction']:.0%} of {split['unit_table']} held out before fitting; the synthesizer never saw "
          f"{sum(split['holdout_rows'].values())} holdout rows", value=split["holdout_rows"])
    _leak_check(b, leak)
    b.add("exact_copies", "PASS" if copies == 0 else "FAIL", True,
          f"{copies} twin row(s) identical to a real-train row over the modelled columns", value=copies, threshold=0)
    b.add("dcr", "PASS" if dcr["passed"] else "FAIL", True,
          f"median DCR twin→train {dcr['median_dcr_twin_to_train']} vs holdout→train {dcr['median_dcr_holdout_to_train']}; "
          f"{dcr['share_twin_closer_to_train_than_holdout']:.0%} of twin rows closer to train than to holdout (ideal ≈ 50%)",
          value=dcr["median_dcr_twin_to_train"], threshold=dcr["median_dcr_holdout_to_train"])
    max_drop = policy.thresholds["max_utility_drop"]
    if util and util["max_auc_drop"] is not None:
        per_model = ", ".join(f"{n}: {m['real']['auc']}→{m['twin']['auc']}" for n, m in util["models"].items())
        b.add("utility_tstr", "PASS" if util["max_auc_drop"] <= max_drop else "FAIL", True,
              f"target {util['target']} ({util['definition']}); AUC real→twin {per_model}; "
              f"worst drop {util['max_auc_drop']} (max {max_drop})", value=util["max_auc_drop"], threshold=max_drop)
    else:
        b.add("utility_tstr", "NOT_RUN", False, "no target column chosen" if not util else "could not train on one of the datasets")
    b.add("fidelity", "INFO", False,
          f"SDMetrics quality {fid['sdmetrics_quality_score']}; mean per-column distance {fid['mean_column_distance']}; "
          f"numeric correlation diff {fid['numeric_correlation_mean_abs_diff']}", value=fid["sdmetrics_quality_score"])
    if robustness:
        r = robustness
        b.add("dcr_robustness", "INFO", False,
              f"{r['seeds']} seeds (different holdout splits): DCR rule passed in {r['passed_runs']}/{r['seeds']}; "
              f"twin→train median {r['median_dcr_twin_to_train']['mean']} ± {r['median_dcr_twin_to_train']['std']}, "
              f"holdout→train {r['median_dcr_holdout_to_train']['mean']} ± {r['median_dcr_holdout_to_train']['std']}; "
              f"closer-to-train share {r['share_twin_closer_to_train_than_holdout']['mean']:.0%} "
              f"± {r['share_twin_closer_to_train_than_holdout']['std']:.0%}", value=r["margin"])
    if dcr.get("per_stratum"):
        failing = [v for v, d in dcr["per_stratum"].items() if not d["passed"]]
        b.add("dcr_per_stratum", "INFO", False,
              f"{len(dcr['per_stratum']) - len(failing)}/{len(dcr['per_stratum'])} strata of {strat} have twin no closer "
              f"to train than holdout" + (f"; closer in: {', '.join(failing)}" if failing else ""),
              value={v: d["passed"] for v, d in dcr["per_stratum"].items()})
    b.add("synthesizer", "INFO", False, f"{model.name} ({model.license})"
          + (f"; stratified by {strat}" if strat else "") + f"; seed {model.seed_note}")
    _review_check(b, dets)
    report = b.build()
    return RunResult(run_id, "synthetic", report, twin, twin_withheld=leak["hard_fail"], decisions=decisions,
                     extras={"originals": {twin_name: view_train.df.reset_index(drop=True)},
                             "real_train_view": x_train, "holdout_view": x_hold})


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
    ap.add_argument("--target", default=None, help='synthetic mode: utility target, e.g. "is_large_claim=amount>p90"')
    ap.add_argument("--dcr-seeds", type=int, default=5, help="synthetic mode: DCR robustness repeats (0 = off)")
    ap.add_argument("--synthesizer", default="stratified_copula",
                    choices=["stratified_copula", "gaussian_copula", "ctgan"], help="synthetic mode: model")
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
        result = run_synthetic(analysis, policy, overrides, target=args.target, golden_dir=golden,
                               method=args.synthesizer, robustness_seeds=args.dcr_seeds)

    write_outputs(result, args.out)
    rep = result.report
    print(f"run {rep['run_id']} mode={rep['mode']} verdict={rep['verdict']}")
    for c in rep["checks"]:
        print(f"  [{c['status']:7}] {'*' if c['blocking'] else ' '} {c['name']}: {c['detail']}")
    print(f"report: {args.out / 'report.json'}" + ("" if not result.twin_withheld else "  (twin WITHHELD)"))
    return 0 if rep["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
