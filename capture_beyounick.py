"""Capture the beyounick workspace for the guide.

Separate from capture.py, which builds the standard demo workspace. This records
the account whose content comes from a real public channel feed, so the screens
that had nothing to show - rate card, library, timeline - can be documented with
a populated example rather than an empty one.
"""
import os

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8078"
OUT = os.path.abspath("docs/screenshots")

# slug -> (path, expected text, so a blank page fails loudly instead of
# producing a reassuring empty screenshot)
SHOTS = [
    ("53-beyounick-today", "/today", "Influencer Agency"),
    ("54-beyounick-content", "/content", "Shark Tank Dombivli"),
    ("55-beyounick-rate-card", "/rate-card", "YouTube integration"),
    ("56-beyounick-library", "/library", "Hook"),
    ("57-beyounick-timeline", "/timeline", "Published"),
    ("58-beyounick-money", "/money", "Revenue sources"),
    ("59-beyounick-deals", "/deals", "Fevikwik"),
]


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000},
                                  device_scale_factor=2)
        page = ctx.new_page()
        page.set_default_timeout(30000)

        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.fill('input[name="email"]', "beyounick@example.com")
        page.fill('input[name="password"]', "nick@123")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        print("signed in as beyounick")

        failed = []
        for slug, path, expect in SHOTS:
            page.goto(BASE + path, wait_until="networkidle")
            body = page.inner_text("body")
            if expect not in body:
                failed.append(f"{path} is missing {expect!r} - not capturing a blank page")
                print(f"  SKIP {path}: missing {expect!r}")
                continue
            page.screenshot(path=f"{OUT}/{slug}.png", full_page=True)
            print(f"  saved {slug}.png  ({len(body.strip())} chars)")

        browser.close()

    if failed:
        raise SystemExit("\n".join(failed))
    print(f"\n{len(SHOTS)} snapshots captured.")


if __name__ == "__main__":
    main()