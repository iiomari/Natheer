"""Independent proof: compare what Nazeer found (and replaced) with an answer key.

Answer key format (CSV, UTF-8, one row per planted value; header names in English or Arabic):
    row          1-based data row in the source file (used when file_id is empty)
    file_id      the record's id value in the source file (preferred: survives duplicate removal)
    column       the column the value was planted in
    type         SAUDI_ID | MOBILE | IBAN | EMAIL | PERSON_NAME   (Arabic labels accepted)
    planted_value
    expected     replace | review | ignore   (look-alikes are "review" or "ignore")

Everything here runs in memory on the session's data; results are counts only.
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

TYPES = ("SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME")
_TYPE_ALIASES = {
    "saudi_id": "SAUDI_ID", "national_id": "SAUDI_ID", "id": "SAUDI_ID", "هوية": "SAUDI_ID", "الهوية": "SAUDI_ID",
    "رقم الهوية": "SAUDI_ID", "هوية / إقامة": "SAUDI_ID", "mobile": "MOBILE", "phone": "MOBILE", "جوال": "MOBILE",
    "الجوال": "MOBILE", "iban": "IBAN", "آيبان": "IBAN", "ايبان": "IBAN", "email": "EMAIL", "بريد": "EMAIL",
    "البريد": "EMAIL", "person_name": "PERSON_NAME", "name": "PERSON_NAME", "اسم": "PERSON_NAME", "الاسم": "PERSON_NAME",
}
_EXPECTED_ALIASES = {
    "replace": "replace", "replaced": "replace", "mask": "replace", "استبدال": "replace", "يستبدل": "replace",
    "review": "review", "مراجعة": "review", "للمراجعة": "review",
    "ignore": "ignore", "keep": "ignore", "تجاهل": "ignore", "يترك": "ignore", "إبقاء": "ignore",
}
_HEADERS = {
    "row": ("row", "الصف", "رقم الصف", "row_number"),
    "file_id": ("file_id", "file id", "id", "record_id", "رقم الملف", "المعرف", "المعرّف"),
    "column": ("column", "العمود"),
    "type": ("type", "kind", "النوع"),
    "planted_value": ("planted_value", "planted value", "value", "القيمة", "القيمة المزروعة"),
    "expected": ("expected", "المتوقع", "النتيجة المتوقعة"),
}
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ALEF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})


class AnswerKeyError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Entry:
    row: int | None
    file_id: str
    column: str
    type: str
    value: str
    expected: str


def _norm_header(h: str) -> str:
    return re.sub(r"[\s_]+", " ", str(h).replace("﻿", "").strip().lower())


def load_key(data: bytes) -> list[Entry]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1256")
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        raise AnswerKeyError("answer_key_empty")
    head = [_norm_header(h) for h in rows[0]]
    idx = {}
    for field, names in _HEADERS.items():
        idx[field] = next((head.index(_norm_header(n)) for n in names if _norm_header(n) in head), None)
    if idx["column"] is None or idx["type"] is None or idx["planted_value"] is None:
        raise AnswerKeyError("answer_key_columns")
    out = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        get = lambda f: (r[idx[f]].strip() if idx[f] is not None and idx[f] < len(r) else "")  # noqa: E731
        t = get("type")
        kind = t.upper() if t.upper() in TYPES else _TYPE_ALIASES.get(t.strip().lower())
        exp = _EXPECTED_ALIASES.get(get("expected").lower(), "replace" if not get("expected") else None)
        if kind is None or exp is None:
            raise AnswerKeyError("answer_key_values")
        row = get("row")
        out.append(Entry(int(row) if row.isdigit() else None, get("file_id"), get("column"), kind, get("planted_value"), exp))
    if not out:
        raise AnswerKeyError("answer_key_empty")
    return out


# ---------------------------------------------------------------- matching

def _digits(v: str) -> str:
    return re.sub(r"\D", "", str(v).translate(_AR_DIGITS))


def core(kind: str, value: str) -> str:
    """The part of a value that must disappear when it is replaced."""
    v = str(value).translate(_AR_DIGITS)
    if kind == "MOBILE":
        d = _digits(v)
        return d[-9:] if len(d) >= 9 else d
    if kind == "SAUDI_ID":
        return _digits(v)
    if kind == "IBAN":
        return _digits(v)[-22:]
    if kind == "PERSON_NAME":
        return re.sub(r"\s+", " ", v.translate(_ALEF)).strip()
    return v.strip().lower()


def _present(kind: str, value: str, cell) -> bool:
    if not isinstance(cell, str) or not cell:
        return False
    c = core(kind, value)
    if not c:
        return False
    if kind in ("MOBILE", "SAUDI_ID", "IBAN"):
        return c in _digits(cell)
    if kind == "PERSON_NAME":
        return c in re.sub(r"\s+", " ", cell.translate(_ALEF))
    return c in cell.lower()


def _col(df: pd.DataFrame, name: str) -> str | None:
    want = re.sub(r"[\s_]+", "_", name.strip())
    return next((c for c in df.columns if re.sub(r"[\s_]+", "_", str(c).strip()) == want), None)


def _locate(tables: dict[str, pd.DataFrame], e: Entry) -> tuple[str, int, str] | None:
    """(table, positional row, column) of an entry in the (cleaned) tables."""
    for t, df in tables.items():
        col = _col(df, e.column)
        if col is None:
            continue
        if e.file_id:
            for c in df.columns:
                hits = [i for i, v in enumerate(df[c].tolist()) if isinstance(v, str) and v.strip() == e.file_id]
                if hits:
                    return t, hits[0], col
        elif e.row is not None and 0 < e.row <= len(df):
            return t, e.row - 1, col
    return None


def evaluate(tables: dict[str, pd.DataFrame], detections, spans, entries: list[Entry],
             twin: dict[str, pd.DataFrame] | None = None, review_below: float = 0.7) -> dict:
    """Per type: planted / found / replaced / missed for values that must be replaced, and how the
    look-alikes ended (ignored, sent to review, wrongly treated as identifiers). Counts only."""
    col_det = {(d.table, d.column): d for d in detections}
    by_cell: dict[tuple[str, int, str], list] = defaultdict(list)
    for sp in spans:
        by_cell[(sp.table, sp.row, sp.column)].append(sp)

    def hit(t, row, col, kind, value):
        """(detected?, confidence) for a planted value."""
        cell = tables[t][col].iat[row]
        d = col_det.get((t, col))
        if d is not None and d.tag == "DIRECT_ID" and d.kind == kind:
            return True, 1.0 if not d.needs_review else 0.6
        best = None
        for sp in by_cell.get((t, row, col), []):
            if isinstance(cell, str) and _present(kind, value, cell[sp.start:sp.end]):
                best = max(best or 0, sp.confidence)
        return best is not None, best

    per = {k: {"planted": 0, "found": 0, "replaced": 0, "missed": 0, "not_located": 0} for k in TYPES}
    # Look-alikes. Expected "ignore": ignored, or wrongly replaced. Expected "review": a value a tool
    # must not treat blindly; Nazeer decides it with evidence (kept or replaced) or leaves it to the admin.
    look = {"total": 0, "ignored": 0, "review": 0, "review_kept": 0, "review_replaced": 0, "wrong": 0,
            "not_located": 0}
    for e in entries:
        loc = _locate(tables, e)
        if e.expected == "replace":
            p = per[e.type]
            p["planted"] += 1
            if loc is None:
                p["not_located"] += 1
                p["missed"] += 1
                continue
            t, row, col = loc
            found, conf = hit(t, row, col, e.type, e.value)
            replaced = None
            if twin is not None and t in twin and col in twin[t].columns:
                replaced = not _present(e.type, e.value, twin[t][col].iat[row])
            p["found"] += found
            if twin is not None:
                p["replaced"] += bool(replaced)
                p["missed"] += not replaced
            else:
                p["missed"] += not found
        else:
            look["total"] += 1
            if loc is None:
                look["not_located"] += 1
                continue
            t, row, col = loc
            found, conf = hit(t, row, col, e.type, e.value)
            kept = True
            if twin is not None and t in twin and col in twin[t].columns:
                kept = _present(e.type, e.value, twin[t][col].iat[row])
            if e.expected == "review" and found and (conf or 0) < review_below:
                look["review"] += 1
                look["review_kept" if kept else "review_replaced"] += 1
            elif not found and kept:
                look["ignored"] += 1
            elif found and kept and (conf or 0) < review_below:
                look["review"] += 1
                look["review_kept"] += 1
            else:
                look["wrong"] += 1
    for p in per.values():
        base = p["planted"]
        done = p["replaced"] if twin is not None else p["found"]
        p["recall"] = round(done / base, 4) if base else None
    return {"types": {k: v for k, v in per.items() if v["planted"]}, "look_alikes": look,
            "measured": "replaced" if twin is not None else "found"}
