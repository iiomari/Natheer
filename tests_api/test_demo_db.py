"""Demo database connection: read-only, the normal flow end to end, credentials never exposed."""
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from nazeer_api.models import AuditEvent
from tests_api.test_p2 import masked_twin, org_admin, work  # noqa: F401

from nazeer_api.demo_seed import build, write  # noqa: E402


@pytest.fixture
def demo_db(tmp_path):
    path = tmp_path / "demo.sqlite"
    write(f"sqlite:///{path}", build(patients=120, appointments=300))
    return f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true"      # read-only, like the SELECT-only user


def use(app, url):
    app.state.settings = replace(app.state.settings, demo_db_url=url)


def test_hidden_when_not_configured(app, org_admin):
    admin, org = org_admin
    use(app, None)
    assert admin.get(f"/api/orgs/{org}/demo-db/tables").json() == {"available": False, "tables": []}


def test_connection_is_read_only(demo_db):
    from nazeer_api.demo_db import _engine

    eng = _engine(demo_db)
    with eng.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM patients")).scalar_one() == 120
        with pytest.raises(OperationalError):
            conn.execute(text("INSERT INTO patients (patient_id, full_name, national_id) VALUES ('X', 'Y', '1')"))
    eng.dispose()


def test_tables_import_and_the_full_flow(app, org_admin, demo_db):
    admin, org = org_admin
    use(app, demo_db)
    r = admin.get(f"/api/orgs/{org}/demo-db/tables").json()
    assert r["available"] and r["tables"] == [{"name": "appointments", "rows": 300}, {"name": "patients", "rows": 120}]
    assert admin.post(f"/api/orgs/{org}/demo-db/import", json={"tables": ["nope"]}).status_code == 422
    ds = admin.post(f"/api/orgs/{org}/demo-db/import", json={"tables": ["patients", "appointments"]}).json()
    work(app)
    ds = admin.get(f"/api/orgs/{org}/datasets/{ds['id']}").json()
    assert ds["status"] == "ready" and ds["name"] == "قاعدة البيانات التجريبية"
    s = ds["summary"]
    assert {t["name"] for t in s["tables"]} == {"patients", "appointments"}
    assert s["relationships"] and s["relationships"][0]["parent_table"] == "patients"
    assert s["found_by_type"]["SAUDI_ID"] == 120
    twin = masked_twin(app, admin, org, ds["id"])
    assert twin["verdict"] == "PASS"
    share = admin.post(f"/api/orgs/{org}/twins/{twin['id']}/shares", json={"external_labels": ["x"]})
    assert share.status_code == 201


def test_credentials_never_appear(app, org_admin, caplog):
    admin, org = org_admin
    secret = "S3cretDemoPassw0rd"
    use(app, f"mysql+pymysql://nazeer_demo_ro:{secret}@127.0.0.1:1/nazeer_demo_source")
    caplog.set_level(logging.DEBUG)
    r = admin.get(f"/api/orgs/{org}/demo-db/tables")
    assert r.status_code == 502 and r.json() == {"code": "demo_db_unreachable"}
    r2 = admin.post(f"/api/orgs/{org}/demo-db/import", json={"tables": ["patients"]})
    assert r2.status_code == 502
    with app.state.sessionmaker() as db:
        audit = json.dumps([e.meta for e in db.query(AuditEvent).all()], ensure_ascii=False)
    blob = r.text + r2.text + caplog.text + audit + repr(app.state.settings)
    assert secret not in blob and "nazeer_demo_ro" not in blob
