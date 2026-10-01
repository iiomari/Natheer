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
