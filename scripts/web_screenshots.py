"""Screenshots of the Nazeer website for docs/ui/web/ (Playwright, headless Chromium).

Needs the API on :8000 (fresh database) and the built site on :3000:
    python scripts\\web_screenshots.py --url http://localhost:3000 --out docs\\ui\\web

Also a live smoke test: it signs up an organization, invites a member, and visits every page.
It fails if any request leaves localhost (no CDNs, no external fonts).
Playwright is a documentation tool only, not a project dependency.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, expect, sync_playwright

PASSWORD = "demo-password-2026"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:3000")
    ap.add_argument("--out", type=Path, default=Path("docs/ui/web"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    external: list[str] = []

    def settle(page: Page) -> None:
        page.locator("[data-sonner-toast]").first.wait_for(state="detached", timeout=15_000)

    def shot(page: Page, name: str, full: bool = True) -> None:
        page.wait_for_timeout(600)
        page.screenshot(path=str(args.out / name), full_page=full)
        print("saved", name)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ar-SA")
        page = ctx.new_page()
        host = urlparse(args.url).hostname
        page.on("request", lambda r: external.append(r.url) if urlparse(r.url).hostname not in (host, None) and not r.url.startswith("data:") else None)

        # public site
        page.goto(args.url)
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        shot(page, "01-landing.png")
        page.goto(f"{args.url}/signup")
        shot(page, "02-signup.png", full=False)

        # sign up an organization
        page.get_by_label("الاسم الكامل").fill("مدير العرض")
        page.get_by_label("اسم المنشأة").fill("الواحة للتأمين")
        page.get_by_label("البريد الإلكتروني", exact=True).fill("admin@alwaha.example.com")
        page.get_by_label("كلمة المرور", exact=True).fill(PASSWORD)
        page.locator("input[name=terms]").check()
        page.get_by_role("button", name="إنشاء الحساب").click()
        page.wait_for_url("**/dashboard**", timeout=30_000)
        expect(page.get_by_role("heading", name="لوحة المعلومات")).to_be_visible()
        shot(page, "03-dashboard.png")

        # team: invite a member
        page.get_by_role("link", name="الفريق").first.click()
        page.wait_for_url("**/team")
        page.get_by_role("button", name="دعوة عضو").first.click()
        page.get_by_role("dialog").get_by_label("البريد الإلكتروني", exact=True).fill("employee@alwaha.example.com")
        shot(page, "04-invite-dialog.png", full=False)
        page.get_by_role("button", name="إرسال الدعوة").click()
        expect(page.get_by_text("employee@alwaha.example.com")).to_be_visible()
        settle(page)
        shot(page, "05-team.png")

        page.get_by_role("link", name="سجل التدقيق").first.click()
        page.wait_for_url("**/audit")
        expect(page.get_by_text("إرسال دعوة")).to_be_visible()
        shot(page, "06-audit.png")
        page.get_by_role("link", name="الإعدادات").first.click()
        page.wait_for_url("**/settings")
        shot(page, "07-settings.png")
        page.get_by_role("link", name="مجموعات البيانات").first.click()
        page.wait_for_url("**/datasets")
        shot(page, "08-datasets-empty.png")

        # dark mode + mobile
        page.get_by_role("button", name="الوضع الداكن").click()
        page.get_by_role("link", name="لوحة المعلومات").first.click()
        page.wait_for_url("**/dashboard")
        shot(page, "09-dashboard-dark.png")
        page.get_by_role("button", name="الوضع الفاتح").click()
        page.set_viewport_size({"width": 390, "height": 844})
        shot(page, "10-dashboard-mobile.png", full=False)
        page.get_by_role("button", name="فتح القائمة").click()
        shot(page, "11-menu-mobile.png", full=False)
        page.set_viewport_size({"width": 1440, "height": 900})

        # logout -> login page with a wrong password
        page.goto(f"{args.url}/login")
        page.get_by_label("البريد الإلكتروني", exact=True).fill("admin@alwaha.example.com")
        page.get_by_label("كلمة المرور", exact=True).fill("wrong-password-1")
        page.get_by_role("button", name="دخول").click()
        expect(page.get_by_role("alert")).to_be_visible()
        shot(page, "12-login-error.png", full=False)
        browser.close()

    if external:
        raise SystemExit(f"external requests made: {sorted(set(external))}")
    print("no external requests")


if __name__ == "__main__":
    main()
