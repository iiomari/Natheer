import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from data_gen import make_demo_data as demo
from nazeer import detect, transform
from nazeer import saudi_ids as s
from nazeer.policy import load_policy, policy_from_dict, resolve
from nazeer.profiling import profile_dataset
from nazeer.tableio import load_csv_folder
from nazeer.transform import Pseudonymizer, render_like

KEY = b"test-key-0123456789-0123456789-abcdef"
ROOT = Path(__file__).resolve().parents[1]


def _p(key=KEY):
    return Pseudonymizer(key)


# ------------------------------------------------------------------ determinism

def test_same_value_same_fake_100_times():
    outs = {_p().value("SAUDI_ID", "1110704341") for _ in range(100)}
    assert len(outs) == 1


def test_different_key_different_fake():
    assert _p().value("SAUDI_ID", "1110704341") != _p(b"another-key-" * 4).value("SAUDI_ID", "1110704341")


_SUBPROCESS_SNIPPET = """
import json, sys
sys.path.insert(0, {root!r})
from nazeer.transform import Pseudonymizer
p = Pseudonymizer({key!r})
print(json.dumps([p.value("SAUDI_ID", "1110704341"), p.value("MOBILE", "0503318842"),
                  p.value("IBAN", "SA0380000000608010167519"), p.value("PERSON_NAME", "محمد العتيبي")],
                 ensure_ascii=True))
"""


def test_determinism_across_processes():
    code = _SUBPROCESS_SNIPPET.format(root=str(ROOT), key=KEY)
    outs = []
    for hashseed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": hashseed, "PYTHONIOENCODING": "utf-8"}
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
        outs.append(json.loads(res.stdout))
    assert outs[0] == outs[1]
    expected = [_p().value("SAUDI_ID", "1110704341"), _p().value("MOBILE", "0503318842"),
                _p().value("IBAN", "SA0380000000608010167519"), _p().value("PERSON_NAME", "محمد العتيبي")]
    assert outs[0] == expected


# ------------------------------------------------------------------ validity

@pytest.mark.parametrize("kind, raw", [
    ("SAUDI_ID", "1110704341"), ("SAUDI_ID", "2129040479"), ("MOBILE", "0503318842"),
    ("IBAN", "SA0380000000608010167519"), ("EMAIL", "someone@example.com"),
])
def test_fake_is_valid_and_different(kind, raw):
    fake = _p().value(kind, raw)
    assert fake != raw
    assert s.is_valid(kind, fake)


@pytest.mark.parametrize("first", ["1", "2"])
def test_id_keeps_citizen_resident_digit(first):
    rng = random.Random(0)
    p = _p()
    for _ in range(200):
        assert p.value("SAUDI_ID", s.gen_saudi_id(rng, first))[0] == first


def test_name_tokens_keep_gender_and_family_slot():
    p = _p()
    fake = p.value("PERSON_NAME", "نورة العتيبي")
    first, family = fake.split(" ")
    assert s.name_gender(first) == "F"
    assert s.is_family_name(family)
    assert fake != "نورة العتيبي"


def test_first_name_alone_matches_full_name_token():
    p = _p()
    assert p.value("PERSON_NAME", "محمد العتيبي").split(" ")[0] == p.value("PERSON_NAME", "محمد")
    assert p.value("PERSON_NAME", "أحمد") == p.value("PERSON_NAME", "احمد")  # spelling-insensitive


def test_mobile_formats_share_one_fake_number():
    p = _p()
    forms = ["0503318842", "+966503318842", "966503318842", "00966503318842", "٠٥٠ ٣٣١ ٨٨٤٢"]
    assert len({s.canonical("MOBILE", p.value("MOBILE", f)) for f in forms}) == 1


# ------------------------------------------------------------------ format preservation

@pytest.mark.parametrize("raw, kind", [
    ("٠٥٠ ٣٣١ ٨٨٤٢", "MOBILE"),
    ("+٩٦٦ ٥٠-٣٣١-٨٨٤٢", "MOBILE"),
    ("00966 50 331 8842", "MOBILE"),
    ("۱۱۱ ۰۷۰ ۴۳۴۱", "SAUDI_ID"),
    ("111-070-4341", "SAUDI_ID"),
    ("SA03 8000 0000 6080 1016 7519", "IBAN"),
    ("sa0380000000608010167519", "IBAN"),
])
def test_format_is_preserved(raw, kind):
    fake = _p().value(kind, raw)
    assert len(fake) == len(raw)
    for a, b in zip(raw, fake):
        if s.ascii_digit(a) is not None:
            assert s.ascii_digit(b) is not None and transform._script_of(a) == transform._script_of(b)
        elif kind != "IBAN" or a in " -":
            assert a == b
    assert s.is_valid(kind, fake)
    assert s.canonical(kind, fake) != s.canonical(kind, raw)


def test_replace_spans_from_end_keeps_offsets():
    text = "جوال ٠٥٠ ٣٣١ ٨٨٤٢ وهوية 1110704341 للمراجع محمد العتيبي."
    spans = [(a, b, k) for a, b, k, _, _ in detect.find_spans(text)]
    out = transform.replace_spans(text, spans, _p())
    assert "1110704341" not in out and "محمد العتيبي" not in out
    assert out.startswith("جوال ") and out.endswith(".")
    assert [k for *_, k, _, _ in detect.find_spans(out)] == [k for _, _, k in spans]


# ------------------------------------------------------------------ collisions

def test_collision_rehash_gives_unique_outputs():
    calls = {"n": 0}

    def sticky(canon, rng):  # first 5 draws always collide
        calls["n"] += 1
        return "1000000008" if calls["n"] <= 5 else s.gen_saudi_id(rng)

    p = Pseudonymizer(KEY, generators={"SAUDI_ID": sticky})
    a, b = p.fake("SAUDI_ID", "1110704341"), p.fake("SAUDI_ID", "1909266858")
    assert a != b
    assert p.collisions["SAUDI_ID"] >= 1


def test_fake_never_equals_any_original():
    p = Pseudonymizer(KEY, generators={"SAUDI_ID": lambda canon, rng: "2129040479" if rng.random() < 0.9 else s.gen_saudi_id(rng)})
    p.forbid("SAUDI_ID", {"2129040479"})
    assert p.fake("SAUDI_ID", "1110704341") != "2129040479"


def test_prepare_is_order_independent():
    vals = [s.gen_saudi_id(random.Random(i)) for i in range(50)]
    p1, p2 = _p(), _p()
    p1.prepare({"SAUDI_ID": vals})
    p2.prepare({"SAUDI_ID": list(reversed(vals))})
    assert [p1.fake("SAUDI_ID", v) for v in vals] == [p2.fake("SAUDI_ID", v) for v in vals]


# ------------------------------------------------------------------ whole dataset

@pytest.fixture(scope="module")
def masked(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    demo.main(["--seed", "11", "--n", "400", "--out", str(out)])
    tables = load_csv_folder(out, ["customers", "claims"])
    prof = profile_dataset(tables)
    dets = detect.detect_columns(tables, prof)
    decisions = resolve(load_policy(ROOT / "config" / "policy.yaml"), prof, dets)
    spans = detect.detect_free_text(tables, detect.free_text_columns(dets))
    twin, stats = transform.apply(tables, prof, decisions, spans, Pseudonymizer(KEY))
    return tables, twin, decisions, spans, stats


def test_referential_integrity(masked):
    tables, twin, *_ = masked
    assert len(twin["customers"]) == len(tables["customers"]) and len(twin["claims"]) == len(tables["claims"])
    assert set(twin["claims"].customer_id) <= set(twin["customers"].customer_id)
    assert twin["customers"].customer_id.is_unique
    orig = tables["claims"].merge(tables["customers"], on="customer_id")
    new = twin["claims"].merge(twin["customers"], on="customer_id")
    assert len(orig) == len(new)
    assert (orig.groupby("claim_type").size() == new.groupby("claim_type").size()).all()


def test_keys_are_remapped(masked):
    tables, twin, *_ = masked
    assert (tables["customers"].customer_id != twin["customers"].customer_id).mean() > 0.99


def test_direct_id_columns_fully_replaced(masked):
    tables, twin, *_ = masked
    for col, kind in (("national_id", "SAUDI_ID"), ("mobile", "MOBILE")):
        orig = {s.canonical(kind, v) for v in tables["customers"][col]}
        new = {s.canonical(kind, v) for v in twin["customers"][col]}
        assert not orig & new
        assert all(s.is_valid(kind, v) for v in twin["customers"][col])
    assert (tables["customers"].full_name != twin["customers"].full_name).all()


def test_text_and_column_stay_consistent(masked):
    tables, twin, _, spans, _ = masked
    ids = tables["customers"].set_index("customer_id").national_id.map(lambda v: s.canonical("SAUDI_ID", v))
    fake_ids = dict(zip(tables["customers"].national_id.map(lambda v: s.canonical("SAUDI_ID", v)),
                        twin["customers"].national_id.map(lambda v: s.canonical("SAUDI_ID", v))))
    checked = 0
    notes_out = twin["claims"].notes.tolist()
    for sp in spans:
        if sp.type != "SAUDI_ID":
            continue
        raw = tables["claims"].notes.iat[sp.row][sp.start:sp.end]
        canon = s.canonical("SAUDI_ID", raw)
        if canon in fake_ids:  # the claimant's own ID mentioned in the note
            twin_found = {s.canonical("SAUDI_ID", notes_out[sp.row][a:b])
                          for a, b, k, _, _ in detect.find_spans(notes_out[sp.row]) if k == "SAUDI_ID"}
            assert fake_ids[canon] in twin_found
            checked += 1
    assert checked > 20
    assert ids.notna().all()


def test_policy_override_wins_and_is_recorded():
    from nazeer.models import ColumnDetection, ColumnProfile, DatasetProfile, TableProfile
    cp = ColumnProfile("t", "code", "short_text", 10, 0, 10, 10.0, 0.0)
    prof = DatasetProfile({"t": TableProfile("t", 10, {"code": cp}, None)})
    det = [ColumnDetection("t", "code", "DIRECT_ID", "SAUDI_ID", 0.55, 0.44, True, True, "borderline")]
    pol = policy_from_dict({"policy": {"SAUDI_ID": {"action": "pseudonymize"}, "default": {"action": "keep"}}})
    assert resolve(pol, prof, det)[0].action == "pseudonymize"
    d = resolve(pol, prof, det, {"t.code": {"tag": "NORMAL"}})[0]
    assert d.action == "keep" and d.human_override and d.tag == "NORMAL"


def test_unknown_action_is_rejected():
    with pytest.raises(ValueError):
        policy_from_dict({"policy": {"age": {"action": "explode"}}})


def test_render_like_fallback_keeps_validity():
    fake = render_like("05 03 31 88 42 x", "MOBILE", "512345678")
    assert s.is_valid("MOBILE", fake)


def test_small_sequential_keys_do_not_exhaust_the_pseudonym_space():
    """Keys 1..9 (common in uploads) cannot all stay one digit; the remap widens instead of failing."""
    import pandas as pd

    from nazeer import pipeline
    from nazeer.policy import load_policy

    tables = {"t": pd.DataFrame({"id": [str(i) for i in range(1, 40)], "v": ["x"] * 39}, dtype=object)}
    res = pipeline.run_masked(pipeline.analyze(tables), load_policy(pipeline.DEFAULT_POLICY), b"k" * 40)
    new = res.twin["t"]["id"].tolist()
    old = [str(i) for i in range(1, 40)]
    assert len(set(new)) == 39  # still a key: unique
    assert all(a != b for a, b in zip(old, new))  # no key keeps its own value
