"""Capture a screenshot of every creator-facing screen in the platform."""
import os

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8077"
OUT = os.path.abspath("docs/screenshots")
os.makedirs(OUT, exist_ok=True)

EMAIL = "alex@creator.dev"
PASSWORD = "demo-password-123"

# (slug, path, title used in the guide)
PAGES = [
    ("01-login", "/login", "Login"),
    ("02-register", "/register", "Register"),
    ("03-today", "/today", "Today"),
    ("04-attention", "/attention", "Attention Center"),
    ("05-copilot", "/copilot", "Creator Copilot"),
    ("06-timeline", "/timeline", "Timeline"),
    ("07-workflow", "/workflow", "Workflow"),
    ("08-workflow-focus", "/workflow/focus", "Focus mode"),
    ("09-workflow-plan", "/workflow/plan", "Week plan"),
    ("10-content", "/content", "Content"),
    ("11-content-pipeline", "/content/pipeline", "Content pipeline"),
    ("12-content-pillars", "/content/pillars", "Content pillars"),
    ("13-ideas", "/ideas", "Ideas"),
    ("14-deals", "/deals", "Deals"),
    ("15-brands", "/brands", "Brands"),
    ("16-offers", "/offers", "Offers"),
    ("17-series", "/series", "Series"),
    ("18-money", "/money", "Money"),
    ("19-money-payments", "/money/payments", "Payments"),
    ("20-rate-card", "/rate-card", "Rate card"),
    ("21-opportunities", "/growth/opportunities", "Opportunities"),
    ("22-growth", "/growth", "Growth"),
    ("23-goals", "/goals", "Goals"),
    ("24-reviews-weekly", "/reviews/weekly", "Weekly review"),
    ("25-reviews-monthly", "/reviews/monthly", "Monthly review"),
    ("26-reviews-business", "/reviews/business", "Business review"),
    ("27-actions", "/actions", "Actions"),
    ("28-calendar", "/calendar", "Calendar"),
    ("29-library", "/library", "Library"),
    ("30-assistant", "/assistant", "Assistant"),
    ("31-search", "/search", "Search"),
    ("32-quick", "/quick", "Quick capture"),
    ("33-settings", "/settings", "Settings"),
    ("34-dashboard-legacy", "/dashboard", "Legacy /dashboard"),
]

# detail pages, resolved from the database after login
DETAIL = [
    ("35-deal-detail", "/deals/{deal_id}", "Deal detail"),
    ("36-brand-detail", "/brands/{brand_id}", "Brand detail"),
    ("37-offer-detail", "/offers/{offer_id}", "Offer detail"),
    ("38-series-detail", "/series/{series_id}", "Series detail"),
    ("39-content-detail", "/content/{content_id}", "Content detail"),
    ("40-atomize", "/content/{atomize_id}/atomize", "Atomize"),
    ("41-repurpose", "/content/{content_id}/repurpose", "Repurpose"),
    ("42-opportunity-detail", "/growth/opportunities/{opp_id}", "Opportunity detail"),
    ("43-idea-detail", "/ideas/{idea_id}", "Idea detail"),
]


def main():
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000},
                                  device_scale_factor=2)
        page = ctx.new_page()
        page.set_default_timeout(30000)

        # ---- public pages
        for slug, path, title in PAGES[:2]:
            page.goto(BASE + path, wait_until="networkidle")
            page.screenshot(path=f"{OUT}/{slug}.png", full_page=True)
            results.append((slug, title, page.url))

        # ---- sign in
        page.goto(BASE + "/login", wait_until="networkidle")
        page.fill('input[name="email"]', EMAIL)
        page.fill('input[name="password"]', PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        print("signed in ->", page.url)

        # ---- authenticated pages
        for slug, path, title in PAGES[2:]:
            page.goto(BASE + path, wait_until="networkidle")
            page.screenshot(path=f"{OUT}/{slug}.png", full_page=True)
            results.append((slug, title, page.title()))

        # ---- resolve real ids for the detail pages
        import sqlite3

        con = sqlite3.connect("demo.db")
        cur = con.cursor()
        ids = {}
        for key, sql in [
            ("deal_id", "select id from brand_deals limit 1"),
            ("brand_id", "select id from brands limit 1"),
            ("offer_id", "select id from offers limit 1"),
            ("series_id", "select id from content_series limit 1"),
            ("content_id", "select id from content_items where status='published' limit 1"),
            ("opp_id", "select id from monetization_opportunities limit 1"),
            ("idea_id", "select id from ideas limit 1"),
        ]:
            row = cur.execute(sql).fetchone()
            ids[key] = row[0] if row else None
        cur.execute("select id from content_items where status='published' limit 1")
        ids["atomize_id"] = ids["content_id"]
        con.close()
        print("detail ids:", ids)

        for slug, tmpl, title in DETAIL:
            path = tmpl
            ok = True
            for k, v in ids.items():
                path = path.replace("{" + k + "}", str(v))
            if "None" in path:
                print(f"  skip {slug}: missing id")
                ok = False
            if not ok:
                continue
            page.goto(BASE + path, wait_until="networkidle")
            page.screenshot(path=f"{OUT}/{slug}.png", full_page=True)
            results.append((slug, title, page.title()))

        browser.close()

    print(f"\ncaptured {len(results)} screens -> {OUT}")
    for slug, title, _ in results:
        print(f"  {slug:28} {title}")


if __name__ == "__main__":
    main()
