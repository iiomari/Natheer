"""Module 6: evaluation. Detection scoring against golden labels (M3); the
fidelity, utility, privacy and leak-scan metrics are added in M5/M7.
"""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

from nazeer.models import Span

IDENTIFIER_TYPES = ("SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME")


def _overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 < b1 and b0 < a1


def score_detection(pred: list[Span], golden: pd.DataFrame, negatives: pd.DataFrame | None = None) -> dict:
    """Recall/precision per identifier type.

    A golden span is found when a predicted span of the same type overlaps it; "exact"
    additionally requires identical offsets. A prediction is a false positive when it
    overlaps no golden span of its type. `hard_negative_hits` counts predictions that
    overlap a planted look-alike (invoice numbers, name-like words).
    """
    by_cell: dict[tuple, list[Span]] = defaultdict(list)
    for sp in pred:
        by_cell[(sp.table, sp.row, sp.column)].append(sp)
    gold_by_cell: dict[tuple, list[tuple[int, int, str]]] = defaultdict(list)
    for g in golden.itertuples(index=False):
        gold_by_cell[(g.table, int(g.row), g.column)].append((int(g.start), int(g.end), g.type))

    stats = {t: dict(golden=0, found=0, exact=0, predicted=0, false_pos=0) for t in IDENTIFIER_TYPES}
    for cell, golds in gold_by_cell.items():
        preds = by_cell.get(cell, [])
        for g0, g1, gt in golds:
            stats[gt]["golden"] += 1
            hits = [p for p in preds if p.type == gt and _overlaps(p.start, p.end, g0, g1)]
            stats[gt]["found"] += bool(hits)
            stats[gt]["exact"] += any(p.start == g0 and p.end == g1 for p in hits)
    for cell, preds in by_cell.items():
        golds = gold_by_cell.get(cell, [])
        for p in preds:
            stats[p.type]["predicted"] += 1
            if not any(gt == p.type and _overlaps(p.start, p.end, g0, g1) for g0, g1, gt in golds):
                stats[p.type]["false_pos"] += 1

    for st in stats.values():
        st["recall"] = round(st["found"] / st["golden"], 4) if st["golden"] else None
        st["precision"] = round(1 - st["false_pos"] / st["predicted"], 4) if st["predicted"] else None

    total_gold = sum(st["golden"] for st in stats.values())
    total_pred = sum(st["predicted"] for st in stats.values())
    numeric = ("SAUDI_ID", "MOBILE", "IBAN", "EMAIL")
    num_gold = sum(stats[t]["golden"] for t in numeric)
    result = {
        "per_type": stats,
        "overall_recall": round(sum(st["found"] for st in stats.values()) / total_gold, 4) if total_gold else None,
        "overall_precision": round(1 - sum(st["false_pos"] for st in stats.values()) / total_pred, 4) if total_pred else None,
        "structured_id_recall": round(sum(stats[t]["found"] for t in numeric) / num_gold, 4) if num_gold else None,
    }
    if negatives is not None:
        hits = 0
        neg_by_cell: dict[tuple, list[tuple[int, int]]] = defaultdict(list)
        for h in negatives.itertuples(index=False):
            neg_by_cell[(h.table, int(h.row), h.column)].append((int(h.start), int(h.end)))
        for cell, negs in neg_by_cell.items():
            for n0, n1 in negs:
                hits += any(_overlaps(p.start, p.end, n0, n1) for p in by_cell.get(cell, []))
        result["hard_negatives"] = len(negatives)
        result["hard_negative_hits"] = hits
    return result


# ---------------------------------------------------------------- leak scan

HARD_FAIL_KINDS = ("SAUDI_ID", "MOBILE", "IBAN", "EMAIL")
MAX_REPORTED_LOCATIONS = 25


def original_identifier_values(tables: dict[str, pd.DataFrame], detections, spans: list[Span]) -> dict[str, set[str]]:
    """Canonical original values of every DIRECT_ID column and every detected span (hard-fail kinds)."""
    from nazeer import saudi_ids as s

    values: dict[str, set[str]] = {k: set() for k in HARD_FAIL_KINDS}
    for d in detections:
        if d.tag == "DIRECT_ID" and d.kind in values:
            for raw in tables[d.table][d.column].dropna().unique():
                if s.is_valid(d.kind, raw):
                    values[d.kind].add(s.canonical(d.kind, raw))
    for sp in spans:
        if sp.type in values:
            values[sp.type].add(s.canonical(sp.type, tables[sp.table][sp.column].iat[sp.row][sp.start:sp.end]))
    return values


def _exhaustive_hits(text: str, originals: dict[str, set[str]]) -> set[tuple[str, str]]:
    """Every original value occurring anywhere in the normalized text, whatever the detector says."""
    import re

    from nazeer import saudi_ids as s

    norm = s.normalize(text)[0]
    hits = set()
    for m in re.finditer(r"\d+", norm):
        run = m.group()
        for i in range(len(run)):
            w10 = run[i:i + 10]
            if len(w10) == 10 and w10 in originals["SAUDI_ID"]:
                hits.add(("SAUDI_ID", w10))
            if run.startswith("05", i) and len(run) >= i + 10 and run[i + 1:i + 10] in originals["MOBILE"]:
                hits.add(("MOBILE", run[i + 1:i + 10]))
            if run.startswith("9665", i) and len(run) >= i + 12 and run[i + 3:i + 12] in originals["MOBILE"]:
                hits.add(("MOBILE", run[i + 3:i + 12]))
            w22 = run[i:i + 22]
            if len(w22) == 22 and "SA" + w22 in originals["IBAN"]:
                hits.add(("IBAN", "SA" + w22))
    lowered = norm.lower()
    if "@" in lowered:
        for email in re.findall(r"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}", lowered):
            if email in originals["EMAIL"]:
                hits.add(("EMAIL", email))
    return hits


def leak_scan(originals: dict[str, set[str]], twin: dict[str, pd.DataFrame], mode: str,
              original_tables: dict[str, pd.DataFrame] | None = None,
              name_columns: list[tuple[str, str]] = ()) -> dict:
    """Hard-fail check: no original identifier may appear anywhere in the twin.

    (a) the detector is rerun on every twin cell and its findings are canonicalized;
    (b) an exhaustive search looks for every known original value in every cell,
        independent of the detector. Names: in masked mode no row may keep its own
        full name (hard fail); in synthetic mode the full-name overlap rate is reported.
    The result holds counts and locations (table, column, row) only, never values.
    """
    from nazeer import detect
    from nazeer import saudi_ids as s

    leaked: dict[str, int] = {k: 0 for k in HARD_FAIL_KINDS}
    by_method = {"detector": 0, "exhaustive": 0}
    locations: list[dict] = []
    cells = 0
    for tname, df in twin.items():
        for col in df.columns:
            for row, v in enumerate(df[col].tolist()):
                if not isinstance(v, str) or not v:
                    continue
                cells += 1
                found: dict[tuple[str, str], str] = {}
                for a, b, k, _, _ in detect.find_spans(v, names=False):
                    if k in originals and s.canonical(k, v[a:b]) in originals[k]:
                        found[(k, s.canonical(k, v[a:b]))] = "detector"
                for hit in _exhaustive_hits(v, originals):
                    found.setdefault(hit, "exhaustive")
                for (k, _), method in found.items():
                    leaked[k] += 1
                    by_method[method] += 1
                    if len(locations) < MAX_REPORTED_LOCATIONS:
                        locations.append({"table": tname, "column": col, "row": row, "kind": k, "method": method})

    names = {"columns": [f"{t}.{c}" for t, c in name_columns]}
    if mode == "masked" and original_tables is not None:
        kept = 0
        for t, c in name_columns:
            if c not in twin[t].columns:
                continue
            orig = original_tables[t][c].fillna("").map(s.normalize_name)
            new = twin[t][c].fillna("").map(s.normalize_name)
            kept += int(((orig == new) & (orig != "")).sum())
        names["rows_keeping_original_full_name"] = kept
    elif mode == "synthetic" and original_tables is not None:
        orig_names = {s.normalize_name(v) for t, c in name_columns for v in original_tables[t][c].dropna()}
        twin_names = {s.normalize_name(v) for t, c in name_columns if c in twin[t].columns for v in twin[t][c].dropna()}
        names["full_name_overlap_rate"] = round(len(twin_names & orig_names) / len(twin_names), 4) if twin_names else 0.0
        names["note"] = "information only: common names recur by chance"

    total = sum(leaked.values())
    hard_fail = total > 0 or names.get("rows_keeping_original_full_name", 0) > 0
    return {
        "hard_fail": hard_fail,
        "verdict": "FAIL" if hard_fail else "PASS",
        "cells_scanned": cells,
        "original_values_checked": {k: len(v) for k, v in originals.items()},
        "leaked_by_kind": leaked,
        "leaks_by_method": by_method,
        "locations": locations,
        "names": names,
    }


def exact_copies(real: pd.DataFrame, twin: pd.DataFrame, columns: list[str] | None = None) -> int:
    """Number of twin rows identical to some real row over `columns` (default: shared columns)."""
    cols = columns or [c for c in twin.columns if c in real.columns]
    if not cols or twin.empty:
        return 0
    real_rows = set(real[cols].astype(str).itertuples(index=False, name=None))
    return int(sum(r in real_rows for r in twin[cols].astype(str).itertuples(index=False, name=None)))
