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
