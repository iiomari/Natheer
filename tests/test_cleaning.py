"""Cleaning rules: one test per rule, plus safety (never changes meaning, never touches identifiers)."""
import json

import pandas as pd

from nazeer.cleaning import CleanOptions, category_suggestions, clean, examples, potential, report_only


def T(**cols):
    return {"t": pd.DataFrame({k: pd.Series(v, dtype=object) for k, v in cols.items()})}


def test_trim_collapses_spaces_and_removes_invisible_characters():
    out, rep = clean(T(a=["  أحمد   علي ", "x​ y", "﻿bom", "nb sp"]))
    assert out["t"]["a"].tolist() == ["أحمد علي", "x y", "bom", "nb sp"]
    assert rep["applied"]["trim"]["total"] == 4


def test_null_like_whole_cells_only():
    notes = ["NULL", "n/a", "-", "  ", "لا يوجد", "المريض قال null لا شيء", "N/A في الملف"]
    out, rep = clean(T(n=notes), CleanOptions(dedupe=False))
    assert out["t"]["n"].tolist()[:5] == [None] * 5
    assert out["t"]["n"].tolist()[5:] == ["المريض قال null لا شيء", "N/A في الملف"]  # text inside notes kept
    assert rep["applied"]["nulls"]["total"] == 5


def test_exact_duplicate_rows_removed_and_counted():
    out, rep = clean(T(a=["1", "1", "2"], b=["x", "x", "x"]))
    assert len(out["t"]) == 2 and rep["applied"]["dedupe"]["by_column"] == {"t": 1}


def test_numbers_stored_as_text_become_plain_numbers():
    out, _ = clean(T(amount=["١٬٢٣٤٫٥", "1,234", "56", "+7.25", "٩٠"] * 5), CleanOptions(dedupe=False))
    assert out["t"]["amount"].tolist()[:5] == ["1234.5", "1234", "56", "7.25", "90"]


def test_numbers_never_touch_identifiers_or_leading_zeros():
    ids = ["1110704341", "1909266858", "2129040479"] * 10
    mobiles = ["0503318842", "0551234567", "0567654321"] * 10
    codes = ["007", "012", "123"] * 10
    out, rep = clean(T(nid=ids, mobile=mobiles, code=codes), CleanOptions(dedupe=False))
    assert out["t"]["nid"].tolist() == ids and out["t"]["mobile"].tolist() == mobiles and out["t"]["code"].tolist() == codes
    assert rep["applied"].get("numbers", {}).get("total", 0) == 0


def test_dates_to_iso_when_confident():
    out, _ = clean(T(d=["25/09/2024", "1/12/2023", "٣١/٠١/٢٠٢٥"]))
    assert out["t"]["d"].tolist() == ["2024-09-25", "2023-12-01", "2025-01-31"]
    out, _ = clean(T(d=["2024/9/5", "2023/12/31"]))
    assert out["t"]["d"].tolist() == ["2024-09-05", "2023-12-31"]


def test_ambiguous_dates_left_alone_and_reported():
    vals = ["01/02/2024", "03/04/2024", "05/06/2024"]  # dd/mm and mm/dd both fit every value
    out, rep = clean(T(d=vals))
    assert out["t"]["d"].tolist() == vals and rep["ambiguous_dates"] == ["t.d"]


def test_arabic_normalization_is_off_by_default_and_never_on_names():
    cats = ["الأدوية", "الادوية", "إسعاف", "طوارئ"] * 9
    names = ["أحمد العتيبي", "إبراهيم الحربي", "سارة القحطاني"] * 12
    out, _ = clean(T(cat=cats, name=names), CleanOptions(dedupe=False))
    assert out["t"]["cat"].tolist() == cats  # off by default
    out, rep = clean(T(cat=cats, name=names), CleanOptions(arabic=True, dedupe=False))
    assert out["t"]["cat"].tolist()[:3] == ["الادويه", "الادويه", "اسعاف"]
    assert out["t"]["name"].tolist() == names  # names are never normalized
    assert "t.name" not in rep["applied"]["arabic"]["by_column"]


def test_phone_unification_opt_in():
    vals = ["+966503318842", "966551234567", "0567654321", "00966500000001"] * 5
    out, _ = clean(T(mobile=vals), CleanOptions(dedupe=False))
    assert out["t"]["mobile"].tolist() == vals  # off by default
    out, _ = clean(T(mobile=vals), CleanOptions(phones=True, dedupe=False))
    assert set(out["t"]["mobile"]) == {"0503318842", "0551234567", "0567654321", "0500000001"}


def test_category_merges_only_when_approved_by_key():
    vals = ["عيادات خارجية"] * 10 + ["عيادات  خارجيه"] * 3 + ["أدوية"] * 8 + ["ادوية"] * 2
    tables = T(kind=vals)
    sug = category_suggestions(tables)
    assert {g["to"] for g in sug} == {"عيادات خارجية", "أدوية"}
    out, _ = clean(tables, CleanOptions(dedupe=False))
    assert out["t"]["kind"].nunique() == 4  # nothing merged without approval
    first = next(g for g in sug if g["to"] == "أدوية")
    out, rep = clean(tables, CleanOptions(merges=[first["key"]], dedupe=False))
    assert set(out["t"]["kind"]) == {"عيادات خارجية", "أدوية"} | {"عيادات خارجيه"}
    assert rep["options"]["merges"] == 1


def test_report_only_flags_without_fixing():
    amounts = [str(x) for x in range(100, 140)] + ["99999"]
    mixed = ["1", "2", "abc", "3", "x", "4", "y", "5", "z", "6"] * 4 + ["7"]
    rep = report_only(T(amount=amounts, mixed=mixed, gap=[None] * 20 + ["a"] * 21))
    by = {r["column"]: r for r in rep}
    assert by["amount"]["extreme_outliers"] == 1
    assert by["mixed"]["mixed_types"] is True
    assert by["gap"]["missing"] == 20
    mobiles = ["+966503318842", "0551234567", "0567654321", "+966500000001"] * 10
    assert report_only(T(mobile=mobiles)) == []  # identifiers are not quantities: no outlier statistics


def test_report_is_value_free_and_examples_show_before_after():
    tables = T(name=["  أحمد ", "NULL"], amount=["١٬٠٠٠", "20"])
    _, rep = clean(tables)
    blob = json.dumps(rep, ensure_ascii=False)
    assert "أحمد" not in blob and "١٬٠٠٠" not in blob
    ex = examples(tables, "trim")
    assert ex[0]["before"] == "  أحمد " and ex[0]["after"] == "أحمد"
    pot = potential(tables)
    assert pot["trim"] == 1 and pot["nulls"] == 1 and pot["arabic"] == 0


def test_cleaned_demo_still_detects_and_masks(tmp_path):
    from data_gen import make_demo_data as demo
    from nazeer import pipeline
    from nazeer.policy import load_policy
    from nazeer.tableio import load_csv_folder

    demo.main(["--seed", "8", "--n", "120", "--out", str(tmp_path)])
    tables, rep = clean(load_csv_folder(tmp_path))
    an = pipeline.analyze(tables, "x")
    assert any(d.kind == "SAUDI_ID" for d in an.detections) and an.spans
    res = pipeline.run_masked(an, load_policy(pipeline.DEFAULT_POLICY), b"k" * 40, apply_fix="auto")
    assert res.report["leak_scan"]["verdict"] == "PASS"
