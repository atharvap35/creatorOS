import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_creator_os_2.db")

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.security import SESSION_COOKIE_NAME


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


def register(client, email="creator@example.com", name="Alex Carter"):
    response = client.post(
        "/register",
        data={"name": name, "email": email, "password": "supersecret"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert SESSION_COOKIE_NAME in client.cookies
    return response


def logout(client):
    client.post("/logout", follow_redirects=False)
    client.cookies.clear()


PAGES = [
    "/today",
    "/content",
    "/content/pipeline",
    "/content/pillars",
    "/ideas",
    "/workflow",
    "/workflow/focus",
    "/deals",
    "/money",
    "/money/payments",
    "/rate-card",
    "/growth",
    "/growth/opportunities",
    "/library",
    "/goals",
    "/reviews/weekly",
    "/reviews/monthly",
    "/calendar",
    "/calendar?view=week",
    "/calendar?view=list",
    "/search",
    "/search?q=Acme",
    "/quick",
    "/onboarding",
    "/assistant",
    "/settings",
]


def test_every_page_renders_for_a_new_account(client):
    register(client)
    for path in PAGES:
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"


def test_pages_require_authentication(client):
    for path in PAGES:
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303, f"{path} was reachable without a session"
        assert response.headers["location"].startswith("/login"), path


def test_legacy_urls_still_resolve(client):
    register(client)
    for path, target in [
        ("/dashboard", "/today"),
        ("/tasks", "/workflow"),
        ("/revenue", "/money"),
        ("/opportunities", "/growth/opportunities"),
    ]:
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == target
        assert client.get(path).status_code == 200


def test_legacy_post_aliases_work(client):
    register(client)
    assert client.post("/tasks", data={"title": "Legacy task"}, follow_redirects=False).status_code == 303
    assert client.post(
        "/revenue", data={"source": "affiliate", "amount": "120", "status": "pending"},
        follow_redirects=False,
    ).status_code == 303
    assert "Legacy task" in client.get("/workflow").text


def test_health_and_json_endpoints(client):
    register(client)
    assert client.get("/health").json() == {"status": "ok"}

    commands = client.get("/api/commands").json()["commands"]
    assert any(c["url"] == "/today" for c in commands)

    today = client.get("/api/today").json()
    assert "workload" in today

    found = client.get("/api/search", params={"q": "Acme"}).json()["results"]
    assert isinstance(found, list)


def test_quick_capture_creates_each_object_type(client):
    register(client)
    client.post("/ideas", data={"title": "Seed clear"}, follow_redirects=False)

    for kind, needle in [
        ("idea", "Quick idea"),
        ("content", "Quick content"),
        ("task", "Quick task"),
        ("deal", "Quick brand"),
        ("revenue", "Quick invoice"),
        ("opportunity", "Quick opportunity"),
    ]:
        response = client.post(
            "/quick",
            data={"type": kind, "title": needle, "body": "details", "amount": "250", "category": "sponsorship", "platform": "instagram"},
            follow_redirects=False,
        )
        assert response.status_code == 303

    from app.database import SessionLocal  # noqa: F811
    from app.models.content import ContentItem
    from app.models.deal import BrandDeal
    from app.models.idea import Idea
    from app.models.opportunity import MonetizationOpportunity
    from app.models.revenue import Revenue
    from app.models.task import Task

    db = SessionLocal()
    try:
        assert db.query(Idea).filter(Idea.title == "Quick idea").count() == 1
        assert db.query(ContentItem).filter(ContentItem.title == "Quick content").count() == 1
        assert db.query(Task).filter(Task.title == "Quick task").count() == 1
        assert db.query(BrandDeal).filter(BrandDeal.brand_name == "Quick brand").count() == 1
        assert db.query(Revenue).filter(Revenue.description == "details").count() >= 1
        assert db.query(MonetizationOpportunity).filter(MonetizationOpportunity.title == "Quick opportunity").count() == 1
    finally:
        db.close()


def test_idea_to_content_conversion_creates_brief_and_task(client):
    register(client)
    client.post(
        "/ideas",
        data={"title": "Convertible idea", "problem": "creators waste time", "audience": "new creators", "potential": "high", "effort": "low"},
        follow_redirects=False,
    )

    from app.database import SessionLocal
    from app.models.brief import ContentBrief
    from app.models.idea import Idea
    from app.models.task import Task

    db = SessionLocal()
    try:
        idea = db.query(Idea).filter(Idea.title == "Convertible idea").one()
    finally:
        db.close()

    response = client.post(
        f"/ideas/{idea.id}/turn-into-content",
        data={"platform": "youtube", "content_type": "video", "due_date": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/content/" in response.headers["location"]

    db = SessionLocal()
    try:
        content = db.query(Idea).filter(Idea.id == idea.id).one()
        assert content.converted_content_id is not None
        assert db.query(ContentBrief).filter(ContentBrief.content_id == content.converted_content_id).count() == 1
        assert db.query(Task).filter(Task.content_id == content.converted_content_id).count() == 1
    finally:
        db.close()


def test_derivative_becomes_real_content(client):
    register(client)
    from app.database import SessionLocal
    from app.models.content import ContentItem

    db = SessionLocal()
    try:
        item = db.query(ContentItem).filter(ContentItem.user_id == 1).first()
    finally:
        db.close()

    client.post(
        f"/content/{item.id}/repurpose",
        data={"action": "reel::instagram"},
        follow_redirects=False,
    )
    page = client.get(f"/content/{item.id}/repurpose")
    assert "Reel" in page.text

    from app.models.repurpose import ContentRepurpose

    db = SessionLocal()
    try:
        derivative = db.query(ContentRepurpose).filter(ContentRepurpose.content_id == item.id).first()
    finally:
        db.close()

    client.post(f"/content/{item.id}/derivatives/{derivative.id}/convert", follow_redirects=False)

    db = SessionLocal()
    try:
        child = db.query(ContentItem).filter(ContentItem.repurposed_from_id == item.id).first()
        assert child is not None
        assert child.user_id == item.user_id
    finally:
        db.close()


def test_deal_pipeline_deliverables_and_health(client):
    register(client)
    from app.database import SessionLocal
    from app.models.deal import BrandDeal

    db = SessionLocal()
    try:
        deal = db.query(BrandDeal).filter(BrandDeal.user_id == 1, BrandDeal.stage == "lead").first()
        if deal is None:
            deal = db.query(BrandDeal).filter(BrandDeal.user_id == 1).first()
    finally:
        db.close()

    client.post(
        f"/deals/{deal.id}/deliverables",
        data={"title": "Two reels", "deadline": "", "notes": ""},
        follow_redirects=False,
    )
    assert "Two reels" in client.get(f"/deals/{deal.id}").text

    client.post(
        f"/deals/{deal.id}",
        data={
            "brand_name": deal.brand_name,
            "campaign_name": deal.campaign_name,
            "stage": "negotiating",
            "payment_status": deal.payment_status.value,
            "deal_value": str(deal.deal_value or 0),
        },
        follow_redirects=False,
    )
    db = SessionLocal()
    try:
        assert db.get(BrandDeal, deal.id).stage == "negotiating"
    finally:
        db.close()


def test_goals_pull_live_metrics(client):
    register(client)
    client.post(
        "/goals",
        data={
            "title": "Earn this month",
            "category": "revenue",
            "metric": "monthly_revenue",
            "target_value": "1000",
            "unit": "USD",
            "deadline": "",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert "Earn this month" in client.get("/goals").text

    from app.database import SessionLocal
    from app.models.goal import CreatorGoal

    db = SessionLocal()
    try:
        goal = db.query(CreatorGoal).filter(CreatorGoal.title == "Earn this month").one()
    finally:
        db.close()

    client.get("/goals")
    db = SessionLocal()
    try:
        assert db.get(CreatorGoal, goal.id).current_value > 0
    finally:
        db.close()


def test_reviews_build_and_seed_next_week(client):
    register(client)
    weekly = client.get("/reviews/weekly")
    assert weekly.status_code == 200
    assert "What worked" in weekly.text

    response = client.post(
        "/reviews/start-week",
        data={"title": "Start the week", "reason": "momentum", "minutes": "25"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    from app.database import SessionLocal
    from app.models.task import Task

    db = SessionLocal()
    try:
        assert db.query(Task).filter(Task.title == "Start the week").count() == 1
    finally:
        db.close()

    assert client.get("/reviews/monthly").status_code == 200


def test_library_and_rate_card_crud(client):
    register(client)
    client.post("/library", data={"title": "My hook", "kind": "hook", "body": "text", "tags": "hooks"}, follow_redirects=False)
    assert "My hook" in client.get("/library").text

    client.post(
        "/rate-card",
        data={
            "name": "Instagram Reel",
            "platform": "instagram",
            "starting_price": "500",
            "typical_price": "800",
            "premium_price": "1200",
            "turnaround_days": "5",
            "notes": "2 revisions",
        },
        follow_redirects=False,
    )
    assert "Instagram Reel" in client.get("/rate-card").text


def test_ai_falls_back_offline_and_never_blocks_the_page(client):
    register(client)
    response = client.post(
        "/assistant",
        data={"action": "hooks", "subject": "growing an audience", "context_text": ""},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "growing an audience" in response.text


def test_onboarding_persists_preferences(client):
    register(client)
    for step in range(6):
        response = client.post(
            "/onboarding",
            data={
                "step": str(step),
                "name": "Alex Carter",
                "niche": "AI workflows",
                "audience": "busy freelancers",
                "tone": "direct",
                "platforms": "youtube,linkedin",
                "primary_goal": "make_money",
                "pillars": "AI,Workflow" if step == 4 else "",
                "working_days": "0,1,2",
                "hours_per_day": "3",
                "monetization_methods": "Sponsorships",
                "brand_preferences": "B2B only",
                "finish": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    from app.database import SessionLocal
    from app.models.pillar import ContentPillar
    from app.services.recommender import preference_for

    db = SessionLocal()
    try:
        pref = preference_for(db, 1)
        assert pref.niche == "AI workflows"
        assert pref.platform_list() == ["youtube", "linkedin"]
        assert pref.working_day_list() == [0, 1, 2]
        assert pref.hours_per_day == 3
        names = {p.name for p in db.query(ContentPillar).filter(ContentPillar.user_id == 1).all()}
        assert {"AI", "Workflow"} <= names
    finally:
        db.close()


def test_tenant_isolation_across_new_surfaces(client):
    register(client, email="first@example.com", name="First")
    client.post("/ideas", data={"title": "Secret first idea"}, follow_redirects=False)
    client.post("/goals", data={"title": "Secret first goal", "target_value": "10"}, follow_redirects=False)
    client.post("/library", data={"title": "Secret first asset", "kind": "hook"}, follow_redirects=False)

    logout(client)
    register(client, email="second@example.com", name="Second")

    for path in ("/ideas", "/goals", "/library", "/search?q=Secret"):
        body = client.get(path).text
        assert "Secret first" not in body, path


def test_cross_tenant_records_cannot_be_mutated(client):
    register(client, email="owner2@example.com")
    client.post("/ideas", data={"title": "Owned idea"}, follow_redirects=False)
    client.post("/goals", data={"title": "Owned goal", "target_value": "5"}, follow_redirects=False)

    from app.database import SessionLocal
    from app.models.goal import CreatorGoal
    from app.models.idea import Idea

    db = SessionLocal()
    try:
        idea = db.query(Idea).filter(Idea.user_id == 1).first()
        goal = db.query(CreatorGoal).filter(CreatorGoal.user_id == 1).first()
    finally:
        db.close()

    logout(client)
    register(client, email="intruder@example.com")

    assert client.post(f"/ideas/{idea.id}/delete", follow_redirects=False).status_code == 303
    assert client.post(f"/goals/{goal.id}/delete", follow_redirects=False).status_code == 303

    db = SessionLocal()
    try:
        assert db.get(Idea, idea.id) is not None
        assert db.get(CreatorGoal, goal.id) is not None
    finally:
        db.close()


def test_recommendations_are_explainable_and_deterministic(client):
    from app.services import recommender

    register(client)
    db = SessionLocal()
    try:
        first = recommender.generate(db, 1, limit=6)
        second = recommender.generate(db, 1, limit=6)
        assert [c["title"] for c in first] == [c["title"] for c in second]
        for candidate in first:
            assert candidate["reason"]
            assert candidate["score_breakdown"]
            assert candidate["cta"]
    finally:
        db.close()


def test_business_health_sections_always_present(client):
    from app.services import health

    register(client)
    db = SessionLocal()
    try:
        report = health.business_health(db, 1)
        assert {s["key"] for s in report["sections"]} == {
            "content",
            "monetization",
            "revenue",
            "consistency",
            "operations",
        }
        for section in report["sections"]:
            assert 0 <= section["score"] <= 100
            assert section["why"]
            assert section["action"]
    finally:
        db.close()


def test_search_is_grouped_and_scoped(client):
    register(client)
    page = client.get("/search", params={"q": "Acme"})
    assert page.status_code == 200
    assert "Deals" in page.text
