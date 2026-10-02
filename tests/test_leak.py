import json

import pytest

from data_gen import make_demo_data as demo
from nazeer import evaluate, pipeline
from nazeer import saudi_ids as s
from nazeer.policy import load_policy
from nazeer.report import validate
from nazeer.tableio import load_csv_folder

KEY = b"leak-test-key-0123456789-0123456789"
ARABIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


@pytest.fixture(scope="module")
def demo_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    demo.main(["--seed", "5", "--n", "400", "--out", str(out)])
    return out


@pytest.fixture(scope="module")
def analysis(demo_dir):
    return pipeline.analyze(load_csv_folder(demo_dir), source="test")


@pytest.fixture(scope="module")
def masked(analysis):
    return pipeline.run_masked(analysis, load_policy(pipeline.DEFAULT_POLICY), KEY)


def _scan(analysis, twin):
    originals = evaluate.original_identifier_values(analysis.tables, analysis.detections, analysis.spans)
    return evaluate.leak_scan(originals, twin, "masked", analysis.tables, [("customers", "full_name")])


def test_leak_scan_is_empty_on_demo(masked):
    leak = masked.report["leak_scan"]
    assert leak["hard_fail"] is False
    assert sum(leak["leaked_by_kind"].values()) == 0
    assert leak["names"]["rows_keeping_original_full_name"] == 0
    assert masked.report["verdict"] == "PASS"
    assert not masked.twin_withheld


def _copy_twin(masked):
    return {t: df.copy() for t, df in masked.twin.items()}


def test_deliberate_leak_in_text_fails(analysis, masked):
    twin = _copy_twin(masked)
    real_id = s.canonical("SAUDI_ID", analysis.tables["customers"].national_id.iat[0])
    spaced = f"{real_id[:3]} {real_id[3:6]} {real_id[6:]}".translate(ARABIC)
    twin["claims"].loc[twin["claims"].index[0], "notes"] += f" رقم الهوية {spaced}"
    leak = _scan(analysis, twin)
    assert leak["hard_fail"] and leak["leaked_by_kind"]["SAUDI_ID"] == 1
    assert leak["locations"][0] == {"table": "claims", "column": "notes", "row": 0, "kind": "SAUDI_ID", "method": "detector"}


def test_leak_hidden_from_detector_is_caught_exhaustively(analysis, masked):
    twin = _copy_twin(masked)
    real_id = s.canonical("SAUDI_ID", analysis.tables["customers"].national_id.iat[1])
    twin["claims"].loc[twin["claims"].index[1], "notes"] += f" مرجع{real_id}999"  # glued: no detector candidate
    leak = _scan(analysis, twin)
    assert leak["hard_fail"] and leak["leaks_by_method"]["exhaustive"] == 1


@pytest.mark.parametrize("kind_col", ["mobile", "national_id"])
def test_leak_in_structured_column_fails(analysis, masked, kind_col):
    twin = _copy_twin(masked)
    twin["customers"].loc[twin["customers"].index[5], kind_col] = analysis.tables["customers"][kind_col].iat[5]
    assert _scan(analysis, twin)["hard_fail"]


def test_kept_full_name_fails(analysis, masked):
    twin = _copy_twin(masked)
    twin["customers"].loc[twin["customers"].index[3], "full_name"] = analysis.tables["customers"].full_name.iat[3]
    leak = _scan(analysis, twin)
    assert leak["hard_fail"] and leak["names"]["rows_keeping_original_full_name"] == 1


def test_human_keep_override_on_identifier_fails_and_withholds_twin(analysis):
    res = pipeline.run_masked(analysis, load_policy(pipeline.DEFAULT_POLICY), KEY,
                              overrides={"customers.mobile": {"action": {"action": "keep"}}})
    assert res.report["verdict"] == "FAIL"
    assert "leak_scan" in res.report["failed_checks"]
    assert res.twin_withheld
    col = next(c for c in res.report["columns"] if c["column"] == "mobile")
    assert col["human_reviewed"] and col["action"] == "keep"


def test_report_schema_without_k_anonymity(masked):
    rep = masked.report
    validate(rep)
    names = {c["name"]: c for c in rep["checks"]}
    assert "k_anonymity" not in rep and not any(n.startswith("k_anonymity") for n in names)
    assert names["residual_identifiers"]["blocking"] is True and names["residual_identifiers"]["status"] == "PASS"
    assert rep["limitations"]
    assert "NAZEER_KEY" in rep["key"]["source"]


def test_exact_copies_counts_identical_rows(analysis):
    real = analysis.tables["customers"]
    assert evaluate.exact_copies(real, real.head(7)) == 7
    assert evaluate.exact_copies(real, real.head(0)) == 0


def test_cli_end_to_end_without_raw_values_in_logs(demo_dir, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NAZEER_KEY", KEY.decode())
    code = pipeline.main(["--csv", str(demo_dir), "--mode", "masked", "--out", str(tmp_path)])
    out = capsys.readouterr()
    assert code == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    validate(report)
    assert (tmp_path / "twin" / "customers.csv").exists() and (tmp_path / "twin" / "claims.csv").exists()

    log_text = (tmp_path / "nazeer.log").read_text(encoding="utf-8") + out.out + out.err
    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    customers = load_csv_folder(demo_dir)["customers"]
    for i in range(len(customers)):
        row = customers.iloc[i]
        for needle in (s.canonical("SAUDI_ID", row.national_id), s.canonical("MOBILE", row.mobile), row.full_name):
            assert needle not in log_text
            assert needle not in report_text
    assert KEY.decode() not in log_text and KEY.decode() not in report_text
