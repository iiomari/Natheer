import pandas as pd
import pytest

from data_gen import make_demo_data as demo
from nazeer import evaluate, pipeline, synth
from nazeer import saudi_ids as s
from nazeer.policy import load_policy
from nazeer.report import validate
from nazeer.tableio import load_csv_folder

TARGET = "is_large_claim=amount>p90"


@pytest.fixture(scope="module")
def analysis(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    demo.main(["--seed", "9", "--n", "800", "--out", str(out)])
    return pipeline.analyze(load_csv_folder(out), source="test")


@pytest.fixture(scope="module")
def parts(analysis):
    train, hold, info = synth.split_holdout(analysis.tables, analysis.profile, 0.2, 0)
    vt, vh = synth.build_view(train, analysis.profile), synth.build_view(hold, analysis.profile)
    modelled, excluded = synth.view_plan(vt, analysis.profile, analysis.detections)
    return train, hold, info, vt, vh, modelled, excluded


@pytest.fixture(scope="module")
def result(analysis):
    return pipeline.run_synthetic(analysis, load_policy(pipeline.DEFAULT_POLICY), target=TARGET)


def test_split_is_by_customer_and_disjoint(analysis, parts):
    train, hold, info, *_ = parts
    assert set(train["customers"].customer_id).isdisjoint(hold["customers"].customer_id)
    assert set(hold["claims"].customer_id) <= set(hold["customers"].customer_id)
    assert set(train["claims"].customer_id) <= set(train["customers"].customer_id)
    assert len(hold["customers"]) == round(0.2 * len(analysis.tables["customers"]))
    assert info["unit_table"] == "customers"


def test_view_and_plan(parts):
    *_, vt, vh, modelled, excluded = parts
    assert vt.base_table == "claims"
    assert "prior_claims" in vt.df.columns and vt.df["prior_claims"].min() == 0
    for col in ("full_name", "national_id", "mobile", "notes", "claim_id", "customer_id"):
        assert col in excluded and col not in modelled
    assert modelled["amount"] == "numerical" and modelled["claim_type"] == "categorical"
    assert modelled["claim_date"] == "datetime"


def test_stratified_copula_picks_the_driving_column(parts):
    *_, vt, vh, modelled, excluded = parts
    model = synth.make_synthesizer("stratified_copula")
    x = synth.typed_view(vt.df, modelled)
    model.fit({"view": x}, synth.SynthSchema(tables={"view": modelled}))
    assert model.details["stratified_by"] == "claim_type"
    out = model.sample(1.0)["view"]
    assert set(out.columns) == set(modelled) and abs(len(out) - len(x)) <= model.details["strata"]


def test_stratified_copula_falls_back_without_a_driver():
    import numpy as np
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"x": rng.normal(size=300), "c": rng.choice(["a", "b"], size=300)})
    model = synth.make_synthesizer("stratified_copula")
    model.fit({"t": df}, synth.SynthSchema(tables={"t": {"x": "numerical", "c": "categorical"}}))
    assert model.details["stratified_by"] is None
    assert len(model.sample(1.0)["t"]) == 300


def test_synthetic_run_passes_and_reports(result):
    rep = result.report
    validate(rep)
    checks = {c["name"]: c for c in rep["checks"]}
    for name in ("holdout_split", "leak_scan", "exact_copies", "dcr", "utility_tstr"):
        assert checks[name]["blocking"]
    assert checks["leak_scan"]["status"] == "PASS"
    assert checks["exact_copies"]["status"] == "PASS"
    assert rep["utility"]["max_auc_drop"] is not None
    assert rep["synthetic"]["license"].startswith("BUSL")
    assert "seed" in rep["synthetic"]


def test_twin_identifiers_are_fresh_and_valid(analysis, result):
    twin = next(iter(result.twin.values()))
    real_ids = {s.canonical("SAUDI_ID", v) for v in analysis.tables["customers"].national_id}
    real_mobiles = {s.canonical("MOBILE", v) for v in analysis.tables["customers"].mobile}
    assert all(s.is_valid("SAUDI_ID", v) for v in twin.national_id)
    assert all(s.is_valid("MOBILE", v) for v in twin.mobile)
    assert not {s.canonical("SAUDI_ID", v) for v in twin.national_id} & real_ids
    assert not {s.canonical("MOBILE", v) for v in twin.mobile} & real_mobiles


def test_real_text_is_never_reused(analysis, result):
    twin = next(iter(result.twin.values()))
    real_notes = set(analysis.tables["claims"].notes)
    assert not set(twin.notes) & real_notes
    real_sentences = {sent.strip() for n in real_notes for sent in n.split(".") if len(sent.strip()) > 15}
    twin_sentences = {sent.strip() for n in twin.notes for sent in n.split(".") if len(sent.strip()) > 15}
    assert not real_sentences & twin_sentences


def test_names_follow_synthetic_gender(result):
    twin = next(iter(result.twin.values()))
    genders = twin.gender.map({"ذكر": "M", "أنثى": "F"})
    first = twin.full_name.str.split(" ").str[0].map(s.name_gender)
    assert (genders == first).mean() > 0.99


def test_copying_training_data_fails_privacy_checks(parts):
    """A 'synthesizer' that memorizes rows must be caught: DCR fails and exact copies > 0."""
    *_, vt, vh, modelled, excluded = parts
    x_train, x_hold = synth.typed_view(vt.df, modelled), synth.typed_view(vh.df, modelled)
    copied = x_train.sample(len(x_hold), random_state=0).reset_index(drop=True)
    d = evaluate.dcr(x_train, copied, x_hold, modelled)
    assert not d["passed"] and d["twin_rows_at_distance_zero"] == len(copied)
    assert evaluate.exact_copies(x_train, copied, list(modelled)) == len(copied)


def test_parse_target():
    assert evaluate.parse_target("is_large_claim=amount>p90") == ("is_large_claim", "amount", 90.0)
    assert evaluate.parse_target("amount>p75") == ("amount>p75", "amount", 75.0)
    assert evaluate.parse_target("flag") == ("flag", "flag", None)


def test_tstr_on_real_copy_has_no_drop(parts):
    *_, vt, vh, modelled, excluded = parts
    x_train, x_hold = synth.typed_view(vt.df, modelled), synth.typed_view(vh.df, modelled)
    u = evaluate.utility_tstr(x_train, x_train, x_hold, modelled, TARGET)
    assert abs(u["max_auc_drop"]) < 1e-9
