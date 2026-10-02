"""Module 4: deterministic keyed pseudonymization and format-preserving replacement.

    seed = HMAC-SHA256(key, f"{kind}:{canonical_value}")   -> random.Random(seed) -> generator

No mapping table is stored: the in-memory cache lives only for one run. The same
value and key give the same fake across tables, columns, free text and runs.

* Collisions (two originals -> one fake, or a fake equal to ANY original value of
  its kind) are resolved by rehashing with a counter. Values are processed in
  sorted order (`prepare`), so the result does not depend on table/row order.
* Person names are mapped per token: first name -> fake first name of the same
  gender, family name -> fake family name. A first name alone in a note maps
  consistently with the full name in the customer column.
* Replacements keep the original's digit script (ASCII / Arabic-Indic / Persian),
  separator positions and prefix style (05 / +966 / 966 / 00966).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import math
import random
import re
from collections import Counter, defaultdict
from typing import Callable, Iterable

import pandas as pd

from nazeer import saudi_ids as s
from nazeer.models import DatasetProfile, Span
from nazeer.policy import Decision

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 1000
NAME_KINDS = ("FIRST_NAME", "FAMILY_NAME")
_WS_SPLIT = re.compile(r"(\s+)")
_ARABIC_INDIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
_PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


class PseudonymSpaceExhausted(RuntimeError):
    """No free pseudonym after MAX_ATTEMPTS rehashes (message never contains the value)."""


PK_WIDEN_AFTER = 50


def _fake_key(canon: str, rng: random.Random, extra_digits: int = 0) -> str:
    """Same shape as the original key: digits re-drawn, other characters kept.

    extra_digits > 0 widens a key whose same-length space is (nearly) exhausted, e.g. keys 1..9:
    nine one-digit keys cannot all map to a different one-digit key without collisions."""
    out = []
    for i, ch in enumerate(canon):
        if ch.isascii() and ch.isdigit():
            out.append(rng.choice("123456789" if i == 0 and ch != "0" else "0123456789"))
        else:
            out.append(ch)
    out.extend(rng.choice("0123456789") for _ in range(extra_digits))
    return "".join(out)


class Pseudonymizer:
    def __init__(self, key: bytes, keep_first_digit: bool = True,
                 generators: dict[str, Callable[[str, random.Random], str]] | None = None):
        if not key:
            raise ValueError("empty key")
        self._key = key
        self.keep_first_digit = keep_first_digit
        self._forbidden: dict[str, set[str]] = defaultdict(set)
        self._used: dict[str, set[str]] = defaultdict(set)
        self._cache: dict[tuple[str, str], str] = {}
        self.collisions: Counter[str] = Counter()
        self._generators = generators or {}

    # ---------------------------------------------------------------- core

    def forbid(self, kind: str, canonical_values: Iterable[str]) -> None:
        """Fakes of `kind` may never equal any of these (the original values)."""
        self._forbidden[kind].update(canonical_values)

    def prepare(self, values: dict[str, Iterable[str]]) -> None:
        """Assign fakes in sorted order so collision handling is order-independent."""
        for kind in sorted(values):
            for canon in sorted(set(values[kind])):
                self.fake(kind, canon)

    def _rng(self, kind: str, canon: str, counter: int) -> random.Random:
        msg = f"{kind}:{canon}" if counter == 0 else f"{kind}:{canon}:{counter}"
        return random.Random(hmac.new(self._key, msg.encode("utf-8"), hashlib.sha256).digest())

    def _generate(self, kind: str, canon: str, rng: random.Random, counter: int = 0) -> str:
        if kind in self._generators:
            return self._generators[kind](canon, rng)
        if kind == "SAUDI_ID":
            first = canon[0] if self.keep_first_digit and canon[:1] in ("1", "2") else None
            return s.gen_saudi_id(rng, first)
        if kind == "MOBILE":
            return s.canonical("MOBILE", s.gen_mobile(rng))
        if kind == "IBAN":
            return s.gen_iban(rng)
        if kind == "EMAIL":
            return s.gen_email(rng)
        if kind == "FIRST_NAME":
            return s.gen_first_name(rng, s.name_gender(canon))
        if kind == "FAMILY_NAME":
            return s.gen_family_name(rng)
        if kind.startswith("PK:"):
            return _fake_key(canon, rng, counter // PK_WIDEN_AFTER)
        raise ValueError(f"no generator for kind {kind}")

    def fake(self, kind: str, canon: str) -> str:
        """Fake for a canonical value. Names: display form; others: canonical form."""
        cached = self._cache.get((kind, canon))
        if cached is not None:
            return cached
        injective = kind not in NAME_KINDS  # name spaces are small; only "never itself" is enforced
        for counter in range(MAX_ATTEMPTS):
            out = self._generate(kind, canon, self._rng(kind, canon, counter), counter)
            norm = s.normalize_name(out) if kind in NAME_KINDS else out
            clash = norm == canon or (injective and (norm in self._forbidden[kind] or norm in self._used[kind]))
            if not clash:
                break
            self.collisions[kind] += 1
        else:
            raise PseudonymSpaceExhausted(f"no free pseudonym for kind {kind} after {MAX_ATTEMPTS} attempts")
        self._used[kind].add(norm)
        self._cache[(kind, canon)] = out
        return out

    def generated(self) -> set[str]:
        """Every pseudonym produced in this run (canonical form): the residual scan's allow-list."""
        return {v for (kind, _), v in self._cache.items() if kind not in NAME_KINDS}

    # ---------------------------------------------------------------- display values

    def name(self, raw: str) -> str:
        """Token-wise fake for a person name, keeping the original whitespace."""
        parts = _WS_SPLIT.split(raw)
        words = [i for i, p in enumerate(parts) if p and not p.isspace()]
        for j, i in enumerate(words):
            kind = name_token_kind(parts[i], j, len(words))
            parts[i] = self.fake(kind, s.normalize_name(parts[i]))
        return "".join(parts)

    def value(self, kind: s.Kind, raw: str) -> str:
        """Fake for one raw identifier value, rendered in the original's format."""
        if kind == "PERSON_NAME":
            return self.name(raw)
        if kind == "EMAIL":
            return self.fake("EMAIL", s.canonical("EMAIL", raw))
        return render_like(raw, kind, self.fake(kind, s.canonical(kind, raw)))


def name_token_kind(token: str, position: int, n_words: int) -> str:
    is_last = n_words >= 2 and position == n_words - 1
    if is_last and (s.is_family_name(token) or s.normalize_name(token).startswith("ال")):
        return "FAMILY_NAME"
    return "FIRST_NAME"


def name_token_values(raw: str) -> list[tuple[str, str]]:
    words = raw.split()
    return [(name_token_kind(w, j, len(words)), s.normalize_name(w)) for j, w in enumerate(words)]


# -------------------------------------------------------------------- rendering

def _script_of(ch: str) -> str:
    if "٠" <= ch <= "٩":
        return "arabic"
    if "۰" <= ch <= "۹":
        return "persian"
    return "ascii"


def _in_script(digit: str, script: str) -> str:
    if script == "arabic":
        return digit.translate(_ARABIC_INDIC)
    if script == "persian":
        return digit.translate(_PERSIAN)
    return digit


def _display_target(raw: str, kind: s.Kind, fake_canon: str) -> str:
    """The fake in the original's flat style (same prefix / letter case), before layout."""
    if kind == "MOBILE":
        flat = s.flatten(raw)
        for prefix in ("+966", "00966", "966", "0"):
            if flat.startswith(prefix):
                return prefix + fake_canon
        return fake_canon
    if kind == "IBAN":
        flat = s.flatten(raw)
        return (fake_canon[:2].lower() if flat[:2].islower() else fake_canon[:2]) + fake_canon[2:]
    return fake_canon


def render_like(raw: str, kind: s.Kind, fake_canon: str) -> str:
    """Lay the fake onto the original layout: same digit script per position, same
    separators at the same positions, same prefix style and letter case."""
    target = _display_target(raw, kind, fake_canon)
    _, offsets = s.normalize(raw)
    slots = [i for i in offsets if not raw[i].isspace() and raw[i] not in "()"]  # brackets are layout
    if len(slots) != len(target):
        # Layout cannot be mirrored (unusual spelling); fall back to the dominant script.
        digits = [ch for ch in raw if s.ascii_digit(ch) is not None]
        script = Counter(_script_of(ch) for ch in digits).most_common(1)[0][0] if digits else "ascii"
        return "".join(_in_script(c, script) if c.isdigit() else c for c in target)
    slot_set, it = set(slots), iter(target)
    out = []
    for i, ch in enumerate(raw):
        if i not in slot_set:
            out.append(ch)
            continue
        c = next(it)
        out.append(_in_script(c, _script_of(ch)) if c.isdigit() and s.ascii_digit(ch) is not None else c)
    return "".join(out)


def replace_spans(text: str, spans: list[tuple[int, int, s.Kind]], pseudo: Pseudonymizer) -> str:
    """Replace from the end to the start so earlier offsets stay valid. Overlaps are skipped."""
    limit = len(text) + 1
    for start, end, kind in sorted(spans, key=lambda x: (x[0], x[1]), reverse=True):
        if end > limit:
            continue
        text = text[:start] + pseudo.value(kind, text[start:end]) + text[end:]
        limit = start
    return text


def _span_index(spans: list[Span], min_conf: float) -> dict[tuple[str, str], dict[int, list[tuple[int, int, str]]]]:
    idx: dict = defaultdict(lambda: defaultdict(list))
    for sp in spans:
        if sp.confidence >= min_conf:
            idx[(sp.table, sp.column)][sp.row].append((sp.start, sp.end, sp.type))
    return idx


def collect_values(tables: dict[str, pd.DataFrame], decisions: list[Decision],
                   spans: list[Span], min_conf: float) -> dict[str, set[str]]:
    """Every canonical value that will be pseudonymized, keyed by pseudonym kind."""
    values: dict[str, set[str]] = defaultdict(set)

    def add(kind: s.Kind, raw: str) -> None:
        if kind == "PERSON_NAME":
            for k, v in name_token_values(raw):
                values[k].add(v)
        else:
            values[kind].add(s.canonical(kind, raw))

    for d in decisions:
        col = tables[d.table][d.column].dropna()
        if d.action == "pseudonymize" and d.kind:
            for raw in col.unique():
                add(d.kind, raw)
        elif d.action == "remap" and d.remap_group:
            values[d.remap_group].update(str(v).strip() for v in col.unique())
    for sp in spans:
        if sp.confidence >= min_conf:
            add(sp.type, tables[sp.table][sp.column].iat[sp.row][sp.start:sp.end])
    return values


def apply(tables: dict[str, pd.DataFrame], prof: DatasetProfile, decisions: list[Decision],
          spans: list[Span], pseudo: Pseudonymizer, min_conf: float = 0.5) -> tuple[dict[str, pd.DataFrame], dict]:
    """Build the masked twin. Returns (twin tables, stats with counts only)."""
    values = collect_values(tables, decisions, spans, min_conf)
    for kind, vals in values.items():
        if not kind.startswith("PK:") and kind not in NAME_KINDS:
            pseudo.forbid(kind, vals)
    pseudo.prepare(values)

    span_idx = _span_index(spans, min_conf)
    twin = {name: df.copy() for name, df in tables.items()}
    stats: dict = {"columns": {}, "spans_replaced": Counter(), "collisions": {}}
    for d in decisions:
        df, col = twin[d.table], d.column
        if d.action == "keep":
            pass
        elif d.action == "drop":
            df.drop(columns=[col], inplace=True)
        elif d.action == "pseudonymize":
            uniq = df[col].dropna().unique()
            mapping = {raw: pseudo.value(d.kind, raw) for raw in uniq}
            df[col] = df[col].map(lambda v: mapping.get(v, v) if isinstance(v, str) else v)
        elif d.action == "remap":
            df[col] = df[col].map(lambda v: pseudo.fake(d.remap_group, str(v).strip()) if isinstance(v, str) else v)
        elif d.action == "replace_spans":
            by_row = span_idx.get((d.table, col), {})
            texts = df[col].tolist()
            for row, row_spans in by_row.items():
                texts[row] = replace_spans(texts[row], row_spans, pseudo)
                stats["spans_replaced"].update(k for _, _, k in row_spans)
            df[col] = texts
        stats["columns"][f"{d.table}.{col}"] = d.action
    stats["spans_replaced"] = dict(stats["spans_replaced"])
    stats["collisions"] = dict(pseudo.collisions)
    log.info("transform: %d columns, spans replaced %s, collisions %s",
             len(decisions), stats["spans_replaced"], stats["collisions"])
    return twin, stats
