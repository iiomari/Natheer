"""Name detection: gazetteer, CamelBERT wrapper (fallbacks tested with a fake model),
and the real local model when it has been downloaded (skipped otherwise)."""
import pytest

from nazeer import detect
from nazeer.camel_ner import CamelNER, UnionNER
from nazeer.ner import GazetteerNER, NERUnavailable, get_name_detector


def _fake_nlp(entities_per_text):
    def nlp(batch, batch_size=16):
        return [entities_per_text(t) for t in batch]
    return nlp


def test_default_detector_is_gazetteer():
    assert isinstance(get_name_detector(), GazetteerNER)


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        get_name_detector("magic")


def test_person_entities_become_spans_and_others_are_ignored():
    def ents(text):
        i = text.index("زيدون")
        return [{"entity_group": "PERS", "score": 0.97, "start": i, "end": i + 5},
                {"entity_group": "LOC", "score": 0.99, "start": 0, "end": 3},
                {"entity_group": "PERS", "score": 0.2, "start": 0, "end": 3}]  # below min_score
    ner = CamelNER(_fake_nlp(ents))
    assert ner.find("تواصل زيدون اليوم") == [(6, 11, 0.97)]


def test_model_error_falls_back_to_gazetteer():
    def broken(batch, batch_size=16):
        raise RuntimeError("boom")
    ner = CamelNER(broken)
    assert ner.find("المراجع محمد العتيبي حضر") == GazetteerNER().find("المراجع محمد العتيبي حضر")
    assert ner.stats["texts_fallback"] == 1 and ner.stats["fallback_reason"]


def test_time_budget_falls_back_for_remaining_texts():
    ner = CamelNER(_fake_nlp(lambda t: []), time_budget_s=-1, batch_size=2)
    out = ner.find_many(["المراجع محمد العتيبي حضر"] * 5)
    assert all(o for o in out)  # gazetteer filled every text
    assert ner.stats["texts_fallback"] == 5 and "time budget" in ner.stats["fallback_reason"]


def test_union_merges_overlaps_and_keeps_both():
    merged = UnionNER._merge([(0, 4, 0.9), (10, 15, 0.8)], [(2, 9, 0.7), (20, 25, 0.6)])
    assert merged == [(0, 9, 0.9), (10, 15, 0.8), (20, 25, 0.6)]


def test_batched_detector_is_used_by_free_text_detection():
    import pandas as pd

    calls = {"n": 0}

    class Batched:
        name = "fake-batched"

        def find(self, text):
            raise AssertionError("find_many should be used")

        def find_many(self, texts):
            calls["n"] += 1
            return [[(0, 4, 0.9)] for _ in texts]

    tables = {"t": pd.DataFrame({"note": ["زيدون حضر اليوم إلى الفرع", None, "زيدون اتصل"]})}
    spans = detect.detect_free_text(tables, [("t", "note")], Batched())
    assert calls["n"] == 1 and len(spans) == 2 and {s.source for s in spans} == {"fake-batched"}


@pytest.fixture(scope="module")
def real_union():
    try:
        return get_name_detector("union")
    except NERUnavailable as e:
        pytest.skip(f"CamelBERT not downloaded: {e}")


def test_real_model_runs_offline_and_matches_or_beats_gazetteer(real_union, tmp_path_factory):
    import os

    from data_gen import make_demo_data as demo
    from nazeer.evaluate import score_detection
    from nazeer.tableio import load_csv_folder, read_csv

    assert os.environ.get("HF_HUB_OFFLINE") == "1"
    out = tmp_path_factory.mktemp("demo")
    demo.main(["--seed", "12", "--n", "40", "--out", str(out)])
    tables = load_csv_folder(out, ["claims"])
    golden = read_csv(out / "_golden" / "golden_labels.csv")
    union = score_detection(detect.detect_free_text(tables, [("claims", "notes")], real_union), golden)
    gaz = score_detection(detect.detect_free_text(tables, [("claims", "notes")]), golden)
    assert union["per_type"]["PERSON_NAME"]["recall"] >= gaz["per_type"]["PERSON_NAME"]["recall"]
    assert real_union.stats["texts_model"] > 0
