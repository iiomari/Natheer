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


def canonical_or_none(kind: str, raw: str) -> str | None:
    from nazeer import saudi_ids as s

    try:
        return s.canonical(kind, raw)
    except Exception:  # noqa: BLE001 - an unparsable value simply cannot match
        return None


def residual_scan(twin: dict[str, pd.DataFrame], generated: set[str],
                  allowed: dict[tuple[str, str, int], set] | None = None,
                  cleared_columns: set[str] = frozenset()) -> dict:
    """Blind-spot check, independent of what the detector found in the originals: every VALID
    identifier left in the twin (checksum-valid national ID, valid mobile, mod-97-valid IBAN, valid
    e-mail) that Nazeer did not generate is a leak. Exceptions, both explicit reviewer decisions:
    values left for review in that cell, and columns confirmed to hold no identifiers.
    Counts and locations only."""
    from nazeer import detect
    from nazeer import saudi_ids as s

    allowed = allowed or {}
    by_kind: dict[str, int] = {k: 0 for k in HARD_FAIL_KINDS}
    locations: list[dict] = []
    for tname, df in twin.items():
        for col in df.columns:
            if f"{tname}.{col}" in cleared_columns:
                continue
            for row, v in enumerate(df[col].tolist()):
                if not isinstance(v, str) or len(v) < 6:
                    continue
                if "@" not in v and sum(ch.isdigit() for ch in v) < 9:
                    continue
                ok = allowed.get((tname, col, row), set())
                for a, b, k, _, _ in detect.find_spans(v, names=False):
                    piece = v[a:b]
                    if k not in by_kind:
                        continue
                    canon = canonical_or_none(k, piece)
                    # find_spans validated IDs, mobiles and e-mails; an IBAN shape must pass mod-97 here
                    if canon is None or (k == "IBAN" and not s.is_valid("IBAN", canon)):
                        continue
                    if canon in generated or canon in ok:
                        continue
                    by_kind[k] += 1
                    if len(locations) < 50:
                        locations.append({"table": tname, "column": col, "row": row, "kind": k})
    found = sum(by_kind.values())
    return {"verdict": "PASS" if found == 0 else "FAIL", "found": found, "by_kind": by_kind,
            "locations": locations,
            "note": "valid identifiers in the twin that Nazeer did not generate (counts and locations only)"}


def exact_copies(real: pd.DataFrame, twin: pd.DataFrame, columns: list[str] | None = None) -> int:
    """Number of twin rows identical to some real row over `columns` (default: shared columns)."""
    cols = columns or [c for c in twin.columns if c in real.columns]
    if not cols or twin.empty:
        return 0
    real_rows = set(real[cols].astype(str).itertuples(index=False, name=None))
    return int(sum(r in real_rows for r in twin[cols].astype(str).itertuples(index=False, name=None)))


# ---------------------------------------------------------------- fidelity (5b)

def fidelity(real: pd.DataFrame, twin: pd.DataFrame, kinds: dict[str, str]) -> dict:
    """Per-column distribution distance and correlation difference, real-train vs twin."""
    import numpy as np
    from scipy.stats import ks_2samp

    def ks(a: pd.Series, b: pd.Series) -> float | None:
        return round(float(ks_2samp(a, b).statistic), 4) if len(a) and len(b) else None

    columns = {}
    for col, kind in kinds.items():
        if kind == "numerical":
            a = pd.to_numeric(real[col], errors="coerce").dropna()
            b = pd.to_numeric(twin[col], errors="coerce").dropna()
            columns[col] = {"metric": "KS statistic", "value": ks(a, b)}
        elif kind == "datetime":
            a = pd.to_datetime(real[col], errors="coerce").dropna().astype("int64")
            b = pd.to_datetime(twin[col], errors="coerce").dropna().astype("int64")
            columns[col] = {"metric": "KS statistic", "value": ks(a, b)}
        else:
            p = real[col].astype(str).value_counts(normalize=True)
            q = twin[col].astype(str).value_counts(normalize=True)
            tvd = 0.5 * float(p.subtract(q, fill_value=0).abs().sum())
            columns[col] = {"metric": "total variation distance", "value": round(tvd, 4)}
    num = [c for c, k in kinds.items() if k == "numerical"]
    corr_diff = None
    if len(num) >= 2:
        cr = real[num].apply(pd.to_numeric, errors="coerce").corr().to_numpy()
        ct = twin[num].apply(pd.to_numeric, errors="coerce").corr().to_numpy()
        iu = np.triu_indices(len(num), 1)
        corr_diff = round(float(np.nanmean(np.abs(cr[iu] - ct[iu]))), 4)
    values = [v["value"] for v in columns.values() if v["value"] is not None]
    return {"columns": columns, "mean_column_distance": round(float(np.mean(values)), 4) if values else None,
            "numeric_correlation_mean_abs_diff": corr_diff}


def sdmetrics_quality(real: pd.DataFrame, twin: pd.DataFrame, kinds: dict[str, str]) -> float | None:
    """SDV/SDMetrics overall quality score (0..1), or None if it cannot run."""
    import logging

    try:
        from sdv.evaluation import evaluate_quality

        from nazeer.synth import SynthSchema, _sdv_metadata

        meta = _sdv_metadata(SynthSchema(tables={"view": kinds}))
        report = evaluate_quality(real[list(kinds)], twin[list(kinds)], meta, verbose=False)
        return round(float(report.get_score()), 4)
    except Exception:  # noqa: BLE001 - optional cross-check
        logging.getLogger(__name__).warning("SDMetrics quality report unavailable", exc_info=True)
        return None


# ---------------------------------------------------------------- utility: TSTR (5b)

def parse_target(spec: str) -> tuple[str, str, float | None]:
    """'is_large_claim=amount>p90' -> ('is_large_claim', 'amount', 90.0); 'flag' -> ('flag', 'flag', None)."""
    import re

    if "=" in spec:
        label, expr = spec.split("=", 1)
    else:
        label, expr = spec, spec
    m = re.fullmatch(r"\s*(\w+)\s*>\s*p(\d{1,2})\s*", expr)
    if m:
        return label.strip(), m.group(1), float(m.group(2))
    return label.strip(), expr.strip(), None


def utility_tstr(train: pd.DataFrame, twin: pd.DataFrame, holdout: pd.DataFrame, kinds: dict[str, str],
                 target: str, seed: int = 0) -> dict:
    """Train-on-synthetic, test-on-real: the same models are trained on real-train and on
    the twin, and both are tested on the real holdout. Reports AUC/F1 and the AUC drop."""
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score, roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    label, source, pct = parse_target(target)
    if source not in train.columns:
        raise ValueError(f"target column {source!r} is not in the modelled data")
    if pct is not None:
        threshold = float(pd.to_numeric(train[source], errors="coerce").quantile(pct / 100))
        definition = f"{source} > P{pct:g} of real-train ({threshold:,.2f})"

        def to_y(df: pd.DataFrame) -> pd.Series:
            return (pd.to_numeric(df[source], errors="coerce") > threshold).astype(int)
    else:
        classes = sorted(train[source].astype(str).unique())
        if len(classes) != 2:
            raise ValueError("target must be binary, or an expression like 'label=column>p90'")
        positive = classes[1]
        definition = f"{source} == {positive}"

        def to_y(df: pd.DataFrame) -> pd.Series:
            return (df[source].astype(str) == positive).astype(int)

    features = [c for c, k in kinds.items() if c != source and k in ("numerical", "categorical")]
    num = [c for c in features if kinds[c] == "numerical"]
    cat = [c for c in features if kinds[c] == "categorical"]

    def prep(df: pd.DataFrame) -> pd.DataFrame:
        x = df[features].copy()
        for c in num:
            x[c] = pd.to_numeric(x[c], errors="coerce").fillna(0.0)
        for c in cat:
            x[c] = x[c].astype(str)
        return x

    def encoder() -> ColumnTransformer:
        return ColumnTransformer([("num", StandardScaler(), num), ("cat", OneHotEncoder(handle_unknown="ignore"), cat)])

    def models() -> dict:
        return {
            "logistic_regression": make_pipeline(encoder(), LogisticRegression(max_iter=2000)),
            "random_forest": make_pipeline(encoder(), RandomForestClassifier(
                n_estimators=200, min_samples_leaf=5, random_state=seed, n_jobs=-1)),
        }

    x_hold, y_hold = prep(holdout), to_y(holdout)
    result = {
        "target": label, "definition": definition, "features": features,
        "positive_rate": {"real_train": round(float(to_y(train).mean()), 4),
                          "twin": round(float(to_y(twin).mean()), 4),
                          "holdout": round(float(y_hold.mean()), 4)},
        "models": {},
    }
    for source_name, df in (("real", train), ("twin", twin)):
        y = to_y(df)
        for name, model in models().items():
            entry = result["models"].setdefault(name, {})
            if y.nunique() < 2:
                entry[source_name] = {"auc": None, "f1": None, "note": "only one class in training labels"}
                continue
            model.fit(prep(df), y)
            proba = model.predict_proba(x_hold)[:, 1]
            entry[source_name] = {"auc": round(float(roc_auc_score(y_hold, proba)), 4),
                                  "f1": round(float(f1_score(y_hold, (proba >= 0.5).astype(int), zero_division=0)), 4)}
    for entry in result["models"].values():
        r, t = entry.get("real", {}).get("auc"), entry.get("twin", {}).get("auc")
        entry["auc_drop"] = round(r - t, 4) if r is not None and t is not None else None
    drops = [e["auc_drop"] for e in result["models"].values() if e["auc_drop"] is not None]
    result["max_auc_drop"] = max(drops) if drops else None
    return result


# ---------------------------------------------------------------- privacy: DCR (5b)

def dcr(train: pd.DataFrame, twin: pd.DataFrame, holdout: pd.DataFrame, kinds: dict[str, str], seed: int = 0,
        strata: str | None = None) -> dict:
    """Distance to closest record in real-train, for twin rows vs holdout rows.

    Agreed rule: PASS if median DCR(twin -> train) >= median DCR(holdout -> train).
    Also reported: the share of twin rows closer to train than to holdout, with train
    subsampled to the holdout size so that about 50% is the ideal.
    """
    import numpy as np
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import OneHotEncoder

    cols = list(kinds)
    cat = [c for c in cols if kinds[c] == "categorical"]
    cont = [c for c in cols if kinds[c] in ("numerical", "datetime")]

    def as_float(series: pd.Series, kind: str) -> pd.Series:
        if kind == "datetime":
            return pd.to_datetime(series, errors="coerce").astype("int64").astype(float) / 8.64e13  # days
        return pd.to_numeric(series, errors="coerce").astype(float)

    ranges = {}
    for c in cont:
        r = as_float(train[c], kinds[c])
        lo, hi = float(r.min()), float(r.max())
        ranges[c] = (lo, hi - lo if hi > lo else 1.0)
    enc = OneHotEncoder(handle_unknown="ignore", sparse_output=False).fit(train[cat].astype(str)) if cat else None

    def encode(df: pd.DataFrame) -> np.ndarray:
        parts = []
        for c in cont:
            lo, span = ranges[c]
            parts.append(((as_float(df[c], kinds[c]).fillna(lo) - lo) / span).to_numpy()[:, None])
        if enc is not None:
            parts.append(enc.transform(df[cat].astype(str)))
        return np.hstack(parts) if parts else np.zeros((len(df), 0))

    x_train, x_twin, x_hold = encode(train), encode(twin), encode(holdout)
    nn_train = NearestNeighbors(n_neighbors=1).fit(x_train)
    d_twin = nn_train.kneighbors(x_twin)[0][:, 0]
    d_hold = nn_train.kneighbors(x_hold)[0][:, 0]

    rng = np.random.default_rng(seed)
    sub = x_train[rng.choice(len(x_train), size=min(len(x_hold), len(x_train)), replace=False)]
    d_sub = NearestNeighbors(n_neighbors=1).fit(sub).kneighbors(x_twin)[0][:, 0]
    d_h = NearestNeighbors(n_neighbors=1).fit(x_hold).kneighbors(x_twin)[0][:, 0]
    med_twin, med_hold = float(np.median(d_twin)), float(np.median(d_hold))
    per_stratum = None
    if strata and strata in twin.columns and strata in holdout.columns:
        per_stratum = {}
        tw_vals, ho_vals = twin[strata].astype(str).to_numpy(), holdout[strata].astype(str).to_numpy()
        for v in sorted(set(tw_vals) | set(ho_vals)):
            a, b = d_twin[tw_vals == v], d_hold[ho_vals == v]
            if len(a) and len(b):
                per_stratum[v] = {"twin_rows": int(len(a)), "holdout_rows": int(len(b)),
                                  "median_dcr_twin_to_train": round(float(np.median(a)), 5),
                                  "median_dcr_holdout_to_train": round(float(np.median(b)), 5),
                                  "passed": bool(np.median(a) >= np.median(b))}
    return {
        "per_stratum": per_stratum,
        "median_dcr_twin_to_train": round(med_twin, 5),
        "median_dcr_holdout_to_train": round(med_hold, 5),
        "passed": bool(med_twin >= med_hold),
        "share_twin_closer_to_train_than_holdout": round(float(np.mean(d_sub < d_h)), 4),
        "share_ideal": 0.5,
        # sklearn computes |x|^2+|y|^2-2xy, so identical rows can come out as ~1e-8, not 0
        "twin_rows_at_distance_zero": int(np.sum(d_twin < 1e-6)),
        "columns": cols,
    }
