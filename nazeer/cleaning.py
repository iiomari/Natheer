"""Basic, widely agreed data cleaning. Runs BEFORE detection and twin generation.

Every rule is a toggle with a safe default and reports how many cells (or rows) it changed. Rules
never change meaning silently:

ON by default
  trim      trim, collapse repeated spaces, remove invisible characters (zero-width, BOM, bidi
            marks, NBSP -> space)
  nulls     whole cells equal to "", NULL, null, N/A, NA, - ... become empty (never text inside notes)
  numbers   numbers stored as text in NUMERIC columns -> plain ASCII ("١٬٢٣٤٫٥" -> "1234.5").
            Skipped for columns with leading zeros or that validate as identifiers (IDs, mobiles).
  dates     a column that is confidently a date -> ISO yyyy-mm-dd. Ambiguous day/month orders
            (every value fits both dd/mm and mm/dd) are left alone and reported.
  dedupe    exact duplicate rows removed (reported per table)
OFF by default (user opts in)
  arabic    normalize Arabic letters in categorical columns (أ/إ/آ->ا, ى->ي, ة->ه, no tashkeel or
            tatweel). Never on name columns.
  phones    unify Saudi mobile formats in mobile columns to 05XXXXXXXX
  merges    unify category variants: only the suggestions the user approved (by key, never by value)
REPORT ONLY (never fixed): missing values per column, extreme numeric outliers, mixed-type columns.

Counts and option flags are value-free; before/after examples (examples()) contain values and are
only ever produced on request, from the originals, during the processing session.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date

import pandas as pd

from nazeer import saudi_ids as s

RULES_ON = ("trim", "nulls", "numbers", "dates", "dedupe")
RULES_OFF = ("arabic", "phones")
NULL_LIKE = {"", "null", "n/a", "na", "-", "--", "none", "nan", "nil", "#n/a", "لا يوجد"}
_INVISIBLE = re.compile(r"[​-‏‪-‮⁦-⁩﻿؜]")
_SPACES = re.compile(r"[ \t  -   　]+")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_NUMBER = re.compile(r"^[+-]?(\d+|\d{1,3}([,٬]\d{3})+)([.٫]\d+)?$")
_DATE = re.compile(r"^(\d{1,4})[-/.](\d{1,2})[-/.](\d{1,4})$")
_TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")


@dataclass
class CleanOptions:
    trim: bool = True
    nulls: bool = True
    numbers: bool = True
    dates: bool = True
    dedupe: bool = True
    arabic: bool = False
    phones: bool = False
    merges: list[str] = field(default_factory=list)  # approved suggestion keys "table.column#n"

    @classmethod
    def from_dict(cls, d: dict | None) -> "CleanOptions":
        d = d or {}
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- per-value transforms

def _trim(v: str) -> str:
    return _SPACES.sub(" ", _INVISIBLE.sub("", v)).strip()


def _number(v: str) -> str:
    t = v.translate(_DIGITS).replace("٬", "").replace(",", "").replace("٫", ".")
    if t.startswith("+"):
        t = t[1:]
    return t


def arabic_normalize(v: str) -> str:
    v = _TASHKEEL.sub("", v)
    return v.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه"}))


# ---------------------------------------------------------------- column tests

def _values(col: pd.Series) -> pd.Series:
    return col.dropna().astype(str)


def numeric_column(col: pd.Series) -> bool:
    v = _values(col)
    if len(v) == 0:
        return False
    norm = v.str.translate(_DIGITS) if hasattr(v.str, "translate") else v.map(lambda x: x.translate(_DIGITS))
    if norm.map(lambda x: bool(_NUMBER.match(x))).mean() < 0.98:
        return False
    if norm.map(lambda x: len(x) > 1 and x[0] == "0" and x[1].isdigit()).any():
        return False  # leading zeros: an identifier or code, not a quantity
    sample = v.head(200)
    for kind in ("SAUDI_ID", "MOBILE", "IBAN"):
        if sample.map(lambda x, k=kind: s.is_valid(k, x)).mean() > 0.5:
            return False
    return True


def _date_parts(v: str):
    m = _DATE.match(v.translate(_DIGITS))
    return tuple(int(x) for x in m.groups()) if m else None


def _valid(y, mth, d) -> bool:
    try:
        date(y, mth, d)
        return 1000 <= y <= 2999
    except ValueError:
        return False


def date_order(col: pd.Series) -> str | None:
    """'ymd' | 'dmy' | 'mdy' if every value parses under exactly one order; 'ambiguous' if several
    orders fit every value; None if the column is not a date column."""
    v = _values(col)
    if len(v) == 0:
        return None
    parts = v.map(_date_parts)
    if parts.isna().mean() > 0.05 or parts.dropna().empty:
        return None
    parts = parts.dropna()
    fits = {
        "ymd": all(_valid(a, b, c) for a, b, c in parts),
        "dmy": all(_valid(c, b, a) for a, b, c in parts),
        "mdy": all(_valid(c, a, b) for a, b, c in parts),
    }
    ok = [k for k, f in fits.items() if f]
    if not ok:
        return None
    return ok[0] if len(ok) == 1 else "ambiguous"


def _to_iso(v: str, order: str) -> str:
    p = _date_parts(v)
    if p is None:
        return v
    a, b, c = p
    y, mth, d = {"ymd": (a, b, c), "dmy": (c, b, a), "mdy": (c, a, b)}[order]
    return f"{y:04d}-{mth:02d}-{d:02d}"


def mobile_column(col: pd.Series) -> bool:
    v = _values(col).head(300)
    return len(v) > 0 and v.map(lambda x: s.is_valid("MOBILE", x)).mean() >= 0.8


def categorical_column(col: pd.Series) -> bool:
    v = _values(col)
    return 0 < v.nunique() <= max(20, int(0.05 * len(col))) and v.str.len().mean() < 40


def name_column(col: pd.Series) -> bool:
    v = _values(col).head(300)
    return len(v) > 0 and v.map(lambda x: s.is_known_name(x.split()[0]) if x.split() else False).mean() >= 0.5


# ---------------------------------------------------------------- suggestions

def category_suggestions(tables: dict[str, pd.DataFrame]) -> list[dict]:
    """Groups of spellings that only differ by spacing, case or Arabic letter forms.
    Returns dicts with values (to show the user during the session); key is value-free."""
    out = []
    for t, df in tables.items():
        for c in df.columns:
            col = df[c]
            if not categorical_column(col) or name_column(col):
                continue
            counts = _values(col).map(_trim).value_counts()
            groups: dict[str, list[tuple[str, int]]] = {}
            for raw, n in counts.items():
                key = arabic_normalize(raw).lower().replace(" ", "")
                groups.setdefault(key, []).append((raw, int(n)))
            n_group = 0
            for variants in groups.values():
                if len(variants) < 2:
                    continue
                variants.sort(key=lambda x: (-x[1], x[0]))
                out.append({"key": f"{t}.{c}#{n_group}", "table": t, "column": c, "to": variants[0][0],
                            "from": [v for v, _ in variants[1:]], "rows": sum(n for _, n in variants[1:])})
                n_group += 1
    return out


# ---------------------------------------------------------------- report only

def report_only(tables: dict[str, pd.DataFrame]) -> list[dict]:
    out = []
    for t, df in tables.items():
        for c in df.columns:
            col = df[c]
            n = len(col)
            missing = int(col.isna().sum())
            v = _values(col)
            nums = pd.to_numeric(v.map(lambda x: x.translate(_DIGITS)), errors="coerce")
            share = float(nums.notna().mean()) if len(v) else 0.0
            outliers = 0
            if share >= 0.98 and nums.notna().sum() >= 20 and numeric_column(col):  # never on identifiers
                q1, q3 = nums.quantile(0.25), nums.quantile(0.75)
                iqr = q3 - q1
                if iqr > 0:
                    outliers = int(((nums < q1 - 3 * iqr) | (nums > q3 + 3 * iqr)).sum())
            mixed = 0.2 <= share < 0.95
            if missing or outliers or mixed:
                out.append({"table": t, "column": c, "missing": missing, "missing_share": round(missing / n, 3) if n else 0,
                            "extreme_outliers": outliers, "mixed_types": mixed})
    return out


# ---------------------------------------------------------------- apply

def _apply_one(tables: dict, rule: str, opts: CleanOptions, suggestions: list[dict],
               record: dict, ambiguous: list[str]) -> dict:
    out = {}
    for t, df in tables.items():
        df = df.copy()
        if rule == "dedupe":
            before = len(df)
            df = df.drop_duplicates().reset_index(drop=True)
            record[t] = record.get(t, 0) + (before - len(df))
            out[t] = df
            continue
        for c in df.columns:
            col = df[c]
            mask = col.notna()
            if rule == "trim":
                new = col.where(~mask, col[mask].astype(str).map(_trim))
            elif rule == "nulls":
                new = col.where(~mask | ~col.astype(str).str.strip().str.lower().isin(NULL_LIKE), None)
            elif rule == "numbers":
                if not numeric_column(col):
                    continue
                new = col.where(~mask, col[mask].astype(str).map(_number))
            elif rule == "dates":
                order = date_order(col)
                if order == "ambiguous":
                    ambiguous.append(f"{t}.{c}")
                    continue
                if order is None:
                    continue
                new = col.where(~mask, col[mask].astype(str).map(lambda x, o=order: _to_iso(x, o)))
            elif rule == "arabic":
                if not categorical_column(col) or name_column(col):
                    continue
                new = col.where(~mask, col[mask].astype(str).map(arabic_normalize))
            elif rule == "phones":
                if not mobile_column(col):
                    continue
                new = col.where(~mask, col[mask].astype(str).map(
                    lambda x: "0" + s.canonical("MOBILE", x) if s.is_valid("MOBILE", x) else x))
            elif rule == "merges":
                chosen = [g for g in suggestions if g["key"] in opts.merges and g["table"] == t and g["column"] == c]
                if not chosen:
                    continue
                mapping = {f: g["to"] for g in chosen for f in g["from"]}
                new = col.where(~mask, col[mask].astype(str).map(lambda x, mp=mapping: mp.get(_trim(x), x)))
            else:
                raise ValueError(rule)
            changed = sum(_differs(a, b) for a, b in zip(col.tolist(), new.tolist()))
            if changed:
                record[f"{t}.{c}"] = changed
            df[c] = new.astype(object).where(new.notna(), None)
        out[t] = df
    return out


def _isnull(v) -> bool:
    return v is None or (isinstance(v, float) and v != v)


def _differs(a, b) -> bool:
    if _isnull(a) or _isnull(b):
        return _isnull(a) != _isnull(b)
    return a != b


ORDER = ("trim", "nulls", "numbers", "dates", "arabic", "phones", "merges", "dedupe")


def clean(tables: dict[str, pd.DataFrame], opts: CleanOptions | None = None) -> tuple[dict, dict]:
    """(cleaned tables, value-free report). The report holds counts per rule and the options used."""
    opts = opts or CleanOptions()
    suggestions = category_suggestions(tables) if opts.merges else []
    per_rule: dict[str, dict] = {}
    ambiguous: list[str] = []
    for rule in ORDER:
        enabled = bool(opts.merges) if rule == "merges" else getattr(opts, rule)
        if not enabled:
            continue
        record: dict = {}
        tables = _apply_one(tables, rule, opts, suggestions, record, ambiguous)
        per_rule[rule] = record
    report = {
        "options": {k: v for k, v in opts.to_dict().items() if k != "merges"} | {"merges": len(opts.merges)},
        "applied": {r: {"total": int(sum(rec.values())), "by_column": rec} for r, rec in per_rule.items()},
        "ambiguous_dates": sorted(set(ambiguous)),
    }
    return tables, report


def potential(tables: dict[str, pd.DataFrame]) -> dict:
    """How many cells/rows each rule WOULD change on its own (for the toggles). Value-free."""
    out = {}
    for rule in ORDER[:-2] + ("dedupe",):
        if rule == "merges":
            continue
        record: dict = {}
        _apply_one(tables, rule, CleanOptions(**{k: k == rule for k in RULES_ON + RULES_OFF}), [], record, [])
        out[rule] = int(sum(record.values()))
    return out


def examples(tables: dict[str, pd.DataFrame], rule: str, n: int = 5) -> list[dict]:
    """Before/after pairs for one rule (contains values: session-only, never stored)."""
    single = CleanOptions(**{k: k == rule for k in RULES_ON + RULES_OFF})
    record: dict = {}
    after = _apply_one(tables, rule, single, [], record, [])
    out = []
    if rule == "dedupe":
        return [{"table": t, "column": "", "before": f"{n_rows}", "after": ""} for t, n_rows in record.items()][:n]
    for key in record:
        t, c = key.split(".", 1)
        b, a = tables[t][c], after[t][c]
        diff = pd.Series([_differs(x, y) for x, y in zip(b.tolist(), a.tolist())])
        for i in diff[diff].index[: max(1, n - len(out))]:
            out.append({"table": t, "column": c, "before": b.iat[i], "after": a.iat[i]})
        if len(out) >= n:
            break
    return out
