"""Pure helpers behind the Streamlit app (testable without a Streamlit runtime)."""
from __future__ import annotations

import pandas as pd

TAGS = ["DIRECT_ID", "QUASI_ID", "SENSITIVE", "NORMAL", "FREE_TEXT"]
KINDS = ["", "SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME"]
ACTIONS = ["policy", "keep", "pseudonymize", "drop"]


def detection_frame(analysis, overrides: dict | None = None) -> pd.DataFrame:
    """One editable row per column; current overrides are shown as already applied."""
    overrides = overrides or {}
    rows = []
    for d in analysis.detections:
        o = overrides.get(f"{d.table}.{d.column}", {})
        rows.append({
            "table": d.table, "column": d.column,
            "type": analysis.profile.column(d.table, d.column).dtype,
            "tag": o.get("tag", d.tag),
            "identifier": o.get("kind", d.kind) or "",
            "action": (o.get("action") or {}).get("action", "policy"),
            "reviewed": bool(o),
            "confidence": round(d.score, 2),
            "needs review": "yes" if d.needs_review else "",
            "why": d.reason,
        })
    return pd.DataFrame(rows)


def overrides_from_edits(analysis, edited: pd.DataFrame) -> tuple[dict, list[str]]:
    """Diff the edited table against the detections -> (overrides, problems).

    A row becomes an override when its tag, identifier or action changed, or when the
    reviewer ticked "reviewed" (confirming the detection). Overrides are recorded in the
    report as human-reviewed.
    """
    det = {(d.table, d.column): d for d in analysis.detections}
    overrides, problems = {}, []
    for row in edited.itertuples(index=False):
        d = det[(row.table, row.column)]
        tag = row.tag if row.tag in TAGS else d.tag
        kind = row.identifier or None
        action = row.action if row.action in ACTIONS else "policy"
        changed = tag != d.tag or kind != d.kind or action != "policy"
        if not (changed or row.reviewed):
            continue
        key = f"{row.table}.{row.column}"
        if tag == "DIRECT_ID" and kind is None:
            problems.append(f"{key}: a direct identifier needs an identifier type")
            continue
        if action == "pseudonymize" and kind is None:
            problems.append(f"{key}: pseudonymize needs an identifier type")
            continue
        o = {"tag": tag, "kind": kind if tag == "DIRECT_ID" or action == "pseudonymize" else None}
        if action != "policy":
            o["action"] = {"action": action}
        overrides[key] = o
    return overrides, problems


def suggestion_frame(kanon_entry: dict) -> pd.DataFrame:
    return pd.DataFrame([{
        "fix": f["name"], "what it does": f["description"], "k before": f["k_before"], "k after": f["k_after"],
        "rows affected": f["rows_affected"], "reaches k_min": "yes" if f["reaches_k_min"] else "no",
    } for f in kanon_entry.get("suggestions", [])])


# ---------------------------------------------------------------- "Why it works"

SAUDI_TYPES = ["Saudi national ID (1…)", "Iqama (2…)", "Saudi mobile (05 / +966 / 966 / 00966)",
               "Saudi IBAN (SA…, mod-97)", "Arabic person names", "Arabic-Indic and Persian digits",
               "email"]


def fake_validity(result, detections) -> dict:
    """Share of twin identifier values that pass the official validators, per column."""
    from nazeer import saudi_ids as s

    kinds = {}
    for d in detections:
        if d.tag == "DIRECT_ID" and d.kind in ("SAUDI_ID", "MOBILE", "IBAN", "EMAIL"):
            kinds.setdefault(d.column, d.kind)
    out = {}
    for table, df in result.twin.items():
        for col in df.columns:
            if col in kinds:
                vals = df[col].dropna().astype(str)
                if len(vals):
                    out[f"{table}.{col}"] = round(float(vals.map(lambda v, k=kinds[col]: s.is_valid(k, v)).mean()), 4)
    return out


def referential_integrity(result, profile) -> dict:
    """Orphan foreign-key values in the twin (0 = joins still work)."""
    out = {}
    for fk in profile.foreign_keys:
        child, parent = result.twin.get(fk.child_table), result.twin.get(fk.parent_table)
        if child is None or parent is None or fk.child_column not in child or fk.parent_column not in parent:
            continue
        values = child[fk.child_column].dropna()
        out[f"{fk.child_table}.{fk.child_column} → {fk.parent_table}.{fk.parent_column}"] = \
            int((~values.isin(set(parent[fk.parent_column]))).sum())
    return out


def local_only_facts() -> list[str]:
    import os

    facts = []
    facts.append("Hugging Face offline mode " + ("ON" if os.environ.get("HF_HUB_OFFLINE") == "1" else "OFF"))
    facts.append("Hugging Face telemetry " + ("OFF" if os.environ.get("HF_HUB_DISABLE_TELEMETRY") == "1" else "ON"))
    try:
        from streamlit import config as st_config

        facts.append("Streamlit usage statistics " + ("OFF" if not st_config.get_option("browser.gatherUsageStats") else "ON"))
        addr = st_config.get_option("server.address")
        facts.append(f"app bound to {addr}" if addr else "app address not restricted")
    except Exception:  # noqa: BLE001 - outside a Streamlit runtime
        pass
    return facts


def why_it_works(analysis, result, golden_scores: dict | None) -> pd.DataFrame:
    rep = result.report if result is not None else None
    rows = []

    # 1. realistic data
    if rep and rep["mode"] == "synthetic" and rep.get("utility", {}).get("max_auc_drop") is not None:
        u = rep["utility"]
        best = max(u["models"].values(), key=lambda m: m["real"]["auc"] or 0)
        metric = (f"TSTR AUC drop {u['max_auc_drop']:.4f} (real {best['real']['auc']:.3f} → twin "
                  f"{best['twin']['auc']:.3f}; target {u['target']})")
    else:
        metric = "run the synthetic twin with a target to measure the TSTR AUC drop"
    rows.append(("Teams need realistic data for analytics and AI",
                 "The twin keeps distributions and relationships (holdout split before training)", metric))

    # 2. valid, consistent fakes
    if result is not None and not result.twin_withheld:
        val = fake_validity(result, analysis.detections)
        ri = referential_integrity(result, analysis.profile)
        pct = (min(val.values()) if val else None)
        parts = [f"{pct:.1%} of fake identifiers pass the official validators" if pct is not None else "no identifier columns"]
        parts.append(("orphan foreign keys: " + ", ".join(f"{k}: {v}" for k, v in ri.items())) if ri
                     else "single table (no joins to check)")
        metric = "; ".join(parts)
    else:
        metric = "run Nazeer to measure"
    rows.append(("Random fake data breaks validation rules and joins",
                 "Keyed, consistent, format-valid pseudonyms (checksums, same fake across tables and text)", metric))

    # 3. hidden identifiers in Arabic text
    if golden_scores:
        n, b = golden_scores["nazeer"], golden_scores["baseline"]
        metric = (f"recall Nazeer {n['overall_recall']:.1%} vs baseline {b['overall_recall']:.1%} "
                  f"(precision {n['overall_precision']:.1%} vs {b['overall_precision']:.1%}; demo answer key)")
    else:
        metric = (f"found in free text: Nazeer {len(analysis.spans):,} vs baseline {len(analysis.baseline_spans):,} "
                  "(no answer key for this data)")
    rows.append(("Identifiers hide in Arabic free text (Arabic digits, spaces, +966)",
                 "Digit normalization with offset map + checksum validation + Arabic name detection", metric))

    # 4. Saudi context, local
    rows.append(("Generic tools do not know Saudi formats and often need the cloud",
                 "Saudi validators and generators; runs entirely on this machine",
                 f"supported: {', '.join(SAUDI_TYPES)} · " + "; ".join(local_only_facts())))

    # 5. evidence
    if rep:
        leaks = sum(rep["leak_scan"]["leaked_by_kind"].values())
        metric = f"verdict {rep['verdict']}; {leaks} original identifier(s) found in the twin ({rep['leak_scan']['cells_scanned']:,} cells scanned)"
    else:
        metric = "run Nazeer to produce the report"
    rows.append(("The data-protection officer has no evidence that the copy is safe",
                 "PASS/FAIL evidence report: leak scan, exact copies, k-anonymity / DCR, utility", metric))

    return pd.DataFrame(rows, columns=["root cause", "Nazeer component", "live metric (this run)"])
