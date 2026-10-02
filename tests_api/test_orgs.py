import pytest
from sqlalchemy import select

from nazeer_api.models import AuditEvent
from tests_api.conftest import PASSWORD, invite, invite_and_join, new_client, signup, token_of


@pytest.fixture
def two_orgs(app):
    a, me_a = signup(app, "admin@alwaha.example.com", org="الواحة للتأمين")
    b, me_b = signup(app, "admin@other.example.com", org="منشأة أخرى")
    return (a, me_a["memberships"][0]["org_id"]), (b, me_b["memberships"][0]["org_id"])


def org_routes(org_id: str, some_id: str = "0" * 32) -> list[tuple[str, str, dict | None]]:
    return [
        ("GET", f"/api/orgs/{org_id}", None),
        ("PATCH", f"/api/orgs/{org_id}", {"name": "hijacked"}),
        ("GET", f"/api/orgs/{org_id}/members", None),
        ("PATCH", f"/api/orgs/{org_id}/members/{some_id}", {"role": "admin"}),
        ("DELETE", f"/api/orgs/{org_id}/members/{some_id}", None),
        ("GET", f"/api/orgs/{org_id}/invitations", None),
        ("POST", f"/api/orgs/{org_id}/invitations", {"email": "x@y.example.com"}),
        ("DELETE", f"/api/orgs/{org_id}/invitations/{some_id}", None),
        ("GET", f"/api/orgs/{org_id}/jobs/{some_id}", None),
        ("POST", f"/api/orgs/{org_id}/jobs/ping", None),
        ("GET", f"/api/orgs/{org_id}/audit", None),
    ]


def test_tenant_isolation_every_org_route_is_404_for_outsiders(app, two_orgs):
    (a, org_a), (b, org_b) = two_orgs
    with app.state.sessionmaker() as db:
        from nazeer_api.models import Membership
        b_admin_membership = db.execute(select(Membership.id).where(Membership.org_id == org_b)).scalar_one()
    job_b = b.post(f"/api/orgs/{org_b}/jobs/ping").json()["id"]
    for some_id in ("0" * 32, b_admin_membership, job_b):
        for method, url, body in org_routes(org_b, some_id):
            r = a.request(method, url, json=body)
            assert r.status_code == 404 and r.json() == {"code": "not_found"}, (method, url, r.status_code)
    assert b.get(f"/api/orgs/{org_b}").json()["name"] == "منشأة أخرى"  # untouched


def test_cross_org_ids_inside_own_org_route_are_404(app, two_orgs):
    """An admin of A cannot reach B's rows by putting B's IDs under A's URL."""
    (a, org_a), (b, org_b) = two_orgs
    job_b = b.post(f"/api/orgs/{org_b}/jobs/ping").json()["id"]
    inv_b = b.post(f"/api/orgs/{org_b}/invitations", json={"email": "z@z.example.com"}).json()["id"]
    member_b = b.get(f"/api/orgs/{org_b}/members").json()[0]["id"]
    assert a.get(f"/api/orgs/{org_a}/jobs/{job_b}").status_code == 404
    assert a.delete(f"/api/orgs/{org_a}/invitations/{inv_b}").status_code == 404
    assert a.patch(f"/api/orgs/{org_a}/members/{member_b}", json={"role": "member"}).status_code == 404
    assert a.delete(f"/api/orgs/{org_a}/members/{member_b}").status_code == 404


def test_anonymous_gets_401(app, two_orgs):
    (_, org_a), _ = two_orgs
    anon = new_client(app)
    assert anon.get(f"/api/orgs/{org_a}").status_code == 401


def test_member_role_limits(app, two_orgs):
    (a, org_a), _ = two_orgs
    emp, me = invite_and_join(app, a, org_a, "employee@alwaha.example.com")
    assert me["email_verified"]  # accepting the emailed invitation verifies the address
    assert emp.get(f"/api/orgs/{org_a}").json()["my_role"] == "member"
    for method, url, body in org_routes(org_a):
        if url.endswith(org_a) and method == "GET":
            continue
        if "/jobs/" in url and method == "GET":
            continue
        r = emp.request(method, url, json=body)
        expected = "data_manager_only" if url.endswith("/members") and method == "GET" else "admin_only"
        assert r.status_code == 403 and r.json()["code"] == expected, (method, url)


def test_invitation_flow_existing_user_must_be_signed_in_as_that_email(app, two_orgs):
    (a, org_a), _ = two_orgs
    person, _ = signup(app, "freelancer@example.com", org=None)
    token = invite(a, org_a, "freelancer@example.com")
    anon = new_client(app)
    assert anon.post("/api/invitations/preview", json={"token": token}).json()["has_account"] is True
    assert anon.post("/api/invitations/accept", json={"token": token}).json()["code"] == "login_required"
    stranger, _ = signup(app, "stranger@example.com", org=None)
    assert stranger.post("/api/invitations/accept", json={"token": token}).json()["code"] == \
        "invitation_for_other_email"
    me = person.post("/api/invitations/accept", json={"token": token}).json()
    assert [m["org_id"] for m in me["memberships"]] == [org_a]
    assert person.post("/api/invitations/accept", json={"token": token}).status_code == 400  # single use


def test_accepting_the_invite_link_verifies_the_account(app, two_orgs):
    (a, org_a), _ = two_orgs
    person, me = signup(app, "late@example.com", org=None)
    assert not me["email_verified"]
    me = person.post("/api/invitations/accept", json={"token": invite(a, org_a, "late@example.com")}).json()
    assert me["email_verified"]


def test_reinvite_revokes_old_link_and_revoked_link_fails(app, two_orgs):
    (a, org_a), _ = two_orgs
    first = invite(a, org_a, "twice@example.com")
    inv2 = a.post(f"/api/orgs/{org_a}/invitations", json={"email": "twice@example.com"}).json()
    anon = new_client(app)
    assert anon.post("/api/invitations/preview", json={"token": first}).status_code == 400
    second = token_of(inv2["link_path"])
    assert a.delete(f"/api/orgs/{org_a}/invitations/{inv2['id']}").status_code == 200
    assert anon.post("/api/invitations/accept", json={"token": second, "full_name": "x y",
                                                      "password": PASSWORD}).status_code == 400


def test_roles_data_manager_and_last_admin_guard(app, two_orgs):
    (a, org_a), _ = two_orgs
    invite_and_join(app, a, org_a, "dm@alwaha.example.com", data_manager=True)
    members = a.get(f"/api/orgs/{org_a}/members").json()
    me_row = next(m for m in members if m["email"] == "admin@alwaha.example.com")
    dm_row = next(m for m in members if m["email"] == "dm@alwaha.example.com")
    assert dm_row["data_manager"] and dm_row["role"] == "member"
    r = a.patch(f"/api/orgs/{org_a}/members/{me_row['id']}", json={"role": "member"})
    assert r.status_code == 409 and r.json()["code"] == "last_admin"
    assert a.delete(f"/api/orgs/{org_a}/members/{me_row['id']}").json()["code"] == "last_admin"
    assert a.patch(f"/api/orgs/{org_a}/members/{dm_row['id']}", json={"role": "admin"}).json()["role"] == "admin"
    assert a.patch(f"/api/orgs/{org_a}/members/{me_row['id']}", json={"role": "member"}).status_code == 200


def test_removed_member_loses_access(app, two_orgs):
    (a, org_a), _ = two_orgs
    emp, _ = invite_and_join(app, a, org_a, "leaver@alwaha.example.com")
    row = next(m for m in a.get(f"/api/orgs/{org_a}/members").json() if m["email"] == "leaver@alwaha.example.com")
    assert a.delete(f"/api/orgs/{org_a}/members/{row['id']}").status_code == 200
    assert emp.get(f"/api/orgs/{org_a}").status_code == 404


def test_audit_log_records_actions_without_values(app, two_orgs):
    (a, org_a), _ = two_orgs
    invite_and_join(app, a, org_a, "audited@alwaha.example.com")
    actions = [e["action"] for e in a.get(f"/api/orgs/{org_a}/audit").json()]
    assert {"org.created", "member.invited", "member.joined"} <= set(actions)
    with app.state.sessionmaker() as db:
        blob = " ".join(str(e.meta) for e in db.execute(select(AuditEvent)).scalars())
    assert "@" not in blob


def test_audit_meta_redacts_value_like_strings(app):
    from nazeer_api import audit
    from nazeer_api.models import AuditEvent as AE

    with app.state.sessionmaker() as db:
        ev = audit.record(db, "x.test", note="1110704341", mail="a@b.example.com", count=3, code="ok_code")
        assert isinstance(ev, AE)
        assert ev.meta == {"note": "<redacted>", "mail": "<redacted>", "count": 3, "code": "ok_code"}
