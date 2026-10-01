import csv
import filecmp
from collections import Counter

import pytest

from data_gen import make_demo_data as demo
from nazeer import saudi_ids as s


def _read(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def demo_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    demo.main(["--seed", "7", "--n", "300", "--out", str(out)])
    return out


def test_byte_identical_across_runs(demo_dir, tmp_path):
    demo.main(["--seed", "7", "--n", "300", "--out", str(tmp_path)])
    for name in ("customers", "claims", "golden_labels", "hard_negatives", "golden_columns"):
        assert filecmp.cmp(demo_dir / f"{name}.csv", tmp_path / f"{name}.csv", shallow=False), name


def test_schema_and_foreign_keys(demo_dir):
    customers, claims = _read(demo_dir / "customers.csv"), _read(demo_dir / "claims.csv")
    assert list(customers[0]) == ["customer_id", "full_name", "national_id", "mobile", "city", "age", "gender"]
    assert list(claims[0]) == ["claim_id", "customer_id", "claim_date", "claim_type", "amount", "notes"]
    assert len(customers) == 300
    ids = {c["customer_id"] for c in customers}
    assert len(ids) == 300
    assert {c["customer_id"] for c in claims} <= ids
    assert len({c["claim_id"] for c in claims}) == len(claims)


def test_structured_identifiers_validate(demo_dir):
    for c in _read(demo_dir / "customers.csv"):
        assert s.is_valid("SAUDI_ID", c["national_id"])
        assert s.is_valid_mobile(c["mobile"])
        assert s.is_known_name(c["full_name"])


def test_every_golden_span_validates(demo_dir):
    claims = _read(demo_dir / "claims.csv")
    golden = _read(demo_dir / "golden_labels.csv")
    assert golden
    for g in golden:
        span = claims[int(g["row"])]["notes"][int(g["start"]):int(g["end"])]
        assert span == span.strip()
        assert s.is_valid(g["type"], span)
    assert set(Counter(g["type"] for g in golden)) == {"SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME"}


def test_hard_negatives_fail_validation(demo_dir):
    claims = _read(demo_dir / "claims.csv")
    negatives = _read(demo_dir / "hard_negatives.csv")
    lookalikes = [h for h in negatives if h["kind"] == "LOOKALIKE_ID"]
    assert lookalikes
    for h in lookalikes:
        flat = s.canonical("SAUDI_ID", claims[int(h["row"])]["notes"][int(h["start"]):int(h["end"])])
        assert len(flat) == 10 and flat[0] in "12"
        assert not s.is_valid_saudi_id(flat) and not s.is_valid_mobile(flat)


def test_digit_scripts_and_spacing_are_mixed(demo_dir):
    claims = _read(demo_dir / "claims.csv")
    golden = [g for g in _read(demo_dir / "golden_labels.csv") if g["type"] in ("SAUDI_ID", "MOBILE")]
    spans = [claims[int(g["row"])]["notes"][int(g["start"]):int(g["end"])] for g in golden]
    assert any(any("٠" <= ch <= "٩" for ch in sp) for sp in spans)
    assert any(any("۰" <= ch <= "۹" for ch in sp) for sp in spans)
    assert any(" " in sp for sp in spans)
    assert any(sp.isascii() and sp.isdigit() for sp in spans)
