"""k-anonymity over quasi-identifier columns, plus fix suggestions when k < k_min.

Suggestions (and combinations of them), each with before/after k:
  * widen_<col>       : numeric bins twice as wide ("30-39" -> "20-39")
  * <col>_to_region   : Saudi city -> administrative region
  * suppress          : quasi values of rows in too-small classes become "*"
Nothing is applied automatically; the user (UI) or `--apply-fix` (CLI) chooses.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import asdict, dataclass, field

import pandas as pd

from nazeer.saudi_ids import normalize_name

SUPPRESSED = "*"
_BIN = re.compile(r"^(\d+)-(\d+)$")

# The 13 administrative regions. Keys are matched with normalize_name.
_REGIONS = {
    "منطقة الرياض": ["الرياض", "الخرج", "الدوادمي", "المجمعة", "وادي الدواسر"],
    "منطقة مكة المكرمة": ["مكة المكرمة", "مكة", "جدة", "الطائف", "رابغ", "القنفذة", "الليث"],
    "منطقة المدينة المنورة": ["المدينة المنورة", "المدينة", "ينبع", "العلا", "بدر"],
    "المنطقة الشرقية": ["الدمام", "الخبر", "الظهران", "الأحساء", "الهفوف", "الجبيل", "القطيف", "حفر الباطن", "رأس تنورة"],
    "منطقة القصيم": ["بريدة", "عنيزة", "الرس"],
    "منطقة عسير": ["أبها", "خميس مشيط", "بيشة", "محايل عسير"],
    "منطقة تبوك": ["تبوك", "الوجه", "ضباء"],
    "منطقة حائل": ["حائل"],
    "منطقة الحدود الشمالية": ["عرعر", "رفحاء", "طريف"],
    "منطقة جازان": ["جازان", "صبيا", "أبو عريش"],
    "منطقة نجران": ["نجران", "شرورة"],
    "منطقة الباحة": ["الباحة"],
    "منطقة الجوف": ["سكاكا", "القريات", "دومة الجندل"],
}
CITY_TO_REGION = {normalize_name(c): region for region, cities in _REGIONS.items() for c in cities}


@dataclass
class KResult:
    k: int                 # size of the smallest equivalence class (0 for an empty table)
    n_classes: int
    rows_in_small_classes: int
    k_min: int

    @property
    def passed(self) -> bool:
        return self.k >= self.k_min


@dataclass
class Fix:
    name: str
    description: str
    ops: list[tuple[str, str]] = field(default_factory=list)  # (column, op)
    k_before: int = 0
    k_after: int = 0
    rows_affected: int = 0
    reaches_k_min: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def k_anonymity(df: pd.DataFrame, quasi_cols: list[str], k_min: int) -> KResult:
    if df.empty or not quasi_cols:
        return KResult(k=len(df), n_classes=1 if len(df) else 0, rows_in_small_classes=0, k_min=k_min)
    sizes = df[quasi_cols].astype(str).value_counts(dropna=False)
    return KResult(k=int(sizes.min()), n_classes=int(len(sizes)),
                   rows_in_small_classes=int(sizes[sizes < k_min].sum()), k_min=k_min)


def _is_bin_column(s: pd.Series) -> bool:
    vals = s.dropna().astype(str)
    return len(vals) > 0 and vals.str.match(_BIN).mean() > 0.95


def _is_city_column(s: pd.Series) -> bool:
    vals = s.dropna().astype(str)
    return len(vals) > 0 and vals.map(lambda v: normalize_name(v) in CITY_TO_REGION).mean() > 0.8


def _widen(s: pd.Series) -> pd.Series:
    def one(v):
        m = _BIN.match(str(v)) if v is not None else None
        if not m:
            return v
        lo, hi = int(m.group(1)), int(m.group(2))
        width = (hi - lo + 1) * 2
        new_lo = lo // width * width
        return f"{new_lo}-{new_lo + width - 1}"
    return s.map(one)


def _to_region(s: pd.Series) -> pd.Series:
    return s.map(lambda v: CITY_TO_REGION.get(normalize_name(str(v)), v) if isinstance(v, str) else v)


def _suppress(df: pd.DataFrame, quasi_cols: list[str], k_min: int) -> tuple[pd.DataFrame, int]:
    out = df.copy()
    keys = out[quasi_cols].astype(str).apply(tuple, axis=1)
    sizes = keys.map(keys.value_counts())
    order = sizes.sort_values(kind="stable")
    small = sizes < k_min
    n = int(small.sum())
    if 0 < n < k_min:
        # The "*" class must itself reach k_min: pull in rows from the next-smallest classes.
        extra = order[~small.loc[order.index]].index[: k_min - n]
        small.loc[extra] = True
        n = int(small.sum())
    out.loc[small, quasi_cols] = SUPPRESSED
    return out, n


def _apply_ops(df: pd.DataFrame, ops: list[tuple[str, str]], quasi_cols: list[str], k_min: int) -> tuple[pd.DataFrame, int]:
    out = df.copy()
    affected = 0
    for col, op in ops:
        if op == "widen":
            out[col] = _widen(out[col])
        elif op == "region":
            out[col] = _to_region(out[col])
        elif op == "suppress":
            out, affected = _suppress(out, quasi_cols, k_min)
    return out, affected


def suggest_fixes(df: pd.DataFrame, quasi_cols: list[str], k_min: int) -> list[Fix]:
    """Candidate fixes, best first: reaching k_min, then fewest suppressed rows, then fewest steps."""
    before = k_anonymity(df, quasi_cols, k_min)
    generalizations = [(c, "widen") for c in quasi_cols if _is_bin_column(df[c])]
    generalizations += [(c, "region") for c in quasi_cols if _is_city_column(df[c])]
    candidates: list[list[tuple[str, str]]] = []
    for r in range(1, len(generalizations) + 1):
        candidates += [list(combo) for combo in itertools.combinations(generalizations, r)]
    candidates = candidates + [c + [("*", "suppress")] for c in candidates] + [[("*", "suppress")]]

    fixes = []
    for ops in candidates:
        fixed, affected = _apply_ops(df, ops, quasi_cols, k_min)
        after = k_anonymity(fixed, quasi_cols, k_min)
        fixes.append(Fix(
            name="+".join(f"{op}_{col}" if op != "suppress" else "suppress" for col, op in ops),
            description=" then ".join(_describe(col, op) for col, op in ops),
            ops=ops, k_before=before.k, k_after=after.k, rows_affected=affected,
            reaches_k_min=after.passed,
        ))
    fixes.sort(key=lambda f: (not f.reaches_k_min, f.rows_affected, len(f.ops), -f.k_after))
    return fixes


def apply_fix(df: pd.DataFrame, fix: Fix, quasi_cols: list[str], k_min: int) -> pd.DataFrame:
    return _apply_ops(df, fix.ops, quasi_cols, k_min)[0]


def _describe(col: str, op: str) -> str:
    return {
        "widen": f"widen {col} bins to double width",
        "region": f"generalize {col} to administrative region",
        "suppress": "replace quasi-identifiers of rows in small classes with '*'",
    }[op]
