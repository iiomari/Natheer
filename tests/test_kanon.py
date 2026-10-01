import pandas as pd

from nazeer import kanon


def _df():
    rows = [("الرياض", "30-39", "ذكر")] * 6 + [("الخرج", "30-39", "ذكر")] * 2 + \
           [("جدة", "40-49", "أنثى")] * 5 + [("الطائف", "50-59", "أنثى")] * 1
    return pd.DataFrame(rows, columns=["city", "age", "gender"])


Q = ["city", "age", "gender"]


def test_k_anonymity_counts_smallest_class():
    res = kanon.k_anonymity(_df(), Q, 5)
    assert res.k == 1 and not res.passed
    assert res.rows_in_small_classes == 3


def test_suggestions_report_before_and_after():
    fixes = kanon.suggest_fixes(_df(), Q, 5)
    assert fixes and all(f.k_before == 1 for f in fixes)
    best = fixes[0]
    assert best.reaches_k_min
    fixed = kanon.apply_fix(_df(), best, Q, 5)
    assert kanon.k_anonymity(fixed, Q, 5).k == best.k_after >= 5


def test_region_generalization():
    out = kanon._to_region(pd.Series(["الرياض", "الخرج", "جدة", "مدينة غير معروفة"]))
    assert out.tolist()[:3] == ["منطقة الرياض", "منطقة الرياض", "منطقة مكة المكرمة"]
    assert out.iloc[3] == "مدينة غير معروفة"


def test_widen_bins():
    assert kanon._widen(pd.Series(["30-39", "80-89"])).tolist() == ["20-39", "80-99"]


def test_suppressed_class_itself_reaches_k():
    df = pd.DataFrame({"a": ["x"] * 10 + ["y", "z"]})
    fixed, n = kanon._suppress(df, ["a"], 5)
    assert kanon.k_anonymity(fixed, ["a"], 5).k >= 5
    assert n == 5  # 2 small rows plus 3 pulled in so the "*" class has 5


def test_passing_table_needs_no_fix():
    df = pd.DataFrame({"a": ["x"] * 10})
    assert kanon.k_anonymity(df, ["a"], 5).passed
