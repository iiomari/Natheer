"""Saudi identifiers: normalization, validators, canonical forms, generators.

Validators expect canonical ASCII input (run `normalize` / `canonical` first):
Arabic-Indic digits are rejected on purpose, because Python's str.isdigit()
and int() silently accept them.
"""
from __future__ import annotations

import random
import re
from functools import lru_cache
from pathlib import Path
from typing import Callable, Literal

Kind = Literal["SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME"]
Gender = Literal["M", "F"]

DATA_DIR = Path(__file__).parent / "data"

# ---------------------------------------------------------------- normalization

_ARABIC_INDIC = {chr(0x0660 + d): str(d) for d in range(10)}
_PERSIAN = {chr(0x06F0 + d): str(d) for d in range(10)}
_DIGITS = {**{str(d): str(d) for d in range(10)}, **_ARABIC_INDIC, **_PERSIAN}

# Characters removed when they sit between two digits. Besides the spec's
# space / hyphen / dot this covers the variants that show up in Arabic text:
# no-break and thin spaces, Unicode dashes, Arabic decimal and thousands
# separators, and invisible bidi marks inserted by editors around numbers.
_SEPARATORS = frozenset(
    " \t   "  # spaces
    "-‐‑‒–−"  # hyphens and dashes
    ".٫٬"  # dot, Arabic decimal and thousands separators
    "()"  # brackets around a group, e.g. "(054) 818 8763"
    "‎‏؜"  # LRM, RLM, Arabic letter mark
    "‪‫‬‭‮⁦⁧⁨⁩"  # bidi embeddings/isolates
)
# Longest separator run still treated as "inside" a number, e.g. "050 - 331".
MAX_SEPARATOR_RUN = 3


def ascii_digit(ch: str) -> str | None:
    """ASCII form of an ASCII, Arabic-Indic or Persian digit; None otherwise."""
    return _DIGITS.get(ch)


def normalize(text: str) -> tuple[str, list[int]]:
    """Convert digits to ASCII and join digit runs split by separators.

    Returns (normalized_text, offset_map) where offset_map[i] is the index in
    `text` of normalized character i. Every other character is kept as is.

        >>> normalize("٠٥٠ ٣٣١ ٨٨٤٢")[0]
        '0503318842'
    """
    out: list[str] = []
    offsets: list[int] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch in _SEPARATORS and i > 0 and ascii_digit(text[i - 1]) is not None:
            j = i
            while j < n and text[j] in _SEPARATORS and j - i < MAX_SEPARATOR_RUN:
                j += 1
            if j < n and ascii_digit(text[j]) is not None:
                i = j  # drop the separator run inside the number
                continue
        out.append(ascii_digit(ch) or ch)
        offsets.append(i)
        i += 1
    return "".join(out), offsets


def to_original_span(offset_map: list[int], start: int, end: int) -> tuple[int, int]:
    """Map a half-open span [start, end) of normalized text back to the original."""
    if not 0 <= start < end <= len(offset_map):
        raise ValueError("span out of range")
    return offset_map[start], offset_map[end - 1] + 1


_TASHKEEL = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # + tatweel
_NAME_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه"})


def normalize_name(s: str) -> str:
    """Spelling-insensitive form of an Arabic name, for matching and HMAC input."""
    s = _TASHKEEL.sub("", s).translate(_NAME_MAP)
    return " ".join(s.split())


# ------------------------------------------------------------------- validators

_TEN_DIGITS = re.compile(r"[0-9]{10}")
_MOBILE = re.compile(r"(?:05|\+9665|9665|009665)[0-9]{8}")
_IBAN = re.compile(r"SA[0-9]{22}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def _id_checksum_total(digits: str) -> int:
    total = 0
    for i, c in enumerate(digits):
        d = int(c)
        if i % 2 == 0:
            d *= 2
            total += d // 10 + d % 10
        else:
            total += d
    return total


def is_valid_saudi_id(s: str) -> bool:
    """National ID (first digit 1) or iqama (2), with the Luhn-style checksum."""
    return bool(_TEN_DIGITS.fullmatch(s)) and s[0] in "12" and _id_checksum_total(s) % 10 == 0


def is_valid_mobile(s: str) -> bool:
    return bool(_MOBILE.fullmatch(s))


def _iban_mod97(iban: str) -> int:
    rearranged = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in rearranged)) % 97


def is_valid_iban(s: str) -> bool:
    """Saudi IBAN: 'SA' + 22 digits, ISO 13616 mod-97 == 1."""
    return bool(_IBAN.fullmatch(s)) and _iban_mod97(s) == 1


def is_valid_email(s: str) -> bool:
    return bool(_EMAIL.fullmatch(s))


def is_known_name(s: str) -> bool:
    """True if the first token is a known first name (gazetteer)."""
    tokens = normalize_name(s).split()
    return bool(tokens) and name_gender(tokens[0]) is not None


VALIDATORS: dict[Kind, Callable[[str], bool]] = {
    "SAUDI_ID": is_valid_saudi_id,
    "MOBILE": is_valid_mobile,
    "IBAN": is_valid_iban,
    "EMAIL": is_valid_email,
    "PERSON_NAME": is_known_name,
}


# -------------------------------------------------------------- canonical forms


def flatten(value: str) -> str:
    """ASCII digits with in-number separators and all whitespace removed; prefixes kept."""
    return "".join(ch for ch in normalize(value)[0] if not ch.isspace())


def is_valid(kind: Kind, raw: str) -> bool:
    """Validate a raw value in any accepted spelling (digit script, separators, case)."""
    if kind in ("PERSON_NAME", "EMAIL"):
        return VALIDATORS[kind](raw.strip())
    flat = flatten(raw)
    return VALIDATORS[kind](flat.upper() if kind == "IBAN" else flat)


def canonical(kind: Kind, value: str) -> str:
    """One spelling per real-world value: the pseudonymization (HMAC) input.

    All mobile formats map to the 9-digit national number, so 05…, +9665…,
    9665… and 009665… of the same line pseudonymize identically.
    """
    if kind == "PERSON_NAME":
        return normalize_name(value)
    if kind == "EMAIL":
        return value.strip().lower()
    flat = flatten(value)
    if kind == "SAUDI_ID":
        return flat
    if kind == "IBAN":
        return flat.upper()
    if kind == "MOBILE":
        digits = flat.lstrip("+")
        for prefix in ("00966", "966", "0"):
            if digits.startswith(prefix):
                return digits[len(prefix):]
        return digits
    raise ValueError(f"unknown kind: {kind}")


# ------------------------------------------------------------------- generators

# Real Saudi bank codes (IBAN positions 5-6), so generated IBANs look plausible.
_BANK_CODES = ("10", "80", "45", "20", "05", "55", "15", "60", "30", "65")
# Mobile operator prefixes after "05".
_MOBILE_SECOND_DIGITS = "0345689"


def gen_saudi_id(rng: random.Random, first_digit: str | None = None) -> str:
    first = first_digit if first_digit is not None else rng.choice("12")
    if first not in ("1", "2"):
        raise ValueError("first_digit must be '1' or '2'")
    body = first + "".join(rng.choice("0123456789") for _ in range(8))
    # The check digit sits at odd index 9, so it is added as is.
    check = (10 - _id_checksum_total(body) % 10) % 10
    return body + str(check)


def gen_mobile(rng: random.Random) -> str:
    return "05" + rng.choice(_MOBILE_SECOND_DIGITS) + "".join(rng.choice("0123456789") for _ in range(7))


def gen_iban(rng: random.Random, bank_code: str | None = None) -> str:
    bank = bank_code if bank_code is not None else rng.choice(_BANK_CODES)
    if len(bank) != 2 or not bank.isascii() or not bank.isdigit():
        raise ValueError("bank_code must be 2 ASCII digits")
    bban = bank + "".join(rng.choice("0123456789") for _ in range(18))
    check = 98 - _iban_mod97("SA00" + bban)
    return f"SA{check:02d}{bban}"


def gen_email(rng: random.Random) -> str:
    user = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(rng.randint(5, 10)))
    return f"{user}{rng.randint(1, 999)}@{rng.choice(('example.com', 'example.org', 'example.net'))}"


@lru_cache(maxsize=None)
def _names(which: str) -> tuple[str, ...]:
    path = DATA_DIR / f"names_{which}.txt"
    return tuple(line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


@lru_cache(maxsize=None)
def _gender_index() -> dict[str, Gender]:
    index: dict[str, Gender] = {normalize_name(n): "M" for n in _names("male")}
    index.update({normalize_name(n): "F" for n in _names("female")})
    return index


@lru_cache(maxsize=None)
def _family_index() -> frozenset[str]:
    return frozenset(normalize_name(n) for n in _names("family"))


def first_names(gender: Gender) -> tuple[str, ...]:
    return _names("male" if gender == "M" else "female")


def family_names() -> tuple[str, ...]:
    return _names("family")


def name_gender(first: str) -> Gender | None:
    """Gender of a first name from the gazetteer, spelling-insensitive."""
    return _gender_index().get(normalize_name(first))


def is_family_name(token: str) -> bool:
    return normalize_name(token) in _family_index()


def gen_first_name(rng: random.Random, gender: Gender | None = None) -> str:
    return rng.choice(first_names(gender or rng.choice("MF")))


def gen_family_name(rng: random.Random) -> str:
    return rng.choice(family_names())


def gen_person_name(rng: random.Random, gender: Gender | None = None) -> str:
    return f"{gen_first_name(rng, gender)} {gen_family_name(rng)}"


GENERATORS: dict[Kind, Callable[[random.Random], str]] = {
    "SAUDI_ID": gen_saudi_id,
    "MOBILE": gen_mobile,
    "IBAN": gen_iban,
    "EMAIL": gen_email,
    "PERSON_NAME": gen_person_name,
}
