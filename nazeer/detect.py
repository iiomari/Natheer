"""Module 2: personal-data detection at column level and inside Arabic free text.

Column level:  score = 0.8 * valid_ratio + 0.2 * name_hint  (sample <= 500 values)
               >= 0.7 tag, 0.4-0.7 "needs human review" (treated as identifier until a
               human clears it: the safe default).
Free text:     normalize -> candidates -> VALIDATOR MUST PASS -> map back to original
               offsets. Digit candidates are tried at the group boundaries recorded in
               the offset map, so an ID glued to a neighbouring number by a space is
               still found, and a look-alike invoice number is rejected by the checksum.
Baseline:      deliberately naive (ASCII digits only, no normalization, no validation)
               for the "baseline vs Nazeer" comparison.
"""
from __future__ import annotations

import logging
import re
from collections import Counter

import pandas as pd

from nazeer import saudi_ids as s
from nazeer.models import ColumnDetection, DatasetProfile, Span, Tag
from nazeer.ner import GazetteerNER, NameDetector

log = logging.getLogger(__name__)

SAMPLE_SIZE = 500
TAG_THRESHOLD = 0.7
REVIEW_THRESHOLD = 0.4
IDENTIFIER_KINDS: tuple[s.Kind, ...] = ("SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME")

# Column-name hints, matched against lower-cased name tokens (split on non-letters).
NAME_HINTS: dict[str, tuple[str, ...]] = {
    "SAUDI_ID": ("id", "national", "iqama", "hawiya", "nid", "هوية", "الهوية", "اقامة", "إقامة", "سجل"),
    "MOBILE": ("phone", "mobile", "jawal", "tel", "جوال", "الجوال", "هاتف", "الهاتف"),
    "IBAN": ("iban", "ايبان", "آيبان", "الآيبان", "حساب"),
    "EMAIL": ("email", "mail", "بريد", "البريد"),
    "PERSON_NAME": ("name", "اسم", "الاسم"),
}
QUASI_HINTS = re.compile(
    r"age|birth|dob|city|region|gender|sex|nationality|zip|postal|عمر|العمر|ميلاد|مدينة|المدينة|منطقة|جنس|الجنس|جنسية",
    re.IGNORECASE)
SENSITIVE_HINTS = re.compile(
    r"diagnos|icd|treatment|procedure|claim_type|amount|cost|salary|income|balance|تشخيص|علاج|مبلغ|راتب|رصيد",
    re.IGNORECASE)

_TOKEN = re.compile(r"[a-z]+|[؀-ۿ]+")
_IBAN_RE = re.compile(r"(?<![A-Za-z0-9])SA\s?\d{22}(?!\d)", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_DIGIT_RUN = re.compile(r"\+?\d+")
_INVOICE_CONTEXT = re.compile(r"(فاتور|طلب|مرجع|وثيق|عملي|إيصال|ايصال|invoice|order|ref)", re.IGNORECASE)

# ---------------------------------------------------------------- column level


def _name_hint(column: str, kind: s.Kind) -> bool:
    tokens = set(_TOKEN.findall(column.lower()))
    return any(h in tokens for h in NAME_HINTS[kind])


def detect_columns(tables: dict[str, pd.DataFrame], prof: DatasetProfile) -> list[ColumnDetection]:
    out = []
    fk_cols = {(fk.child_table, fk.child_column) for fk in prof.foreign_keys}
    for tname, df in tables.items():
        for col in df.columns:
            cp = prof.column(tname, col)
            values = df[col].dropna()
            sample = values.sample(min(SAMPLE_SIZE, len(values)), random_state=0) if len(values) else values
            best: tuple[float, float, bool, s.Kind | None] = (0.0, 0.0, False, None)
            if cp.dtype != "free_text":
                for kind in IDENTIFIER_KINDS:
                    ratio = float(sample.map(lambda v, k=kind: s.is_valid(k, v)).mean()) if len(sample) else 0.0
                    hint = _name_hint(col, kind)
                    score = 0.8 * ratio + 0.2 * hint
                    if score > best[0]:
                        best = (score, ratio, hint, kind)
            score, ratio, hint, kind = best
            if score >= TAG_THRESHOLD:
                det = ColumnDetection(tname, col, "DIRECT_ID", kind, score, ratio, hint, False,
                                      f"{ratio:.0%} of sampled values validate as {kind}")
            elif score >= REVIEW_THRESHOLD:
                det = ColumnDetection(tname, col, "DIRECT_ID", kind, score, ratio, hint, True,
                                      f"borderline: {ratio:.0%} validate as {kind}; please review")
            else:
                det = ColumnDetection(tname, col, *_non_identifier_tag(col, cp.dtype, cp.is_primary_key,
                                                                         (tname, col) in fk_cols),
                                      score=score, valid_ratio=ratio, name_hint=hint, needs_review=False,
                                      reason="")
                det.reason = _reason(det.tag, cp.dtype)
            out.append(det)
    counts = Counter(d.tag for d in out)
    log.info("column detection: %s; %d need review", dict(counts), sum(d.needs_review for d in out))
    return out


def _non_identifier_tag(col: str, dtype: str, is_pk: bool, is_fk: bool) -> tuple[Tag, None]:
    if is_pk or is_fk:
        return "NORMAL", None
    if dtype == "free_text":
        return "FREE_TEXT", None
    if QUASI_HINTS.search(col):
        return "QUASI_ID", None
    if SENSITIVE_HINTS.search(col):
        return "SENSITIVE", None
    return "NORMAL", None


def _reason(tag: Tag, dtype: str) -> str:
    return {
        "FREE_TEXT": "long Arabic text; scanned for embedded identifiers",
        "QUASI_ID": "column name suggests a quasi-identifier",
        "SENSITIVE": "column name suggests sensitive content",
        "NORMAL": f"no identifier pattern ({dtype})",
    }[tag]


# ---------------------------------------------------------------- free text


def find_spans(text: str, ner: NameDetector | None = None, names: bool = True,
               name_spans: list[tuple[int, int, float]] | None = None) -> list[tuple[int, int, s.Kind, float, str]]:
    """All identifier spans in one text: (start, end, kind, confidence, source), original offsets.
    `name_spans` lets a batched name detector pass its precomputed result for this text."""
    norm, offsets = s.normalize(text)
    found: list[tuple[int, int, s.Kind, float, str]] = []
    taken = [False] * len(norm)

    def claim(a: int, b: int, kind: s.Kind, conf: float, source: str = "regex+validator") -> None:
        o_start, o_end = s.to_original_span(offsets, a, b)
        found.append((o_start, o_end, kind, conf, source))
        for i in range(a, b):
            taken[i] = True

    for m in _IBAN_RE.finditer(norm):
        if s.is_valid("IBAN", m.group()):
            claim(m.start(), m.end(), "IBAN", 0.99)
    for m in _EMAIL_RE.finditer(norm):
        if not any(taken[m.start():m.end()]) and s.is_valid("EMAIL", m.group()):
            claim(m.start(), m.end(), "EMAIL", 0.99)
    for m in _DIGIT_RUN.finditer(norm):
        if any(taken[m.start():m.end()]):
            continue
        for a, b, kind in _digit_candidates(m.group(), m.start(), offsets):
            context = norm[max(0, a - 25):a]
            conf = 0.6 if (kind == "SAUDI_ID" and _INVOICE_CONTEXT.search(context)) else 0.95
            claim(a, b, kind, conf)
    if names:
        detected = name_spans if name_spans is not None else (ner or GazetteerNER()).find(text)
        source = getattr(ner, "name", "gazetteer") if ner is not None else "gazetteer"
        for a, b, conf in detected:
            if not any(taken[i] for i in range(len(norm)) if a <= offsets[i] < b):
                found.append((a, b, "PERSON_NAME", conf, source))
    return sorted(found)


def _digit_candidates(run: str, run_start: int, offsets: list[int]) -> list[tuple[int, int, s.Kind]]:
    """Validated windows of a digit run, cut only at original group boundaries.

    Boundaries are where normalization removed a separator (a gap in the offset map),
    plus the run ends. Longest valid windows win; windows never overlap.
    """
    bounds = [0] + [i for i in range(1, len(run))
                    if offsets[run_start + i] - offsets[run_start + i - 1] > 1] + [len(run)]
    windows = []
    for i, a in enumerate(bounds):
        for b in bounds[i + 1:]:
            piece = run[a:b]
            if piece.startswith("+") and a != 0:
                continue
            for kind in ("SAUDI_ID", "MOBILE"):
                if s.VALIDATORS[kind](piece):
                    windows.append((b - a, a, b, kind))
    chosen, used = [], set()
    for _, a, b, kind in sorted(windows, key=lambda w: (-w[0], w[1])):
        if used.isdisjoint(range(a, b)):
            chosen.append((run_start + a, run_start + b, kind))
            used.update(range(a, b))
    return chosen


def detect_free_text(tables: dict[str, pd.DataFrame], columns: list[tuple[str, str]],
                     ner: NameDetector | None = None) -> list[Span]:
    ner = ner or GazetteerNER()
    spans: list[Span] = []
    for tname, col in columns:
        texts = tables[tname][col].tolist()
        valid = [(row, t) for row, t in enumerate(texts) if isinstance(t, str) and t]
        batched = ner.find_many([t for _, t in valid]) if hasattr(ner, "find_many") else None
        for i, (row, text) in enumerate(valid):
            names = batched[i] if batched is not None else None
            spans += [Span(tname, row, col, a, b, kind, conf, src)
                      for a, b, kind, conf, src in find_spans(text, ner, name_spans=names)]
    log.info("free-text detection: %d spans %s", len(spans), dict(Counter(sp.type for sp in spans)))
    return spans


# ---------------------------------------------------------------- baseline

_BASELINE = [
    ("SAUDI_ID", re.compile(r"(?<![0-9])[12][0-9]{9}(?![0-9])")),
    ("MOBILE", re.compile(r"(?<![0-9])05[0-9]{8}(?![0-9])")),
    ("IBAN", re.compile(r"SA[0-9]{22}")),
    ("EMAIL", _EMAIL_RE),
]


def baseline_find_spans(text: str) -> list[tuple[int, int, s.Kind, float, str]]:
    """Naive generic-tool behaviour: ASCII digit regex, no normalization, no validation, no names."""
    out = []
    for kind, rx in _BASELINE:
        out += [(m.start(), m.end(), kind, 1.0, "baseline") for m in rx.finditer(text)]
    return sorted(out)


def baseline_free_text(tables: dict[str, pd.DataFrame], columns: list[tuple[str, str]]) -> list[Span]:
    spans = []
    for tname, col in columns:
        for row, text in enumerate(tables[tname][col].tolist()):
            if isinstance(text, str):
                spans += [Span(tname, row, col, a, b, k, c, src) for a, b, k, c, src in baseline_find_spans(text)]
    return spans


def free_text_columns(detections: list[ColumnDetection]) -> list[tuple[str, str]]:
    return [(d.table, d.column) for d in detections if d.tag == "FREE_TEXT"]
