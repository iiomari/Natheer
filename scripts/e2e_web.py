"""End-to-end story in a real browser (Playwright), with screenshots into docs/ui/web/.

Needs a fresh API on :8000, the worker, and the built site on :3000:
    python scripts\\e2e_web.py --url http://localhost:3000 --data data\\demo --out docs\\ui\\web

Story: organization signs up -> invites an employee (link) -> uploads demo data -> reviews detection
-> generates a masked twin (FAIL on k) -> applies the suggested fix (PASS) -> shares with the employee
and one external recipient -> the employee opens the invite link, sees the share in "received" and
downloads CSV and Excel -> the external recipient accepts the share link and sees it too.
Fails if any request leaves the site's host. Playwright is a dev tool only, not a project dependency.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, expect, sync_playwright

PASSWORD = "demo-password-2026"
TIMEOUT = 180_000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:3000")
    ap.add_argument("--data", type=Path, default=Path("data/demo"))
    ap.add_argument("--out", type=Path, default=Path("docs/ui/web"))
    ap.add_argument("--tag", default="", help="suffix for test e-mails (e.g. a run id against a shared server)")
    args = ap.parse_args()
    tag = f"+{args.tag}" if args.tag else ""
    args.out.mkdir(parents=True, exist_ok=True)
    host = urlparse(args.url).hostname
    external: list[str] = []
    downloads: list[str] = []

    def watch(page: Page) -> None:
        page.on("request", lambda r: external.append(r.url)
                if urlparse(r.url).hostname not in (host, None) and not r.url.startswith(("data:", "blob:")) else None)

    def shot(page: Page, name: str, full: bool = True) -> None:
        page.wait_for_timeout(700)
        page.screenshot(path=str(args.out / name), full_page=full)
        print("saved", name)

    tmp = Path(tempfile.mkdtemp(prefix="nazeer-e2e-"))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        admin_ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ar-SA", accept_downloads=True)
        page = admin_ctx.new_page()
        watch(page)

        page.goto(f"{args.url}/signup")
        page.get_by_label("الاسم الكامل").fill("مدير العرض")
        page.get_by_label("اسم المنشأة").fill("الواحة للتأمين")
        page.get_by_label("البريد الإلكتروني", exact=True).fill(f"admin{tag}@alwaha.example.com")
        page.get_by_label("كلمة المرور", exact=True).fill(PASSWORD)
        page.locator("input[name=terms]").check()
        page.get_by_role("button", name="إنشاء الحساب").click()
        page.wait_for_url("**/dashboard**", timeout=30_000)
        org_base = page.url.split("/dashboard")[0]
        shot(page, "p2-01-dashboard.png")

        # invite an employee: the link is shown, not emailed
        page.goto(f"{org_base}/team")
        page.get_by_role("button", name="دعوة عضو").first.click()
        page.get_by_role("dialog").get_by_label("البريد الإلكتروني", exact=True).fill(f"employee{tag}@alwaha.example.com")
        page.get_by_role("button", name="إنشاء رابط الدعوة").click()
        link_box = page.get_by_role("dialog").get_by_label("رابط الدعوة")
        expect(link_box).to_be_visible()
        invite_link = link_box.input_value()
        shot(page, "p2-02-invite-link.png", full=False)
        page.get_by_role("button", name="تم").click()

        # upload the demo data
        page.goto(f"{org_base}/datasets")
        page.get_by_role("button", name="رفع بيانات").first.click()
        page.locator("input[type=file]").set_input_files([str(args.data / "customers.csv"), str(args.data / "claims.csv")])
        page.get_by_label("اسم مجموعة البيانات (اختياري)").fill("مطالبات العرض")
        shot(page, "p2-03-upload.png", full=False)
        page.get_by_role("button", name="رفع ومعالجة").click()
        page.wait_for_url("**/datasets/**", timeout=30_000)
        expect(page.get_by_role("heading", name="مراجعة الكشف")).to_be_visible(timeout=TIMEOUT)
        shot(page, "p2-04-review.png")
        # cleaning: opt in to phone unification, look at before/after, apply and re-detect
        cleaning = page.get_by_role("heading", name="تنظيف البيانات")
        cleaning.scroll_into_view_if_needed()
        page.get_by_role("checkbox", name=re.compile("توحيد صيغة الجوال")).click()
        phones_row = page.locator("li").filter(has_text="توحيد صيغة الجوال")
        phones_row.get_by_role("button", name="قبل / بعد").click()
        expect(phones_row.locator("table")).to_be_visible(timeout=TIMEOUT)
        shot(page, "p4-01-cleaning.png", full=False)
        page.get_by_role("button", name="طبّق وأعد الكشف").click()
        expect(phones_row.get_by_text(re.compile("طُبِّق على"))).to_be_visible(timeout=TIMEOUT)
        expect(page.get_by_role("heading", name="مراجعة الكشف")).to_be_visible(timeout=TIMEOUT)
        page.get_by_role("tab", name="أداة تقليدية").click()
        page.get_by_role("heading", name="البيانات الشخصية داخل النصوص").scroll_into_view_if_needed()
        shot(page, "p2-05-baseline-view.png", full=False)

        # generate: FAIL on k-anonymity, then the suggested fix
        page.get_by_role("button", name="ولّد النظير").click()
        page.wait_for_url("**/twins/**", timeout=TIMEOUT)
        expect(page.get_by_text("النتيجة:")).to_be_visible()
        shot(page, "p2-06-twin-fail.png")
        page.get_by_role("button", name="طبّق الإصلاح المقترح").click()
        page.wait_for_url("**/datasets/**", timeout=30_000)
        page.wait_for_url("**/twins/**", timeout=TIMEOUT)
        expect(page.get_by_text("النتيجة: ناجح")).to_be_visible()
        shot(page, "p2-07-twin-pass.png")
        page.get_by_role("button", name="عرض المعاينة (تتضمّن قيماً أصلية)").click()
        expect(page.get_by_text("الخلايا المتغيّرة مظلّلة").first).to_be_visible(timeout=60_000)
        page.get_by_role("heading", name="قبل وبعد").scroll_into_view_if_needed()
        shot(page, "p2-08-preview.png", full=False)
        page.evaluate("window.scrollTo(0, 0)")

        # share with the employee? not a member yet; share with an external recipient first
        page.get_by_role("button", name="مشاركة").first.click()
        dlg = page.get_by_role("dialog")
        dlg.get_by_placeholder("مثال: شركة التحليل أو analyst@example.com").fill("شركة التحليل")
        dlg.get_by_role("button", name="إضافة").click()
        dlg.get_by_role("button", name="مشاركة", exact=True).click()
        expect(dlg.get_by_text("أُنشئت المشاركة")).to_be_visible()
        share_link = dlg.get_by_role("textbox", name="شركة التحليل", exact=True).input_value()
        assert share_link.startswith("http"), share_link
        shot(page, "p2-09-share-links.png", full=False)
        dlg.get_by_role("button", name="تم").click()

        # the employee joins through the invite link
        emp_ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ar-SA", accept_downloads=True)
        emp = emp_ctx.new_page()
        watch(emp)
        emp.goto(invite_link)
        emp.get_by_label("الاسم الكامل").fill("موظف العرض")
        emp.get_by_label("كلمة المرور", exact=True).fill(PASSWORD)
        emp.get_by_role("button", name="إنشاء الحساب وقبول الدعوة").click()
        emp.wait_for_url("**/app/**", timeout=30_000)

        # now share with the employee too
        page.reload()
        page.get_by_role("button", name="مشاركة").first.click()
        dlg = page.get_by_role("dialog")
        dlg.get_by_text("موظف العرض").click()
        dlg.get_by_role("button", name="مشاركة", exact=True).click()
        expect(dlg.get_by_text("أُنشئت المشاركة")).to_be_visible()
        dlg.get_by_role("button", name="تم").click()

        emp.goto(f"{args.url}/app/received")
        expect(emp.get_by_text("مطالبات العرض")).to_be_visible()
        shot(emp, "p2-10-received.png")
        emp.get_by_text("مطالبات العرض").click()
        expect(emp.get_by_text("هذه بيانات نظيرة لا تحتوي أي شخص حقيقي.")).to_be_visible()
        expect(emp.get_by_role("heading", name="ما نُظِّف قبل التوليد")).to_be_visible()
        shot(emp, "p2-11-received-detail.png")
        zip_path = None
        for label in ("تحميل CSV", "تحميل Excel"):
            with emp.expect_download() as d:
                emp.get_by_role("button", name=label).click()
            downloads.append(d.value.suggested_filename)
            if d.value.suggested_filename.endswith(".zip"):
                zip_path = d.value.path()
            emp.wait_for_timeout(1600)

        # P5: the employee scores the customers and returns the file (key + nazeer_ref + score)
        with zipfile.ZipFile(zip_path) as z:
            rows = list(csv.reader(io.StringIO(z.read("customers.csv").decode("utf-8-sig"))))
        head = rows[0]
        ki, ri = head.index("customer_id"), head.index("nazeer_ref")
        results = tmp / "results.csv"
        with results.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["customer_id", "nazeer_ref", "score"])
            for i, r in enumerate(rows[1:]):
                w.writerow([r[ki], r[ri], i])
        emp.locator("input[type=file]").set_input_files(str(results))
        emp.get_by_role("button", name="إرسال النتائج").click()
        expect(emp.get_by_text(re.compile("صف مقبول")).first).to_be_visible(timeout=TIMEOUT)
        emp.get_by_role("heading", name="إعادة النتائج إلى المنشأة").scroll_into_view_if_needed()
        shot(emp, "p5-01-return-sent.png", full=False)

        # the admin re-links it with the original files, then downloads the result
        page.goto(f"{org_base}/returns")
        expect(page.get_by_text("results.csv")).to_be_visible(timeout=TIMEOUT)
        shot(page, "p5-02-returns.png", full=False)
        page.get_by_role("button", name="إعادة الربط").first.click()
        dlg = page.get_by_role("dialog")
        dlg.locator("input[type=file]").set_input_files([str(args.data / "customers.csv"), str(args.data / "claims.csv")])
        shot(page, "p5-03-relink-upload.png", full=False)
        dlg.get_by_role("button", name="ابدأ إعادة الربط").click()
        expect(dlg.get_by_text(re.compile("صف بسجلاته الحقيقية"))).to_be_visible(timeout=TIMEOUT)
        shot(page, "p5-04-relinked.png", full=False)
        with page.expect_download() as d:
            dlg.get_by_text("تنزيل CSV").click()
        with zipfile.ZipFile(d.value.path()) as z:
            linked = list(csv.reader(io.StringIO(z.read("results.csv").decode("utf-8-sig"))))
        with (args.data / "customers.csv").open(encoding="utf-8") as f:
            original = list(csv.reader(f))
        oi = original[0].index("customer_id")
        assert len(linked) == len(rows), (len(linked), len(rows))
        for r in linked[1:]:  # the score (row number) landed on the real key of that row
            assert r[0] == original[1 + int(r[linked[0].index("score")])][oi], "re-linked key does not match"
        downloads.append(d.value.suggested_filename)
        dlg.get_by_role("button", name="إغلاق").click()

        # the external recipient accepts the share link with a new individual account
        ext_ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ar-SA")
        ext = ext_ctx.new_page()
        watch(ext)
        ext.goto(share_link)
        shot(ext, "p2-12-share-link.png", full=False)
        ext.get_by_role("link", name="إنشاء حساب فرد").click()
        ext.get_by_label("الاسم الكامل").fill("محلل خارجي")
        ext.get_by_label("البريد الإلكتروني", exact=True).fill(f"analyst{tag}@example.com")
        ext.get_by_label("كلمة المرور", exact=True).fill(PASSWORD)
        ext.locator("input[name=terms]").check()
        ext.get_by_role("button", name="إنشاء الحساب").click()
        ext.wait_for_url("**/s?token=**", timeout=30_000)
        ext.get_by_role("button", name="قبول واستعراض البيانات").click()
        ext.wait_for_url("**/app/received/**", timeout=30_000)
        expect(ext.get_by_text("مطالبات العرض").first).to_be_visible()

        page.goto(f"{org_base}/shares")
        expect(page.get_by_text("مطالبات العرض").first).to_be_visible()
        shot(page, "p2-13-shares.png")
        browser.close()

    print("downloads:", downloads)
    assert any(n.endswith(".zip") for n in downloads) and any(n.endswith(".xlsx") for n in downloads), downloads
    if external:
        raise SystemExit(f"external requests made: {sorted(set(external))}")
    print("E2E OK; no external requests")


if __name__ == "__main__":
    main()
