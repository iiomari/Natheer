"""P4: cleaning before detection, through the API (toggles, previews, approvals, report)."""
import json

from sqlalchemy import select

from nazeer_api.models import AuditEvent, Blob
from tests_api.conftest import invite_and_join
from tests_api.test_p2 import demo_files, masked_twin, org_admin, ready_dataset, work  # noqa: F401

MESSY = ("ID,Name,Kind,Amount,Visit,Note\n"
         "1,أحمد   العتيبي,أدوية,\"1,250\",25/09/2024,NULL\n"
         "2,سارة القحطاني,ادوية,٣٠٠,1/12/2023,-\n"
         "3,خالد الحربي,أدوية,40,31/01/2025,موعد عادي\n"
         "4,نورة الشهري,أدوية,55,02/02/2024,N/A\n"
         "5,فهد الزهراني,عيادات,60,03/03/2024,\n"
         "5,فهد الزهراني,عيادات,60,03/03/2024,\n"
         "6,ريم الدوسري,عيادات,70,04/03/2024,متابعة\n").encode("utf-8")


def _ds(client, org, ds_id):
    return client.get(f"/api/orgs/{org}/datasets/{ds_id}").json()


def test_defaults_clean_before_detection_and_report_counts(app, org_admin):
    admin, org = org_admin
    ds = ready_dataset(app, admin, org, [("visits.csv", MESSY)])
    c = ds["summary"]["cleaning"]
    applied = {r: v["total"] for r, v in c["report"]["applied"].items()}
    assert applied["trim"] >= 1 and applied["nulls"] >= 2 and applied["dedupe"] == 1 and applied["dates"] >= 5
    assert ds["summary"]["total_rows"] == 6 and c["rows_before"] == 7
    assert c["potential"]["arabic"] >= 1 and c["report"]["options"]["arabic"] is False
    assert any(g["column"] == "Kind" for g in c["suggestions"])
    blob = json.dumps(ds["summary"]["cleaning"], ensure_ascii=False)
    assert "أحمد" not in blob and "ادوية" not in blob  # stored summary is value-free


def test_examples_and_suggestions_are_session_only(app, org_admin):
    admin, org = org_admin
    ds = ready_dataset(app, admin, org, [("visits.csv", MESSY)])
    ex = admin.get(f"/api/orgs/{org}/datasets/{ds['id']}/cleaning/examples/trim").json()["examples"]
    assert {"before": "أحمد   العتيبي", "after": "أحمد العتيبي"}.items() <= ex[0].items()
    sug = admin.get(f"/api/orgs/{org}/datasets/{ds['id']}/cleaning/suggestions").json()
    assert any(g["to"] == "أدوية" and "ادوية" in g["from"] for g in sug)
    assert admin.get(f"/api/orgs/{org}/datasets/{ds['id']}/cleaning/examples/bogus").status_code == 404
    admin.post(f"/api/orgs/{org}/datasets/{ds['id']}/end-session")
    assert admin.get(f"/api/orgs/{org}/datasets/{ds['id']}/cleaning/examples/trim").status_code == 410
    assert admin.get(f"/api/orgs/{org}/datasets/{ds['id']}/cleaning/suggestions").status_code == 410
    assert admin.post(f"/api/orgs/{org}/datasets/{ds['id']}/clean", json={}).status_code == 410


def test_reclean_with_new_options_and_approved_merge(app, org_admin):
    admin, org = org_admin
    ds = ready_dataset(app, admin, org, [("visits.csv", MESSY)])
    key = next(g["key"] for g in ds["summary"]["cleaning"]["suggestions"] if g["column"] == "Kind")
    r = admin.post(f"/api/orgs/{org}/datasets/{ds['id']}/clean",
                   json={"dedupe": False, "merges": [key], "arabic": False})
    assert r.status_code == 202
    assert _ds(admin, org, ds["id"])["status"] == "processing"
    work(app)
    ds2 = _ds(admin, org, ds["id"])
    assert ds2["status"] == "ready" and ds2["summary"]["total_rows"] == 7
    rep = ds2["summary"]["cleaning"]["report"]
    assert rep["options"]["dedupe"] is False and rep["options"]["merges"] == 1
    assert rep["applied"]["merges"]["total"] == 1
    assert next(g for g in ds2["summary"]["cleaning"]["suggestions"] if g["key"] == key)["approved"] is True
    with app.state.sessionmaker() as db:
        kinds = sorted(b.kind for b in db.execute(select(Blob).where(Blob.dataset_id == ds["id"])).scalars())
        ev = db.execute(select(AuditEvent).where(AuditEvent.action == "dataset.cleaning_changed")).scalar_one()
    assert kinds == ["clean", "tables"]  # one cleaned copy, replaced, never accumulated
    assert "أدوية" not in json.dumps(ev.meta, ensure_ascii=False)
    bad = admin.post(f"/api/orgs/{org}/datasets/{ds['id']}/clean", json={"merges": ["أدوية"]})
    assert bad.status_code == 422


def test_twin_report_and_recipient_see_what_was_cleaned(app, org_admin, demo_files):
    admin, org = org_admin
    emp, _ = invite_and_join(app, admin, org, "employee@alwaha.example.com")
    ds = ready_dataset(app, admin, org, demo_files)
    twin = masked_twin(app, admin, org, ds["id"], apply_fix="auto")
    assert twin["verdict"] == "PASS"
    rep = admin.get(f"/api/orgs/{org}/twins/{twin['id']}/report.json").json()
    assert rep["cleaning"]["options"]["trim"] is True and "applied" in rep["cleaning"]
    emp_m = next(m for m in admin.get(f"/api/orgs/{org}/members").json() if m["email"] == "employee@alwaha.example.com")
    admin.post(f"/api/orgs/{org}/twins/{twin['id']}/shares", json={"member_ids": [emp_m["id"]]})
    got = emp.get("/api/received").json()[0]
    assert {"trim", "nulls", "numbers", "dates", "dedupe"} <= set(got["cleaning"]["rules"])
    assert "arabic" not in got["cleaning"]["rules"]


def test_member_without_data_role_cannot_clean(app, org_admin):
    admin, org = org_admin
    ds = ready_dataset(app, admin, org, [("visits.csv", MESSY)])
    other, _ = invite_and_join(app, admin, org, "m@alwaha.example.com", role="member")
    assert other.post(f"/api/orgs/{org}/datasets/{ds['id']}/clean", json={}).status_code == 403
    assert other.get(f"/api/orgs/{org}/datasets/{ds['id']}/cleaning/suggestions").status_code == 403
