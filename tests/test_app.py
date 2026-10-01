"""Headless UI test of the Streamlit flow (streamlit.testing.v1.AppTest)."""
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


def test_flow_load_detect_run_results(app, monkeypatch):
    monkeypatch.setenv("NAZEER_KEY", KEY)
    app.button(key="demo").click().run()
    assert not app.exception
    an = app.session_state["analysis"]
    assert an is not None and an.spans
    headers = [h.value for h in app.header]
    assert "2 · What Nazeer found" in headers
    assert len(app.dataframe) >= 2  # detection table + baseline comparison
    app.button(key="run").click().run()
    assert not app.exception
    res = app.session_state["result"]
    assert res is not None and res.mode == "masked"
    assert "4 · Evidence" in [h.value for h in app.header]
    verdict_boxes = [m.value for m in list(app.success) + list(app.error)]
    assert any("Verdict" in v for v in verdict_boxes)


def test_missing_key_shows_message_not_traceback(app, monkeypatch):
    monkeypatch.delenv("NAZEER_KEY", raising=False)
    app.button(key="demo").click().run()
    app.button(key="run").click().run()
    assert not app.exception
    assert app.session_state["result"] is None
    assert any("NAZEER_KEY" in e.value for e in app.error)
