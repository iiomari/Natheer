"""End-to-end story in a real browser (Playwright), with screenshots into docs/ui/web/.

Needs a fresh API on :8000, the worker, and the built site on :3000:
    python scripts\\e2e_web.py --url http://localhost:3000 --data data\\demo --out docs\\ui\\web

Story: organization signs up -> invites an employee (link) -> uploads demo data -> cleaning -> reviews
detection -> generates a masked twin (PASS) -> shares with the employee and one external recipient ->
the employee downloads Excel, returns a 100-row subset with a score column (one token altered, one row
duplicated) -> the admin sees both caught, confirms, re-links with the original file and checks every
row -> the external recipient accepts the share link -> the three sample files (hospital, bank,
insurance) each go upload -> answer-key check -> twin PASS -> share -> download.
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


SAMPLES = [
    ("clinic_appointments_clean.csv", "clinic_appointments_answer_key.csv", "مواعيد العيادات"),
    ("bank_accounts_clean.csv", "bank_accounts_answer_key.csv", "حسابات البنك"),
    ("hospital_patients_test.csv", "hospital_patients_answer_key.csv", "مرضى المستشفى"),
    ("bank_customers_test.csv", "bank_customers_answer_key.csv", "عملاء البنك"),
    ("insurance_claims_test.xlsx", "insurance_claims_answer_key.csv", "مطالبات التأمين"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:3000")
    ap.add_argument("--data", type=Path, default=Path("data/demo"))
    ap.add_argument("--out", type=Path, default=Path("docs/ui/web"))
    ap.add_argument("--samples", type=Path, default=Path("web/public/samples"))
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
        expect(page.get_by_role("heading", name="الأعمدة")).to_be_visible(timeout=TIMEOUT)
        shot(page, "p2-04-review.png")
        # cleaning: opt in to phone unification, look at before/after, apply and re-detect
        # cleaning is optional: a clean file needs nothing; the toggles sit behind «خيارات التنظيف»
        expect(page.get_by_text("البيانات نظيفة")).to_be_visible(timeout=TIMEOUT)
        page.get_by_role("button", name="خيارات التنظيف").click()
        cleaning = page.get_by_role("heading", name="تنظيف البيانات")
        cleaning.scroll_into_view_if_needed()
        page.get_by_role("checkbox", name=re.compile("توحيد صيغة الجوال")).click()
        phones_row = page.locator("li").filter(has_text="توحيد صيغة الجوال")
        phones_row.get_by_role("button", name="قبل / بعد").click()
        expect(phones_row.locator("table")).to_be_visible(timeout=TIMEOUT)
        shot(page, "p4-01-cleaning.png", full=False)
        page.get_by_role("button", name="طبّق وأعد الكشف").click()
        expect(page.get_by_text("نُظِّف الملف")).to_be_visible(timeout=TIMEOUT)
        expect(page.get_by_role("heading", name="الأعمدة")).to_be_visible(timeout=TIMEOUT)
        page.get_by_role("tab", name="أداة تقليدية").click()
        page.get_by_role("heading", name="داخل النصوص").scroll_into_view_if_needed()
        shot(page, "p2-05-baseline-view.png", full=False)

        # generate: the masked twin passes every blocking check (no k-anonymity step any more)
        page.get_by_role("button", name="ولّد النظير").click()
        page.wait_for_url("**/twins/**", timeout=TIMEOUT)
        expect(page.get_by_text("ناجح · يمكن مشاركته")).to_be_visible(timeout=TIMEOUT)
        expect(page.get_by_text("فحص البقايا").first).to_be_visible()
        expect(page.get_by_text("رمز التحقق", exact=True)).to_be_visible()
        assert page.get_by_text("خطر التعرّف بالتركيب").count() == 0
        shot(page, "p2-07-twin-pass.png")
        # the one-page PDF report (Arabic), kept in docs/ui/web for review
        with page.expect_download() as d:
            page.get_by_role("link", name="التقرير", exact=True).click()
        d.value.save_as(str(args.out / "p7-report.pdf"))
        # the twin itself: paginated table with the token column and replaced cells marked
        page.get_by_role("link", name="عرض النظير").click()
        page.wait_for_url("**/view", timeout=30_000)
        expect(page.get_by_role("button", name="ترتيب حسب رمز_التحقق")).to_be_visible(timeout=TIMEOUT)
        expect(page.get_by_text("قيمة استُبدلت ببديل")).to_be_visible()
        shot(page, "p7-twin-view.png", full=False)
        page.get_by_role("tab", name=re.compile("claims")).click()
        page.get_by_label("بحث في الجدول").fill("هوية")
        expect(page.get_by_text(re.compile("صف · صفحة"))).to_be_visible(timeout=TIMEOUT)
        page.wait_for_timeout(800)
        shot(page, "p7-twin-view-search.png", full=False)
        page.go_back()
        page.wait_for_url("**/twins/**", timeout=30_000)
        page.get_by_text("تفاصيل للمختصين").click()
        page.get_by_role("button", name="عرض المعاينة (تتضمّن قيماً أصلية)").click()
        expect(page.get_by_text("النظير", exact=True).first).to_be_visible(timeout=60_000)
        page.get_by_text("تفاصيل للمختصين").scroll_into_view_if_needed()
        shot(page, "p2-08-preview.png", full=False)
        page.evaluate("window.scrollTo(0, 0)")

        # share with the employee? not a member yet; share with an external recipient first
        page.get_by_role("button", name="مشاركة").first.click()
        dlg = page.get_by_role("dialog")
        dlg.get_by_placeholder("اسم أو بريد، مثل شركة التحليل").fill("شركة التحليل")
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
        expect(emp.get_by_text("بيانات نظيرة: لا شخص حقيقي فيها.")).to_be_visible()
        expect(emp.get_by_role("heading", name="ما نُظِّف قبل التوليد")).to_be_visible()
        shot(emp, "p2-11-received-detail.png")
        emp.get_by_role("link", name=re.compile("عرض البيانات")).click()
        emp.wait_for_url("**/view", timeout=30_000)
        expect(emp.get_by_role("button", name="ترتيب حسب رمز_التحقق")).to_be_visible(timeout=TIMEOUT)
        shot(emp, "p7-recipient-view.png", full=False)
        emp.go_back()
        emp.wait_for_url("**/received/**", timeout=30_000)
        xlsx_path = None
        for label in ("تحميل Excel", "تحميل CSV"):
            with emp.expect_download() as d:
                emp.get_by_role("button", name=label).click()
            downloads.append(d.value.suggested_filename)
            if d.value.suggested_filename.endswith(".xlsx"):
                xlsx_path = d.value.path()
            emp.wait_for_timeout(1600)

        # P5 (token): the employee returns a SUBSET of 100 customers with a score column, in Excel;
        # one token was altered and one row duplicated: the report must catch both
        from openpyxl import Workbook, load_workbook

        ws = load_workbook(io.BytesIO(Path(xlsx_path).read_bytes()))["customers"]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        head = rows[0]
        assert head[0] == "رمز_التحقق", head[:3]
        picked = [r + [str(i)] for i, r in enumerate(rows[1:101])]
        tok = picked[2][0]
        picked[2][0] = tok[:-2] + ("A" if tok[-2] != "A" else "B") + tok[-1]   # one character altered
        picked.append(list(picked[0]))                                       # one duplicated row
        wb = Workbook()
        out_ws = wb.active
        out_ws.append(head + ["score"])
        for r in picked:
            out_ws.append(r)
        results = tmp / "results.xlsx"
        wb.save(results)
        emp.locator("input[type=file]").set_input_files(str(results))
        emp.get_by_role("button", name="إرسال النتائج").click()
        expect(emp.get_by_text(re.compile("صف مُتحقَّق")).first).to_be_visible(timeout=TIMEOUT)
        emp.get_by_role("heading", name="أعد النتائج").scroll_into_view_if_needed()
        shot(emp, "p5-01-return-sent.png", full=False)

        # the admin sees the verification report, confirms the partial integrity, re-links with the
        # organization's own original file (a superset of the 100 rows) and downloads the result
        page.goto(f"{org_base}/returns")
        expect(page.get_by_text("results.xlsx")).to_be_visible(timeout=TIMEOUT)
        card = page.locator("div.rounded-xl").filter(has_text="results.xlsx").first
        for label, n in (("مُتحقَّق", "99"), ("غير صالح", "1"), ("مكرر", "1")):
            tile = card.locator("div.rounded-xl").filter(has=page.get_by_text(label, exact=True)).first
            expect(tile).to_contain_text(n)
        shot(page, "p5-02-returns.png", full=False)
        page.get_by_role("button", name="إعادة الربط").first.click()
        dlg = page.get_by_role("dialog")
        dlg.locator("input[type=file]").set_input_files([str(args.data / "customers.csv")])
        dlg.locator("input[type=checkbox]").check()
        shot(page, "p5-03-relink-upload.png", full=False)
        dlg.get_by_role("button", name="ابدأ إعادة الربط").click()
        expect(dlg.get_by_text(re.compile("صف بسجلاته الحقيقية"))).to_be_visible(timeout=TIMEOUT)
        shot(page, "p5-04-relinked.png", full=False)
        with page.expect_download() as d:
            dlg.get_by_text("تنزيل CSV").click()
        with zipfile.ZipFile(d.value.path()) as z:
            linked = list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode("utf-8-sig"))))
        with (args.data / "customers.csv").open(encoding="utf-8") as f:
            original = list(csv.reader(f))
        lh, oi = linked[0], original[0].index("customer_id")
        assert len(linked) - 1 == 99, len(linked)
        for r in linked[1:]:  # the score (row number) landed on the organization's real row
            assert r[lh.index("customer_id")] == original[1 + int(r[lh.index("score")])][oi], "re-linked key mismatch"
            assert r[lh.index("حالة_الربط")] == "مرتبط"
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

        # the three sample files (three sectors): upload -> cleaning -> detection (+ answer key) ->
        # twin PASS -> share -> the employee downloads it
        member_label = "موظف العرض"
        for sample, key_file, title in SAMPLES:
            page.goto(f"{org_base}/datasets")
            page.get_by_role("button", name="رفع بيانات").first.click()
            dlg = page.get_by_role("dialog")
            dlg.locator("li").filter(has=page.locator(f"a[href='/samples/{sample}']"))                 .get_by_role("button", name="استخدم هذا الملف").click()       # one-click example
            expect(dlg.get_by_role("button", name="تم اختياره")).to_be_visible(timeout=30_000)
            if sample == SAMPLES[0][0]:
                shot(page, "p8-samples-dialog.png", full=False)
            page.get_by_label("اسم مجموعة البيانات (اختياري)").fill(title)
            page.get_by_role("button", name="رفع ومعالجة").click()
            page.wait_for_url("**/datasets/**", timeout=30_000)
            expect(page.get_by_role("heading", name="الأعمدة")).to_be_visible(timeout=TIMEOUT)
            if "_clean" in sample:
                expect(page.get_by_text("البيانات نظيفة")).to_be_visible()
                if sample == SAMPLES[0][0]:
                    shot(page, "p8-clean-file.png", full=False)
            else:
                expect(page.get_by_text(re.compile("يمكن تنظيف"))).to_be_visible()
                if sample == "hospital_patients_test.csv":
                    shot(page, "p8-cleaning-offer.png", full=False)
                page.get_by_role("button", name="نظّف", exact=True).click()
                expect(page.get_by_text("نُظِّف الملف")).to_be_visible(timeout=TIMEOUT)
            expect(page.get_by_text("ما اكتُشف:")).to_be_visible()
            page.get_by_role("button", name="تحقق بمفتاح إجابة").click()
            page.locator("input[type=file][accept='.csv,text/csv']").set_input_files(str(args.samples / key_file))
            page.get_by_role("button", name="قارن").click()
            expect(page.get_by_text("وجده نَظير", exact=True)).to_be_visible(timeout=TIMEOUT)
            page.get_by_text("مفتاح الإجابة", exact=True).scroll_into_view_if_needed()
            shot(page, f"p6-{sample.split('_')[0]}-answer-key.png", full=False)
            page.get_by_role("button", name="ولّد النظير").click()
            page.wait_for_url("**/twins/**", timeout=TIMEOUT)
            expect(page.get_by_text(re.compile("ناجح|راسب")).first).to_be_visible(timeout=TIMEOUT)
            shot(page, f"p6-{sample.split('_')[0]}-twin.png", full=False)
            expect(page.get_by_text("ناجح · يمكن مشاركته")).to_be_visible(timeout=TIMEOUT)
            page.get_by_role("button", name="مشاركة").first.click()
            dlg = page.get_by_role("dialog")
            dlg.get_by_text(member_label).click()
            dlg.get_by_role("button", name="مشاركة", exact=True).click()
            expect(dlg.get_by_text("أُنشئت المشاركة")).to_be_visible()
            dlg.get_by_role("button", name="تم").click()
            emp.goto(f"{args.url}/app/received")
            emp.get_by_text(title).first.click()
            expect(emp.get_by_text("بيانات نظيرة: لا شخص حقيقي فيها.")).to_be_visible()
            with emp.expect_download() as d:
                emp.get_by_role("button", name="تحميل Excel").click()
            downloads.append(d.value.suggested_filename)
            print("sample OK:", sample)
        browser.close()

    print("downloads:", downloads)
    assert any(n.endswith(".zip") for n in downloads) and any(n.endswith(".xlsx") for n in downloads), downloads
    if external:
        raise SystemExit(f"external requests made: {sorted(set(external))}")
    print("E2E OK; no external requests")


if __name__ == "__main__":
    main()
