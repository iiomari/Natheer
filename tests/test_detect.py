import pytest

from data_gen import make_demo_data as demo
from nazeer import detect
from nazeer.evaluate import score_detection
from nazeer.profiling import profile_dataset
from nazeer.tableio import load_csv_folder, read_csv

RECALL_TARGET = 0.90  # plan: identifier recall >= 0.90 on golden labels


@pytest.fixture(scope="module")
def demo_data(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    demo.main(["--seed", "42", "--n", "1000", "--out", str(out)])
    tables = load_csv_folder(out, ["customers", "claims"])
    return out, tables, profile_dataset(tables)


def test_profile_keys(demo_data):
    _, _, prof = demo_data
    assert prof.tables["customers"].primary_key == "customer_id"
    assert prof.tables["claims"].primary_key == "claim_id"
    fks = {(f.child_table, f.child_column, f.parent_table, f.parent_column) for f in prof.foreign_keys}
    assert fks == {("claims", "customer_id", "customers", "customer_id")}


def test_profile_types(demo_data):
    _, _, prof = demo_data
    assert prof.column("claims", "notes").dtype == "free_text"
    assert prof.column("claims", "claim_date").dtype == "date"
    assert prof.column("claims", "amount").dtype == "numeric"
    assert prof.column("customers", "age").dtype == "numeric"
    assert prof.column("customers", "gender").dtype == "categorical"
    assert prof.column("customers", "city").dtype == "categorical"


def test_column_tags_match_golden(demo_data):
    out, tables, prof = demo_data
    golden = read_csv(out / "_golden" / "golden_columns.csv")
    got = {(d.table, d.column): d for d in detect.detect_columns(tables, prof)}
    for g in golden.itertuples(index=False):
        d = got[(g.table, g.column)]
        assert d.tag == g.tag, (g.table, g.column, d.tag)
        if isinstance(g.kind, str) and g.kind:
            assert d.kind == g.kind and not d.needs_review


def _scores(demo_data, finder):
    out, tables, _ = demo_data
    spans = finder(tables, [("claims", "notes")])
    return score_detection(spans, read_csv(out / "_golden" / "golden_labels.csv"), read_csv(out / "_golden" / "hard_negatives.csv"))


def test_free_text_recall_meets_target(demo_data):
    res = _scores(demo_data, detect.detect_free_text)
    for kind in ("SAUDI_ID", "MOBILE", "IBAN", "EMAIL"):
        assert res["per_type"][kind]["recall"] >= RECALL_TARGET, (kind, res["per_type"][kind])
    assert res["overall_recall"] >= RECALL_TARGET, res


def test_lookalike_ids_are_rejected(demo_data):
    out, tables, _ = demo_data
    spans = detect.detect_free_text(tables, [("claims", "notes")])
    negatives = read_csv(out / "_golden" / "hard_negatives.csv")
    lookalikes = negatives[negatives.kind == "LOOKALIKE_ID"]
    res = score_detection(spans, read_csv(out / "_golden" / "golden_labels.csv"), lookalikes)
    assert res["hard_negative_hits"] == 0


def test_nazeer_beats_baseline(demo_data):
    nazeer = _scores(demo_data, detect.detect_free_text)
    baseline = _scores(demo_data, detect.baseline_free_text)
    assert nazeer["overall_recall"] > baseline["overall_recall"]
    assert nazeer["per_type"]["SAUDI_ID"]["precision"] > baseline["per_type"]["SAUDI_ID"]["precision"]


@pytest.mark.parametrize(
    "text, kind",
    [
        ("جوالي ٠٥٠ ٣٣١ ٨٨٤٢ شكرا", "MOBILE"),
        ("هويتي ۱۱۱-۰۷۰-۴۳۴۱", "SAUDI_ID"),
        ("رقم 12 1110704341 للمراجعة", "SAUDI_ID"),  # glued to a neighbouring number by a space
        ("الآيبان SA03 8000 0000 6080 1016 7519", "IBAN"),
        ("على +966 50 331 8842", "MOBILE"),
        ("البريد a.b@example.com", "EMAIL"),
    ],
)
def test_find_spans_examples(text, kind):
    spans = detect.find_spans(text)
    assert any(k == kind for _, _, k, _, _ in spans), spans


def test_invoice_number_with_bad_checksum_is_ignored():
    assert detect.find_spans("فاتورة رقم 1234567890 بتاريخ اليوم") == []


def test_name_word_needs_context():
    assert detect.find_spans("على أمل الرد خلال يومين") == []
    spans = detect.find_spans("المراجعة أمل حضرت اليوم")
    assert [sp[2] for sp in spans] == ["PERSON_NAME"]


@pytest.mark.parametrize("text", ["وصل الطلب على الفور", "أرسل إلى الفرع", "وعلى المستفيد المراجعة"])
def test_function_words_are_not_names(text):
    assert detect.find_spans(text) == []


def test_name_ending_in_alef_maqsura_is_found():
    assert [sp[2] for sp in detect.find_spans("المراجع يحيى العتيبي")] == ["PERSON_NAME"]


def test_cue_does_not_cross_sentence_boundary():
    assert detect.find_spans("تم التواصل مع المستفيد. وعد الفرع بالرد") == []
    assert [sp[2] for sp in detect.find_spans("الطبيب المعالج د. أمل")] == ["PERSON_NAME"]
