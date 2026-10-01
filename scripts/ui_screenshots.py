"""Screenshots of the four-step UI for docs/ui/ (Playwright, headless Chromium).

Start the app first (demo mode needs no key), then run this with any Python that has
Playwright installed:

    streamlit run nazeer\\app.py --server.port 8601 --server.headless true
    python scripts\\ui_screenshots.py --url http://localhost:8601 --out docs\\ui

Playwright is a documentation tool only; it is not a Nazeer dependency.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

WIDTH, HEIGHT = 1600, 900  # a common projector-friendly 16:9 size
FULL_HEIGHT = """() => Math.max(...[document.body,
  document.querySelector('[data-testid="stMain"]'),
  document.querySelector('[data-testid="stAppViewContainer"]'),
  document.querySelector('[data-testid="stMainBlockContainer"]')].filter(Boolean).map(e => e.scrollHeight))"""


def settle(page: Page, ms: int = 2500) -> None:
    page.wait_for_timeout(500)
    page.locator('[data-testid="stSpinner"]').first.wait_for(state="detached", timeout=600_000)
    page.wait_for_timeout(ms)


def shot(page: Page, out: Path, name: str, full: bool = True) -> None:
    settle(page)
    if full:
        page.set_viewport_size({"width": WIDTH, "height": max(HEIGHT, min(int(page.evaluate(FULL_HEIGHT)) + 40, 6000))})
        page.wait_for_timeout(1500)
    page.screenshot(path=str(out / name))
    page.set_viewport_size({"width": WIDTH, "height": HEIGHT})
    print("saved", name)


def click(page: Page, label: str) -> None:
    page.get_by_role("button", name=label, exact=True).first.click()
    settle(page)


def walk(page: Page, url: str, out: Path, suffix: str = "") -> None:
    page.goto(url)
    page.get_by_role("button", name="تحميل بيانات العرض").wait_for(timeout=120_000)
    shot(page, out, f"after-0-start{suffix}.png", full=False)
    click(page, "تحميل بيانات العرض")
    page.get_by_role("button", name="التالي: ماذا وجد نظير؟").wait_for(timeout=300_000)
    shot(page, out, f"after-1-data{suffix}.png")
    click(page, "التالي: ماذا وجد نظير؟")
    shot(page, out, f"after-2-detection{suffix}.png")
    if suffix:
        return
    click(page, "التالي: ولّد النظير")
    shot(page, out, "after-3-before-generate.png", full=False)
    click(page, "ولّد النظير")
    page.get_by_role("button", name="التالي: الإثبات").wait_for(timeout=600_000)
    shot(page, out, "after-3-twin.png")
    click(page, "التالي: الإثبات")
    shot(page, out, "after-4-proof-k-fail.png")
    click(page, "طبّق الإصلاح المقترح")
    page.get_by_role("button", name="ازرع تسريباً").wait_for(timeout=600_000)
    shot(page, out, "after-4-proof-pass.png")
    click(page, "ازرع تسريباً")
    page.get_by_role("button", name="أزل التسريب المزروع").wait_for(timeout=600_000)
    shot(page, out, "after-4-planted-leak.png")
    page.get_by_role("tab", name="ليش يشتغل؟").click()
    shot(page, out, "after-why-it-works.png")
    page.get_by_role("tab", name="جرّب نصّك").click()
    shot(page, out, "after-try-your-text.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8601")
    ap.add_argument("--out", type=Path, default=Path("docs/ui"))
    ap.add_argument("--dark", action="store_true", help="also capture steps 1-2 in dark mode")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        walk(browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, color_scheme="light"), args.url, args.out)
        if args.dark:
            walk(browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, color_scheme="dark"), args.url,
                 args.out, "-dark")
        browser.close()


if __name__ == "__main__":
    main()
