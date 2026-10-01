"""Headless UI tests of the Streamlit flow (streamlit.testing.v1.AppTest)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from data_gen import make_demo_data as demo

APP = str(Path(__file__).resolve().parents[1] / "nazeer" / "app.py")
KEY = "app-test-key-0123456789-0123456789"


@pytest.fixture(scope="module")
def small_demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    demo.main(["--seed", "3", "--n", "300", "--out", str(out)])
    return out


@pytest.fixture
def app(small_demo, monkeypatch):
    monkeypatch.setenv("NAZEER_DEMO_DIR", str(small_demo))
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    assert not at.exception
    return at


def _md(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def _to_twin_step(at):
    """Demo loaded -> step 2 -> step 3 (the "generate" button)."""
    at.button(key="next_1").click().run()
    at.button(key="next_2").click().run()
    assert not at.exception
    return at


def test_demo_walkthrough_four_steps(app, monkeypatch):
    """Smoke test of the pitch path: demo mode, no key typed, all four steps, fix, planted leak, reset."""
    monkeypatch.delenv("NAZEER_KEY", raising=False)
    assert app.session_state["step"] == 1 and app.session_state["tables"] is None
    assert "تحميل بيانات العرض" in [b.label for b in app.button]

    # 1. data: both tables, tracked customer highlighted
    app.button(key="demo").click().run()
    assert not app.exception
    assert app.session_state["analysis"] is not None and app.session_state["demo_mode"]
    tracked = app.session_state["tracked"]
    assert tracked is not None and app.selectbox(key="track_pick").value == tracked
    md = _md(app)
    assert "١. البيانات" in [h.value for h in app.header]
    assert "customers" in md and "claims" in md and "المتتبَّع" in md

    # 2. detection: baseline vs Nazeer, same note, highlights carry text labels
    app.button(key="next_1").click().run()
    assert not app.exception and app.session_state["step"] == 2
    md = _md(app)
    assert "أداة تقليدية" in md and "نَظير" in md and "إنذارات كاذبة" in md
    assert 'class="nz-lab' in md and "هوية" in md
    assert app.session_state["tracked"] == tracked  # the selection survives the step change

    # 3. twin: generated with the preset demo key, before/after of the same customer
    app.button(key="next_2").click().run()
    app.button(key="run").click().run()
    assert not app.exception
    res = app.session_state["result"]
    assert res is not None and res.mode == "masked" and not res.twin_withheld
    assert "demo" in res.report["key"]["source"]
    md = _md(app)
    assert "الأصل" in md and "النظير" in md and 'class="changed"' in md
    assert "نفس الأعداد والمجاميع والروابط — بدون عميل حقيقي." in md

    # 4. proof: four verdict cards; k-anonymity fix turns the verdict to PASS
    app.button(key="next_3").click().run()
    assert not app.exception and app.session_state["step"] == 4
    md = _md(app)
    for title in ("تسريب", "صلاحية البدائل", "سلامة الروابط", "خطر التعرّف بالتركيب"):
        assert title in md
    assert md.count('class="nz-card ') >= 4
    k = res.report["k_anonymity"]["customers"]
    if not k["passed_before"]:
        assert res.report["verdict"] == "FAIL"
        app.button(key="apply_fix").click().run()
        assert not app.exception
        rep = app.session_state["result"].report
        k2 = rep["k_anonymity"]["customers"]
        assert k2["applied_fix"]["name"] == k["suggestions"][0]["name"]  # the recommended fix
        assert k2["k_before"] == k["k_before"] and k2["passed_after"]
        assert rep["verdict"] == "PASS" and "النتيجة" in _md(app)

    # planted leak is caught by the real leak scan; the delivered twin is untouched
    twin_before = app.session_state["result"].twin["claims"].copy()
    app.button(key="plant_leak").click().run()
    assert not app.exception
    planted = app.session_state["planted"]
    assert planted["leak"]["verdict"] == "FAIL" and sum(planted["leak"]["leaked_by_kind"].values()) >= 1
    assert "تسريب" in _md(app)
    assert app.session_state["result"].twin["claims"].equals(twin_before)
    app.button(key="unplant_leak").click().run()
    assert app.session_state["planted"] is None

    # reset
    app.button(key="reset").click().run()
    assert not app.exception
    assert app.session_state["tables"] is None and app.session_state["step"] == 1


def test_session_from_before_the_redesign_does_not_crash(app):
    """A browser tab opened before the redesign keeps its analysis across a code reload but has
    no tracking keys; the derived state must be rebuilt instead of raising AttributeError."""
    app.button(key="demo").click().run()
    for k in ("labels", "tracked", "golden"):
        app.session_state[k] = None
    app.run()
    app.button(key="next_1").click().run()
    assert not app.exception
    assert app.session_state["labels"] and app.session_state["tracked"] in app.session_state["labels"]
    assert app.session_state["golden"] is not None and "أداة تقليدية" in _md(app)


def test_flow_load_detect_run_results(app, monkeypatch):
    monkeypatch.setenv("NAZEER_KEY", KEY)
    app.button(key="demo").click().run()
    assert not app.exception
    an = app.session_state["analysis"]
    assert an is not None and an.spans
    app.button(key="next_1").click().run()
    assert "٢. الكشف" in [h.value for h in app.header]
    app.button(key="next_2").click().run()
    app.button(key="run").click().run()
    assert not app.exception
    res = app.session_state["result"]
    assert res is not None and res.mode == "masked"
    assert "NAZEER_KEY" in res.report["key"]["source"]  # a real key is used when one is set
    app.button(key="next_3").click().run()
    assert "٤. الإثبات" in [h.value for h in app.header]
    assert "النتيجة" in _md(app)


def test_missing_key_shows_message_not_traceback(app, monkeypatch):
    """Outside demo mode (uploads, MySQL) the preset key is never used: NAZEER_KEY is required."""
    monkeypatch.delenv("NAZEER_KEY", raising=False)
    app.button(key="demo").click().run()
    app.session_state["demo_mode"] = False  # as if the same tables had been uploaded
    app.run()
    _to_twin_step(app)
    app.button(key="run").click().run()
    assert not app.exception
    assert app.session_state["result"] is None
    assert any("NAZEER_KEY" in e.value for e in app.error)


def test_synthetic_flow(app):
    app.button(key="demo").click().run()
    app.radio(key="mode").set_value("synthetic").run()
    assert app.text_input(key="target").value == "is_large_claim=amount>p90"
    _to_twin_step(app)
    app.button(key="run").click().run()
    assert not app.exception
    res = app.session_state["result"]
    assert res is not None and res.mode == "synthetic"
    assert res.report["utility"]["max_auc_drop"] is not None
    app.button(key="next_3").click().run()
    assert not app.exception
    md = _md(app)
    assert "الفائدة للتحليل" in md and "تجريبي" in md


def test_override_and_kanon_apply_in_ui(app, monkeypatch):
    monkeypatch.setenv("NAZEER_KEY", KEY)
    app.button(key="demo").click().run()
    app.session_state["overrides"] = {"customers.national_id": {"tag": "DIRECT_ID", "kind": "SAUDI_ID"}}
    _to_twin_step(app)
    app.button(key="run").click().run()
    assert not app.exception
    rep = app.session_state["result"].report
    col = next(c for c in rep["columns"] if c["column"] == "national_id")
    assert col["human_reviewed"]
    k = rep["k_anonymity"]["customers"]
    if k["passed_before"]:
        pytest.skip("demo sample already k-anonymous; nothing to apply")
    app.button(key="next_3").click().run()
    pick = k["suggestions"][-1]["name"]  # not the recommended one: the choice must be honoured
    app.selectbox(key="fix_pick").set_value(pick).run()
    app.button(key="apply_fix").click().run()
    assert not app.exception
    k2 = app.session_state["result"].report["k_anonymity"]["customers"]
    assert k2["applied_fix"]["name"] == pick
    assert k2["k_before"] == k["k_before"] and k2["k_after"] >= k["k_after"]


def test_mysql_connect_without_credentials_shows_message(app, monkeypatch):
    monkeypatch.setenv("NAZEER_MYSQL_PASSWORD", "CHANGE_ME")
    app.button(key="mysql_connect").click().run()
    assert not app.exception
    assert app.session_state["tables"] is None
    assert any("waiting for credentials" in e.value for e in app.error)


def test_write_to_source_database_is_refused_in_ui(app, monkeypatch):
    monkeypatch.setenv("NAZEER_KEY", KEY)
    monkeypatch.setenv("NAZEER_MYSQL_PASSWORD", "dummy")
    app.button(key="demo").click().run()
    app.session_state["mysql_db"] = "nazeer_prod_demo"  # pretend the source is MySQL
    app.checkbox(key="write_db").check().run()
    app.text_input(key="target_db").set_value("NAZEER_PROD_DEMO").run()
    _to_twin_step(app)
    app.button(key="run").click().run()
    assert not app.exception
    assert any("SOURCE database" in e.value for e in app.error)
    assert app.session_state["mysql_written"] is None


def test_why_it_works_tab_shows_live_metrics(app, monkeypatch):
    monkeypatch.setenv("NAZEER_KEY", KEY)
    app.button(key="demo").click().run()
    _to_twin_step(app)
    app.button(key="run").click().run()
    assert not app.exception
    assert [t.label for t in app.tabs] == ["نَظير", "ليش يشتغل؟", "جرّب نصّك"]
    why = "\n".join(m.value for m in app.tabs[1].markdown)
    assert why.count('class="nz-why"') == 5
    assert "صالحة" in why and "مقابل" in why and ("ناجح PASS" in why or "راسب FAIL" in why)


def test_try_your_text_tab(app):
    md = "\n".join(m.value for m in app.tabs[2].markdown)
    assert "أداة تقليدية" in md and "بعد الإخفاء" in md
    assert "١١١٠٧٠٤٣٤١" in md  # the example's Arabic-Indic ID is shown (LTR-isolated)
    assert 'class="nz-hl rejected"' in md  # the invoice number fails the checksum
