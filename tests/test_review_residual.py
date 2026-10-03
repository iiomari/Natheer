"""Review band for uncertain free-text values, IBANs with a failing checksum, the residual scan,
and recall against independent answer keys (three files, three sectors)."""
from pathlib import Path

import pandas as pd
import pytest

from nazeer import pipeline
from nazeer.detect import find_spans
from nazeer.ingest import read_files
from nazeer.policy import load_policy

KEY = b"review-residual-test-key-0123456789"
SAMPLES = Path(__file__).resolve().parents[1] / "web" / "public" / "samples"
VALID_ID = "1000000008"        # passes the national ID checksum
VALID_IBAN = "SA0380000000608010167519"


def _run(tables, **kw):
    an = pipeline.analyze(tables, "t")
    return an, pipeline.run_masked(an, load_policy(pipeline.DEFAULT_POLICY), KEY, **kw)


def _notes(*texts):
    rows = len(texts)
    mobiles = [f"05{(31 + i) % 100:02d}{(7 * i) % 1000000:06d}" for i in range(rows)]
    return {"t": pd.DataFrame({"id": [f"R{i}" for i in range(rows)], "mobile": mobiles,
                               "notes": list(texts)}, dtype=object)}


# ---------------------------------------------------------------- review band

def test_a_lone_checksum_valid_number_after_an_order_word_waits_for_the_admin():
    texts = [f"رقم الطلب {VALID_ID} لدى المختبر"] + ["تمت المتابعة مع المريض في العيادة"] * 30
    an, res = _run(_notes(*texts), overrides={"t.notes": {"tag": "FREE_TEXT", "kind": None}})
    assert VALID_ID in res.twin["t"]["notes"].iat[0]               # too few to decide: unchanged, pending
    assert res.report["free_text"]["review"]["totals"]["pending"] == 1
    assert res.report["verdict"] == "PASS"                           # a decision, not a leak
    key = res.report["free_text"]["review"]["groups"][0]["key"]
    _, decided = _run(_notes(*texts), overrides={"t.notes": {"tag": "FREE_TEXT", "kind": None}},
                      review_decisions={"groups": {key: "replace"}})
    assert VALID_ID not in decided.twin["t"]["notes"].iat[0]
    assert decided.report["free_text"]["review"]["totals"] == {"auto": 0, "admin": 1, "pending": 0, "replace": 1, "keep": 0}


def test_id_in_identifying_context_is_still_replaced():
    texts = [f"المريض أرسل هويته {VALID_ID} مع التحويل"] + ["تمت المتابعة"] * 30
    _, res = _run(_notes(*texts), overrides={"t.notes": {"tag": "FREE_TEXT", "kind": None}})
    assert VALID_ID not in res.twin["t"]["notes"].iat[0]


# ---------------------------------------------------------------- IBAN shapes

def test_spaced_iban_with_bad_checksum_next_to_account_word_is_an_iban():
    bad = "SA48 8018 4001 9273 4690 0330"  # exact Saudi shape, failing mod-97 (a typo)
    spans = find_spans(f"طلب استرداد المبلغ على الآيبان {bad}", names=False)
    assert [(k, c) for _, _, k, c, _ in spans] == [("IBAN", 0.9)]
    alone = find_spans(f"المرجع {bad}", names=False)
    assert [(k, c) for _, _, k, c, _ in alone] == [("IBAN", 0.6)]   # no context: review


def test_valid_iban_in_lower_case_and_groups():
    v = VALID_IBAN.lower()
    assert [k for _, _, k, _, _ in find_spans(f"حوّل إلى {v}", names=False)] == ["IBAN"]
    grouped = " ".join(VALID_IBAN[i:i + 4] for i in range(0, 24, 4))
    assert [k for _, _, k, _, _ in find_spans(f"الحساب {grouped}", names=False)] == ["IBAN"]


# ---------------------------------------------------------------- general detection fixes

def test_mobile_in_brackets_and_unknown_first_name_before_family_name():
    spans = find_spans("الوكيل عمار الغامدي يتابع الطلب على (054) 818 8763")
    kinds = {(k, t) for a, b, k, _, _ in spans for t in ["الوكيل عمار الغامدي يتابع الطلب على (054) 818 8763"[a:b]]}
    assert ("PERSON_NAME", "عمار الغامدي") in kinds
    assert any(k == "MOBILE" and "818 8763" in t for k, t in kinds)
    assert not [s for s in find_spans("راجع مستشفى الحمادي") if s[2] == "PERSON_NAME"]


def test_title_line_above_a_semicolon_table():
    text = "كشف العملاء - سري\nالاسم;الجوال;المدينة\nأحمد;0503318842;الرياض\nسارة;0551234567;جدة\nخالد;0567654321;أبها\n"
    res = read_files([("x.csv", text.encode("utf-8"))])
    df = next(iter(res.tables.values()))
    assert list(df.columns) == ["الاسم", "الجوال", "المدينة"] and len(df) == 3
    assert res.report()[0]["skipped_title_rows"] == 1 and res.report()[0]["delimiter"] == ";"


# ---------------------------------------------------------------- residual scan

def test_residual_scan_catches_identifiers_nazeer_did_not_generate():
    # a column Nazeer does not treat as identifiers, holding one real IBAN among codes
    codes = [f"REF-{i:05d}" for i in range(40)]
    codes[3] = VALID_IBAN
    tables = {"t": pd.DataFrame({"id": [f"R{i}" for i in range(40)], "code": codes}, dtype=object)}
    an, res = _run(tables, overrides={"t.code": {"tag": "NORMAL", "kind": None}})
    names = {c["name"]: c for c in res.report["checks"]}
    assert names["residual_identifiers"]["status"] == "FAIL" and names["residual_identifiers"]["blocking"]
    assert res.report["verdict"] == "FAIL"
    assert res.report["residual_scan"]["by_kind"]["IBAN"] == 1
    assert VALID_IBAN not in str(res.report)                      # counts and locations only
    # a reviewer confirms the column holds no identifiers: no longer flagged
    _, ok = _run(tables, overrides={"t.code": {"tag": "NORMAL", "kind": None}}, cleared_columns=["t.code"])
    assert ok.report["residual_scan"]["verdict"] == "PASS"


def test_generated_pseudonyms_are_not_flagged():
    ids = []
    import random
    rng = random.Random(3)
    from nazeer import saudi_ids as s
    for _ in range(40):
        ids.append(s.gen_saudi_id(rng, "1"))
    tables = {"t": pd.DataFrame({"national_id": ids, "x": ["a"] * 40}, dtype=object)}
    _, res = _run(tables)
    assert res.report["residual_scan"]["verdict"] == "PASS" and res.report["verdict"] == "PASS"


# ---------------------------------------------------------------- independent answer keys

def test_generated_keys_that_look_like_identifiers_are_not_flagged():
    # fake keys keep the "APT-####-######" shape; their digits can read as a mobile or an ID
    keys = [f"APT-2026-{i:06d}" for i in range(1, 301)]
    tables = {"t": pd.DataFrame({"appointment_id": keys, "clinic": ["الأسنان"] * 300}, dtype=object)}
    _, res = _run(tables)
    assert res.report["residual_scan"]["verdict"] == "PASS"


@pytest.mark.parametrize("data,key", [
    ("hospital_patients_test.csv", "hospital_patients_answer_key.csv"),
    ("bank_customers_test.csv", "bank_customers_answer_key.csv"),
    ("insurance_claims_test.xlsx", "insurance_claims_answer_key.csv"),
    ("clinic_appointments_clean.csv", "clinic_appointments_answer_key.csv"),
    ("bank_accounts_clean.csv", "bank_accounts_answer_key.csv"),
])
@pytest.mark.parametrize("cleaning", [True, False], ids=["cleaned", "skipped"])
def test_recall_against_answer_keys(data, key, cleaning):
    import sys
    sys.path.insert(0, str(SAMPLES.parents[2] / "scripts"))
    from eval_answer_key import run

    out = run([SAMPLES / data], SAMPLES / key, cleaning=cleaning)  # cleaning is optional
    assert out["verdict"] == "PASS", out["failed_checks"]
    for kind, v in out["types"].items():
        assert v["recall"] == 1.0, (kind, v)
    look = out["look_alikes"]
    assert look["wrong"] == 0 and look["ignored"] + look["review"] == look["total"] - look["not_located"]
