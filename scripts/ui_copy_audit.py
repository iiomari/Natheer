"""Copy audit: screenshot + visible word count of every screen of the main flow
(upload -> cleaning -> detection -> twin -> share -> received).

    python scripts\\ui_copy_audit.py --url http://localhost:3000 --label before   (or --label after)

Writes docs/ui/copy/<label>/<screen>.png and words.json. Words are counted in the page's <main> (or in
the open dialog), sidebar and header excluded: tokens that contain a letter or a digit.
Playwright is a dev tool only.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

PASSWORD = "demo-password-2026"
TIMEOUT = 180_000
SAMPLES = Path("web/public/samples")
COUNT_JS = """(el) => (el.innerText || '').split(/\\s+/).filter(t => /[\\p{L}\\p{N}]/u.test(t)).length"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:3000")
    ap.add_argument("--label", required=True)
    a = ap.parse_args()
    out = Path("docs/ui/copy") / a.label
    out.mkdir(parents=True, exist_ok=True)
    tag = f"{a.label}{int(time.time()) % 100000}"
    words: dict[str, int] = {}

    def capture(page: Page, name: str, dialog: bool = False) -> None:
        page.wait_for_timeout(900)
        target = page.get_by_role("dialog") if dialog else page.locator("main")
        words[name] = int(target.evaluate(COUNT_JS))
        if dialog:
            target.screenshot(path=str(out / f"{name}.png"))
        else:
            page.screenshot(path=str(out / f"{name}.png"), full_page=True)
        print(f"{name}: {words[name]} words")

    def upload(page: Page, org_base: str, sample: str, name: str, shot_dialog: bool = False) -> None:
        page.goto(f"{org_base}/datasets")
        page.get_by_role("button", name=re.compile("رفع")).first.click()
        dlg = page.get_by_role("dialog")
        dlg.locator("li").filter(has=page.locator(f"a[href='/samples/{sample}']")) \
            .get_by_role("button", name=re.compile("استخدم")).click()
        expect(dlg.get_by_text(sample)).to_be_visible(timeout=30_000)
        if shot_dialog:
            capture(page, "1-upload", dialog=True)
        dlg.locator("input[name=name]").fill(name)
        dlg.locator("button[type=submit]").click()
        page.wait_for_url("**/datasets/**", timeout=30_000)
        expect(page.locator("main table").first).to_be_visible(timeout=TIMEOUT)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ar-SA").new_page()
        page.goto(f"{a.url}/signup")
        page.get_by_label("الاسم الكامل").fill("مدير العرض")
        page.get_by_label("اسم المنشأة").fill("الواحة للتأمين")
        page.get_by_label("البريد الإلكتروني", exact=True).fill(f"copy{tag}@alwaha.example.com")
        page.get_by_label("كلمة المرور", exact=True).fill(PASSWORD)
        page.locator("input[name=terms]").check()
        page.get_by_role("button", name="إنشاء الحساب").click()
        page.wait_for_url("**/dashboard**", timeout=30_000)
        org_base = page.url.split("/dashboard")[0]

        upload(page, org_base, "hospital_patients_test.csv", "مرضى المستشفى")
        capture(page, "2-cleaning")
        upload(page, org_base, "clinic_appointments_clean.csv", "مواعيد العيادات", shot_dialog=True)
        capture(page, "3-detection")

        page.get_by_role("button", name=re.compile("ولّد|توليد")).first.click()
        page.wait_for_url("**/twins/**", timeout=TIMEOUT)
        expect(page.get_by_text(re.compile("ناجح")).first).to_be_visible(timeout=TIMEOUT)
        capture(page, "4-twin")

        page.get_by_role("button", name=re.compile("مشاركة|شارك")).first.click()
        dlg = page.get_by_role("dialog")
        dlg.get_by_placeholder(re.compile("شركة")).fill("شركة التحليل")
        dlg.get_by_role("button", name="إضافة").click()
        capture(page, "5-share", dialog=True)
        dlg.get_by_role("button", name=re.compile("^(مشاركة|شارك)$")).click()
        link = dlg.get_by_role("textbox", name="شركة التحليل", exact=True)
        expect(link).to_be_visible(timeout=30_000)
        share_link = link.input_value()

        ext = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ar-SA").new_page()
        ext.goto(share_link)
        ext.get_by_role("link", name=re.compile("إنشاء حساب")).click()
        ext.get_by_label("الاسم الكامل").fill("محلل خارجي")
        ext.get_by_label("البريد الإلكتروني", exact=True).fill(f"ext{tag}@example.com")
        ext.get_by_label("كلمة المرور", exact=True).fill(PASSWORD)
        ext.locator("input[name=terms]").check()
        ext.get_by_role("button", name="إنشاء الحساب").click()
        ext.wait_for_url("**/s?token=**", timeout=30_000)
        ext.get_by_role("button", name=re.compile("قبول")).click()
        ext.wait_for_url("**/app/received/**", timeout=30_000)
        expect(ext.locator("main h1")).to_be_visible(timeout=30_000)
        capture(ext, "6-received")
        browser.close()

    (out / "words.json").write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
    print("total", sum(words.values()))


if __name__ == "__main__":
    main()
