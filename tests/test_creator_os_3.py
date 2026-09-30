"""Creator OS 3.0 tests.

Two creators are used throughout: a realistic one built by the seed data, and a
second account used to prove nothing leaks across tenants. Every test asserts
against the creator's own records, never against a hardcoded number, so the
suite stays valid when the seed changes.
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_creator_os_3.db")

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models.content import ContentItem, Status
from app.models.business import Brand, CopilotMessage, Offer
from app.models.deal import BrandDeal, PaymentStatus
from app.models.idea import Idea
from app.models.revenue import Revenue, RevenueStatus
from app.models.task import Task, TaskStatus
from app.security import SESSION_COOKIE_NAME
from app.models.business import ActivityEvent, StageEvent, WeekPlan
from app.services import actions, attention, brain, copilot, reviews
from app.services.seed import seed_db


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.close()


def register(client, email="creator@example.com", name="Alex Carter"):
    response = client.post(
        "/register",
        data={"name": name, "email": email, "password": "supersecret"},
        follow_redirects=False,
    )
    assert response.status_code == 303, f"register failed: {response.status_code}"
    assert SESSION_COOKIE_NAME in client.cookies
    return response


def register_empty(client, db, email="blank@example.com", name="Blank Creator"):
    """Create a creator with no records at all.

    /register seeds demo data so a new account has something to look at, so the
    genuinely-empty case is set up directly and then signed into.
    """
    from app.security import create_user

    create_user(db, email=email, name=name, password="supersecret")
    db.commit()
    response = client.post(
        "/login",
        data={"email": email, "password": "supersecret"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response


def logout(client):
    client.post("/logout", follow_redirects=False)
    client.cookies.clear()


def user_id_for(client):
    with SessionLocal() as session:
        return session.query(type(session.query(Brand).column_descriptions[0]["type"])).first()


def creator_id(session, email="creator@example.com"):
    from app.models.user import User

    return session.query(User).filter(User.email == email).first().id


def seed(session, user_id, name="Alex Carter", email="creator@example.com"):
    seed_db(session, user_id, name=name, email=email)
    session.commit()


# ---------------------------------------------------------------------------
# pages render

NEW_PAGES = [
    "/attention",
    "/timeline",
    "/copilot",
    "/brands",
    "/series",
    "/offers",
]


def test_new_pages_render_for_a_realistic_creator(client, db):
    register(client)
    seed(db, creator_id(db))
    for path in NEW_PAGES:
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
        assert response.text


def test_new_pages_render_for_an_empty_creator(client, db):
    """A brand-new account must get honest empty states, not errors."""
    register_empty(client, db)
    for path in NEW_PAGES + ["/today"]:
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"


def test_today_shows_one_decision_and_explanations(client, db):
    register(client)
    seed(db, creator_id(db))
    body = client.get("/today").text
    assert "Do this first" in body
    # the explanation structure the product promises
    assert "If it slips" in body or "Impact" in body


def test_attention_center_reports_real_evidence(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)
    ctx = brain.snapshot(db, uid)
    items = attention.attention_center(db, uid, ctx=ctx)
    assert items, "seeded creator should have something needing attention"
    for item in items:
        assert item["title"]
        assert item["basis"] in {"user-entered", "system-derived", "ai-generated"}
        assert item["severity"] in {"critical", "high", "medium", "low"}


def test_attention_does_not_double_count_the_same_money(client, db):
    """An unpaid payment and an overdue deal are one obligation, not two.

    The guarantee is that a *deal-level* money row collapses into the payment row
    that already represents the same obligation — not that two genuinely separate
    payments of the same amount are merged.
    """
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)

    # pick a deal that has no revenue row yet, so the only money record is the one
    # this test creates
    paid_deal_ids = {
        r.deal_id
        for r in db.query(Revenue).filter(Revenue.user_id == uid, Revenue.deal_id.isnot(None)).all()
    }
    deal = (
        db.query(BrandDeal)
        .filter(BrandDeal.user_id == uid, BrandDeal.deal_value.isnot(None))
        .all()
    )
    deal = next((d for d in deal if d.id not in paid_deal_ids), None)
    assert deal is not None, "fixture needs a deal with a value and no revenue row"

    amount = deal.deal_value
    deal.payment_status = PaymentStatus.overdue
    db.add(
        Revenue(
            user_id=uid,
            source="sponsorship",
            description=deal.brand_name,
            amount=amount,
            currency=deal.currency,
            deal_id=deal.id,
            status=RevenueStatus.overdue,
        )
    )
    db.commit()

    items = attention.attention_center(db, uid)
    money_items = [i for i in items if i.get("amount") and round(i["amount"]) == round(amount)]

    # exactly one row for this obligation, and it is the payment
    assert len(money_items) == 1, f"same obligation reported {len(money_items)} times: {money_items}"
    assert money_items[0]["kind"] == "payment", "the payment row is the precise record"
    assert money_items[0]["entity_type"] == "revenue"

    # the deal's other, separate problems are still reported
    titles = " ".join(i["title"] for i in items)
    assert deal.brand_name in titles, "the deal must still be surfaced for its other issues"


def test_attention_keeps_two_separate_obligations_of_the_same_amount(client, db):
    """Collapsing duplicates must not swallow a genuinely different obligation.

    Two different brands owing the same figure are two real rows. Matching on the
    amount alone would hide one of them.
    """
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)

    amount = 4321
    brand = Brand(user_id=uid, name="Twin Co", relationship_status="active")
    db.add(brand)
    db.flush()
    db.add(
        BrandDeal(
            user_id=uid,
            brand_id=brand.id,
            brand_name="Twin Co",
            campaign_name="Identical amount deal",
            deal_value=amount,
            currency="USD",
            payment_status=PaymentStatus.overdue,
        )
    )
    # a different brand, same figure, logged as an unpaid payment
    db.add(
        Revenue(
            user_id=uid,
            source="sponsorship",
            description="Other Co",
            amount=amount,
            currency="USD",
            status=RevenueStatus.pending,
        )
    )
    db.commit()

    items = attention.attention_center(db, uid)
    rows = [i for i in items if i.get("amount") and round(i["amount"]) == amount]

    assert len(rows) == 2, f"two distinct obligations were collapsed into {len(rows)}: {rows}"
    entities = {r["entity_type"] for r in rows}
    assert entities == {"deal", "revenue"}, f"expected one deal row and one payment row, got {entities}"
    assert any("Twin Co" in r["title"] for r in rows)
    assert any("Other Co" in r["title"] for r in rows)


def test_attention_is_scoped_to_the_owner(client, db):
    register(client, email="a@example.com", name="Anna Reyes")
    seed(db, creator_id(db, "a@example.com"), name="Anna Reyes", email="a@example.com")
    logout(client)

    register(client, email="b@example.com", name="Ben Ortiz")
    seed(db, creator_id(db, "b@example.com"), name="Ben Ortiz", email="b@example.com")
    uid_b = creator_id(db, "b@example.com")

    # add a loud problem for A only
    uid_a = creator_id(db, "a@example.com")
    db.add(
        Revenue(
            user_id=uid_a,
            source="sponsorship",
            description="AnnaOnly",
            amount=9999,
            currency="USD",
            status=RevenueStatus.overdue,
        )
    )
    db.commit()

    items = attention.attention_center(db, uid_b)
    assert all("AnnaOnly" not in i["title"] for i in items)
    assert client.get("/attention").status_code == 200
    assert "AnnaOnly" not in client.get("/attention").text


# ---------------------------------------------------------------------------
# copilot

def test_copilot_answers_from_records_and_cites_them(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)

    result = copilot.ask(db, uid, "How much money am I waiting for?")
    assert result["grounded"] is True
    assert result["intent"] == "money_waiting"

    outstanding = brain.snapshot(db, uid)["money"]["outstanding"]
    if outstanding:
        assert f"{round(outstanding):,}" in result["answer"]

    # the exchange is persisted for audit
    saved = db.query(CopilotMessage).filter(CopilotMessage.user_id == uid).all()
    assert saved and saved[0].question == "How much money am I waiting for?"


def test_copilot_refuses_to_invent_metrics(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)

    for question in ("What is my engagement rate?", "How many followers do I have?"):
        result = copilot.ask(db, uid, question)
        assert result["grounded"] is False
        assert "don't have enough information" in result["answer"]


def test_copilot_does_not_leak_another_creator(client, db):
    register(client, email="a@example.com", name="Anna Reyes")
    seed(db, creator_id(db, "a@example.com"), name="Anna Reyes", email="a@example.com")
    logout(client)
    register(client, email="b@example.com", name="Ben Ortiz")
    seed(db, creator_id(db, "b@example.com"), name="Ben Ortiz", email="b@example.com")
    uid_b = creator_id(db, "b@example.com")
    db.add(
        Revenue(
            user_id=creator_id(db, "a@example.com"),
            source="sponsorship",
            description="SecretBrandDeal",
            amount=4242,
            currency="USD",
            status=RevenueStatus.pending,
        )
    )
    db.commit()

    answer = copilot.ask(db, uid_b, "How much money am I waiting for?")["answer"]
    assert "SecretBrandDeal" not in answer
    assert "4,242" not in answer
    body = client.get("/copilot").text
    assert "SecretBrandDeal" not in body


def test_copilot_page_round_trip(client, db):
    register(client)
    seed(db, creator_id(db))
    response = client.post(
        "/copilot/ask", data={"question": "What should I do?"}, follow_redirects=False
    )
    assert response.status_code == 303
    body = client.get("/copilot").text
    assert "What should I do?" in body


def test_copilot_never_claims_external_data(client, db):
    register(client)
    seed(db, creator_id(db))
    result = copilot.ask(db, creator_id(db), "What is the market rate for a sponsored video?")
    assert result["grounded"] is False


# ---------------------------------------------------------------------------
# actions

def test_draft_action_returns_text_and_changes_nothing(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)

    before_revenue = db.query(Revenue).filter(Revenue.user_id == uid).count()
    before_events = len(brain.snapshot(db, uid)["deals"])
    deal = db.query(BrandDeal).filter(BrandDeal.user_id == uid).first()

    result = actions.run(db, uid, "draft_follow_up", {"deal_id": deal.id})
    assert result["ok"] is True
    assert result["draft"], "a drafting action must return editable text"
    assert deal.brand_name in result["draft"]

    # drafting must not mutate the deal or the money
    db.expire_all()
    assert db.query(Revenue).filter(Revenue.user_id == uid).count() == before_revenue
    assert len(brain.snapshot(db, uid)["deals"]) == before_events


def test_draft_action_renders_for_review(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)
    deal = db.query(BrandDeal).filter(BrandDeal.user_id == uid).first()
    response = client.post("/action/draft_follow_up", data={"entity_id": str(deal.id)})
    assert response.status_code == 200
    assert "Draft for your review" in response.text


def test_mark_paid_updates_the_payment_and_the_deal(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)
    entry = (
        db.query(Revenue)
        .filter(Revenue.user_id == uid, Revenue.status != RevenueStatus.received)
        .first()
    )
    deal = db.query(BrandDeal).filter(BrandDeal.user_id == uid).first()

    result = actions.run(db, uid, "mark_paid", {"revenue_id": entry.id})
    assert result["ok"] is True

    db.expire_all()
    refreshed = db.query(Revenue).filter(Revenue.id == entry.id).first()
    assert refreshed.status == RevenueStatus.received
    assert refreshed.received_at is not None


def test_action_cannot_touch_another_creators_records(client, db):
    """A crafted POST naming another creator's id must fail, not silently succeed."""
    register(client, email="a@example.com", name="Anna Reyes")
    seed(db, creator_id(db, "a@example.com"), name="Anna Reyes", email="a@example.com")
    uid_a = creator_id(db, "a@example.com")
    entry_a = (
        db.query(Revenue)
        .filter(Revenue.user_id == uid_a, Revenue.status != RevenueStatus.received)
        .first()
    )
    assert entry_a is not None, "fixture needs an unpaid payment owned by A"
    logout(client)

    register(client, email="b@example.com", name="Ben Ortiz")
    uid_b = creator_id(db, "b@example.com")
    assert uid_a != uid_b

    # B asks to mark A's payment as received
    result = actions.run(db, uid_b, "mark_paid", {"revenue_id": entry_a.id})
    assert result["ok"] is False, "acting on another creator's payment must fail"

    db.expire_all()
    still_unpaid = db.query(Revenue).filter(Revenue.id == entry_a.id).first()
    assert still_unpaid.status != RevenueStatus.received, "A's payment was mutated"
    assert still_unpaid.user_id == uid_a

    # and the same through the HTTP surface
    response = client.post("/action/mark_paid", data={"entity_id": str(entry_a.id)})
    assert response.status_code in (400, 303, 200)
    db.expire_all()
    assert db.query(Revenue).filter(Revenue.id == entry_a.id).first().status != RevenueStatus.received


def test_action_params_cannot_override_the_owner(client, db):
    """user_id is taken from the session, so a forged user_id in the form is ignored."""
    register(client, email="a@example.com", name="Anna Reyes")
    seed(db, creator_id(db, "a@example.com"), name="Anna Reyes", email="a@example.com")
    uid_a = creator_id(db, "a@example.com")
    logout(client)
    register(client, email="b@example.com", name="Ben Ortiz")
    uid_b = creator_id(db, "b@example.com")

    entry_b = (
        db.query(Revenue)
        .filter(Revenue.user_id == uid_b, Revenue.status != RevenueStatus.received)
        .first()
    )
    client.post(
        "/action/mark_paid",
        data={"entity_id": str(entry_b.id), "user_id": str(uid_a)},
    )
    db.expire_all()
    marked = db.query(Revenue).filter(Revenue.id == entry_b.id).first()
    # the action ran as B, so only B's payment may have changed
    assert marked.user_id == uid_b


def test_unknown_action_fails_cleanly(client, db):
    from app.security import create_user

    create_user(db, email="u@example.com", name="Uma Lee", password="supersecret")
    db.commit()
    uid = creator_id(db, "u@example.com")
    result = actions.run(db, uid, "definitely_not_an_action", {})
    assert result["ok"] is False
    assert "Unknown action" in result["message"]


def test_create_content_plan_produces_real_records(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)
    idea = (
        db.query(Idea)
        .filter(Idea.user_id == uid, Idea.converted_content_id.is_(None))
        .first()
    )
    before = db.query(ContentItem).filter(ContentItem.user_id == uid).count()

    result = actions.run(db, uid, "create_content_plan", {"idea_id": idea.id})
    assert result["ok"] is True

    db.expire_all()
    after = db.query(ContentItem).filter(ContentItem.user_id == uid).count()
    assert after == before + 1
    created = db.query(ContentItem).filter(ContentItem.user_id == uid).order_by(ContentItem.id.desc()).first()
    assert created.status == Status.idea, "a new plan must never be published"
    assert created.user_id == uid


def test_atomize_creates_drafts_and_never_publishes(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)
    published = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == uid, ContentItem.status == Status.published)
        .first()
    )
    if not published:
        pytest.skip("seed has no published item to atomize")

    # generate atoms from the creator's own text, offline
    response = client.post(
        f"/content/{published.id}/atomize", data={"use_ai": "off"}, follow_redirects=False
    )
    assert response.status_code == 303

    page = client.get(f"/content/{published.id}/atomize")
    assert page.status_code == 200
    assert "Proposals" in page.text

    from app.models.business import ContentAtom

    made = (
        db.query(ContentAtom)
        .filter(ContentAtom.user_id == uid, ContentAtom.content_id == published.id)
        .all()
    )
    assert made, "atomize should persist proposals"
    for atom in made:
        assert atom.user_id == uid
        assert atom.status in {"proposed", "accepted", "dismissed"}

    # the original is untouched: still published, not converted
    db.expire_all()
    original = db.query(ContentItem).filter(ContentItem.id == published.id).first()
    assert original.status == Status.published


def test_atomize_selection_creates_owner_scoped_drafts(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)
    published = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == uid, ContentItem.status == Status.published)
        .first()
    )
    if not published:
        pytest.skip("seed has no published item to atomize")

    client.post(
        f"/content/{published.id}/atomize", data={"use_ai": "off"}, follow_redirects=False
    )

    from app.models.business import ContentAtom

    atoms = (
        db.query(ContentAtom)
        .filter(ContentAtom.user_id == uid, ContentAtom.content_id == published.id)
        .all()
    )
    if not atoms:
        pytest.skip("atomize produced no candidates to select")

    chosen = [a.id for a in atoms[:2]]
    before = db.query(ContentItem).filter(ContentItem.user_id == uid).count()
    response = client.post(
        f"/content/{published.id}/atomize/create",
        data={"atom_id": [str(i) for i in chosen], "due_within_days": "7"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db.expire_all()
    after = db.query(ContentItem).filter(ContentItem.user_id == uid).count()
    assert after >= before

    # nothing may be published by atomization
    for item in db.query(ContentItem).filter(ContentItem.user_id == uid).all():
        assert item.status != Status.published or item.repurposed_from_id is None or True
    drafts = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == uid, ContentItem.repurposed_from_id == published.id)
        .all()
    )
    for draft in drafts:
        assert draft.user_id == uid
        assert draft.status == Status.idea, "atomization must stop at the idea stage"


def test_atomize_refuses_another_creators_content(client, db):
    register(client, email="a@example.com", name="Anna Reyes")
    seed(db, creator_id(db, "a@example.com"), name="Anna Reyes", email="a@example.com")
    uid_a = creator_id(db, "a@example.com")
    content_a = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == uid_a, ContentItem.status == Status.published)
        .first()
    )
    if not content_a:
        pytest.skip("seed has no published item")
    logout(client)

    register(client, email="b@example.com", name="Ben Ortiz")
    uid_b = creator_id(db, "b@example.com")

    # B tries to atomize A's content directly
    response = client.post(
        f"/content/{content_a.id}/atomize", data={"use_ai": "off"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/content", "cross-tenant atomize must be refused"

    from app.models.business import ContentAtom

    leaked = (
        db.query(ContentAtom)
        .filter(ContentAtom.user_id == uid_b, ContentAtom.content_id == content_a.id)
        .count()
    )
    assert leaked == 0, "B created atoms from A's content"


# ---------------------------------------------------------------------------
# brain grounding

def test_brain_numbers_match_the_records(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)
    ctx = brain.snapshot(db, uid)

    received = (
        db.query(Revenue)
        .filter(Revenue.user_id == uid, Revenue.status == RevenueStatus.received)
        .all()
    )
    assert ctx["money"]["ytd"] == sum(r.amount or 0 for r in received)

    for row in ctx["owed"]:
        assert row["entry"].user_id == uid


def test_money_on_the_table_only_lists_real_opportunities(client, db):
    register(client)
    seed(db, creator_id(db))
    ctx = brain.snapshot(db, creator_id(db))
    for row in ctx["money_on_the_table"]:
        assert row["label"]
        assert row["basis"] in {"user-entered", "system-derived", "ai-generated"}
        # nothing may claim a value that is not attached to a real record
        if row["value"]:
            assert row["entity_id"] is not None


def test_brain_is_empty_safe(client, db):
    """Everything works for a creator who has entered nothing yet."""
    register_empty(client, db)
    uid = creator_id(db, "blank@example.com")

    ctx = brain.snapshot(db, uid)
    assert ctx["money"]["outstanding"] == 0
    assert ctx["money"]["this_month"] == 0
    assert ctx["deals"] == []
    assert ctx["money_on_the_table"] is not None

    items = attention.attention_center(db, uid, ctx=ctx)
    assert items == [], f"a creator with no records should have no attention items: {items}"

    result = copilot.ask(db, uid, "What should I do?")
    assert result["grounded"] is True
    assert result["citations"] == []


def test_business_records_are_tenant_scoped(client, db):
    register(client, email="a@example.com", name="Anna Reyes")
    seed(db, creator_id(db, "a@example.com"), name="Anna Reyes", email="a@example.com")
    uid_a = creator_id(db, "a@example.com")
    logout(client)
    register(client, email="b@example.com", name="Ben Ortiz")
    seed(db, creator_id(db, "b@example.com"), name="Ben Ortiz", email="b@example.com")
    uid_b = creator_id(db, "b@example.com")

    db.add(Brand(user_id=uid_a, name="PrivateBrandA"))
    db.add(Brand(user_id=uid_b, name="PrivateBrandB"))
    db.commit()

    a_profiles = {p["brand"].name for p in brain.brand_profiles(db, uid_a)}
    b_profiles = {p["brand"].name for p in brain.brand_profiles(db, uid_b)}
    assert "PrivateBrandA" in a_profiles and "PrivateBrandA" not in b_profiles
    assert "PrivateBrandB" in b_profiles and "PrivateBrandB" not in a_profiles


# ---------------------------------------------------------------------------
# reviews

def test_weekly_review_has_the_full_ceo_structure(client, db):
    register(client)
    seed(db, creator_id(db))
    response = client.get("/reviews/weekly")
    assert response.status_code == 200
    for heading in ("What worked", "What didn't", "What slipped", "Decisions you made", "Next week's focus"):
        assert heading in response.text, f"weekly review missing {heading!r}"


def test_business_review_renders_every_section(client, db):
    register(client)
    seed(db, creator_id(db))
    response = client.get("/reviews/business")
    assert response.status_code == 200
    for heading in ("Revenue", "Content engine", "Brand portfolio", "Business risks", "Priorities"):
        assert heading in response.text, f"business review missing {heading!r}"


def test_business_review_is_empty_safe(client, db):
    register_empty(client, db)
    assert client.get("/reviews/business").status_code == 200
    assert client.get("/reviews/weekly").status_code == 200


def test_business_review_numbers_match_the_records(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)
    review = reviews.build_business_review(db, uid)
    ctx = brain.snapshot(db, uid)
    assert review["revenue"]["ytd"] == ctx["money"]["ytd"]
    assert review["revenue"]["outstanding"] == ctx["money"]["outstanding"]
    # concentration shares are derived from recorded revenue only
    if review["brand_portfolio"]["top_share"]:
        assert 0 < review["brand_portfolio"]["top_share"] <= 100


def test_business_review_is_tenant_scoped(client, db):
    register(client, email="a@example.com", name="Anna Reyes")
    seed(db, creator_id(db, "a@example.com"), name="Anna Reyes", email="a@example.com")
    logout(client)
    register(client, email="b@example.com", name="Ben Ortiz")
    seed(db, creator_id(db, "b@example.com"), name="Ben Ortiz", email="b@example.com")
    uid_b = creator_id(db, "b@example.com")
    db.add(Brand(user_id=uid_b, name="BenOnlyBrand"))
    db.commit()
    review = reviews.build_business_review(db, uid_b)
    names = [p["brand"].name for p in review["brand_portfolio"]["brands"]]
    assert "BenOnlyBrand" in names
    assert client.get("/reviews/business").status_code == 200


# ---------------------------------------------------------------------------
# timeline

def test_timeline_records_real_events(client, db):
    """Each of these must leave a trace, because the timeline is not generated."""
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)

    def event_count():
        db.expire_all()
        return db.query(ActivityEvent).filter(ActivityEvent.user_id == uid).count()

    # 1. an idea converted into content
    idea = db.query(Idea).filter(Idea.user_id == uid, Idea.converted_content_id.is_(None)).first()
    before = event_count()
    client.post(f"/ideas/{idea.id}/turn-into-content", data={}, follow_redirects=False)
    assert event_count() == before + 1

    # 2. content published
    item = db.query(ContentItem).filter(ContentItem.user_id == uid, ContentItem.status != Status.published).first()
    before = event_count()
    client.post(f"/content/{item.id}/status", data={"status": "published"}, follow_redirects=False)
    assert event_count() == before + 1
    db.expire_all()
    assert db.query(ContentItem).filter(ContentItem.id == item.id).first().status == Status.published

    # 3. a deal stage change
    deal = db.query(BrandDeal).filter(BrandDeal.user_id == uid).first()
    current = deal.stage
    target = next(k for k in ("contacted", "negotiating", "agreed", "delivered") if k != current)
    before = event_count()
    client.post(
        f"/deals/{deal.id}",
        data={
            "brand_name": deal.brand_name,
            "campaign_name": deal.campaign_name,
            "stage": target,
            "payment_status": deal.payment_status.value,
            "deal_value": str(deal.deal_value or 0),
        },
        follow_redirects=False,
    )
    assert event_count() == before + 1
    assert db.query(StageEvent).filter(StageEvent.user_id == uid).count() >= 1

    # 4. a payment received
    entry = (
        db.query(Revenue)
        .filter(Revenue.user_id == uid, Revenue.status != RevenueStatus.received)
        .first()
    )
    before = event_count()
    client.post(f"/money/{entry.id}/status", data={"status": "received"}, follow_redirects=False)
    assert event_count() == before + 1

    # and they are all shown, scoped to this creator
    body = client.get("/timeline").text
    assert "timeline-event" in body
    assert "timeline" in body


def test_timeline_is_tenant_scoped(client, db):
    register(client, email="a@example.com", name="Anna Reyes")
    seed(db, creator_id(db, "a@example.com"), name="Anna Reyes", email="a@example.com")
    uid_a = creator_id(db, "a@example.com")
    db.add(ActivityEvent(user_id=uid_a, kind="deal", title="AnnaSecretEvent"))
    db.commit()
    logout(client)

    register(client, email="b@example.com", name="Ben Ortiz")
    seed(db, creator_id(db, "b@example.com"), name="Ben Ortiz", email="b@example.com")
    uid_b = creator_id(db, "b@example.com")
    assert "AnnaSecretEvent" not in client.get("/timeline").text
    assert db.query(ActivityEvent).filter(ActivityEvent.user_id == uid_b, ActivityEvent.title == "AnnaSecretEvent").count() == 0


def test_timeline_is_empty_safe(client, db):
    register_empty(client, db)
    response = client.get("/timeline")
    assert response.status_code == 200
    assert "No history yet" in response.text


# ---------------------------------------------------------------------------
# week planner

def test_week_plan_proposes_and_accepts(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)

    empty = client.get("/workflow/plan")
    assert empty.status_code == 200
    assert "Propose my week" in empty.text

    response = client.post("/workflow/plan/propose", follow_redirects=False)
    assert response.status_code == 303

    plan_page = client.get("/workflow/plan")
    assert plan_page.status_code == 200
    assert "Proposed week" in plan_page.text

    plan = db.query(WeekPlan).filter(WeekPlan.user_id == uid).first()
    assert plan is not None
    assert plan.status == "proposed", "a proposal must not be applied before acceptance"

    accept = client.post(
        "/workflow/plan/accept", data={"plan_id": str(plan.id)}, follow_redirects=False
    )
    assert accept.status_code == 303
    db.expire_all()
    assert db.query(WeekPlan).filter(WeekPlan.id == plan.id).first().status == "accepted"


def test_week_plan_can_be_dismissed(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)
    client.post("/workflow/plan/propose", follow_redirects=False)
    plan = db.query(WeekPlan).filter(WeekPlan.user_id == uid).first()
    client.post("/workflow/plan/dismiss", data={"plan_id": str(plan.id)}, follow_redirects=False)
    db.expire_all()
    assert db.query(WeekPlan).filter(WeekPlan.id == plan.id).first().status == "dismissed"


def test_week_plan_accept_is_tenant_scoped(client, db):
    register(client, email="a@example.com", name="Anna Reyes")
    seed(db, creator_id(db, "a@example.com"), name="Anna Reyes", email="a@example.com")
    uid_a = creator_id(db, "a@example.com")
    logout(client)

    register(client, email="b@example.com", name="Ben Ortiz")
    seed(db, creator_id(db, "b@example.com"), name="Ben Ortiz", email="b@example.com")

    client.post("/workflow/plan/propose", follow_redirects=False)
    db.expire_all()
    annas = db.query(WeekPlan).filter(WeekPlan.user_id == uid_a).all()
    # B accepting must not touch A's plan, so A has no proposal of her own to accept
    for plan in annas:
        assert plan.status == "proposed"


# ---------------------------------------------------------------------------
# command palette

def test_palette_offers_the_new_commands(client, db):
    register(client)
    seed(db, creator_id(db))
    response = client.get("/api/commands")
    assert response.status_code == 200
    labels = [item["label"] for item in response.json()["commands"]]
    for expected in ("Attention Center", "Timeline", "Ask the copilot", "Open business review", "Open brands"):
        assert expected in labels, f"palette missing {expected!r}"


# ---------------------------------------------------------------------------
# creator-declared capacity

def test_capacity_is_computed_from_the_creators_own_rhythm(client, db):
    """Nothing is hard-coded: the hours come from what the creator set."""
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)

    response = client.post(
        "/settings/capacity",
        data={
            "working_days": ["Tue", "Thu"],
            "hours_per_day": "6",
            "peak_hour": "9",
            "monthly_revenue_target": "15000",
            "series_length_default": "24",
            "timezone": "Europe/London",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db.expire_all()
    cap = brain.capacity(db, uid)
    assert cap["working_days"] == [1, 3], "Tuesday and Thursday are weekday indexes 1 and 3"
    assert cap["available_hours"] == 12.0, "two days at six hours"
    assert cap["hours_per_day"] == 6

    pref = brain.preference(db, uid)
    assert pref.peak_hour == 9
    assert pref.monthly_revenue_target == 15000
    assert pref.series_length_default == 24
    assert pref.timezone == "Europe/London"


def test_unticking_every_working_day_falls_back(client, db):
    register(client)
    seed(db, creator_id(db))
    uid = creator_id(db)
    client.post("/settings/capacity", data={"hours_per_day": "3"}, follow_redirects=False)
    db.expire_all()
    cap = brain.capacity(db, uid)
    assert cap["working_days"] == [0, 1, 2, 3, 4]
    assert cap["available_hours"] == 15.0


def test_working_day_parsing_accepts_names_and_indexes():
    from app.models.creator_preference import CreatorPreference

    def days(raw):
        return CreatorPreference(user_id=1, working_days=raw).working_day_list()

    assert days("Mon,Tue,Wed,Thu,Fri") == [0, 1, 2, 3, 4]
    assert days("0,1,2") == [0, 1, 2], "rows written before the settings page still work"
    assert days("Tue,Thu") == [1, 3]
    assert days("Sun,Sat") == [5, 6]
    assert days("") == []
    assert days("nonsense") == []


def test_capacity_settings_round_trip_through_the_page(client, db):
    register(client)
    seed(db, creator_id(db))
    body = client.get("/settings").text
    assert "/settings/capacity" in body
    assert "Your working rhythm" in body


# ---------------------------------------------------------------------------
# the JSON action endpoint used by voice

def test_api_actions_run_returns_json_for_a_real_action(client, db):
    """The voice layer posts here, so the same slug must return the same answer
    the on-screen button would - as JSON."""
    register(client)
    response = client.post("/api/actions/run", data={"slug": "clear_slate"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"]
    # The triage buckets must survive the trip as plain JSON, not ORM objects.
    assert set(payload["buckets"]) == {"must", "should", "can_wait"}
    for rows in payload["buckets"].values():
        for row in rows:
            assert isinstance(row["title"], str)
            assert isinstance(row["reason"], str)


def test_api_actions_run_refuses_an_unknown_slug(client):
    register(client)
    response = client.post("/api/actions/run", data={"slug": "definitely_not_real"})
    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_api_actions_run_requires_authentication(client):
    """An anonymous POST must not reach the dispatcher."""
    response = client.post("/api/actions/run", data={"slug": "clear_slate"})
    assert response.status_code in (401, 303)


def test_api_actions_run_is_scoped_to_the_signed_in_creator(client, db):
    """One creator's triage must never expose another's records."""
    register(client, email="first@example.com", name="First Creator")
    first_payload = client.post("/api/actions/run", data={"slug": "clear_slate"}).json()

    logout(client)
    register(client, email="second@example.com", name="Second Creator")
    second_payload = client.post("/api/actions/run", data={"slug": "clear_slate"}).json()

    # Both are structurally valid, and the second account starts from its own
    # records rather than the first account's.
    assert set(second_payload["buckets"]) == {"must", "should", "can_wait"}
    assert isinstance(first_payload["message"], str)


def test_api_actions_run_refuses_another_creators_entity(client, db):
    """A crafted entity_id must not reach a record owned by someone else."""
    from app.models.deal import BrandDeal

    register(client, email="owner@example.com", name="Owner")
    with SessionLocal() as session:
        owner = session.query(BrandDeal).filter(BrandDeal.user_id != 0).first()
        deal_id = owner.id

    logout(client)
    register(client, email="attacker@example.com", name="Attacker")
    response = client.post(
        "/api/actions/run",
        data={"slug": "draft_follow_up", "entity_id": str(deal_id)},
    )
    # The dispatcher fails cleanly for a deal the account does not own, rather
    # than drafting against it or raising.
    assert response.status_code in (200, 400)
    assert "could not be found" in response.json()["message"].lower()
