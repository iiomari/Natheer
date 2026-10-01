import pytest

from data_gen import make_demo_data as demo
from nazeer import pipeline, ui_logic
from nazeer.policy import load_policy
from nazeer.tableio import load_csv_folder

KEY = b"ui-logic-key-0123456789-0123456789"


@pytest.fixture(scope="module")
def analysis(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    demo.main(["--seed", "4", "--n", "300", "--out", str(out)])
    return pipeline.analyze(load_csv_folder(out), source="test")


def test_unchanged_table_gives_no_overrides(analysis):
    overrides, problems = ui_logic.overrides_from_edits(analysis, ui_logic.detection_frame(analysis))
    assert overrides == {} and problems == []


def test_edits_become_overrides(analysis):
    df = ui_logic.detection_frame(analysis)
    df.loc[(df.table == "customers") & (df.column == "city"), "tag"] = "NORMAL"
    df.loc[(df.table == "customers") & (df.column == "national_id"), "reviewed"] = True
    df.loc[(df.table == "claims") & (df.column == "amount"), "action"] = "drop"
    overrides, problems = ui_logic.overrides_from_edits(analysis, df)
    assert problems == []
    assert overrides["customers.city"] == {"tag": "NORMAL", "kind": None}
    assert overrides["customers.national_id"] == {"tag": "DIRECT_ID", "kind": "SAUDI_ID"}
    assert overrides["claims.amount"]["action"] == {"action": "drop"}
    # round trip: the frame shows existing overrides as applied
    again = ui_logic.detection_frame(analysis, overrides)
    assert again.loc[(again.table == "customers") & (again.column == "city"), "tag"].item() == "NORMAL"
    assert ui_logic.overrides_from_edits(analysis, again)[0] == overrides


def test_direct_id_without_type_is_rejected(analysis):
    df = ui_logic.detection_frame(analysis)
    df.loc[(df.table == "customers") & (df.column == "city"), "tag"] = "DIRECT_ID"
    overrides, problems = ui_logic.overrides_from_edits(analysis, df)
    assert "customers.city" not in overrides and problems


def test_overrides_are_recorded_and_untagging_text_cannot_hide_leaks(analysis):
    policy = load_policy(pipeline.DEFAULT_POLICY)
    res = pipeline.run_masked(analysis, policy, KEY, {"claims.notes": {"tag": "NORMAL", "kind": None}},
                              apply_fix="auto")
    col = next(c for c in res.report["columns"] if c["column"] == "notes")
    assert col["human_reviewed"] and col["tag"] == "NORMAL" and col["action"] == "keep"
    assert res.report["leak_scan"]["hard_fail"]  # notes kept raw -> identifiers found -> FAIL
    assert res.twin_withheld


def test_newly_tagged_free_text_column_is_scanned(analysis):
    import pandas as pd

    tables = {k: v.copy() for k, v in analysis.tables.items()}
    tables["customers"]["remark"] = "اتصل على 0503318842 للمتابعة"
    an = pipeline.analyze(tables)
    res = pipeline.run_masked(an, load_policy(pipeline.DEFAULT_POLICY), KEY,
                              {"customers.remark": {"tag": "FREE_TEXT", "kind": None}}, apply_fix="auto")
    assert "0503318842" not in " ".join(res.twin["customers"]["remark"].astype(str))
    assert isinstance(res.twin["customers"], pd.DataFrame)


def test_suggestion_frame(analysis):
    res = pipeline.run_masked(analysis, load_policy(pipeline.DEFAULT_POLICY), KEY)
    k = res.report["k_anonymity"]["customers"]
    frame = ui_logic.suggestion_frame(k)
    if not k["passed_before"]:
        assert len(frame) == len(k["suggestions"]) and {"k before", "k after", "rows affected"} <= set(frame.columns)


# ---------------------------------------------------------------- redesigned UI helpers

@pytest.fixture(scope="module")
def masked(analysis):
    return pipeline.run_masked(analysis, load_policy(pipeline.DEFAULT_POLICY), KEY)


def test_entity_tracking_follows_one_customer_across_tables(analysis):
    assert ui_logic.entity_key(analysis.profile) == ("customers", "customer_id")
    who = ui_logic.default_entity(analysis)
    rows = ui_logic.entity_rows(analysis, who)
    assert len(rows["customers"]) == 1 and rows["claims"]
    assert set(analysis.tables["claims"]["customer_id"].iloc[rows["claims"]]) == {who}
    labels = ui_logic.entity_labels(analysis)
    assert labels[who] == ui_logic.entity_label(analysis, who) and who in labels[who]
    assert ui_logic.entity_notes(analysis, who)  # the default customer has notes worth showing


def test_note_marks_label_rejected_lookalikes_and_baseline_false_alarms():
    from nazeer import detect
    from nazeer.models import Span

    text = "هويته ١١١٠٧٠٤٣٤١ ورقم الفاتورة 1234567890 وجواله ٠٥٠ ٣٣١ ٨٨٤٢"
    naz = [Span("t", 0, "c", a, b, k, conf, src) for a, b, k, conf, src in detect.find_spans(text)]
    base = [Span("t", 0, "c", a, b, k, conf, src) for a, b, k, conf, src in detect.baseline_find_spans(text)]
    base_marks, naz_marks = ui_logic.note_marks(text, naz, base)
    invoice = (text.index("1234567890"), text.index("1234567890") + 10)
    assert (*invoice, "false_alarm", "SAUDI_ID") in base_marks  # baseline flags the invoice number
    assert (*invoice, "rejected", "SAUDI_ID") in naz_marks  # Nazeer shows it was checked and refused
    assert {m[3] for m in naz_marks if m[2] == "hit"} == {"SAUDI_ID", "MOBILE"}


def test_detection_summary_without_answer_key(analysis):
    no_key = ui_logic.detection_summary(analysis, None)
    assert no_key["nazeer"]["found"] == len(analysis.spans) and no_key["nazeer"]["false_alarms"] is None
    assert no_key["baseline"]["false_alarms"] >= 0


def test_twin_totals_and_proof_cards(analysis, masked):
    tot = ui_logic.twin_totals(analysis, masked)
    assert tot["all_same"] and tot["orphans"] == 0
    assert all(s["column"] not in ("mobile", "national_id") for t in tot["tables"] for s in t["sums"])
    p = ui_logic.proof(analysis, masked)
    assert p["leak"]["status"] == "PASS" and p["validity"]["status"] == "PASS" and p["links"]["status"] == "PASS"
    assert p["k"]["status"] == masked.report["checks"][[c["name"] for c in masked.report["checks"]].index(
        "k_anonymity[customers]")]["status"]


def test_plant_leak_is_caught_and_leaves_the_twin_untouched(analysis, masked):
    who = ui_logic.default_entity(analysis)
    before = {t: df.copy() for t, df in masked.twin.items()}
    planted = ui_logic.plant_leak(analysis, masked, who)
    assert planted["leak"]["verdict"] == "FAIL" and planted["leak"]["leaked_by_kind"][planted["kind"]] >= 1
    assert any(loc["row"] == planted["row"] for loc in planted["leak"]["locations"])
    assert all(masked.twin[t].equals(before[t]) for t in before)
    assert ui_logic.disguise("SAUDI_ID", "1110704341") == "١١١ ٠٧٠ ٤٣٤١"


def test_mask_text_preview_replaces_identifiers_with_valid_fakes():
    from nazeer import detect
    from nazeer import saudi_ids as s

    text = "هويته 1110704341 وجواله 0503318842"
    spans = [(a, b, k) for a, b, k, _, _ in detect.find_spans(text)]
    out = ui_logic.mask_text(text, spans, KEY)
    assert "1110704341" not in out and "0503318842" not in out
    found = {k: out[a:b] for a, b, k, _, _ in detect.find_spans(out, names=False)}
    assert s.is_valid("SAUDI_ID", found["SAUDI_ID"]) and s.is_valid("MOBILE", found["MOBILE"])
    assert ui_logic.mask_text(text, spans, KEY) == out  # deterministic for one key


def test_why_it_works_has_five_rows(analysis, masked):
    rows = ui_logic.why_it_works(analysis, masked, None)
    assert len(rows) == 5 and all(r["cause"] and r["component"] for r in rows)
    assert rows[1]["metric"] == "100% صالحة"
    assert ui_logic.why_it_works(analysis, None, None)[0]["metric"] is None  # not measured yet
