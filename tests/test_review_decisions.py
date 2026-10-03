"""Decisions on uncertain values: group statistics, cross-checks, admin overrides (nazeer.review)."""
import random

import pandas as pd

from nazeer import pipeline
from nazeer import saudi_ids as s
from nazeer.policy import load_policy
from nazeer.review import phrase_before

KEY = b"review-decisions-test-key-0123456789"
FILLER = ["تمت المتابعة مع العميل في الفرع الرئيسي", "طلب العميل تحديث بيانات العنوان الوطني",
          "لا توجد ملاحظات إضافية على هذا السجل", "تم إرسال كشف الحساب الشهري بنجاح"]


def random_ref(rng):
    return "1" + "".join(str(rng.randrange(10)) for _ in range(9))


def build(notes, national_ids=None):
    n = len(notes)
    rng = random.Random(5)
    ids = national_ids or [s.gen_saudi_id(rng, "1") for _ in range(n)]
    return {"t": pd.DataFrame({"customer": [f"C{i:04d}" for i in range(n)], "national_id": ids,
                               "notes": notes}, dtype=object)}


def run(tables, decisions=None):
    an = pipeline.analyze(tables, "t")
    res = pipeline.run_masked(an, load_policy(pipeline.DEFAULT_POLICY), KEY,
                              {"t.notes": {"tag": "FREE_TEXT", "kind": None}}, review_decisions=decisions)
    return an, res, res.report["free_text"]["review"]


def group(review, phrase):
    return next(g for g in review["groups"] if g["phrase"] == s.normalize_name(phrase))


def test_phrase_is_the_words_right_before_the_number():
    t = "يرجى مراجعة رقم الطلب: 1234567890 لدى المختبر"
    assert phrase_before(t, t.index("1234")) == s.normalize_name("رقم الطلب")
    assert phrase_before("12 3456789012", 3) == ""


def test_random_numbers_after_a_phrase_are_kept_automatically():
    rng = random.Random(1)
    notes = [f"رقم الطلب {random_ref(rng)} لدى المختبر" for _ in range(120)] + FILLER * 5
    an, res, review = run(build(notes))
    g = group(review, "رقم الطلب")
    assert g["population"] == 120 and 4 <= g["passed"] <= 25          # ~10% pass the check digit by chance
    assert g["auto"] == "keep" and g["reason"]["code"] == "chance" and g["pending"] == 0
    kept = [v for v in g["values"]]
    assert kept and all(v["final"] == "keep" for v in kept)
    for v in kept:                                                     # left unchanged in the twin
        assert res.twin["t"]["notes"].iat[v["row"]] == an.tables["t"]["notes"].iat[v["row"]]
    assert res.report["verdict"] == "PASS"


def test_real_ids_after_a_phrase_are_replaced_automatically():
    rng = random.Random(2)
    ids = [s.gen_saudi_id(rng, "1") for _ in range(40)]
    notes = [f"رقم الوثيقة {v} سارية حتى نهاية العام" for v in ids] + FILLER * 5
    an, res, review = run(build(notes))
    g = group(review, "رقم الوثيقة")
    assert g["population"] == 40 and g["passed"] == 40 and g["auto"] == "replace" and g["reason"]["code"] == "ids"
    for v in g["values"]:
        assert ids[v["row"]] not in res.twin["t"]["notes"].iat[v["row"]]


def test_mixed_group_goes_to_the_admin_and_overrides_work_per_group_and_value():
    rng = random.Random(3)
    nums = [s.gen_saudi_id(rng, "1") if i % 2 == 0 else random_ref(rng) for i in range(24)]
    notes = [f"المرجع رقم {v} في النظام" for v in nums] + FILLER * 5
    an, res, review = run(build(notes))
    g = group(review, "المرجع رقم")
    assert g["auto"] is None and g["reason"]["code"] == "mixed" and g["pending"] == g["count"] > 0
    assert review["totals"]["pending"] == g["count"]
    for v in g["values"]:                                                # undecided: unchanged
        assert res.twin["t"]["notes"].iat[v["row"]] == an.tables["t"]["notes"].iat[v["row"]]
    first = g["values"][0]
    decisions = {"groups": {g["key"]: "keep"}, "values": {g["key"]: {f"{first['row']}:{first['start']}": "replace"}}}
    _, res2, review2 = run(build(notes), decisions)
    g2 = group(review2, "المرجع رقم")
    assert g2["pending"] == 0 and review2["totals"]["admin"] == g2["count"]
    finals = {(v["row"], v["final"]) for v in g2["values"]}
    assert (first["row"], "replace") in finals
    assert res2.twin["t"]["notes"].iat[first["row"]] != an.tables["t"]["notes"].iat[first["row"]]
    others = [v for v in g2["values"] if v["row"] != first["row"]]
    assert all(res2.twin["t"]["notes"].iat[v["row"]] == an.tables["t"]["notes"].iat[v["row"]] for v in others)


def test_numbers_matching_the_id_column_are_replaced_even_in_a_kept_group():
    rng = random.Random(4)
    ids = [s.gen_saudi_id(rng, "1") for _ in range(130)]
    refs = [random_ref(rng) for _ in range(120)]
    notes = [f"رقم الطلب {r} لدى المختبر" for r in refs] + [f"رقم الطلب {ids[0]} لدى المختبر"] + FILLER * 2 + ["تم"]
    an, res, review = run(build(notes, ids[:len(notes)]))
    g = group(review, "رقم الطلب")
    assert g["auto"] == "keep"
    row = len(refs)
    v = next(v for v in g["values"] if v["row"] == row)
    assert v["final"] == "replace" and v["reason"]["code"] == "matches_id_column"
    assert ids[0] not in res.twin["t"]["notes"].iat[row]


def test_switching_decisions_back_and_forth_loses_nothing():
    rng = random.Random(6)
    nums = [s.gen_saudi_id(rng, "1") if i % 2 == 0 else random_ref(rng) for i in range(24)]
    notes = [f"المرجع رقم {v} في النظام" for v in nums] + FILLER * 5
    an, _, review = run(build(notes))
    key = group(review, "المرجع رقم")["key"]
    _, a1, _ = run(build(notes), {"groups": {key: "replace"}})
    _, b, _ = run(build(notes), {"groups": {key: "keep"}})
    _, a2, _ = run(build(notes), {"groups": {key: "replace"}})
    assert a1.twin["t"].equals(a2.twin["t"])                              # deterministic: same twin again
    assert b.twin["t"]["notes"].tolist()[:24] == notes[:24]               # "keep" restores the originals
    changed = [i for i in range(len(notes)) if a1.twin["t"]["notes"].iat[i] != b.twin["t"]["notes"].iat[i]]
    assert changed and all(i < 24 for i in changed)                       # only the decided cells differ
