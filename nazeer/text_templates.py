"""Free-text templates for the SYNTHETIC twin (mode 5b).

Hand-written and deliberately different from the demo generator's templates:
synthetic mode never reuses real text. Slots are filled with the synthetic row's
own generated identifiers, so the twin stays realistic for testing.
"""
from __future__ import annotations

import random

SYNTHETIC_NOTE_TEMPLATES = [
    "راجع {NAME} قسم المطالبات وزوّدنا برقم التواصل {MOBILE}.",
    "تمت مطابقة رقم الهوية {ID} مع بيانات الوثيقة.",
    "يُرجى إشعار {FIRST} بنتيجة المراجعة عبر الجوال {MOBILE}.",
    "استلمنا طلب {NAME} وسيتم الرد خلال خمسة أيام عمل.",
    "المرفقات مكتملة ولا يلزم إجراء إضافي.",
    "أُحيلت المطالبة إلى المراجعة الطبية الثانية.",
    "تم تحديث بيانات المستفيد صاحب الهوية {ID}.",
    "لا ملاحظات على هذه المطالبة.",
]


def synthetic_note(rng: random.Random, name: str, id_: str, mobile: str) -> str:
    k = rng.choice([1, 1, 2])
    parts = rng.sample(SYNTHETIC_NOTE_TEMPLATES, k)
    first = name.split(" ")[0] if name else ""
    return " ".join(p.format(NAME=name, FIRST=first, ID=id_, MOBILE=mobile) for p in parts)
