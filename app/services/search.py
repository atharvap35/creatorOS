"""Global search and the command palette, grouped by object type."""

from sqlalchemy.orm import Session

from app.models.content import ContentItem
from app.models.deal import BrandDeal
from app.models.idea import Idea
from app.models.opportunity import MonetizationOpportunity
from app.models.repurpose import ContentRepurpose
from app.models.revenue import Revenue
from app.models.task import Task

MAX_PER_GROUP = 5


def _like(term: str) -> str:
    return f"%{term.strip()}%"


def search_all(db: Session, user_id: int, query: str) -> list:
    term = (query or "").strip()
    if len(term) < 2:
        return []

    groups = []

    deals = (
        db.query(BrandDeal)
        .filter(BrandDeal.user_id == user_id)
        .filter(BrandDeal.brand_name.ilike(_like(term)) | BrandDeal.campaign_name.ilike(_like(term)))
        .limit(MAX_PER_GROUP)
        .all()
    )
    if deals:
        groups.append(
            {
                "group": "Deals",
                "items": [
                    {
                        "title": f"{d.brand_name} — {d.campaign_name}",
                        "subtitle": f"{d.stage or d.status.value} · {d.currency} {round(d.deal_value or 0)}",
                        "url": f"/deals/{d.id}",
                    }
                    for d in deals
                ],
            }
        )

    content = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == user_id)
        .filter(
            ContentItem.title.ilike(_like(term))
            | ContentItem.topic.ilike(_like(term))
            | ContentItem.description.ilike(_like(term))
        )
        .limit(MAX_PER_GROUP)
        .all()
    )
    if content:
        groups.append(
            {
                "group": "Content",
                "items": [
                    {
                        "title": c.title,
                        "subtitle": f"{c.status.value} · {c.platform.value}",
                        "url": f"/content/{c.id}",
                    }
                    for c in content
                ],
            }
        )

    tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id)
        .filter(Task.title.ilike(_like(term)) | Task.description.ilike(_like(term)))
        .limit(MAX_PER_GROUP)
        .all()
    )
    if tasks:
        groups.append(
            {
                "group": "Tasks",
                "items": [
                    {"title": t.title, "subtitle": t.status.value, "url": f"/workflow?focus={t.id}"}
                    for t in tasks
                ],
            }
        )

    ideas = (
        db.query(Idea)
        .filter(Idea.user_id == user_id)
        .filter(Idea.title.ilike(_like(term)) | Idea.description.ilike(_like(term)))
        .limit(MAX_PER_GROUP)
        .all()
    )
    if ideas:
        groups.append(
            {
                "group": "Ideas",
                "items": [
                    {"title": i.title, "subtitle": i.status.value, "url": f"/ideas/{i.id}"}
                    for i in ideas
                ],
            }
        )

    revenue = (
        db.query(Revenue)
        .filter(Revenue.user_id == user_id)
        .filter(Revenue.description.ilike(_like(term)) | Revenue.notes.ilike(_like(term)))
        .limit(MAX_PER_GROUP)
        .all()
    )
    if revenue:
        groups.append(
            {
                "group": "Revenue",
                "items": [
                    {
                        "title": r.description or r.source.value,
                        "subtitle": f"{r.status.value} · {r.currency} {round(r.amount or 0)}",
                        "url": "/money",
                    }
                    for r in revenue
                ],
            }
        )

    opportunities = (
        db.query(MonetizationOpportunity)
        .filter(MonetizationOpportunity.user_id == user_id)
        .filter(MonetizationOpportunity.title.ilike(_like(term)) | MonetizationOpportunity.description.ilike(_like(term)))
        .limit(MAX_PER_GROUP)
        .all()
    )
    if opportunities:
        groups.append(
            {
                "group": "Opportunities",
                "items": [
                    {"title": o.title, "subtitle": o.status.value, "url": f"/growth/opportunities/{o.id}"}
                    for o in opportunities
                ],
            }
        )

    return groups


def command_items(db: Session, user_id: int) -> list:
    return [
        {"label": "Create idea", "url": "/quick?type=idea", "hint": "Capture a spark in seconds"},
        {"label": "Create content", "url": "/quick?type=content", "hint": "Add to the pipeline"},
        {"label": "Add task", "url": "/quick?type=task", "hint": "One step, linked or standalone"},
        {"label": "Add deal", "url": "/quick?type=deal", "hint": "New brand partnership"},
        {"label": "Log revenue", "url": "/quick?type=revenue", "hint": "Record money in"},
        {"label": "Ask the copilot", "url": "/copilot", "hint": "Answered from your records"},
        {"label": "Attention Center", "url": "/attention", "hint": "What is slipping"},
        {"label": "Timeline", "url": "/timeline", "hint": "Your business history"},
        {"label": "Plan my week", "url": "/workflow/plan", "hint": "Propose a schedule"},
        {"label": "Plan next episode", "url": "/series", "hint": "Fill the gap in a series"},
        {"label": "Open brands", "url": "/brands", "hint": "Relationships, not logos"},
        {"label": "Open offers", "url": "/offers", "hint": "What you actually sell"},
        {"label": "Find overdue payments", "url": "/money/payments", "hint": "Who owes you money"},
        {"label": "Show today's priorities", "url": "/today", "hint": "Your command centre"},
        {"label": "Start focus mode", "url": "/workflow/focus", "hint": "One task, no noise"},
        {"label": "Open weekly review", "url": "/reviews/weekly", "hint": "Close the loop"},
        {"label": "Open monthly review", "url": "/reviews/monthly", "hint": "Month in numbers"},
        {"label": "Open business review", "url": "/reviews/business", "hint": "The CEO view"},
        {"label": "Open rate card", "url": "/rate-card", "hint": "Pricing you can point to"},
        {"label": "Content calendar", "url": "/calendar", "hint": "Month, week or list"},
        {"label": "Open library", "url": "/library", "hint": "Hooks, templates, brand kit"},
    ]


def quick_search(db: Session, user_id: int, query: str) -> list:
    """Flat result list for the command palette."""
    flat = []
    for group in search_all(db, user_id, query):
        for item in group["items"]:
            flat.append({**item, "group": group["group"]})
    return flat
