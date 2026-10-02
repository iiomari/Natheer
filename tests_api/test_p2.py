"""P2: upload -> detection -> masked twin -> report -> share -> recipient sees and downloads."""
import io
import zipfile
from dataclasses import replace
from datetime import timedelta

import pytest
from openpyxl import load_workbook
from sqlalchemy import select, update

from data_gen import make_demo_data as demo
from nazeer_api.db import utcnow
from nazeer_api.models import Blob, Dataset, Share
from nazeer_api.processing import sweep
from nazeer_api.worker import run_one
from tests_api.conftest import invite_and_join, new_client, signup, token_of


@pytest.fixture(scope="module")
def demo_files(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    demo.main(["--seed", "5", "--n", "150", "--out", str(out)])
    files = [(p.name, p.read_bytes()) for p in sorted(out.glob("*.csv"))]
    # a hostile cell: must come out of every export as text, never as a formula
    name, data = files[0]
    files[0] = (name, data.replace(b"\n", b"\n", 1))
    return files


def work(app, n=5):
    for _ in range(n):
        if not run_one(app.state.sessionmaker, app.state.settings, "test-worker"):
            break


def upload(client, org, files, name="demo"):
    r = client.post(f"/api/orgs/{org}/datasets", data={"name": name},
                    files=[("files", (n, d, "text/csv")) for n, d in files])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def ready_dataset(app, client, org, files):
    ds_id = upload(client, org, files)
    work(app)
    ds = client.get(f"/api/orgs/{org}/datasets/{ds_id}").json()
    assert ds["status"] == "ready", ds
    return ds


def masked_twin(app, client, org, ds_id, **extra):
    r = client.post(f"/api/orgs/{org}/datasets/{ds_id}/generate", json={"mode": "masked", **extra})
    assert r.status_code == 202, r.text
    work(app)
    ds = client.get(f"/api/orgs/{org}/datasets/{ds_id}").json()
    assert ds["generate_job"]["status"] == "succeeded", ds["generate_job"]
    return client.get(f"/api/orgs/{org}/twins/{ds['generate_job']['result']['twin_id']}").json()


@pytest.fixture
def org_admin(app):
    c, me = signup(app, "admin@alwaha.example.com", org="الواحة للتأمين")
    return c, me["memberships"][0]["org_id"]


def test_full_story_upload_detect_twin_share_receive_download(app, org_admin, demo_files):
    admin, org = org_admin
    emp, _ = invite_and_join(app, admin, org, "employee@alwaha.example.com")
    ds = ready_dataset(app, admin, org, demo_files)
    summary = ds["summary"]
    assert {t["name"] for t in summary["tables"]} == {"customers", "claims"}
    assert summary["relationships"] and summary["notes"]
    assert summary["spans"]["nazeer_found"] > summary["spans"]["baseline_found"]
    note = admin.get(f"/api/orgs/{org}/datasets/{ds['id']}/notes/0").json()
    assert note["text"] and note["nazeer"]

    twin = masked_twin(app, admin, org, ds["id"], apply_fix="auto")
    assert twin["verdict"] == "PASS" and twin["proof"]["leak"]["status"] == "PASS"
    preview = admin.get(f"/api/orgs/{org}/twins/{twin['id']}/preview").json()
    assert preview["tables"] and any(cell[2] for t in preview["tables"] for r in t["rows"] for cell in r.values())

    members = admin.get(f"/api/orgs/{org}/members").json()
    emp_m = next(m for m in members if m["email"] == "employee@alwaha.example.com")
    share = admin.post(f"/api/orgs/{org}/twins/{twin['id']}/shares",
                       json={"member_ids": [emp_m["id"]], "external_labels": ["شريك خارجي"]}).json()
    assert share["status"] == "active" and len(share["new_links"]) == 1

    # the employee sees it immediately in "received"
    got = emp.get("/api/received").json()
    assert [g["id"] for g in got] == [share["id"]] and got[0]["org_name"] == "الواحة للتأمين"
    detail = emp.get(f"/api/received/{share['id']}").json()
    assert detail["preview"] and detail["proof"]["leak"]["status"] == "PASS"
    for fmt in ("csv", "xlsx"):
        url = emp.post(f"/api/received/{share['id']}/download", json={"format": fmt}).json()["url"]
        r = emp.get(url)
        assert r.status_code == 200 and len(r.content) > 100
    assert admin.get(f"/api/orgs/{org}/shares").json()[0]["download_count"] == 2


def test_twin_downloads_contain_no_original_identifier(app, org_admin, demo_files):
    admin, org = org_admin
    ds = ready_dataset(app, admin, org, demo_files)
    twin = masked_twin(app, admin, org, ds["id"], apply_fix="auto")
    me_id = admin.get("/api/auth/me").json()
    share = admin.post(f"/api/orgs/{org}/twins/{twin['id']}/shares", json={"external_labels": ["x"]}).json()
    rec, _ = signup(app, "rec@example.com", org=None)
    rec.post("/api/share-links/accept", json={"token": token_of(share["new_links"][0]["link_path"])})
    data = rec.get(rec.post(f"/api/received/{share['id']}/download", json={"format": "csv"}).json()["url"]).content
    text = " ".join(zipfile.ZipFile(io.BytesIO(data)).read(n).decode("utf-8-sig") for n in zipfile.ZipFile(io.BytesIO(data)).namelist())
    originals = demo_files[1][1].decode("utf-8")  # customers.csv
    ids = [line.split(",")[2] for line in originals.splitlines()[1:6]]
    assert ids and not any(i in text for i in ids)
    assert me_id


def test_fail_twin_cannot_be_shared(app, org_admin, demo_files):
    admin, org = org_admin
    ds = ready_dataset(app, admin, org, demo_files)
    twin = masked_twin(app, admin, org, ds["id"])  # no k-anonymity fix -> FAIL on this demo
    assert twin["verdict"] == "FAIL"
    r = admin.post(f"/api/orgs/{org}/twins/{twin['id']}/shares", json={"external_labels": ["x"]})
    assert r.status_code == 409 and r.json()["code"] == "twin_not_shareable"


def _shared(app, admin, org, demo_files):
    ds = ready_dataset(app, admin, org, demo_files)
    twin = masked_twin(app, admin, org, ds["id"], apply_fix="auto")
    return admin.post(f"/api/orgs/{org}/twins/{twin['id']}/shares",
                      json={"external_labels": ["a", "b"], "formats": ["csv"]}).json()


def test_account_that_did_not_accept_the_link_cannot_see_the_share(app, org_admin, demo_files):
    admin, org = org_admin
    share = _shared(app, admin, org, demo_files)
    # registered with the very email the admin had in mind, but never opened the link
    squatter, _ = signup(app, "partner@example.com", org=None)
    assert squatter.get("/api/received").json() == []
    assert squatter.get(f"/api/received/{share['id']}").status_code == 404
    assert squatter.post(f"/api/received/{share['id']}/download", json={"format": "csv"}).status_code == 404
    partner, _ = signup(app, "real-partner@example.com", org=None)
    token = token_of(share["new_links"][0]["link_path"])
    assert partner.post("/api/share-links/accept", json={"token": token}).status_code == 200
    assert [g["id"] for g in partner.get("/api/received").json()] == [share["id"]]
    # the link is single use: another account cannot reuse it
    r = squatter.post("/api/share-links/accept", json={"token": token})
    assert r.status_code == 409 and r.json()["code"] == "link_already_used"
    assert squatter.get("/api/received").json() == []


def test_expired_and_revoked_shares_are_blocked(app, org_admin, demo_files):
    admin, org = org_admin
    share = _shared(app, admin, org, demo_files)
    rec, _ = signup(app, "r1@example.com", org=None)
    rec.post("/api/share-links/accept", json={"token": token_of(share["new_links"][0]["link_path"])})
    url = rec.post(f"/api/received/{share['id']}/download", json={"format": "csv"}).json()["url"]
    admin.post(f"/api/orgs/{org}/shares/{share['id']}/revoke")
    assert rec.get(url).status_code == 410
    assert rec.get(f"/api/received/{share['id']}").json()["status"] == "revoked"
    assert rec.post(f"/api/received/{share['id']}/download", json={"format": "csv"}).status_code == 410

    share2 = _shared(app, admin, org, demo_files)
    rec2, _ = signup(app, "r2@example.com", org=None)
    rec2.post("/api/share-links/accept", json={"token": token_of(share2["new_links"][0]["link_path"])})
    with app.state.sessionmaker() as db:
        db.execute(update(Share).where(Share.id == share2["id"]).values(expires_at=utcnow() - timedelta(minutes=1)))
        db.commit()
    assert rec2.post(f"/api/received/{share2['id']}/download", json={"format": "csv"}).status_code == 410
    # an unaccepted link of an expired share cannot be accepted either
    late, _ = signup(app, "late@example.com", org=None)
    assert late.post("/api/share-links/accept", json={"token": token_of(share2["new_links"][1]["link_path"])}).status_code == 410


def test_download_link_is_bound_signed_and_format_limited(app, org_admin, demo_files):
    admin, org = org_admin
    share = _shared(app, admin, org, demo_files)
    rec, _ = signup(app, "r3@example.com", org=None)
    rec.post("/api/share-links/accept", json={"token": token_of(share["new_links"][0]["link_path"])})
    assert rec.post(f"/api/received/{share['id']}/download", json={"format": "xlsx"}).json()["code"] == "format_not_allowed"
    url = rec.post(f"/api/received/{share['id']}/download", json={"format": "csv"}).json()["url"]
    other, _ = signup(app, "r4@example.com", org=None)
    assert other.get(url).status_code == 403  # bound to the user
    assert rec.get(url[:-3] + "AAA").status_code == 403  # signature
    assert rec.get(url).status_code == 200


def test_exports_neutralize_formulas(app, org_admin):
    admin, org = org_admin
    rows = ["id,name,comment,amount"] + [f"{i},عميل {i},=HYPERLINK(\"http://evil\"),-{i}.5" for i in range(1, 40)]
    ds = ready_dataset(app, admin, org, [("t.csv", "\n".join(rows).encode())])
    twin = masked_twin(app, admin, org, ds["id"])
    if twin["verdict"] != "PASS":
        twin = masked_twin(app, admin, org, ds["id"], apply_fix="auto")
    share = admin.post(f"/api/orgs/{org}/twins/{twin['id']}/shares", json={"external_labels": ["x"]}).json()
    rec, _ = signup(app, "r5@example.com", org=None)
    rec.post("/api/share-links/accept", json={"token": token_of(share["new_links"][0]["link_path"])})
    xlsx = rec.get(rec.post(f"/api/received/{share['id']}/download", json={"format": "xlsx"}).json()["url"]).content
    ws = load_workbook(io.BytesIO(xlsx)).active
    comments = [ws.cell(row=r, column=3).value for r in range(2, 5)]
    assert all(c.startswith("'=") for c in comments)
    assert ws.cell(row=2, column=4).value == "-1.5"  # numbers untouched
    csvz = rec.get(rec.post(f"/api/received/{share['id']}/download", json={"format": "csv"}).json()["url"]).content
    body = zipfile.ZipFile(io.BytesIO(csvz)).read("t.csv").decode("utf-8-sig")
    assert "'=HYPERLINK" in body and ",=HYPERLINK" not in body


def test_originals_not_persisted_after_the_session(app, org_admin, demo_files):
    admin, org = org_admin
    ds = ready_dataset(app, admin, org, demo_files)
    with app.state.sessionmaker() as db:
        kinds = {b.kind for b in db.execute(select(Blob).where(Blob.dataset_id == ds["id"])).scalars()}
    assert kinds == {"tables"}  # the raw upload is deleted as soon as it is parsed
    masked_twin(app, admin, org, ds["id"], apply_fix="auto")
    assert admin.post(f"/api/orgs/{org}/datasets/{ds['id']}/end-session").status_code == 200
    with app.state.sessionmaker() as db:
        kinds = {b.kind for b in db.execute(select(Blob).where(Blob.dataset_id == ds["id"])).scalars()}
    assert kinds == {"twin"}
    assert admin.get(f"/api/orgs/{org}/datasets/{ds['id']}/notes/0").status_code == 410
    r = admin.post(f"/api/orgs/{org}/datasets/{ds['id']}/generate", json={"mode": "masked"})
    assert r.status_code == 410

    # a second dataset whose session simply times out: the sweep removes the originals
    ds2 = ready_dataset(app, admin, org, demo_files)
    with app.state.sessionmaker() as db:
        db.execute(update(Blob).where(Blob.dataset_id == ds2["id"]).values(expires_at=utcnow() - timedelta(seconds=1)))
        db.execute(update(Dataset).where(Dataset.id == ds2["id"]).values(session_expires_at=utcnow() - timedelta(seconds=1)))
        db.commit()
        assert sweep(db, app.state.settings)["originals_deleted"] == 1
        assert db.execute(select(Blob).where(Blob.dataset_id == ds2["id"])).first() is None
    assert admin.get(f"/api/orgs/{org}/datasets/{ds2['id']}").json()["session_open"] is False


def test_stored_bytes_are_encrypted(app, org_admin, demo_files):
    admin, org = org_admin
    ready_dataset(app, admin, org, demo_files)
    needle = demo_files[1][1].splitlines()[1].split(b",")[2]  # a national ID from customers.csv
    with app.state.sessionmaker() as db:
        for b in db.execute(select(Blob)).scalars():
            assert needle not in b.data


def test_tenant_isolation_for_data(app, org_admin, demo_files):
    admin, org = org_admin
    ds = ready_dataset(app, admin, org, demo_files)
    twin = masked_twin(app, admin, org, ds["id"], apply_fix="auto")
    other, me = signup(app, "other@example.com", org="منشأة أخرى")
    org_b = me["memberships"][0]["org_id"]
    for url in (f"/api/orgs/{org}/datasets", f"/api/orgs/{org}/datasets/{ds['id']}", f"/api/orgs/{org}/twins/{twin['id']}",
                f"/api/orgs/{org}/shares", f"/api/orgs/{org}/twins/{twin['id']}/preview"):
        assert other.get(url).status_code == 404, url
    # own org URL with the other org's IDs
    assert other.get(f"/api/orgs/{org_b}/datasets/{ds['id']}").status_code == 404
    assert other.get(f"/api/orgs/{org_b}/twins/{twin['id']}").status_code == 404
    assert other.post(f"/api/orgs/{org_b}/twins/{twin['id']}/shares", json={"external_labels": ["x"]}).status_code == 404


def test_roles_for_data(app, org_admin, demo_files):
    admin, org = org_admin
    plain, _ = invite_and_join(app, admin, org, "plain@alwaha.example.com")
    dm, _ = invite_and_join(app, admin, org, "dm@alwaha.example.com", data_manager=True)
    assert plain.get(f"/api/orgs/{org}/datasets").json()["code"] == "data_manager_only"
    ds = ready_dataset(app, dm, org, demo_files)  # a data manager can upload
    twin = masked_twin(app, dm, org, ds["id"], apply_fix="auto")
    assert dm.get(f"/api/orgs/{org}/twins/{twin['id']}/preview").json()["code"] == "admin_only"  # originals: admins only
    assert admin.get(f"/api/orgs/{org}/twins/{twin['id']}/preview").status_code == 200


def test_messy_file_through_the_api_and_clear_errors(app, org_admin):
    admin, org = org_admin
    text = "الاسم;رقم الهوية;المدينة\n" + "\n".join(f"عميل {i};{1100000000 + i};الرياض" for i in range(30))
    ds = ready_dataset(app, admin, org, [("ملف.csv", text.encode("cp1256"))])
    assert ds["summary"]["ingest"][0]["encoding"] == "windows-1256"
    bad = upload(admin, org, [("doc.pdf", b"%PDF-1.4 x")])
    work(app)
    failed = admin.get(f"/api/orgs/{org}/datasets/{bad}").json()
    assert failed["status"] == "failed" and failed["error_code"] == "ingest:unsupported_type"


def test_hosted_limits(app, org_admin, demo_files):
    admin, org = org_admin
    app.state.settings = replace(app.state.settings, max_rows_synthetic=100)
    ds = ready_dataset(app, admin, org, demo_files)
    r = admin.post(f"/api/orgs/{org}/datasets/{ds['id']}/generate", json={"mode": "synthetic"})
    assert r.status_code == 422 and r.json()["code"] == "synthetic_too_large"
    assert admin.post(f"/api/orgs/{org}/datasets/{ds['id']}/generate", json={"mode": "masked"}).status_code == 202
    app.state.settings = replace(app.state.settings, org_quota_mb=0)
    r = admin.post(f"/api/orgs/{org}/datasets", files=[("files", ("x.csv", b"a,b\n1,2\n", "text/csv"))])
    assert r.status_code == 413 and r.json()["code"] == "quota_exceeded"


def test_recipient_cannot_reach_org_routes(app, org_admin, demo_files):
    admin, org = org_admin
    share = _shared(app, admin, org, demo_files)
    rec, _ = signup(app, "outsider@example.com", org=None)
    rec.post("/api/share-links/accept", json={"token": token_of(share["new_links"][0]["link_path"])})
    assert rec.get(f"/api/orgs/{org}/datasets").status_code == 404
    assert rec.get(f"/api/orgs/{org}/twins/{share['twin_id']}").status_code == 404
    anon = new_client(app)
    assert anon.get("/api/received").status_code == 401


def test_unexpected_processing_error_marks_the_dataset_failed(app, org_admin, monkeypatch):
    admin, org = org_admin
    import nazeer_api.processing as proc

    def boom(*a, **k):
        raise FileNotFoundError("names list missing")
    monkeypatch.setattr(proc, "process_upload", boom)
    ds_id = upload(admin, org, [("t.csv", b"a,b\n1,2\n3,4\n")])
    work(app)
    ds = admin.get(f"/api/orgs/{org}/datasets/{ds_id}").json()
    assert ds["status"] == "failed" and ds["error_code"] == "processing_failed"
