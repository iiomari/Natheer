"""Seeded, reproducible demo dataset with golden labels. No real people.

    python -m data_gen.make_demo_data --seed 42 --n 3000 --out data\\demo

Writes:
  customers.csv        customer_id, full_name, national_id, mobile, city, age, gender
  claims.csv           claim_id, customer_id (FK), claim_date, claim_type, amount, notes
  golden_labels.csv    every planted identifier in notes: table,row,column,start,end,type
  hard_negatives.csv   look-alikes that must NOT be flagged: table,row,column,start,end,kind
  golden_columns.csv   expected column-level tag and identifier kind

Planted signal for the utility test: claim amount grows with age, claim type
and the customer's number of prior claims.
"""
from __future__ import annotations

import argparse
import csv
import random
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from data_gen.templates_ar import HARD_NEGATIVE_SENTENCES, IDENTIFIER_SENTENCES, NEUTRAL_SENTENCES
from nazeer import saudi_ids as s

CITIES = [
    ("الرياض", 26), ("جدة", 16), ("مكة المكرمة", 8), ("المدينة المنورة", 6), ("الدمام", 7),
    ("الخبر", 4), ("الأحساء", 4), ("الطائف", 4), ("تبوك", 3), ("بريدة", 3), ("أبها", 3),
    ("خميس مشيط", 3), ("حائل", 2), ("جازان", 2), ("نجران", 2), ("الجبيل", 2), ("ينبع", 1),
    ("الباحة", 1), ("عرعر", 1), ("سكاكا", 1),
]
GENDER_AR = {"M": "ذكر", "F": "أنثى"}

# claim type -> (base amount SAR, base weight)
CLAIM_TYPES = {
    "طوارئ": (1500, 18),
    "عيادات خارجية": (400, 30),
    "تنويم": (9000, 8),
    "أسنان": (800, 12),
    "بصريات": (600, 7),
    "أدوية": (300, 15),
    "عمليات جراحية": (20000, 4),
    "أمومة": (12000, 6),
}
CLAIMS_PER_CUSTOMER = ([0, 1, 2, 3, 4, 5, 6], [10, 25, 25, 18, 10, 7, 5])
START, END = date(2023, 1, 1), date(2025, 12, 31)

GOLDEN_COLUMNS = [
    # table, column, expected tag, identifier kind
    ("customers", "customer_id", "NORMAL", ""),
    ("customers", "full_name", "DIRECT_ID", "PERSON_NAME"),
    ("customers", "national_id", "DIRECT_ID", "SAUDI_ID"),
    ("customers", "mobile", "DIRECT_ID", "MOBILE"),
    ("customers", "city", "QUASI_ID", ""),
    ("customers", "age", "QUASI_ID", ""),
    ("customers", "gender", "QUASI_ID", ""),
    ("claims", "claim_id", "NORMAL", ""),
    ("claims", "customer_id", "NORMAL", ""),
    ("claims", "claim_date", "NORMAL", ""),
    ("claims", "claim_type", "SENSITIVE", ""),
    ("claims", "amount", "SENSITIVE", ""),
    ("claims", "notes", "FREE_TEXT", ""),
]

_ARABIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
_PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_SLOT = re.compile(r"\{([A-Z_]+(?::[^}]+)?)\}")


# ------------------------------------------------------------------ rendering

def _script(rng: random.Random, text: str, ascii_p: float = 0.5, arabic_p: float = 0.4) -> str:
    r = rng.random()
    if r < ascii_p:
        return text
    if r < ascii_p + arabic_p:
        return text.translate(_ARABIC)
    return text.translate(_PERSIAN)


def _sep(rng: random.Random) -> str:
    r = rng.random()
    return "" if r < 0.5 else (" " if r < 0.82 else "-")


def _group(digits: str, sizes: list[int], sep: str) -> str:
    parts, i = [], 0
    for n in sizes:
        parts.append(digits[i:i + n])
        i += n
    parts.append(digits[i:])
    return sep.join(p for p in parts if p)


def render_id_like(rng: random.Random, digits: str) -> str:
    return _script(rng, _group(digits, [3, 3, 4], _sep(rng)))


def render_mobile(rng: random.Random, national9: str) -> str:
    sep, r = _sep(rng), rng.random()
    if r < 0.6:
        text = _group("0" + national9, [3, 3, 4], sep)
    elif r < 0.85:
        text = "+" + _group("966" + national9, [3, 2, 3, 4], sep)
    elif r < 0.9:
        text = "966" + national9
    else:
        text = _group("00966" + national9, [5, 2, 3, 4], sep)
    return _script(rng, text)


def render_iban(rng: random.Random, iban: str) -> str:
    text = _group(iban, [4] * 6, " ") if rng.random() < 0.5 else iban
    return _script(rng, text, ascii_p=0.85, arabic_p=0.15)


def lookalike_id(rng: random.Random) -> str:
    """10 digits starting with 1 or 2 that FAIL the ID checksum (invoice/order numbers)."""
    while True:
        d = rng.choice("12") + "".join(rng.choice("0123456789") for _ in range(9))
        if not s.is_valid_saudi_id(d):
            return d


# ------------------------------------------------------------------ note builder

@dataclass
class Person:
    full_name: str
    gender: str
    national_id: str
    mobile9: str
    iban: str
    email: str


@dataclass
class Note:
    parts: list[str] = field(default_factory=list)
    pos: int = 0
    labels: list[tuple[int, int, str]] = field(default_factory=list)
    negatives: list[tuple[int, int, str]] = field(default_factory=list)

    def add(self, text: str, label: str | None = None, negative: str | None = None) -> None:
        start, end = self.pos, self.pos + len(text)
        if label:
            self.labels.append((start, end, label))
        if negative:
            self.negatives.append((start, end, negative))
        self.parts.append(text)
        self.pos = end

    @property
    def text(self) -> str:
        return "".join(self.parts)


def _fill(note: Note, template: str, who: Person, rng: random.Random) -> None:
    last = 0
    for m in _SLOT.finditer(template):
        note.add(template[last:m.start()])
        last = m.end()
        slot = m.group(1)
        if slot == "NAME":
            note.add(who.full_name, "PERSON_NAME")
        elif slot == "FIRST":
            note.add(who.full_name.split(" ")[0], "PERSON_NAME")
        elif slot in ("OTHER_NAME_M", "OTHER_NAME_F"):
            note.add(s.gen_person_name(rng, slot[-1]), "PERSON_NAME")
        elif slot == "ID":
            note.add(render_id_like(rng, who.national_id), "SAUDI_ID")
        elif slot == "OTHER_ID":
            note.add(render_id_like(rng, s.gen_saudi_id(rng)), "SAUDI_ID")
        elif slot == "MOBILE":
            note.add(render_mobile(rng, who.mobile9), "MOBILE")
        elif slot == "OTHER_MOBILE":
            note.add(render_mobile(rng, s.canonical("MOBILE", s.gen_mobile(rng))), "MOBILE")
        elif slot == "IBAN":
            note.add(render_iban(rng, who.iban), "IBAN")
        elif slot == "EMAIL":
            note.add(who.email, "EMAIL")
        elif slot in ("INVOICE", "ORDER"):
            note.add(render_id_like(rng, lookalike_id(rng)), negative="LOOKALIKE_ID")
        elif slot == "POLICY":
            note.add(_script(rng, "".join(rng.choice("0123456789") for _ in range(8))), negative="NUMBER")
        elif slot == "AMOUNT":
            note.add(_script(rng, f"{rng.uniform(100, 50000):,.2f}"), negative="NUMBER")
        elif slot == "DATE":
            d = START + timedelta(days=rng.randrange((END - START).days))
            fmt = rng.choice(["%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"])
            note.add(_script(rng, d.strftime(fmt)), negative="NUMBER")
        elif slot.startswith("NW:"):
            note.add(slot[3:], negative="NAME_WORD")
        else:
            raise ValueError(f"unknown slot {slot}")
    note.add(template[last:])


def make_note(who: Person, rng: random.Random) -> Note:
    sentences = (
        rng.sample(IDENTIFIER_SENTENCES, rng.choices([0, 1, 2, 3], [25, 40, 25, 10])[0])
        + rng.sample(HARD_NEGATIVE_SENTENCES, rng.choices([0, 1, 2], [50, 38, 12])[0])
        + (rng.sample(NEUTRAL_SENTENCES, 1) if rng.random() < 0.5 else [])
    )
    if not sentences:
        sentences = rng.sample(NEUTRAL_SENTENCES, 1)
    rng.shuffle(sentences)
    note = Note()
    for i, template in enumerate(sentences):
        if i:
            note.add(" ")
        _fill(note, template, who, rng)
    return note


# ------------------------------------------------------------------ tables

def _claim_type(rng: random.Random, age: int, gender: str) -> str:
    names, weights = [], []
    for name, (_, w) in CLAIM_TYPES.items():
        if name == "أمومة" and not (gender == "F" and 18 <= age <= 45):
            w = 0
        if name in ("تنويم", "عمليات جراحية") and age > 55:
            w *= 2
        names.append(name)
        weights.append(w)
    return rng.choices(names, weights)[0]


def _amount(rng: random.Random, claim_type: str, age: int, prior: int) -> float:
    base = CLAIM_TYPES[claim_type][0]
    age_factor = 1 + max(0, age - 40) / 40
    prior_factor = 1 + 0.25 * min(prior, 6)
    return round(base * age_factor * prior_factor * rng.lognormvariate(0, 0.45), 2)


def _customer_storage_mobile(rng: random.Random, national9: str) -> str:
    r = rng.random()
    return ("0" + national9) if r < 0.85 else ("+966" + national9 if r < 0.95 else "966" + national9)


def generate(seed: int, n: int) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    city_names, city_weights = zip(*CITIES)

    customers, people = [], []
    for i in range(n):
        gender = rng.choice("MF")
        national_id = s.gen_saudi_id(rng, "1" if rng.random() < 0.7 else "2")
        mobile9 = s.canonical("MOBILE", s.gen_mobile(rng))
        person = Person(
            full_name=s.gen_person_name(rng, gender),
            gender=gender,
            national_id=national_id,
            mobile9=mobile9,
            iban=s.gen_iban(rng),
            email=s.gen_email(rng),
        )
        people.append(person)
        customers.append({
            "customer_id": 100001 + i,
            "full_name": person.full_name,
            # 3% of IDs stored with Arabic-Indic digits, as in messy real columns
            "national_id": national_id.translate(_ARABIC) if rng.random() < 0.03 else national_id,
            "mobile": _customer_storage_mobile(rng, mobile9),
            "city": rng.choices(city_names, city_weights)[0],
            "age": int(rng.triangular(18, 80, 35)),
            "gender": GENDER_AR[gender],
        })

    raw_claims = []
    for cust, person in zip(customers, people):
        k = rng.choices(*CLAIMS_PER_CUSTOMER)[0]
        dates = sorted(START + timedelta(days=rng.randrange((END - START).days)) for _ in range(k))
        for prior, d in enumerate(dates):
            ctype = _claim_type(rng, cust["age"], person.gender)
            note = make_note(person, rng)
            raw_claims.append((d, cust["customer_id"], ctype, _amount(rng, ctype, cust["age"], prior), note))
    raw_claims.sort(key=lambda c: (c[0], c[1]))

    claims, golden, negatives = [], [], []
    for row, (d, cid, ctype, amount, note) in enumerate(raw_claims):
        claims.append({
            "claim_id": 500001 + row,
            "customer_id": cid,
            "claim_date": d.isoformat(),
            "claim_type": ctype,
            "amount": f"{amount:.2f}",
            "notes": note.text,
        })
        golden += [dict(table="claims", row=row, column="notes", start=a, end=b, type=t) for a, b, t in note.labels]
        negatives += [dict(table="claims", row=row, column="notes", start=a, end=b, kind=k) for a, b, k in note.negatives]

    _self_check(claims, golden, negatives)
    columns = [dict(table=t, column=c, tag=tag, kind=k) for t, c, tag, k in GOLDEN_COLUMNS]
    return {"customers": customers, "claims": claims, "golden_labels": golden,
            "hard_negatives": negatives, "golden_columns": columns}


def _self_check(claims: list[dict], golden: list[dict], negatives: list[dict]) -> None:
    """Every planted identifier must validate; every look-alike must not."""
    for g in golden:
        span = claims[g["row"]]["notes"][g["start"]:g["end"]]
        if not s.is_valid(g["type"], span):
            raise AssertionError(f"planted {g['type']} at row {g['row']} does not validate")
    for h in negatives:
        if h["kind"] == "LOOKALIKE_ID":
            span = claims[h["row"]]["notes"][h["start"]:h["end"]]
            if s.is_valid("SAUDI_ID", span) or s.is_valid("MOBILE", span):
                raise AssertionError(f"hard negative at row {h['row']} validates")


def write(tables: dict[str, list[dict]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        with (out_dir / f"{name}.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n", type=int, default=3000, help="number of customers (2000-5000)")
    ap.add_argument("--out", type=Path, default=Path("data") / "demo")
    args = ap.parse_args(argv)
    tables = generate(args.seed, args.n)
    write(tables, args.out)
    counts = ", ".join(f"{k}={len(v)}" for k, v in tables.items())
    print(f"wrote {args.out}: {counts}")


if __name__ == "__main__":
    main()
