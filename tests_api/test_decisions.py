"""Decisions on uncertain values through the API: pending blocks sharing; group / value decisions;
apply in place (same twin, only decided cells change); one-click suggestions; value-free audit."""
import json
import random

import pandas as pd
from sqlalchemy import select

from nazeer import saudi_ids as s
from nazeer_api.models import AuditEvent
from tests_api.test_p2 import masked_twin, org_admin, ready_dataset, work  # noqa: F401
from tests_api.test_p5_tokens import csv_bytes

FILLER = ["تمت المتابعة مع العميل في الفرع الرئيسي", "طلب العميل تحديث بيانات العنوان الوطني",
          "لا توجد ملاحظات إضافية على هذا السجل", "تم إرسال كشف الحساب الشهري بنجاح"]


def mixed_dataset():
    rng = random.Random(9)
    rows = []
    for i in range(60):
        if i < 24:
            v = s.gen_saudi_id(rng, "1") if i % 2 == 0 else "1" + "".join(str(rng.randrange(10)) for _ in range(9))
            note = f"المرجع رقم {v} في النظام"
        else:
            note = FILLER[i % 4] + f" ملاحظة {i}"
        rows.append({"customer": f"C{i:04d}", "full_name": f"{s.gen_first_name(rng)} {s.gen_family_name(rng)}",
                     "mobile": s.gen_mobile(rng), "notes": note})
    return pd.DataFrame(rows)


def test_pending_blocks_sharing_until_decided_then_applies_in_place(app, org_admin):
    admin, org = org_admin
    df = mixed_dataset()
    ds = ready_dataset(app, admin, org, [("accounts.csv", csv_bytes(df))])
    base = f"/api/orgs/{org}/datasets/{ds['id']}"
    d = admin.get(f"{base}/decisions").json()
    g = next(x for x in d["groups"] if "المرجع" in x["phrase"])
    assert g["auto"] is None and g["pending"] == g["count"] > 0 and len(g["examples"]) == 3
    assert d["totals"]["pending"] == g["count"]

    twin = masked_twin(app, admin, org, ds["id"])
    assert twin["verdict"] == "PASS" and twin["review"]["totals"]["pending"] == g["count"]
    r = admin.post(f"/api/orgs/{org}/twins/{twin['id']}/shares", json={"external_labels": ["x"]})
    assert r.status_code == 409 and r.json()["code"] == "decisions_pending"

    # per group, then one value overridden
    first = admin.get(f"{base}/decisions", params={"group": g["key"]}).json()
    items = next(x for x in first["groups"] if x["key"] == g["key"])["items"]
    assert len(items) == g["count"]
    assert admin.put(f"{base}/decisions", json={"groups": {g["key"]: "keep"}}).json()["totals"]["pending"] == 0
    t = admin.put(f"{base}/decisions", json={"values": {g["key"]: {items[0]["id"]: "replace"}}}).json()["totals"]
    assert t == {"auto": t["auto"], "admin": g["count"], "pending": 0, "replace": t["replace"], "keep": t["keep"]}
    assert admin.get(f"/api/orgs/{org}/twins/{twin['id']}").json()["decisions_stale"] is True

    before = admin.get(f"/api/orgs/{org}/twins/{twin['id']}/rows", params={"size": 100}).json()
    assert admin.post(f"/api/orgs/{org}/twins/{twin['id']}/apply-decisions").status_code == 202
    work(app)
    after_twin = admin.get(f"/api/orgs/{org}/twins/{twin['id']}").json()                  # same twin id
    assert after_twin["review"]["totals"]["pending"] == 0 and after_twin["decisions_stale"] is False
    after = admin.get(f"/api/orgs/{org}/twins/{twin['id']}/rows", params={"size": 100}).json()
    changed = [(r1["n"], c) for r1, r2 in zip(before["rows"], after["rows"]) for c in r1["cells"]
               if c != "رمز_التحقق" and r1["cells"][c][0] != r2["cells"][c][0]]
    assert changed == [(items[0]["row"], "notes")]                                       # only the decided cell
    assert admin.post(f"/api/orgs/{org}/twins/{twin['id']}/shares", json={"external_labels": ["x"]}).status_code == 201

    with app.state.sessionmaker() as db:
        metas = [e.meta for e in db.execute(select(AuditEvent).where(AuditEvent.action.like("dataset.decisions%"))).scalars()]
    blob = json.dumps(metas, ensure_ascii=False)
    assert metas and "المرجع رقم" in blob
    assert not any(v in blob for v in df["notes"].str.extract(r"(\d{10})")[0].dropna())


def test_accept_suggestions_in_one_click(app, org_admin):
    admin, org = org_admin
    ds = ready_dataset(app, admin, org, [("accounts.csv", csv_bytes(mixed_dataset()))])
    base = f"/api/orgs/{org}/datasets/{ds['id']}"
    g = next(x for x in admin.get(f"{base}/decisions").json()["groups"] if x["pending"])
    t = admin.post(f"{base}/decisions/accept").json()["totals"]
    assert t["pending"] == 0 and t["admin"] >= g["count"]
    d = admin.get(f"{base}/decisions").json()
    assert next(x for x in d["groups"] if x["key"] == g["key"])["admin"] == g["suggestion"]
    assert admin.put(f"{base}/decisions", json={"groups": {"nope|x|SAUDI_ID|y": "keep"}}).status_code == 422
