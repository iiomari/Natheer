import json
from pathlib import Path

import pandas as pd
import pytest

from nazeer import eval_human
from nazeer import saudi_ids as s

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "data" / "human_notes_TEMPLATE.csv"


def test_parse_markers_gives_clean_text_and_spans():
    p = eval_human.parse_marked("جوال ⟦NAME:نورة⟧ هو ⟦MOBILE:٠٥٠ ٣٣١ ٨٨٤٢⟧، والفاتورة 1234567890.")
    assert p.text == "جوال نورة هو ٠٥٠ ٣٣١ ٨٨٤٢، والفاتورة 1234567890."
    assert [(p.text[a:b], k) for a, b, k in p.spans] == [("نورة", "PERSON_NAME"), ("٠٥٠ ٣٣١ ٨٨٤٢", "MOBILE")]


@pytest.mark.parametrize("bad", ["⟦PHONE:0503318842⟧", "⟦ID:⟧", "⟦ID:111 ⟦MOBILE:0503318842⟧", "رقم ⟦ID:1110704341", "⟧"])
def test_malformed_markup_is_rejected(bad):
    with pytest.raises(eval_human.MarkupError):
        eval_human.parse_marked(bad)


def test_template_scores_and_never_reports_values(tmp_path):
    out = tmp_path / "r.json"
    assert eval_human.main(["--notes", str(TEMPLATE), "--json", str(out), "--ner", "gazetteer"]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["nazeer"]["overall_recall"] == 1.0
    assert result["nazeer"]["overall_recall"] > result["baseline"]["overall_recall"]
    text = out.read_text(encoding="utf-8")
    df = pd.read_csv(TEMPLATE, dtype=str, encoding="utf-8-sig")
    for note in df.note:
        for a, b, _ in eval_human.parse_marked(note).spans:
            value = eval_human.parse_marked(note).text[a:b]
            assert value not in text


def test_misses_and_invalid_format_are_reported_by_position_only():
    df = pd.DataFrame({"author": ["t", "t"],
                       "note": ["المراجع ذكر رقمًا ⟦ID:1234567890⟧ للتحقق.",          # invented: fails checksum
                                "تواصل مع ⟦NAME:زيدون⟧ غدًا."]})                     # name not in gazetteer
    r = eval_human.evaluate_notes(df, None)
    assert r["golden_failing_official_format"] == {"SAUDI_ID": 1}
    kinds = {m["type"] for m in r["nazeer_misses"]}
    assert kinds == {"SAUDI_ID", "PERSON_NAME"}
    for m in r["nazeer_misses"]:
        assert set(m) == {"row", "type", "start", "end", "valid_format"}
    assert r["nazeer_on_valid_format_only"]["per_type"]["SAUDI_ID"]["golden"] == 0


def test_unmarked_invoice_number_counts_as_extra_if_flagged():
    df = pd.DataFrame({"author": ["t"], "note": ["الفاتورة 1110704341 ورقم الهوية ⟦ID:1909266858⟧"]})
    r = eval_human.evaluate_notes(df, None)
    # 1110704341 happens to be checksum-valid: an honest false positive the harness must surface
    assert r["nazeer_extras"] == [{"row": 0, "type": "SAUDI_ID", "start": 9, "end": 19}]


def test_make_ids_are_valid():
    ids = eval_human.make_ids(50, seed=1)
    assert all(s.is_valid("SAUDI_ID", v) for v in ids["national_id (citizen)"])
    assert all(v.startswith("2") for v in ids["iqama (resident)"])
    assert all(s.is_valid("MOBILE", v) for v in ids["mobile"]) and all(s.is_valid("IBAN", v) for v in ids["iban"])


def test_missing_notes_file_explains_what_to_do(tmp_path, capsys):
    assert eval_human.main(["--notes", str(tmp_path / "none.csv")]) == 1
    assert "HOW_TO_WRITE_NOTES" in capsys.readouterr().err
