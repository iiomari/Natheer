"""Module 5b: synthetic twin.

The `Synthesizer` protocol is the seam that lets SDV (BUSL-1.1) be replaced later by
our own scipy/numpy implementation: callers only ever see `SynthSchema` (our own
neutral description) and plain DataFrames. Only this module imports SDV.

Rules enforced here:
* the holdout is split off BEFORE anything is fitted (by parent entity, so a
  customer's rows never straddle train and holdout);
* DIRECT_ID, free-text, key and high-cardinality text columns never reach the
  synthesizer; identifiers are filled afterwards by Nazeer's own generators
  (never equal to any original value) and free text from text_templates.py.
"""
from __future__ import annotations

import logging
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal, Protocol

import numpy as np
import pandas as pd

from nazeer import saudi_ids as s
from nazeer.models import ColumnDetection, DatasetProfile
from nazeer.safe_log import route_library_loggers
from nazeer.text_templates import synthetic_note

log = logging.getLogger(__name__)

SdType = Literal["numerical", "categorical", "datetime", "id"]
DATETIME_FORMAT = "%Y-%m-%d"
HIGH_CARDINALITY_RATIO = 0.5


# ---------------------------------------------------------------- the seam

@dataclass
class SynthSchema:
    """Neutral description of what to synthesize (no SDV types)."""
    tables: dict[str, dict[str, SdType]]
    primary_keys: dict[str, str | None] = field(default_factory=dict)
    relationships: list[tuple[str, str, str, str]] = field(default_factory=list)  # parent, pk, child, fk


class Synthesizer(Protocol):
    name: str
    license: str
    seed_note: str

    def fit(self, tables: dict[str, pd.DataFrame], schema: SynthSchema) -> None: ...

    def sample(self, scale: float = 1.0, seed: int | None = None) -> dict[str, pd.DataFrame]: ...


def _sdv_metadata(schema: SynthSchema):
    from sdv.metadata import Metadata

    tables = {}
    for t, cols in schema.tables.items():
        columns = {}
        for c, kind in cols.items():
            columns[c] = {"sdtype": kind, "datetime_format": DATETIME_FORMAT} if kind == "datetime" else {"sdtype": kind}
        entry = {"columns": columns}
        if schema.primary_keys.get(t):
            entry["primary_key"] = schema.primary_keys[t]
        tables[t] = entry
    rels = [{"parent_table_name": p, "parent_primary_key": pk, "child_table_name": c, "child_foreign_key": fk}
            for p, pk, c, fk in schema.relationships]
    return Metadata.load_from_dict({"METADATA_SPEC_VERSION": "V1", "tables": tables, "relationships": rels})


class SdvSingleTable:
    """SDV GaussianCopula (default) or CTGAN on one table."""
    license = "BUSL-1.1 (SDV, copulas, rdt, ctgan)"
    seed_note = "fixed by SDV (no seed parameter; sampling is deterministic per fit)"

    def __init__(self, method: Literal["gaussian_copula", "ctgan"] = "gaussian_copula", **kwargs):
        self.name = f"sdv.{method}"
        self._method, self._kwargs = method, kwargs
        self._model, self._table, self._rows = None, None, 0

    def fit(self, tables: dict[str, pd.DataFrame], schema: SynthSchema) -> None:
        from sdv.single_table import CTGANSynthesizer, GaussianCopulaSynthesizer

        if len(tables) != 1:
            raise ValueError("single-table synthesizer needs exactly one table")
        (self._table, df), = tables.items()
        cls = GaussianCopulaSynthesizer if self._method == "gaussian_copula" else CTGANSynthesizer
        self._model = cls(_sdv_metadata(schema), **self._kwargs)
        route_library_loggers()
        self._model.fit(df)
        self._rows = len(df)

    def sample(self, scale: float = 1.0, seed: int | None = None) -> dict[str, pd.DataFrame]:
        self._model.reset_sampling()
        return {self._table: self._model.sample(num_rows=max(1, int(round(self._rows * scale))))}


class SdvStratifiedCopula:
    """One Gaussian copula per value of the categorical column that drives the numeric
    columns most (largest mean correlation ratio eta^2 on real-train). A plain copula
    models dependence as linear correlation in a latent space and cannot express
    "amount depends on WHICH claim type"; stratifying restores that. Strata smaller
    than `min_rows` are merged into one "other" stratum (no copula on a handful of rows).
    Falls back to a single copula when no column qualifies.
    """
    license = "BUSL-1.1 (SDV, copulas, rdt)"
    seed_note = "fixed by SDV (no seed parameter; sampling is deterministic per fit)"
    name = "sdv.gaussian_copula.stratified"
    OTHER = "__other__"

    def __init__(self, by: str | None = None, min_rows: int = 50, max_categories: int = 12, min_eta2: float = 0.1):
        self.by, self.min_rows, self.max_categories, self.min_eta2 = by, min_rows, max_categories, min_eta2
        self._models: dict[str, tuple[object, int]] = {}
        self._table = None
        self.details: dict = {}

    @staticmethod
    def _eta2(cat: pd.Series, num: pd.Series) -> float:
        num = pd.to_numeric(num, errors="coerce")
        mask = num.notna()
        cat, num = cat[mask], num[mask]
        if len(num) < 2:
            return 0.0
        if (num > 0).all():
            num = np.log(num)
        g = num.groupby(cat)
        ss_between = float((g.count() * (g.mean() - num.mean()) ** 2).sum())
        ss_total = float(((num - num.mean()) ** 2).sum())
        return ss_between / ss_total if ss_total else 0.0

    def _choose(self, df: pd.DataFrame, kinds: dict[str, SdType]) -> tuple[str | None, dict]:
        nums = [c for c, k in kinds.items() if k == "numerical"]
        scores = {}
        for c, k in kinds.items():
            if k == "categorical" and 2 <= df[c].nunique() <= self.max_categories and nums:
                scores[c] = round(float(np.mean([self._eta2(df[c], df[n]) for n in nums])), 4)
        best = max(scores, key=scores.get) if scores else None
        return (best if best and scores[best] >= self.min_eta2 else None), scores

    def fit(self, tables: dict[str, pd.DataFrame], schema: SynthSchema) -> None:
        from sdv.single_table import GaussianCopulaSynthesizer

        (self._table, df), = tables.items()
        kinds = schema.tables[self._table]
        by, scores = (self.by, {}) if self.by else self._choose(df, kinds)
        self.details = {"stratified_by": by, "eta2_by_candidate": scores, "min_rows": self.min_rows}
        if by is None:
            groups = {self.OTHER: df}
        else:
            counts = df[by].value_counts()
            big = [v for v, n in counts.items() if n >= self.min_rows]
            groups = {v: df[df[by] == v] for v in big}
            small = df[~df[by].isin(big)]
            if len(small):
                groups[self.OTHER] = small
            self.details.update(strata=len(groups), merged_small_strata=int(len(counts) - len(big)),
                                smallest_stratum_rows=int(min(len(g) for g in groups.values())))
        for value, part in groups.items():
            sub_kinds = dict(kinds) if value == self.OTHER else {k: v for k, v in kinds.items() if k != by}
            model = GaussianCopulaSynthesizer(_sdv_metadata(SynthSchema(tables={self._table: sub_kinds})))
            route_library_loggers()
            model.fit(part[list(sub_kinds)].reset_index(drop=True))
            self._models[value] = (model, len(part))
        self.by = by

    def sample(self, scale: float = 1.0, seed: int | None = None) -> dict[str, pd.DataFrame]:
        parts = []
        for value, (model, n) in self._models.items():
            model.reset_sampling()
            part = model.sample(num_rows=max(1, int(round(n * scale))))
            if value != self.OTHER:
                part[self.by] = value
            parts.append(part)
        return {self._table: pd.concat(parts, ignore_index=True)}


class SdvMultiTable:
    """SDV HMA for parent/child tables (stretch, M8)."""
    name = "sdv.hma"
    license = "BUSL-1.1 (SDV, copulas, rdt)"
    seed_note = "fixed by SDV (no seed parameter; sampling is deterministic per fit)"

    def __init__(self) -> None:
        self._model = None

    def fit(self, tables: dict[str, pd.DataFrame], schema: SynthSchema) -> None:
        from sdv.multi_table import HMASynthesizer

        self._model = HMASynthesizer(_sdv_metadata(schema), verbose=False)
        route_library_loggers()
        self._model.fit(tables)

    def sample(self, scale: float = 1.0, seed: int | None = None) -> dict[str, pd.DataFrame]:
        return self._model.sample(scale=scale)


METHODS = ("stratified_copula", "gaussian_copula", "ctgan", "hma")


def make_synthesizer(method: str = "stratified_copula", **kwargs) -> Synthesizer:
    if method == "hma":
        return SdvMultiTable()
    if method == "stratified_copula":
        return SdvStratifiedCopula(**kwargs)
    if method in ("gaussian_copula", "ctgan"):
        return SdvSingleTable(method, **kwargs)
    raise ValueError(f"unknown synthesizer {method!r}; choose from {METHODS}")


# ---------------------------------------------------------------- split and view

def parent_table(prof: DatasetProfile, tables: dict[str, pd.DataFrame]) -> str:
    """The table whose rows are the privacy unit: a parent no FK points out of, else the largest."""
    children = {fk.child_table for fk in prof.foreign_keys}
    parents = [fk.parent_table for fk in prof.foreign_keys if fk.parent_table not in children]
    return parents[0] if parents else max(tables, key=lambda t: len(tables[t]))


def split_holdout(tables: dict[str, pd.DataFrame], prof: DatasetProfile, frac: float = 0.2,
                  seed: int = 0) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict]:
    """Split by parent entity; children follow their parent. Done before any fitting."""
    unit = parent_table(prof, tables)
    pk = prof.tables[unit].primary_key
    ids = tables[unit][pk] if pk else pd.Series(range(len(tables[unit])), index=tables[unit].index)
    rng = np.random.default_rng(seed)
    hold_ids = set(rng.choice(ids.to_numpy(), size=int(round(len(ids) * frac)), replace=False))
    train, hold = {}, {}
    in_hold = ids.isin(hold_ids)
    train[unit], hold[unit] = tables[unit][~in_hold].copy(), tables[unit][in_hold].copy()
    for fk in prof.foreign_keys:
        if fk.parent_table == unit and fk.child_table not in train:
            child = tables[fk.child_table]
            mask = child[fk.child_column].isin(hold_ids)
            train[fk.child_table], hold[fk.child_table] = child[~mask].copy(), child[mask].copy()
    for t, df in tables.items():  # unrelated tables: plain row split
        if t not in train:
            mask = pd.Series(rng.random(len(df)) < frac, index=df.index)
            train[t], hold[t] = df[~mask].copy(), df[mask].copy()
    info = {"unit_table": unit, "holdout_fraction": frac, "seed": seed,
            "train_rows": {t: int(len(d)) for t, d in train.items()},
            "holdout_rows": {t: int(len(d)) for t, d in hold.items()}}
    if pk:
        assert set(train[unit][pk]).isdisjoint(hold[unit][pk]), "holdout overlaps training"
    return train, hold, info


@dataclass
class View:
    """A flat analytics table: the largest child joined with its parents."""
    df: pd.DataFrame
    origin: dict[str, tuple[str, str]]  # view column -> (table, column); derived columns -> ("<derived>", desc)
    base_table: str


def build_view(tables: dict[str, pd.DataFrame], prof: DatasetProfile) -> View:
    if not prof.foreign_keys:
        t = max(tables, key=lambda n: len(tables[n]))
        return View(tables[t].copy(), {c: (t, c) for c in tables[t].columns}, t)
    child = max({fk.child_table for fk in prof.foreign_keys}, key=lambda n: len(tables[n]))
    df = tables[child].copy()
    origin = {c: (child, c) for c in df.columns}
    for fk in [f for f in prof.foreign_keys if f.child_table == child]:
        parent = tables[fk.parent_table].rename(columns={fk.parent_column: fk.child_column})
        rename = {c: (c if c not in df.columns else f"{fk.parent_table}_{c}") for c in parent.columns if c != fk.child_column}
        parent = parent.rename(columns=rename)
        df = df.merge(parent, on=fk.child_column, how="left")
        origin.update({new: (fk.parent_table, old) for old, new in rename.items()})
        date_cols = [c for c in tables[child].columns if prof.column(child, c).dtype == "date"]
        prior = f"prior_{child}"
        if date_cols:
            order = pd.to_datetime(df[date_cols[0]], errors="coerce")
            df[prior] = df.assign(_o=order).sort_values([fk.child_column, "_o"]).groupby(fk.child_column).cumcount()
        else:
            df[prior] = df.groupby(fk.child_column).cumcount()
        origin[prior] = ("<derived>", f"earlier {child} rows of the same {fk.parent_table}")
    return View(df, origin, child)


def view_plan(view: View, prof: DatasetProfile, dets: list[ColumnDetection]) -> tuple[dict[str, SdType], dict[str, str]]:
    """(modelled columns -> sdtype, excluded columns -> reason)."""
    by_col = {(d.table, d.column): d for d in dets}
    keys = {(t.name, t.primary_key) for t in prof.tables.values() if t.primary_key}
    keys |= {(fk.child_table, fk.child_column) for fk in prof.foreign_keys}
    modelled, excluded = {}, {}
    for col, (t, c) in view.origin.items():
        if t == "<derived>":
            modelled[col] = "numerical"
            continue
        d, cp = by_col[(t, c)], prof.column(t, c)
        if d.tag == "DIRECT_ID":
            excluded[col] = f"direct identifier ({d.kind}): regenerated by Nazeer"
        elif d.tag == "FREE_TEXT":
            excluded[col] = "free text: filled from synthetic templates (real text is never reused)"
        elif (t, c) in keys:
            excluded[col] = "key: new keys are generated"
        elif cp.dtype == "numeric":
            modelled[col] = "numerical"
        elif cp.dtype == "date":
            modelled[col] = "datetime"
        elif cp.dtype == "categorical" or cp.n_unique <= HIGH_CARDINALITY_RATIO * max(cp.n_rows, 1):
            modelled[col] = "categorical"
        else:
            excluded[col] = "high-cardinality text: could copy real values, so it is not modelled"
    return modelled, excluded


def typed_view(df: pd.DataFrame, modelled: dict[str, SdType]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for col, kind in modelled.items():
        if kind == "numerical":
            out[col] = pd.to_numeric(df[col], errors="coerce")
        elif kind == "datetime":
            out[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime(DATETIME_FORMAT)
        else:
            out[col] = df[col].astype(str)
    return out.reset_index(drop=True)


# ---------------------------------------------------------------- fill identifiers and text

_MALE = {"ذكر", "m", "male", "رجل"}
_FEMALE = {"أنثى", "انثى", "f", "female", "امرأة"}


def _gender_of(value) -> s.Gender | None:
    v = str(value).strip().lower()
    return "M" if v in _MALE else ("F" if v in _FEMALE else None)


def _fresh(kind: s.Kind, rng: random.Random, forbidden: set[str], used: set[str], first_digit: str | None = None) -> str:
    for _ in range(1000):
        if kind == "SAUDI_ID":
            v = s.gen_saudi_id(rng, first_digit)
        else:
            v = s.GENERATORS[kind](rng)
        canon = s.canonical(kind, v)
        if canon not in forbidden and canon not in used:
            used.add(canon)
            return v
    raise RuntimeError(f"no fresh {kind} value after 1000 attempts")


def _mobile_style(values: pd.Series) -> list[tuple[str, float]]:
    styles = Counter()
    for v in values.dropna():
        flat = s.flatten(v)
        styles[next((p for p in ("+966", "00966", "966", "0") if flat.startswith(p)), "0")] += 1
    total = sum(styles.values()) or 1
    return [(p, n / total) for p, n in styles.most_common()] or [("0", 1.0)]


def fill_synthetic(synth: pd.DataFrame, view: View, real_view: pd.DataFrame, excluded: dict[str, str],
                   dets: list[ColumnDetection], originals: dict[str, set[str]], seed: int = 0) -> pd.DataFrame:
    """Add regenerated identifier, key and text columns to the sampled rows (view column order)."""
    rng = random.Random(seed)
    out = synth.copy()
    by_col = {(d.table, d.column): d for d in dets}
    gender_col = next((c for c in out.columns if by_col.get(view.origin.get(c, ("", ""))) and
                       real_view[c].map(_gender_of).notna().mean() > 0.9), None)
    genders = out[gender_col].map(_gender_of) if gender_col else pd.Series([None] * len(out))
    used: dict[str, set[str]] = {k: set() for k in ("SAUDI_ID", "MOBILE", "IBAN", "EMAIL")}
    generated: dict[str, list[str]] = {}

    for col, reason in excluded.items():
        t, c = view.origin[col]
        d = by_col[(t, c)]
        if d.tag == "DIRECT_ID" and d.kind == "PERSON_NAME":
            generated[col] = [s.gen_person_name(rng, g) for g in genders]
        elif d.tag == "DIRECT_ID" and d.kind == "SAUDI_ID":
            firsts = real_view[col].dropna().map(lambda v: s.canonical("SAUDI_ID", v)[:1])
            p1 = float((firsts == "1").mean()) if len(firsts) else 0.5
            generated[col] = [_fresh("SAUDI_ID", rng, originals["SAUDI_ID"], used["SAUDI_ID"],
                                     "1" if rng.random() < p1 else "2") for _ in range(len(out))]
        elif d.tag == "DIRECT_ID" and d.kind == "MOBILE":
            styles = _mobile_style(real_view[col])
            vals = []
            for _ in range(len(out)):
                national = s.canonical("MOBILE", _fresh("MOBILE", rng, originals["MOBILE"], used["MOBILE"]))
                prefix = rng.choices([p for p, _ in styles], [w for _, w in styles])[0]
                vals.append(prefix + national)
            generated[col] = vals
        elif d.tag == "DIRECT_ID" and d.kind in ("IBAN", "EMAIL"):
            generated[col] = [_fresh(d.kind, rng, originals[d.kind], used[d.kind]) for _ in range(len(out))]
        elif "key" in reason:
            generated[col] = [str(100000 + i) for i in rng.sample(range(900000), len(out))]
        elif d.tag != "FREE_TEXT":
            generated[col] = [None] * len(out)  # high-cardinality text: not modelled, left empty

    name_col = next((c for c in excluded if by_col[view.origin[c]].kind == "PERSON_NAME"), None)
    id_col = next((c for c in excluded if by_col[view.origin[c]].kind == "SAUDI_ID"), None)
    mob_col = next((c for c in excluded if by_col[view.origin[c]].kind == "MOBILE"), None)
    for col in excluded:
        if by_col[view.origin[col]].tag == "FREE_TEXT":
            generated[col] = [
                synthetic_note(rng,
                               generated[name_col][i] if name_col else s.gen_person_name(rng),
                               generated[id_col][i] if id_col else s.gen_saudi_id(rng),
                               generated[mob_col][i] if mob_col else s.gen_mobile(rng))
                for i in range(len(out))]
    for col, vals in generated.items():
        out[col] = vals
    ordered = [c for c in view.df.columns if c in out.columns]
    return out[ordered]
