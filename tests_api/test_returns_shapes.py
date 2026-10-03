"""Returns lists never break: empty, legacy (made before the verification token) and normal returns,
for the organization (admin) and for the recipient. The API always returns the complete shape."""
from nazeer_api.models import Return
from tests_api.test_p2 import org_admin  # noqa: F401
from tests_api.test_p5_tokens import download, make_patients, share_to_employee, submit, to_xlsx

REPORT_KEYS = {"rows_returned", "rows_shared", "coverage", "counts", "integrity", "rows_by_status", "added_columns",
               "rows_changed_in_twin_columns", "tables"}
COUNT_KEYS = {"verified", "invalid", "missing", "foreign", "old_key", "duplicate"}


def complete(item):
    assert REPORT_KEYS <= set(item["report"]) and set(item["report"]["counts"]) == COUNT_KEYS
    assert isinstance(item["report"]["added_columns"], dict) and isinstance(item["report"]["rows_by_status"], dict)
    assert isinstance(item["added_columns"], list) and "legacy" in item


def test_empty_legacy_and_normal_returns(app, org_admin):
    admin, org = org_admin
    emp, share, twin, _ = share_to_employee(app, admin, org, make_patients(60))
    # empty
    assert admin.get(f"/api/orgs/{org}/returns").json() == []
    assert emp.get(f"/api/received/{share['id']}/returns").json() == []

    # legacy: a row as P5 (nazeer_ref) stored it, without a verification report
    with app.state.sessionmaker() as db:
        db.add(Return(org_id=org, share_id=share["id"], twin_id=twin["id"], submitted_by=emp.get("/api/auth/me").json()["id"],
                      file_name="old.csv", rows_total=12, rows_accepted=12, rejected={"ref_mismatch": 0},
                      columns=["score"], blob_id=None, report=None))
        db.commit()
    # normal
    sub = download(emp, share["id"]).head(10).copy()
    sub["score"] = "1"
    assert submit(emp, share["id"], to_xlsx(sub)).status_code == 201

    org_list = admin.get(f"/api/orgs/{org}/returns").json()
    mine = emp.get(f"/api/received/{share['id']}/returns").json()
    assert len(org_list) == len(mine) == 2
    for item in org_list + mine:
        complete(item)
    legacy = next(x for x in org_list if x["file_name"] == "old.csv")
    normal = next(x for x in org_list if x["file_name"] != "old.csv")
    assert legacy["legacy"] is True and legacy["relinkable"] is False and legacy["report"]["counts"]["verified"] == 0
    assert normal["legacy"] is False and normal["relinkable"] is True and normal["report"]["counts"]["verified"] == 10
    assert next(x for x in mine if x["file_name"] == "old.csv")["legacy"] is True
    detail = admin.get(f"/api/orgs/{org}/returns/{legacy['id']}").json()
    complete(detail)
    r = admin.post(f"/api/orgs/{org}/returns/{legacy['id']}/relink", files=[("files", ("p.csv", b"a\n1", "text/csv"))])
    assert r.status_code == 422 and r.json()["code"] == "relink_no_verified"
