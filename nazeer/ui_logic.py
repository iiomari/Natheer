"""Pure helpers behind the Streamlit app (testable without a Streamlit runtime).

Presentation only: these functions read an Analysis / RunResult and shape it for the
screen. They never change detection, transformation, metrics or thresholds.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd

TAGS = ["DIRECT_ID", "QUASI_ID", "SENSITIVE", "NORMAL", "FREE_TEXT"]
KINDS = ["", "SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME"]
ACTIONS = ["policy", "keep", "pseudonymize", "drop"]
HARD_KINDS = ("SAUDI_ID", "MOBILE", "IBAN", "EMAIL")
# Display only: spans at or below this confidence get a "needs review" label in the UI
# (a lone first name with no family name or cue, or an ID next to an invoice-like word).
# The pipeline still replaces every span at or above min_span_confidence.
REVIEW_AT_OR_BELOW = 0.7


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


# ---------------------------------------------------------------- following one entity across tables

def entity_key(profile) -> tuple[str, str] | None:
    """(table, column) of the entity to follow, e.g. ("customers", "customer_id"): the parent
    that most foreign keys point at, else the first table with a primary key."""
    parents = Counter((fk.parent_table, fk.parent_column) for fk in profile.foreign_keys)
    if parents:
        return parents.most_common(1)[0][0]
    for name, t in profile.tables.items():
        if t.primary_key:
            return name, t.primary_key
    return None


def entity_values(analysis) -> list[str]:
    key = entity_key(analysis.profile)
    if key is None:
        return []
    return analysis.tables[key[0]][key[1]].dropna().astype(str).tolist()


def entity_rows(analysis, value) -> dict[str, list[int]]:
    """Positional rows of one entity in every table: its own row, plus child rows via foreign keys."""
    key = entity_key(analysis.profile)
    if key is None or value is None:
        return {}
    table, col = key
    tables = analysis.tables

    def rows_where(t: str, c: str) -> list[int]:
        return [i for i, v in enumerate(tables[t][c].astype(str).tolist()) if v == str(value)]

    out = {table: rows_where(table, col)}
    for fk in analysis.profile.foreign_keys:
        if (fk.parent_table, fk.parent_column) == key:
            out[fk.child_table] = rows_where(fk.child_table, fk.child_column)
    return out


def entity_label(analysis, value) -> str:
    """"<name> · <key>" when the entity table has a person-name column, else the key."""
    key = entity_key(analysis.profile)
    if key is None:
        return str(value)
    table, col = key
    name_col = next((d.column for d in analysis.detections
                     if d.table == table and d.tag == "DIRECT_ID" and d.kind == "PERSON_NAME"), None)
    rows = entity_rows(analysis, value).get(table, [])
    if name_col and rows:
        name = analysis.tables[table][name_col].iat[rows[0]]
        if isinstance(name, str) and name:
            return f"{name} · {value}"
    return str(value)


def entity_labels(analysis) -> dict[str, str]:
    """{key: "<name> · <key>"} for every entity, in one pass (for a selectbox)."""
    key = entity_key(analysis.profile)
    if key is None:
        return {}
    table, col = key
    keys = analysis.tables[table][col].astype(str).tolist()
    name_col = next((d.column for d in analysis.detections
                     if d.table == table and d.tag == "DIRECT_ID" and d.kind == "PERSON_NAME"), None)
    if name_col is None:
        return {k: k for k in keys}
    names = analysis.tables[table][name_col].tolist()
    return {k: (f"{n} · {k}" if isinstance(n, str) and n else k) for k, n in zip(keys, names)}


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _cell_spans(spans) -> dict[tuple[str, str, int], list]:
    out: dict = defaultdict(list)
    for sp in spans:
        out[(sp.table, sp.column, sp.row)].append(sp)
    return out


def note_score(analysis, cell: tuple[str, str, int], naz=None, base=None) -> int:
    """How well one free-text cell shows the difference between Nazeer and the baseline."""
    from nazeer import saudi_ids as s

    naz = naz if naz is not None else _cell_spans(analysis.spans)
    base = base if base is not None else _cell_spans(analysis.baseline_spans)
    n, b = naz.get(cell, []), base.get(cell, [])
    text = analysis.tables[cell[0]][cell[1]].iat[cell[2]]
    missed = sum(not any(_overlaps((x.start, x.end), (y.start, y.end)) for y in b) for x in n)
    false_alarms = sum(not s.is_valid(y.type, text[y.start:y.end]) for y in b)
    return missed + 3 * false_alarms + 2 * len({x.type for x in n})


def entity_notes(analysis, value) -> list[tuple[str, str, int]]:
    """Free-text cells of one entity that contain something to show, best first."""
    rows = entity_rows(analysis, value)
    cols = [(d.table, d.column) for d in analysis.detections if d.tag == "FREE_TEXT"]
    naz, base = _cell_spans(analysis.spans), _cell_spans(analysis.baseline_spans)
    cells = [(t, c, r) for t, c in cols for r in rows.get(t, [])
             if isinstance(analysis.tables[t][c].iat[r], str) and analysis.tables[t][c].iat[r]]
    return sorted(cells, key=lambda cell: (-note_score(analysis, cell, naz, base), cell))


def default_entity(analysis):
    """The entity whose notes best show what a generic tool misses (few notes, many findings)."""
    key = entity_key(analysis.profile)
    if key is None:
        return None
    cols = [(d.table, d.column) for d in analysis.detections if d.tag == "FREE_TEXT"]
    naz, base = _cell_spans(analysis.spans), _cell_spans(analysis.baseline_spans)
    owner: dict[tuple[str, int], str] = {}
    for fk in analysis.profile.foreign_keys:
        if (fk.parent_table, fk.parent_column) == key:
            for i, v in enumerate(analysis.tables[fk.child_table][fk.child_column].astype(str).tolist()):
                owner[(fk.child_table, i)] = v
    for i, v in enumerate(analysis.tables[key[0]][key[1]].astype(str).tolist()):
        owner[(key[0], i)] = v
    score: Counter = Counter()
    notes: Counter = Counter()
    kinds: dict[str, set] = defaultdict(set)
    for t, c, r in naz:
        if (t, c) in cols and (t, r) in owner:
            v = owner[(t, r)]
            score[v] += note_score(analysis, (t, c, r), naz, base)
            notes[v] += 1
            kinds[v].update(sp.type for sp in naz[(t, c, r)])
    if not score:
        values = entity_values(analysis)
        return values[0] if values else None
    return max(score, key=lambda v: (len(kinds[v]) >= 4, notes[v] <= 3, score[v], -int(v) if v.isdigit() else 0))


# ---------------------------------------------------------------- highlighted notes

def note_marks(text: str, nazeer_spans, baseline_spans) -> tuple[list[tuple], list[tuple]]:
    """(baseline marks, Nazeer marks) for one note; a mark is (start, end, status, kind).

    status: "hit" (identifier), "review" (low confidence, still replaced), "rejected" (Nazeer
    checked a look-alike and the official validator refused it), "false_alarm" (the baseline
    flagged a number that fails the official validator).
    """
    from nazeer import saudi_ids as s

    base = []
    for sp in baseline_spans:
        ok = s.is_valid(sp.type, text[sp.start:sp.end])
        base.append((sp.start, sp.end, "hit" if ok else "false_alarm", sp.type))
    naz = [(sp.start, sp.end, "review" if sp.confidence <= REVIEW_AT_OR_BELOW else "hit", sp.type)
           for sp in nazeer_spans]
    for a, b, status, kind in base:
        if status == "false_alarm" and not any(_overlaps((a, b), (x[0], x[1])) for x in naz):
            naz.append((a, b, "rejected", kind))
    return sorted(base), sorted(naz)


def cell_marks(analysis, cell: tuple[str, str, int]) -> tuple[str, list[tuple], list[tuple]]:
    t, c, r = cell
    text = analysis.tables[t][c].iat[r]
    naz = [sp for sp in analysis.spans if (sp.table, sp.column, sp.row) == cell]
    base = [sp for sp in analysis.baseline_spans if (sp.table, sp.column, sp.row) == cell]
    return (text, *note_marks(text, naz, base))


def twin_marks(text: str) -> list[tuple]:
    """Identifiers in a twin note (all of them fakes), found by re-running the detector."""
    from nazeer import detect

    if not isinstance(text, str) or not text:
        return []
    return [(a, b, "twin", k) for a, b, k, _, _ in detect.find_spans(text)]


def mask_text(text: str, spans: list[tuple[int, int, str]], key: bytes) -> str:
    """Preview: the text with each span replaced the way the masked twin would replace it."""
    from nazeer import saudi_ids as s
    from nazeer import transform

    pseudo = transform.Pseudonymizer(key)
    values: dict[str, set[str]] = defaultdict(set)
    for a, b, kind in spans:
        if kind == "PERSON_NAME":
            for k, v in transform.name_token_values(text[a:b]):
                values[k].add(v)
        else:
            values[kind].add(s.canonical(kind, text[a:b]))
    for kind, vals in values.items():
        if kind not in transform.NAME_KINDS:
            pseudo.forbid(kind, vals)
    pseudo.prepare(values)
    return transform.replace_spans(text, spans, pseudo)


# ---------------------------------------------------------------- detection headline

def detection_summary(analysis, golden_scores: dict | None) -> dict:
    """Found and false alarms for the baseline and for Nazeer.

    With the demo answer key: identifiers found out of all planted ones, and flags that match no
    planted identifier. Without it: what each tool flagged; baseline false alarms are flags that
    fail the official validator, and Nazeer's are unknown (every flag already passed it).
    """
    from nazeer import saudi_ids as s

    if golden_scores:
        out = {"has_key": True}
        for who in ("baseline", "nazeer"):
            per = golden_scores[who]["per_type"]
            out[who] = {"found": sum(v["found"] for v in per.values()),
                        "false_alarms": sum(v["false_pos"] for v in per.values()),
                        "recall": golden_scores[who]["overall_recall"]}
        out["total"] = sum(v["golden"] for v in golden_scores["nazeer"]["per_type"].values())
        return out
    bad = 0
    for sp in analysis.baseline_spans:
        text = analysis.tables[sp.table][sp.column].iat[sp.row]
        bad += not s.is_valid(sp.type, text[sp.start:sp.end])
    return {"has_key": False, "total": None,
            "baseline": {"found": len(analysis.baseline_spans), "false_alarms": bad, "recall": None},
            "nazeer": {"found": len(analysis.spans), "false_alarms": None, "recall": None}}


# ---------------------------------------------------------------- original vs twin

def compare_rows(original: pd.DataFrame, twin: pd.DataFrame, rows: list[int],
                 columns: list[str] | None = None) -> list[dict]:
    """Per row: {column: (original value, twin value, changed?)}. A masked twin keeps row
    positions, so row i of the twin is row i of the original."""
    cols = columns or [c for c in original.columns]
    out = []
    for r in rows:
        if r >= len(twin):
            continue
        row = {}
        for c in cols:
            o = original[c].iat[r] if c in original.columns else None
            t = twin[c].iat[r] if c in twin.columns else None
            row[c] = (o, t, _show(o) != _show(t))
        out.append(row)
    return out


def _show(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def column_actions(result) -> dict[tuple[str, str], str]:
    return {(d.table, d.column): d.action for d in result.decisions}


def _as_number(series: pd.Series) -> pd.Series | None:
    num = pd.to_numeric(series, errors="coerce")
    return num if num.notna().mean() > 0.95 else None


def twin_totals(analysis, result) -> dict:
    """Row counts, numeric totals (columns numeric in both) and broken links: original vs twin."""
    tables = []
    for name, twin in result.twin.items():
        orig = analysis.tables.get(name)
        if orig is None:
            continue
        skip = {analysis.profile.tables[name].primary_key} | {
            fk.child_column for fk in analysis.profile.foreign_keys if fk.child_table == name} | {
            d.column for d in analysis.detections if d.table == name and d.tag == "DIRECT_ID"}
        sums = []
        for col in orig.columns:
            if col in skip or col not in twin.columns or analysis.profile.column(name, col).dtype != "numeric":
                continue
            o, t = _as_number(orig[col]), _as_number(twin[col])
            if o is not None and t is not None:
                sums.append({"column": col, "original": float(o.sum()), "twin": float(t.sum())})
        tables.append({"table": name, "rows_original": int(len(orig)), "rows_twin": int(len(twin)), "sums": sums})
    orphans = referential_integrity(result, analysis.profile)
    same = all(t["rows_original"] == t["rows_twin"] and all(abs(s["original"] - s["twin"]) < 1e-6 for s in t["sums"])
               for t in tables)
    return {"tables": tables, "orphans": sum(orphans.values()), "links": len(orphans),
            "all_same": same and sum(orphans.values()) == 0}


# ---------------------------------------------------------------- proof

def proof(analysis, result) -> dict:
    """Numbers behind the four proof cards of a masked run (status computed from the report
    and from the twin itself; nothing is re-thresholded)."""
    rep = result.report
    check = {c["name"]: c for c in rep["checks"]}
    leak = rep["leak_scan"]
    out = {"leak": {"status": leak["verdict"], "leaks": sum(leak["leaked_by_kind"].values()),
                    "cells": leak["cells_scanned"],
                    "names_kept": leak.get("names", {}).get("rows_keeping_original_full_name", 0)}}
    if result.twin_withheld:
        out["validity"] = out["links"] = None
    else:
        val = fake_validity(result, analysis.detections)
        out["validity"] = {"status": "PASS" if val and min(val.values()) == 1.0 else ("FAIL" if val else "NOT_RUN"),
                           "share": min(val.values()) if val else None, "columns": val}
        ri = referential_integrity(result, analysis.profile)
        out["links"] = {"status": "PASS" if sum(ri.values()) == 0 else "FAIL", "orphans": sum(ri.values()),
                        "links": ri}
    k = next(iter(rep.get("k_anonymity", {}).items()), None)
    if k:
        table, e = k
        name = f"k_anonymity[{table}]"
        out["k"] = {"status": check[name]["status"] if name in check else ("PASS" if e["passed_after"] else "FAIL"),
                    "table": table, **e}
    else:
        out["k"] = None
    return out


def planted_value(analysis, entity) -> tuple[str, str] | None:
    """(kind, raw value) of a real identifier to plant: the entity's own ID, mobile, IBAN or
    email if it has one, else the first identifier found in free text."""
    rows = entity_rows(analysis, entity)
    for kind in HARD_KINDS:
        for d in analysis.detections:
            if d.tag == "DIRECT_ID" and d.kind == kind and rows.get(d.table):
                v = analysis.tables[d.table][d.column].iat[rows[d.table][0]]
                if isinstance(v, str) and v:
                    return kind, v
    for sp in analysis.spans:
        if sp.type in HARD_KINDS:
            return sp.type, analysis.tables[sp.table][sp.column].iat[sp.row][sp.start:sp.end]
    return None


def disguise(kind: str, raw: str) -> str:
    """The value as someone might type it in a note: Arabic-Indic digits, in spaced groups."""
    from nazeer import saudi_ids as s

    if kind == "EMAIL":
        return raw
    flat = s.flatten(raw)
    prefix = "SA" if flat.upper().startswith("SA") else ""
    digits = flat[len(prefix):].lstrip("+")
    size = 4 if kind == "IBAN" else 3
    groups = [digits[i:i + size] for i in range(0, len(digits), size)]
    if len(groups) > 1 and len(groups[-1]) == 1:
        groups[-2:] = [groups[-2] + groups[-1]]
    return prefix + " ".join(groups).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def plant_leak(analysis, result, entity, overrides: dict | None = None) -> dict | None:
    """Copy the twin, write one real identifier (disguised) into a free-text cell, and run the
    pipeline's own leak scan on the copy. The real twin is not touched."""
    from nazeer import evaluate
    from nazeer.pipeline import spans_for
    from nazeer.policy import apply_overrides

    picked = planted_value(analysis, entity)
    if picked is None or result.twin_withheld or result.mode != "masked":
        return None
    kind, raw = picked
    shown = disguise(kind, raw)
    twin = {t: df.copy() for t, df in result.twin.items()}
    rows = entity_rows(analysis, entity)
    cols = [(d.table, d.column) for d in analysis.detections if d.tag == "FREE_TEXT" and d.column in twin.get(d.table, {})]
    target = next(((t, c, rows[t][0]) for t, c in cols if rows.get(t)), None)
    if target is None and cols:
        target = (cols[0][0], cols[0][1], 0)
    if target is None:
        t = next(iter(twin))
        c = next((c for c in twin[t].columns if twin[t][c].map(lambda v: isinstance(v, str)).all()), twin[t].columns[0])
        target = (t, c, 0)
    t, c, r = target
    before = twin[t][c].iat[r] if isinstance(twin[t][c].iat[r], str) else ""
    note = f"{before} للتواصل: {shown}".strip()
    values = twin[t][c].astype(object).tolist()
    values[r] = note
    twin[t][c] = values
    dets = apply_overrides(analysis.detections, overrides or {})
    _, all_spans = spans_for(analysis, dets)
    originals = evaluate.original_identifier_values(analysis.tables, dets, all_spans)
    name_cols = [(d.table, d.column) for d in dets if d.tag == "DIRECT_ID" and d.kind == "PERSON_NAME"]
    leak = evaluate.leak_scan(originals, twin, result.mode, analysis.tables, name_cols)
    start = len(note) - len(shown)
    return {"kind": kind, "table": t, "column": c, "row": r, "text": note, "start": start, "end": len(note),
            "leak": leak}


# ---------------------------------------------------------------- "Why it works"

SAUDI_TYPES = ["الهوية الوطنية (1…)", "الإقامة (2…)", "الجوال (05 / ‎+966 / 966 / 00966)",
               "الآيبان السعودي (SA…)", "الأسماء العربية", "الأرقام العربية والفارسية", "البريد الإلكتروني"]


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

    def on_off(flag: bool) -> str:
        return "مفعّل" if flag else "غير مفعّل"

    facts = [f"وضع عدم الاتصال لنماذج Hugging Face: {on_off(os.environ.get('HF_HUB_OFFLINE') == '1')}",
             f"إيقاف قياس الاستخدام في Hugging Face: {on_off(os.environ.get('HF_HUB_DISABLE_TELEMETRY') == '1')}"]
    try:
        from streamlit import config as st_config

        facts.append(f"إيقاف إحصاءات استخدام Streamlit: {on_off(not st_config.get_option('browser.gatherUsageStats'))}")
        addr = st_config.get_option("server.address")
        facts.append(f"التطبيق مربوط بالعنوان {addr} فقط" if addr else "عنوان التطبيق غير مقيَّد")
    except Exception:  # noqa: BLE001 - outside a Streamlit runtime
        pass
    return facts


def why_it_works(analysis, result, golden_scores: dict | None) -> list[dict]:
    """Five rows: root cause -> Nazeer component -> live metric from this session.
    `metric` is the short headline (None = not measured yet), `detail` one line under it."""
    rep = result.report if result is not None else None
    rows = []

    # 1. realistic data
    if rep and rep["mode"] == "synthetic" and rep.get("utility", {}).get("max_auc_drop") is not None:
        u = rep["utility"]
        best = max(u["models"].values(), key=lambda m: m["real"]["auc"] or 0)
        metric = f"انخفاض AUC ‏{u['max_auc_drop']:.4f}"
        detail = (f"نموذج مدرَّب على الحقيقي {best['real']['auc']:.3f} ومدرَّب على النظير {best['twin']['auc']:.3f}، "
                  "واختُبر الاثنان على بيانات حقيقية لم يرها أيٌّ منهما")
    elif result is not None and not result.twin_withheld and rep["mode"] == "masked":
        tot = twin_totals(analysis, result)
        rows_twin = sum(t["rows_twin"] for t in tot["tables"])
        metric = "مطابقة 100%" if tot["all_same"] else "يوجد فرق"
        detail = f"عدد الصفوف ({rows_twin:,}) والمجاميع والروابط في النظير كما في الأصل"
    else:
        metric, detail = None, "ولّد النظير لقياس ذلك"
    rows.append({"cause": "فرق التطوير والتحليل تحتاج بيانات واقعية",
                 "component": "نظير يحافظ على الأعداد والتوزيعات والعلاقات بين الجداول",
                 "metric": metric, "detail": detail})

    # 2. valid, consistent fakes
    if result is not None and not result.twin_withheld:
        val = fake_validity(result, analysis.detections)
        ri = referential_integrity(result, analysis.profile)
        pct = min(val.values()) if val else None
        metric = f"{pct:.0%} صالحة" if pct is not None else "لا أعمدة معرّفات"
        detail = (f"{sum(ri.values())} روابط مكسورة بين الجداول" if ri else "جدول واحد، لا روابط لفحصها")
        detail += " · البدائل تجتاز خوارزميات التحقق الرسمية"
    else:
        metric, detail = None, "ولّد النظير لقياس ذلك"
    rows.append({"cause": "البيانات الوهمية العشوائية تفشل في التحقق وتكسر الروابط",
                 "component": "بدائل صالحة بمفتاح سري: نفس الشخص يأخذ نفس البديل في كل الجداول والنصوص",
                 "metric": metric, "detail": detail})

    # 3. hidden identifiers in Arabic text
    if golden_scores:
        n, b = golden_scores["nazeer"], golden_scores["baseline"]
        metric = f"{n['overall_recall']:.1%} مقابل {b['overall_recall']:.1%}"
        detail = "ما وجده نظير مقابل الأداة التقليدية من المعرّفات المزروعة في ملاحظات العرض"
    else:
        metric = f"{len(analysis.spans):,} مقابل {len(analysis.baseline_spans):,}"
        detail = "ما علّمه نظير مقابل الأداة التقليدية (لا يوجد مفتاح إجابة لهذه البيانات)"
    rows.append({"cause": "المعرّفات تختبئ في النص العربي: أرقام عربية، مسافات، ‎+966",
                 "component": "توحيد الأرقام مع خريطة للمواضع، ثم تحقق رسمي، ثم كشف الأسماء العربية",
                 "metric": metric, "detail": detail})

    # 4. Saudi context, local
    rows.append({"cause": "الأدوات العامة لا تعرف الصيغ السعودية وتعتمد غالباً على السحابة",
                 "component": "مدقّقات ومولّدات سعودية، ويعمل بالكامل على هذا الجهاز",
                 "metric": f"{len(SAUDI_TYPES)} أنواع سعودية",
                 "detail": "، ".join(SAUDI_TYPES) + " · " + " · ".join(local_only_facts())})

    # 5. evidence
    if rep:
        leaks = sum(rep["leak_scan"]["leaked_by_kind"].values())
        metric = "ناجح PASS" if rep["verdict"] == "PASS" else "راسب FAIL"
        detail = f"{leaks} معرّفاً أصلياً في النظير، بعد فحص {rep['leak_scan']['cells_scanned']:,} خلية"
    else:
        metric, detail = None, "ولّد النظير للحصول على التقرير"
    rows.append({"cause": "مسؤول حماية البيانات لا يملك دليلاً على أن النسخة آمنة",
                 "component": "تقرير إثبات بنتيجة ناجح أو راسب: تسريب، نسخ مطابقة، خطر التعرّف، الفائدة",
                 "metric": metric, "detail": detail})
    return rows
