"""Two CLEAN fictional datasets with answer keys: the common real case (data that is already tidy and
is shared for model training and testing). Written independently: its own name lists, validators and
generators (no code or names from make_eval_samples.py, the hospital test file or the demo generator).

* clinic_appointments_clean.csv   1,000 appointments, ISO dates, consistent types, label «لم_يحضر»
* bank_accounts_clean.csv         600 customers: name, national ID / iqama, mobile, IBAN, e-mail, notes

    python scripts\\make_clean_samples.py --out web\\public\\samples [--seed 11]
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import random
from datetime import date, timedelta
from pathlib import Path

MALE = ["سلمان", "تركي", "فيصل", "حمد", "ناصر", "عبدالرحمن", "يوسف", "إبراهيم", "معاذ", "أسامة", "قصي", "هاني",
        "جاسم", "عبدالعزيز", "سامي", "نواف"]
FEMALE = ["أمل", "فاطمة", "خلود", "روان", "ليان", "جواهر", "نورة", "ابتسام", "حصة", "مشاعل", "أسماء", "منى",
          "سلمى", "دلال", "هالة", "عبير"]
FAMILY = ["الشهراني", "المري", "الهاجري", "العجمي", "الجبرين", "السديري", "التميمي", "الكثيري", "باوزير", "الزامل",
          "العيسى", "النعيمي", "الأنصاري", "البيشي", "الخثعمي", "الصقير"]
CLINICS = ["الباطنية", "الأطفال", "العيون", "الأسنان", "الجلدية", "العظام"]
BRANCHES = ["الرياض - الملز", "جدة - الروضة", "الدمام - الشاطئ", "مكة - العزيزية", "أبها - المنسك"]
ACCOUNT_TYPES = ["جاري", "توفير", "استثماري"]


def luhn_national(rng: random.Random, first: str) -> str:
    """A 10-digit national ID / iqama number passing the official check digit."""
    digits = [int(first)] + [rng.randrange(10) for _ in range(8)]
    total = 0
    for i, d in enumerate(digits):
        v = d * 2 if i % 2 == 0 else d
        total += v // 10 + v % 10
    return "".join(map(str, digits)) + str((10 - total % 10) % 10)


def is_national(v: str) -> bool:
    if len(v) != 10 or not v.isdigit() or v[0] not in "12":
        return False
    total = sum((int(c) * 2 // 10 + int(c) * 2 % 10) if i % 2 == 0 else int(c) for i, c in enumerate(v))
    return total % 10 == 0


def non_national(rng: random.Random) -> str:
    while True:
        v = "1" + "".join(str(rng.randrange(10)) for _ in range(9))
        if not is_national(v):
            return v


def mobile(rng: random.Random) -> str:
    return "05" + str(rng.choice([0, 3, 4, 5, 6, 9])) + "".join(str(rng.randrange(10)) for _ in range(7))


def saudi_iban(rng: random.Random) -> str:
    account = "".join(str(rng.randrange(10)) for _ in range(20))
    check = 98 - int(account + "281000") % 97
    return f"SA{check:02d}{account}"


def full_name(rng: random.Random) -> tuple[str, str]:
    female = rng.random() < 0.5
    return f"{rng.choice(FEMALE if female else MALE)} {rng.choice(FAMILY)}", "أنثى" if female else "ذكر"


class AnswerKey:
    FIELDS = ["row", "file_id", "column", "type", "planted_value", "expected"]

    def __init__(self):
        self.rows: list[dict] = []

    def add(self, row, file_id, column, kind, value, expected="replace"):
        self.rows.append(dict(zip(self.FIELDS, [row, file_id, column, kind, value, expected])))

    def write(self, path: Path):
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=self.FIELDS)
            w.writeheader()
            w.writerows(self.rows)


def _csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------- clinic appointments (model training)

def clinic(rng: random.Random, n: int = 1000) -> tuple[str, AnswerKey]:
    key, rows = AnswerKey(), []
    start = date(2026, 1, 4)
    for i in range(n):
        aid = f"APT-2026-{i + 1:06d}"
        name, gender = full_name(rng)
        nid = luhn_national(rng, "1" if rng.random() < 0.85 else "2")
        mob = mobile(rng)
        booked = start + timedelta(days=rng.randrange(0, 240))
        lead = rng.choice([0, 1, 2, 3, 5, 7, 10, 14, 21, 30, 45])
        visit = booked + timedelta(days=lead)
        missed = rng.choice([0, 0, 0, 0, 1, 1, 2, 3])
        reminder = rng.random() < 0.6
        insured = rng.random() < 0.7
        age = rng.randint(1, 85)
        logit = -2.2 + 0.035 * lead + 0.55 * missed - 0.8 * reminder - 0.3 * insured
        no_show = int(rng.random() < 1 / (1 + math.exp(-logit)))
        note = ""
        k = rng.randrange(10)
        row = i + 1
        if k == 0:
            m2 = mobile(rng)
            note = f"طلب المريض التواصل معه على الرقم {m2} لتأكيد الموعد"
            key.add(row, aid, "ملاحظة_الاستقبال", "MOBILE", m2)
        elif k == 1:
            other, _ = full_name(rng)
            note = f"يرافق المريض {other} وهو المسؤول عن متابعة الحالة"
            key.add(row, aid, "ملاحظة_الاستقبال", "PERSON_NAME", other)
        elif k == 2:
            v = luhn_national(rng, "2")
            note = f"تم التحقق من إقامة المرافق رقم {v} عند الاستقبال"
            key.add(row, aid, "ملاحظة_الاستقبال", "SAUDI_ID", v)
        elif k == 3:
            v = luhn_national(rng, "1")  # checksum-valid, but a booking reference
            note = f"رقم الحجز المرجعي {v} صادر من بوابة المواعيد"
            key.add(row, aid, "ملاحظة_الاستقبال", "SAUDI_ID", v, "review")
        elif k == 4:
            v = non_national(rng)
            note = f"رقم الإحالة {v} من المركز الصحي التابع للحي"
            key.add(row, aid, "ملاحظة_الاستقبال", "SAUDI_ID", v, "ignore")
        else:
            note = rng.choice(["حضر المريض قبل الموعد بربع ساعة وأنهى إجراءات التسجيل",
                               "يحتاج المريض إلى تحاليل دم قبل زيارة الطبيب القادمة",
                               "تم تأجيل الموعد السابق بطلب من المريض بسبب السفر",
                               "المريض يفضّل المواعيد الصباحية في بداية الأسبوع",
                               "أُرسل تذكير بالموعد قبل يومين عبر الرسائل النصية"])
        rows.append({"رقم_الموعد": aid, "اسم_المريض": name, "رقم_الهوية": nid, "رقم_الجوال": mob,
                     "العمر": age, "الجنس": gender, "العيادة": rng.choice(CLINICS),
                     "تاريخ_الحجز": booked.isoformat(), "تاريخ_الموعد": visit.isoformat(), "أيام_الانتظار": lead,
                     "مواعيد_فائتة_سابقاً": missed, "تذكير_برسالة": "نعم" if reminder else "لا",
                     "لديه_تأمين": "نعم" if insured else "لا", "ملاحظة_الاستقبال": note, "لم_يحضر": no_show})
        key.add(row, aid, "اسم_المريض", "PERSON_NAME", name)
        key.add(row, aid, "رقم_الهوية", "SAUDI_ID", nid)
        key.add(row, aid, "رقم_الجوال", "MOBILE", mob)
    return _csv(rows), key


# ---------------------------------------------------------------- bank accounts

def bank(rng: random.Random, n: int = 600) -> tuple[str, AnswerKey]:
    key, rows = AnswerKey(), []
    for i in range(n):
        cid = f"CUS-{500000 + i}"
        name, _ = full_name(rng)
        nid = luhn_national(rng, "1" if rng.random() < 0.75 else "2")
        mob, iban = mobile(rng), saudi_iban(rng)
        email = f"user{i + 1:04d}@bank-mail.example.com"
        joined = date(2015, 1, 1) + timedelta(days=rng.randrange(0, 4000))
        balance = round(rng.lognormvariate(9.5, 1.1), 2)
        note = ""
        k = rng.randrange(8)
        row = i + 1
        if k == 0:
            v = saudi_iban(rng)
            note = f"يحوّل العميل راتبه شهرياً من حساب آخر برقم آيبان {v}"
            key.add(row, cid, "ملاحظات_الموظف", "IBAN", v)
        elif k == 1:
            m2 = mobile(rng)
            note = f"رقم جوال بديل للتواصل عند الطوارئ {m2}"
            key.add(row, cid, "ملاحظات_الموظف", "MOBILE", m2)
        elif k == 2:
            v = luhn_national(rng, "1")
            note = f"رقم العملية {v} لتحديث بيانات الحساب"
            key.add(row, cid, "ملاحظات_الموظف", "SAUDI_ID", v, "review")
        else:
            note = rng.choice(["العميل يفضّل التواصل عبر البريد الإلكتروني", "تم تحديث عنوان السكن الوطني",
                               "طلب العميل رفع حد البطاقة الائتمانية", "حساب نشط ولا توجد ملاحظات على السجل",
                               "فُعّلت الخدمات المصرفية عبر الإنترنت بنجاح"])
        rows.append({"رقم_العميل": cid, "الاسم_الكامل": name, "رقم_الهوية_أو_الإقامة": nid, "الجوال": mob,
                     "الآيبان": iban, "البريد_الإلكتروني": email, "الفرع": rng.choice(BRANCHES),
                     "نوع_الحساب": rng.choice(ACCOUNT_TYPES), "الرصيد": f"{balance:.2f}",
                     "تاريخ_الانضمام": joined.isoformat(), "ملاحظات_الموظف": note})
        key.add(row, cid, "الاسم_الكامل", "PERSON_NAME", name)
        key.add(row, cid, "رقم_الهوية_أو_الإقامة", "SAUDI_ID", nid)
        key.add(row, cid, "الجوال", "MOBILE", mob)
        key.add(row, cid, "الآيبان", "IBAN", iban)
        key.add(row, cid, "البريد_الإلكتروني", "EMAIL", email)
    return _csv(rows), key


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("web/public/samples"))
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    text, k = clinic(random.Random(a.seed))
    (a.out / "clinic_appointments_clean.csv").write_text(text, encoding="utf-8", newline="")
    k.write(a.out / "clinic_appointments_answer_key.csv")
    text2, k2 = bank(random.Random(a.seed + 1))
    (a.out / "bank_accounts_clean.csv").write_text(text2, encoding="utf-8", newline="")
    k2.write(a.out / "bank_accounts_answer_key.csv")
    print(f"clinic: {len(k.rows)} key rows; bank: {len(k2.rows)} key rows -> {a.out}")


if __name__ == "__main__":
    main()
