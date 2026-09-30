"""Capture the app in real working states: an answered question, an honest refusal,
a proposed week, and a drafted follow-up."""
import os

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8077"
OUT = os.path.abspath("docs/screenshots")

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
    page = ctx.new_page()
    page.set_default_timeout(30000)

    page.goto(BASE + "/login", wait_until="networkidle")
    page.fill('input[name="email"]', "alex@creator.dev")
    page.fill('input[name="password"]', "demo-password-123")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    # 1. Copilot answering a real question (via the suggested-question button)
    page.goto(BASE + "/copilot", wait_until="networkidle")
    page.click('button:has-text("What am I forgetting?")')
    page.wait_for_load_state("networkidle")
    page.screenshot(path=f"{OUT}/44-copilot-answer.png", full_page=True)
    print("44 copilot answer")

    # 2. Copilot honestly refusing an unanswerable question
    page.goto(BASE + "/copilot", wait_until="networkidle")
    page.fill('textarea[name="question"]', "what is my engagement rate")
    page.click('button:has-text("Ask")')
    page.wait_for_load_state("networkidle")
    page.screenshot(path=f"{OUT}/45-copilot-refusal.png", full_page=True)
    print("45 copilot refusal")

    # 3. A real proposed week
    page.goto(BASE + "/workflow/plan", wait_until="networkidle")
    page.click('text=Propose my week')
    page.wait_for_load_state("networkidle")
    page.screenshot(path=f"{OUT}/46-week-proposed.png", full_page=True)
    print("46 week proposed")

    # 4. A drafted follow-up from the Attention Center
    page.goto(BASE + "/attention", wait_until="networkidle")
    link = page.query_selector('text=Draft Follow Up')
    if link:
        link.click()
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{OUT}/47-attention-draft.png", full_page=True)
        print("47 attention draft")
    else:
        print("47 skipped: no Draft Follow Up link")

    # 5. Atomize a published piece offline
    page.goto(BASE + "/content/1/atomize", wait_until="networkidle")
    btn = page.query_selector('text=Generate repurposing plan')
    if btn:
        btn.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=f"{OUT}/48-atomize-generated.png", full_page=True)
        print("48 atomize generated")
    else:
        print("48 skipped")

    browser.close()
print("done")
