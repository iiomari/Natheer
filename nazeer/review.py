"""Decisions on free-text values the detector is unsure of (e.g. a checksum-valid number after
"رقم الطلب"): Nazeer decides most of them from evidence; the admin decides the rest.

Groups: uncertain values are grouped by (table, column, context phrase), the phrase being the one or
two words just before the number ("رقم الطلب", "رقم الوثيقة").

Group statistics (Saudi ID / iqama numbers): every ID-shaped number (10 digits starting with 1 or 2)
that follows the same phrase in the same column is counted, including the ones that fail the
check digit (the detector silently rejects those). A random number passes the check digit with
probability 1/10; real ID numbers pass 100%.

    n < MIN_GROUP (10)                                  -> too few to judge: ask the admin
    one-sided binomial P(X >= k | n, 0.10) >= 0.01      -> consistent with chance: not IDs, KEEP
    95% one-sided lower bound of k/n >= 0.80            -> IDs, REPLACE
    otherwise                                           -> mixed: ask the admin
    (suggestion for the admin: replace if k/n >= 0.5, else keep)

Cross-check, per value, before the group rule: a number equal to a value of a detected ID column is
an ID (replace); a number equal to a value of a non-personal column (an order or policy number
column) is a reference (keep). An IBAN shape with a failing checksum is always an account number
(replace).

Admin overrides: per value > per group > automatic. Nothing undecided is replaced: it stays as is and
blocks sharing until decided. Everything returned here is value-free (positions, counts, phrases).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd
from scipy.stats import beta, binom

from nazeer import saudi_ids as s

CHANCE = 0.10          # P(random 10-digit number starting with 1/2 passes the check digit)
MIN_GROUP = 10         # fewer ID-shaped numbers than this: too few to judge
ALPHA_CHANCE = 0.01    # binomial p-value above which the pass rate is consistent with chance
ID_LOWER_BOUND = 0.80  # 95% lower bound of the pass rate above which the numbers are IDs
REVIEW_BELOW = 0.7     # = detect.SPAN_REVIEW_BELOW

_WORD = re.compile(r"[A-Za-z؀-ۿ]+")
_TEN = re.compile(r"(?<!\d)[12]\d{9}(?!\d)")


def phrase_before(text: str, start: int) -> str:
    """The one or two words just before position `start` (normalized), "" if none."""
    before = text[max(0, start - 40):start]
    words = _WORD.findall(before)
    tail = before[before.rfind(words[-1]) + len(words[-1]):] if words else ""
    if not words or len(tail.strip(" :#-/()،,.")) > 0:
        return ""
    return s.normalize_name(" ".join(words[-2:]))


@dataclass
class Group:
    key: str
    table: str
    column: str
    phrase: str
    kind: str
    values: list = field(default_factory=list)     # [(row, start, end)] candidates in this group
    population: int = 0
    passed: int = 0
    auto: str | None = None                         # "keep" | "replace" | None
    suggestion: str = "keep"
    reason: dict = field(default_factory=dict)


def _id_shaped_after(tables, table: str, column: str, phrase: str) -> tuple[int, int]:
    n = k = 0
    for v in tables[table][column].tolist():
        if not isinstance(v, str) or not v:
            continue
        norm, offsets = s.normalize(v)
        for m in _TEN.finditer(norm):
            a = offsets[m.start()]
            if phrase_before(v, a) == phrase:
                n += 1
                k += s.is_valid("SAUDI_ID", m.group())
    return n, k


def _decide(n: int, k: int) -> tuple[str | None, str, dict]:
    if n < MIN_GROUP:
        return None, ("replace" if n and k / n >= 0.5 else "keep"), {"code": "too_few", "n": n, "k": k}
    p_chance = float(binom.sf(k - 1, n, CHANCE))
    lower = float(beta.ppf(0.05, k, n - k + 1)) if k > 0 else 0.0
    if p_chance >= ALPHA_CHANCE:
        return "keep", "keep", {"code": "chance", "n": n, "k": k, "p": round(p_chance, 4)}
    if lower >= ID_LOWER_BOUND:
        return "replace", "replace", {"code": "ids", "n": n, "k": k, "lower": round(lower, 3)}
    return None, ("replace" if k / n >= 0.5 else "keep"), {"code": "mixed", "n": n, "k": k}


def _column_values(tables, detections) -> tuple[dict[str, set], dict[str, set]]:
    """{column label: canonical digit strings} for detected ID columns, and for non-personal columns."""
    ids, refs = {}, {}
    for d in detections:
        if d.tag == "FREE_TEXT":
            continue
        vals = {re.sub(r"\D", "", s.normalize(str(v))[0]) for v in tables[d.table][d.column].dropna().tolist()}
        vals.discard("")
        label = f"{d.table}.{d.column}"
        if d.tag == "DIRECT_ID" and d.kind == "SAUDI_ID":
            ids[label] = vals
        elif d.tag != "DIRECT_ID":
            refs[label] = vals
    return ids, refs


def groups_for(tables: dict[str, pd.DataFrame], spans, detections) -> list[Group]:
    """Group the uncertain spans and decide each group automatically where the evidence allows."""
    by_key: dict[str, Group] = {}
    for sp in spans:
        if sp.confidence >= REVIEW_BELOW:
            continue
        text = tables[sp.table][sp.column].iat[sp.row]
        phrase = phrase_before(text, sp.start)
        key = f"{sp.table}|{sp.column}|{sp.type}|{phrase}"
        g = by_key.get(key)
        if g is None:
            g = by_key[key] = Group(key, sp.table, sp.column, phrase, sp.type)
        g.values.append((sp.row, sp.start, sp.end))
    for g in by_key.values():
        if g.kind == "SAUDI_ID":
            g.population, g.passed = _id_shaped_after(tables, g.table, g.column, g.phrase)
            g.auto, g.suggestion, g.reason = _decide(g.population, g.passed)
        elif g.kind == "IBAN":
            g.auto, g.suggestion, g.reason = "replace", "replace", {"code": "iban_shape", "n": len(g.values)}
        else:
            g.suggestion, g.reason = "replace", {"code": "unknown", "n": len(g.values)}
    return sorted(by_key.values(), key=lambda g: (-len(g.values), g.key))


def resolve(tables, spans, detections, decisions: dict | None = None) -> tuple[set, dict]:
    """(positions to replace {(table, column, row, start)}, value-free summary).
    decisions = {"groups": {key: "keep"|"replace"}, "values": {key: {"row:start": "keep"|"replace"}}}."""
    decisions = decisions or {}
    by_group, by_value = decisions.get("groups") or {}, decisions.get("values") or {}
    ids, refs = _column_values(tables, detections)
    replace: set = set()
    out_groups, totals = [], {"auto": 0, "admin": 0, "pending": 0, "replace": 0, "keep": 0}
    for g in groups_for(tables, spans, detections):
        rows = []
        for row, start, end in g.values:
            text = tables[g.table][g.column].iat[row]
            digits = re.sub(r"\D", "", s.normalize(text[start:end])[0])
            auto, why = g.auto, dict(g.reason)
            hit_id = next((c for c, vals in ids.items() if digits in vals), None)
            hit_ref = next((c for c, vals in refs.items() if digits in vals), None) if not hit_id else None
            if hit_id:
                auto, why = "replace", {"code": "matches_id_column", "column": hit_id}
            elif hit_ref:
                auto, why = "keep", {"code": "matches_reference_column", "column": hit_ref}
            admin = (by_value.get(g.key) or {}).get(f"{row}:{start}") or by_group.get(g.key)
            final = admin or auto or "pending"
            by = "admin" if admin else ("auto" if auto else "pending")
            totals[by] += 1
            if final in ("keep", "replace"):
                totals[final] += 1
            if final == "replace":
                replace.add((g.table, g.column, row, start))
            rows.append({"row": row, "start": start, "end": end, "auto": auto, "reason": why,
                         "admin": admin, "final": final})
        finals = {r["final"] for r in rows}
        out_groups.append({
            "key": g.key, "table": g.table, "column": g.column, "phrase": g.phrase, "kind": g.kind,
            "count": len(rows), "population": g.population, "passed": g.passed, "auto": g.auto,
            "suggestion": g.suggestion, "reason": g.reason, "admin": by_group.get(g.key),
            "final": finals.pop() if len(finals) == 1 else "mixed",
            "pending": sum(r["final"] == "pending" for r in rows), "values": rows})
    return replace, {"groups": out_groups, "totals": totals,
                     "rule": {"chance": CHANCE, "min_group": MIN_GROUP, "alpha": ALPHA_CHANCE,
                              "id_lower_bound": ID_LOWER_BOUND}}


def refresh(summary: dict, decisions: dict | None) -> dict:
    """Re-apply admin decisions to a stored (value-free) summary without re-running detection."""
    decisions = decisions or {}
    by_group, by_value = decisions.get("groups") or {}, decisions.get("values") or {}
    totals = {"auto": 0, "admin": 0, "pending": 0, "replace": 0, "keep": 0}
    groups = []
    for g in summary.get("groups", []):
        rows = []
        for v in g["values"]:
            admin = (by_value.get(g["key"]) or {}).get(f"{v['row']}:{v['start']}") or by_group.get(g["key"])
            final = admin or v["auto"] or "pending"
            by = "admin" if admin else ("auto" if v["auto"] else "pending")
            totals[by] += 1
            if final in ("keep", "replace"):
                totals[final] += 1
            rows.append({**v, "admin": admin, "final": final})
        finals = {r["final"] for r in rows}
        groups.append({**g, "values": rows, "admin": by_group.get(g["key"]),
                       "final": finals.pop() if len(finals) == 1 else "mixed",
                       "pending": sum(r["final"] == "pending" for r in rows)})
    return {**summary, "groups": groups, "totals": totals}
