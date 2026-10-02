"""Person-name detection in Arabic free text.

`GazetteerNER` is the always-available fallback: first-name list lookup, extended
by a following family name. `CamelNER` (stretch, M8) wraps a local CAMeL Lab
model. Both return (start, end, confidence) spans in ORIGINAL text offsets.
"""
from __future__ import annotations

import re
from typing import Protocol

from nazeer import saudi_ids as s

_WORD = re.compile(r"[ء-يٰٱ-ۓ]+")

# First names that are also everyday words ("أمل" = hope, "وعد" = promised, ...).
# These count as names only with a family name after them or a person cue before them.
AMBIGUOUS_FIRST_NAMES = frozenset(s.normalize_name(w) for w in (
    "أمل", "وعد", "فجر", "شروق", "ندى", "هدى", "منى", "سعيد", "عبير", "صبا", "حياة", "بشرى",
    "وفاء", "ملاك", "بسمة", "غالية", "عزيزة", "جميلة", "كريم", "منير", "سالم", "عادل", "نبيل",
    "حور", "شوق", "وداد", "سمر", "رشا", "ربيع", "بدر", "هلال", "صقر", "ليلى", "مي", "لين", "جود",
))
# Words that typically precede a person's name: titles, roles, kinship.
PERSON_CUES = frozenset(s.normalize_name(w) for w in (
    "السيد", "السيدة", "الاستاذ", "الأستاذة", "الأستاذ", "د", "دكتور", "الدكتور", "الدكتورة",
    "الطبيب", "الطبيبة", "الممرضة", "الممرض", "المستفيد", "المستفيدة", "المريض", "المريضة",
    "المراجع", "المراجعة", "العميل", "العميلة", "اسم", "باسم", "ابنه", "ابنته", "ابنها", "ابنتها",
    "زوجة", "زوج", "والد", "والدة", "أخو", "أخت", "الأخ", "الأخت", "لحساب", "للمستفيد",
))
_CLITICS = ("و", "ب", "ل", "ف")
# Function words that collide with names after normalization (ى→ي): "على" → "علي".
# Checked on the RAW token, before normalization.
STOPWORDS = frozenset(("على", "إلى", "الى", "لدى", "حتى", "متى", "سوى", "مدى", "أعلى", "اعلى"))


class NameDetector(Protocol):
    name: str

    def find(self, text: str) -> list[tuple[int, int, float]]: ...


class NERUnavailable(RuntimeError):
    """The model is missing, failed to load, or exceeded its time budget."""


class GazetteerNER:
    name = "gazetteer"

    def find(self, text: str) -> list[tuple[int, int, float]]:
        words = [(m.start(), m.end(), m.group()) for m in _WORD.finditer(text)]
        spans: list[tuple[int, int, float]] = []
        i = 0
        while i < len(words):
            start, end, word = words[i]
            offset = _first_name_offset(word)
            if offset is None:
                # An unknown first name followed by a known family name ("عمار الغامدي") is a name too.
                if (i + 1 < len(words) and _could_be_first_name(word)
                        and _only_space_between(text, end, words[i + 1][0]) and s.is_family_name(words[i + 1][2])):
                    spans.append((start, words[i + 1][1], 0.75))
                    i += 2
                    continue
                i += 1
                continue
            first = s.normalize_name(word[offset:])
            has_family = (
                i + 1 < len(words)
                and _only_space_between(text, end, words[i + 1][0])
                and s.is_family_name(words[i + 1][2])
            )
            prev = s.normalize_name(words[i - 1][2]) if i > 0 else ""
            has_cue = prev in PERSON_CUES and _cue_gap_ok(text, words[i - 1][1], start, prev)
            if first in AMBIGUOUS_FIRST_NAMES and not (has_family or has_cue):
                i += 1
                continue
            span_end = words[i + 1][1] if has_family else end
            confidence = 0.9 if has_family else (0.8 if has_cue else 0.7)
            spans.append((start + offset, span_end, confidence))
            i += 2 if has_family else 1
        return spans


# Words that come before a family name without being a person ("مستشفى الحمادي", "شركة الراجحي").
_NOT_FIRST_NAMES = frozenset(s.normalize_name(w) for w in (
    "مستشفى", "مجمع", "شركة", "مؤسسة", "مكتب", "صيدلية", "عيادة", "عيادات", "مركز", "مدرسة", "جامعة", "بنك",
    "مصرف", "فرع", "حي", "شارع", "طريق", "مدينة", "قبيلة", "عائلة", "أسرة", "آل", "بن", "بنت", "ابن", "أبو", "أم",
    "مجموعة", "مصنع", "معهد", "سوق", "برج", "فندق", "مطعم", "جمعية", "وقف", "قصر", "مزرعة", "استراحة",
))


def _could_be_first_name(word: str) -> bool:
    w = s.normalize_name(word)
    return (len(w) >= 2 and w.isalpha() and not w.startswith("ال") and w not in STOPWORDS
            and w not in _NOT_FIRST_NAMES and w not in PERSON_CUES and not s.is_family_name(word))


def _first_name_offset(word: str) -> int | None:
    """0 if `word` is a first name, 1 if it is a clitic + first name (e.g. "ومحمد"), else None."""
    if word not in STOPWORDS and s.name_gender(word) is not None:
        return 0
    rest = word[1:]
    if len(word) > 3 and word[0] in _CLITICS and rest not in STOPWORDS and s.name_gender(rest) is not None:
        return 1
    return None


def _only_space_between(text: str, a: int, b: int) -> bool:
    return 0 < b - a <= 2 and text[a:b].isspace()


_ABBREVIATED_CUES = frozenset(("د",))  # "د. محمد": the dot belongs to the title


def _cue_gap_ok(text: str, a: int, b: int, cue: str) -> bool:
    """Cue and name in the same sentence: only spaces between them (or "." after an abbreviation)."""
    gap = text[a:b]
    if not 0 < len(gap) <= 3:
        return False
    if cue in _ABBREVIATED_CUES:
        return set(gap) <= {" ", "."}
    return set(gap) <= {" ", "/", ":"} and gap.strip(" ") in ("", "/", ":")  # "السيد/ محمد", "العميل: محمد"


NER_MODES = ("gazetteer", "union", "camel", "auto")


def get_name_detector(mode: str = "gazetteer") -> NameDetector:
    """Name detector by mode:
    gazetteer  fast first-name list + family-name extension (default for whole datasets)
    union      CamelBERT + gazetteer (best recall; ~0.1 s per note on CPU)
    camel      CamelBERT only
    auto       union when the model is installed locally, otherwise gazetteer
    "union"/"camel" raise NERUnavailable if the local model is missing."""
    if mode == "gazetteer":
        return GazetteerNER()
    if mode not in NER_MODES:
        raise ValueError(f"unknown name detector {mode!r}; choose from {NER_MODES}")
    try:
        from nazeer.camel_ner import CamelNER, UnionNER  # noqa: PLC0415 - optional heavy dependency

        camel = CamelNER.load()
    except Exception as e:  # noqa: BLE001
        if mode in ("camel", "union"):
            raise NERUnavailable(f"CamelBERT NER unavailable ({type(e).__name__}); run scripts\\download_models.py") from None
        return GazetteerNER()
    return camel if mode == "camel" else UnionNER(camel)
