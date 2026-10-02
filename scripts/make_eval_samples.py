"""Two fictional evaluation files with their answer keys, written independently of the hospital test
file and of Nazeer's own demo generator (own name lists, own validators, own mess patterns):

* bank_customers_test.csv      semicolon CSV, a title line above the header, grouped/Arabic digits,
                               e-mails, IBANs in several shapes, look-alike reference numbers;
* insurance_claims_test.xlsx   two sheets (members, claims) linked by membership number, glued
                               identifiers, titles before names, look-alike policy numbers.

    python scripts\\make_eval_samples.py --out web\\public\\samples [--seed 7]
"""
from __future__ import annotations

import argparse
import csv
import io
import random
from pathlib import Path

FIRST_M = ["ثامر", "مشاري", "مهند", "رائد", "وليد", "بندر", "هشام", "عمار", "طلال", "نايف", "أنس", "يزيد", "غازي",
           "صالح", "إياد", "مازن", "حسام", "منصور", "عادل", "باسل"]
FIRST_F = ["رهف", "جود", "لجين", "دانة", "شهد", "ريما", "غدير", "أريج", "ميار", "لولوة", "تهاني", "بشرى", "عهود",
           "مها", "سديم", "رزان", "نجلاء", "وعد", "هيفاء", "منيرة"]
FAMILY = ["الغامدي", "الزهراني", "الشهري", "البلوي", "الحويطي", "العمري", "الجهني", "الصاعدي", "الرويلي", "السلمي",
          "المالكي", "الثبيتي", "الحازمي", "اليامي", "الفيفي", "العنزي", "الشريف", "باعشن", "الأحمدي", "المحمدي"]
BRANCHES = ["فرع الشمال", "فرع العليا", "فرع الخبر", "فرع المدينة", "فرع أبها"]
PROVIDERS = ["مستشفى الأمل", "مجمع الشفاء الطبي", "عيادات النخبة", "مستشفى الرعاية", "صيدلية الوفاء"]
NATIONALITIES = ["سعودي", "سعودية", "يمني", "مصري", "سوداني", "باكستاني"]
AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


# ---------------------------------------------------------------- own generators and validators

def gen_id(rng: random.Random, first: str) -> str:
    body = [int(first)] + [rng.randint(0, 9) for _ in range(8)]
    for check in range(10):
        digits = body + [check]
        total = 0
        for i, d in enumerate(digits):
            x = d * 2 if i % 2 == 0 else d
            total += x - 9 if x > 9 else x
        if total % 10 == 0:
            return "".join(map(str, digits))
    raise AssertionError


def id_valid(v: str) -> bool:
    if len(v) != 10 or not v.isdigit() or v[0] not in "12":
        return False
    total = 0
    for i, c in enumerate(v):
        x = int(c) * 2 if i % 2 == 0 else int(c)
        total += x - 9 if x > 9 else x
    return total % 10 == 0


def near_miss_id(rng: random.Random) -> str:
    """A 10-digit number starting with 1 that fails the checksum (a plausible reference number)."""
    while True:
        v = "1" + "".join(str(rng.randint(0, 9)) for _ in range(9))
        if not id_valid(v):
            return v


def gen_mobile(rng: random.Random) -> str:
    return "05" + rng.choice("0345689") + "".join(str(rng.randint(0, 9)) for _ in range(7))


def gen_iban(rng: random.Random) -> str:
    bban = "".join(str(rng.randint(0, 9)) for _ in range(20))  # SA + 2 check digits + 20 = 24 characters
    n = int(bban + "2810" + "00")  # S=28 A=10, check digits 00
    check = 98 - n % 97
    return f"SA{check:02d}{bban}"


def gen_email(rng: random.Random, i: int) -> str:
    user = rng.choice(["m", "a", "s", "r", "k", "n"]) + rng.choice(["ali", "omar", "sara", "noor", "fahad", "dana"])
    return f"{user}.{i}{rng.choice(['', '_', '.'])}{rng.randint(10, 99)}@{rng.choice(['mail.example.com', 'example.org', 'inbox.example.net'])}"


# ---------------------------------------------------------------- formatting messes

def fmt_mobile(rng: random.Random, m: str) -> str:
    style = rng.randrange(6)
    if style == 0:
        return m
    if style == 1:
        return f"{m[:3]}-{m[3:6]}-{m[6:]}"
    if style == 2:
        return f"+966 {m[1:3]} {m[3:6]} {m[6:]}"
    if style == 3:
        return m.translate(AR_DIGITS)
    if style == 4:
        return "00966" + m[1:]
    return f"({m[:3]}) {m[3:6]} {m[6:]}"


def fmt_id(rng: random.Random, v: str) -> str:
    style = rng.randrange(5)
    if style == 0:
        return v.translate(AR_DIGITS)
    if style == 1:
        return f"{v[0]} {v[1:4]} {v[4:7]} {v[7:]}"
    return v


def fmt_iban(rng: random.Random, v: str) -> str:
    style = rng.randrange(4)
    if style == 0:
        return " ".join(v[i:i + 4] for i in range(0, 24, 4))
    if style == 1:
        return v.lower()
    if style == 2:
        return "SA " + v[2:]
    return v


def person(rng: random.Random, four: bool = False) -> str:
    female = rng.random() < 0.45
    first = rng.choice(FIRST_F if female else FIRST_M)
    if four:
        return f"{first} {rng.choice(FIRST_M)} {rng.choice(FIRST_M)} {rng.choice(FAMILY)}"
    return f"{first} {rng.choice(FAMILY)}"


class Key:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, row: int, file_id: str, column: str, kind: str, value: str, expected: str = "replace"):
        self.rows.append({"row": row, "file_id": file_id, "column": column, "type": kind,
                          "planted_value": value, "expected": expected})

    def write(self, path: Path):
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["row", "file_id", "column", "type", "planted_value", "expected"])
            w.writeheader()
            w.writerows(self.rows)


# ---------------------------------------------------------------- bank customers

def bank(rng: random.Random, n: int = 450) -> tuple[str, Key]:
    cols = ["معرف العميل", "الاسم الرباعي", "رقم السجل المدني", "هاتف التواصل", "البريد الالكتروني",
            "رقم الحساب الدولي", "نوع الحساب", "الرصيد", "تاريخ فتح الحساب", "الفرع", "ملاحظات الموظف"]
    key, out = Key(), []
    for i in range(n):
        cid = f"C-24-{i + 1:05d}"
        name = person(rng, four=True)
        nid = gen_id(rng, rng.choice("1112"))
        mob = gen_mobile(rng)
        email = gen_email(rng, i) if rng.random() < 0.8 else rng.choice(["", "غير متوفر"])
        iban = gen_iban(rng)
        r = {"معرف العميل": cid, "الاسم الرباعي": name, "رقم السجل المدني": fmt_id(rng, nid),
             "هاتف التواصل": fmt_mobile(rng, mob), "البريد الالكتروني": email,
             "رقم الحساب الدولي": fmt_iban(rng, iban),
             "نوع الحساب": rng.choice(["جاري", "جاري ", "توفير", " توفير", "استثمار"]),
             "الرصيد": rng.choice([f"{rng.randint(100, 900000):,}", str(rng.randint(100, 90000)),
                                   str(rng.randint(100, 9000)).translate(AR_DIGITS)]),
             "تاريخ فتح الحساب": rng.choice([f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/20{rng.randint(10, 24)}",
                                             f"20{rng.randint(10, 24)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"]),
             "الفرع": rng.choice(BRANCHES), "ملاحظات الموظف": ""}
        row = i + 1
        key.add(row, cid, "الاسم الرباعي", "PERSON_NAME", name)
        key.add(row, cid, "رقم السجل المدني", "SAUDI_ID", r["رقم السجل المدني"])
        key.add(row, cid, "هاتف التواصل", "MOBILE", r["هاتف التواصل"])
        if "@" in email:
            key.add(row, cid, "البريد الالكتروني", "EMAIL", email)
        key.add(row, cid, "رقم الحساب الدولي", "IBAN", r["رقم الحساب الدولي"])
        note = rng.randrange(10)
        if note == 0:
            v = fmt_id(rng, gen_id(rng, "1"))
            r["ملاحظات الموظف"] = f"تم التحقق من الهوية رقم {v} في الفرع"
            key.add(row, cid, "ملاحظات الموظف", "SAUDI_ID", v)
        elif note == 1:
            v = fmt_iban(rng, gen_iban(rng))
            r["ملاحظات الموظف"] = f"العميل طلب تحويل راتبه إلى الحساب {v}"
            key.add(row, cid, "ملاحظات الموظف", "IBAN", v)
        elif note == 2:
            agent, m = person(rng), fmt_mobile(rng, gen_mobile(rng))
            r["ملاحظات الموظف"] = f"الوكيل {agent} يتابع الطلب على {m}"
            key.add(row, cid, "ملاحظات الموظف", "PERSON_NAME", agent)
            key.add(row, cid, "ملاحظات الموظف", "MOBILE", m)
        elif note == 3:
            e = gen_email(rng, 9000 + i)
            r["ملاحظات الموظف"] = f"أرسل كشف الحساب إلى {e} بناءً على طلبه"
            key.add(row, cid, "ملاحظات الموظف", "EMAIL", e)
        elif note == 4:
            v = gen_id(rng, "1")  # checksum-valid, but it is a transaction number
            r["ملاحظات الموظف"] = f"رقم العملية {v} قيد المعالجة"
            key.add(row, cid, "ملاحظات الموظف", "SAUDI_ID", v, "review")
        elif note == 5:
            v = near_miss_id(rng)
            r["ملاحظات الموظف"] = f"مرجع التحويل {v} بتاريخ اليوم"
            key.add(row, cid, "ملاحظات الموظف", "SAUDI_ID", v, "ignore")
        elif note == 6:
            r["ملاحظات الموظف"] = f"البطاقة المنتهية بـ {rng.randint(1000, 9999)} أوقفت مؤقتاً"
        elif note == 7:
            r["ملاحظات الموظف"] = rng.choice(["لا يوجد", "-", "NULL"])
        else:
            r["ملاحظات الموظف"] = rng.choice(["العميل راضٍ عن الخدمة", "طلب رفع حد البطاقة", "تحديث بيانات العنوان"])
        out.append(r)
    for j in rng.sample(range(n), 8):  # exact duplicates
        out.append(dict(out[j]))
    buf = io.StringIO()
    buf.write("كشف عملاء الفروع - سري - للاستخدام الداخلي\n")
    w = csv.DictWriter(buf, fieldnames=cols, delimiter=";")
    w.writeheader()
    w.writerows(out)
    return buf.getvalue(), key


# ---------------------------------------------------------------- insurance claims (two sheets)

def insurance(rng: random.Random, n_members: int = 260, n_claims: int = 520) -> tuple[bytes, Key]:
    from openpyxl import Workbook

    key = Key()
    members = []
    for i in range(n_members):
        mid = f"INS-{70000 + i}"
        name = person(rng)
        nid = gen_id(rng, rng.choice("12"))
        mob = gen_mobile(rng)
        members.append([mid, name, nid if rng.random() < 0.8 else nid.translate(AR_DIGITS),
                        rng.choice(NATIONALITIES), f"{rng.randint(1950, 2015)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                        fmt_mobile(rng, mob)])
        key.add(i + 1, mid, "اسم المؤمن له", "PERSON_NAME", name)
        key.add(i + 1, mid, "هوية / إقامة", "SAUDI_ID", members[-1][2])
        key.add(i + 1, mid, "جوال", "MOBILE", members[-1][5])
    claims = []
    for j in range(n_claims):
        cid = f"CLM-{900000 + j}"
        mem = rng.choice(members)
        desc = ""
        kind = rng.randrange(9)
        if kind == 0:
            m = gen_mobile(rng)
            v = "966" + m[1:]
            desc = f"اتصل المؤمن له من الرقم {v} للاستفسار"
            key.add(j + 1, cid, "وصف المطالبة", "MOBILE", v)
        elif kind == 1:
            v = gen_id(rng, "2")
            desc = f"تم إرفاق صورة هوية:{v} للمرافق"
            key.add(j + 1, cid, "وصف المطالبة", "SAUDI_ID", v)
        elif kind == 2:
            nm = person(rng)
            desc = f"صاحب المطالبة السيد/ {nm} راجع قسم الطوارئ"
            key.add(j + 1, cid, "وصف المطالبة", "PERSON_NAME", nm)
        elif kind == 3:
            v = gen_id(rng, "1")
            desc = f"رقم الوثيقة {v} سارية حتى نهاية العام"
            key.add(j + 1, cid, "وصف المطالبة", "SAUDI_ID", v, "review")
        elif kind == 4:
            v = near_miss_id(rng)
            desc = f"مرتبطة بالمطالبة السابقة {v}"
            key.add(j + 1, cid, "وصف المطالبة", "SAUDI_ID", v, "ignore")
        elif kind == 5:
            e = gen_email(rng, 5000 + j)
            desc = f"يرجى مراسلة المؤمن له على {e}"
            key.add(j + 1, cid, "وصف المطالبة", "EMAIL", e)
        elif kind == 6:
            v = fmt_iban(rng, gen_iban(rng))
            desc = f"يُحوَّل التعويض إلى آيبان {v}"
            key.add(j + 1, cid, "وصف المطالبة", "IBAN", v)
        else:
            desc = rng.choice(["مراجعة دورية", "صرف أدوية مزمنة", "أشعة مقطعية", "غير متوفر", ""])
        claims.append([cid, mem[0], rng.choice([f"{rng.randint(1, 28)}/{rng.randint(1, 12)}/2025",
                                                f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"]),
                       rng.choice(PROVIDERS), rng.choice([f"{rng.randint(100, 50000):,}.00", str(rng.randint(100, 9000))]), desc])
    wb = Workbook()
    ws = wb.active
    ws.title = "المؤمن لهم"
    ws.append(["رقم العضوية", "اسم المؤمن له", "هوية / إقامة", "الجنسية", "تاريخ الميلاد", "جوال"])
    for r in members:
        ws.append(r)
    ws2 = wb.create_sheet("المطالبات")
    ws2.append(["رقم المطالبة", "رقم العضوية", "تاريخ المطالبة", "مقدم الخدمة", "قيمة المطالبة", "وصف المطالبة"])
    for r in claims:
        ws2.append(r)
    ws2.append([None] * 6)  # trailing empty row
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), key


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("web/public/samples"))
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    text, k = bank(random.Random(a.seed))
    (a.out / "bank_customers_test.csv").write_text(text, encoding="utf-8-sig", newline="")
    k.write(a.out / "bank_customers_answer_key.csv")
    data, k2 = insurance(random.Random(a.seed + 1))
    (a.out / "insurance_claims_test.xlsx").write_bytes(data)
    k2.write(a.out / "insurance_claims_answer_key.csv")
    print(f"bank: {len(k.rows)} key rows; insurance: {len(k2.rows)} key rows -> {a.out}")


if __name__ == "__main__":
    main()
