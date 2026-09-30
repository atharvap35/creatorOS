"""The creator business health score.

Every section returns a score, a plain-language state, the evidence behind it and
the single most useful next action. No black boxes, no invented benchmarks.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.content import ContentItem, Status
from app.models.deal import BrandDeal
from app.models.idea import Idea
from app.models.opportunity import MonetizationOpportunity
from app.models.rate_card import RateCardItem
from app.models.revenue import Revenue, RevenueStatus
from app.models.task import Task, TaskStatus
from app.services import insights


def _state(score: int) -> str:
    if score >= 80:
        return "strong"
    if score >= 60:
        return "steady"
    if score >= 40:
        return "needs_attention"
    return "critical"


def _clamp(value, low=0, high=100):
    return max(low, min(high, int(value)))


def content_engine(db: Session, user_id: int) -> dict:
    total = db.query(ContentItem).filter(ContentItem.user_id == user_id).count()
    published = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == user_id, ContentItem.status == Status.published)
        .count()
    )
    in_flight = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == user_id, ContentItem.status != Status.published)
        .count()
    )
    stuck = insights.stuck_content(db, user_id)
    last_30 = (
        db.query(ContentItem)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.status == Status.published,
            ContentItem.published_at >= datetime.now() - timedelta(days=30),
        )
        .count()
    )

    score = _clamp(20 + last_30 * 12 + min(in_flight, 8) * 4 - len(stuck) * 6)
    if published == 0:
        why = "You haven't published anything yet, so there's no performance to learn from."
        action = "Publish one piece this week — consistency matters more than volume."
    elif len(stuck) > 0:
        why = f"{len(stuck)} content item(s) have not been touched in two weeks."
        action = "Finish, archive, or reschedule your stale content."
    elif last_30 == 0:
        why = f"You have {published} published pieces but nothing in the last 30 days."
        action = "Get one piece back into production to protect momentum."
    else:
        why = f"{last_30} piece(s) published in the last 30 days with {in_flight} in production."
        action = "Keep the pipeline fed — schedule your next publish date."

    return {
        "score": score,
        "state": _state(score),
        "why": why,
        "action": action,
        "metrics": {"total": total, "published": published, "in_flight": in_flight, "stuck": len(stuck)},
    }


def monetization_engine(db: Session, user_id: int) -> dict:
    open_deals = (
        db.query(BrandDeal)
        .filter(BrandDeal.user_id == user_id, BrandDeal.stage.notin_(["completed", "cancelled", "declined"]))
        .count()
    )
    opportunities = (
        db.query(MonetizationOpportunity)
        .filter(MonetizationOpportunity.user_id == user_id, MonetizationOpportunity.status.in_(["idea", "evaluating"]))
        .count()
    )
    has_rate_card = db.query(RateCardItem).filter(RateCardItem.user_id == user_id).count() > 0

    score = _clamp(15 + open_deals * 18 + opportunities * 8 + (20 if has_rate_card else 0))
    if open_deals == 0 and opportunities == 0:
        why = "No active deals or opportunities — monetization has no pipeline."
        action = "Add three opportunities you could realistically pursue this month."
    elif not has_rate_card:
        why = f"{open_deals} open deal(s) but no rate card to price future work with."
        action = "Build a rate card so pricing conversations start from your numbers."
    else:
        why = f"{open_deals} open deal(s) and {opportunities} opportunit(ies) in play."
        action = "Move your best opportunity forward with a concrete next action."

    return {
        "score": score,
        "state": _state(score),
        "why": why,
        "action": action,
        "metrics": {"open_deals": open_deals, "opportunities": opportunities, "rate_card": has_rate_card},
    }


def revenue_health(db: Session, user_id: int) -> dict:
    totals = insights.revenue_totals(db, user_id)
    owed = insights.payments_owed(db, user_id)
    overdue = [o for o in owed if o["severity"] == "overdue"]
    overdue_total = sum(o["amount"] for o in overdue)

    base = 20 + min(totals["this_month"], 100000) / 1000 * 0.6
    base -= len(overdue) * 12
    base += 20 if totals["recurring"] else 0
    score = _clamp(base)

    if totals["this_month"] == 0 and totals["ytd"] == 0:
        why = "No received revenue recorded yet."
        action = "Log your first payment so the money page becomes useful."
    elif overdue:
        why = f"{len(overdue)} payment(s) worth {round(overdue_total)} are past their due date."
        action = "Chase the oldest overdue payment today — it's the fastest money you can win."
    elif owed:
        why = f"{len(owed)} payment(s) worth {round(totals['outstanding'])} are still pending."
        action = "Follow up on pending payments before they age."
    else:
        why = f"{round(totals['this_month'])} received this month with nothing outstanding."
        action = "Keep the streak and raise your rate card prices."

    return {
        "score": score,
        "state": _state(score),
        "why": why,
        "action": action,
        "metrics": {
            "this_month": totals["this_month"],
            "outstanding": totals["outstanding"],
            "overdue_count": len(overdue),
        },
    }


def consistency(db: Session, user_id: int) -> dict:
    data = insights.publishing_consistency(db, user_id)
    score = _clamp(10 + data["active_weeks"] * 11 + min(data["total"], 12) * 2)
    if data["active_weeks"] == 0:
        why = "No publishing activity in the last 8 weeks."
        action = "Pick a realistic weekly cadence and protect it."
    elif data["active_weeks"] < data["total"] * 0.6:
        why = f"You published in {data['active_weeks']} of 8 weeks — the rhythm is broken."
        action = "Aim for at least one publish every week, even a short-form piece."
    else:
        why = f"You published in {data['active_weeks']} of the last 8 weeks."
        action = "Hold this cadence; it is your most valuable business habit."

    return {
        "score": score,
        "state": _state(score),
        "why": why,
        "action": action,
        "metrics": {"active_weeks": data["active_weeks"], "total": data["total"]},
    }


def operations(db: Session, user_id: int) -> dict:
    open_tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.status != TaskStatus.completed)
        .all()
    )
    overdue = [t for t in open_tasks if t.due_date and t.due_date < datetime.now()]
    uncontacted = [
        d
        for d in db.query(BrandDeal)
        .filter(BrandDeal.user_id == user_id, BrandDeal.stage.notin_(["completed", "cancelled"]))
        .all()
        if not d.follow_up_date
    ]

    score = _clamp(85 - len(overdue) * 9 - len(uncontacted) * 6)
    if not open_tasks and not uncontacted:
        why = "No overdue tasks and every open deal has a follow-up scheduled."
        action = "Use the spare capacity to build the next thing."
    elif overdue:
        why = f"{len(overdue)} task(s) are past their due date."
        action = "Clear overdue tasks first — they are the reason nothing else moves."
    else:
        why = f"{len(uncontacted)} open deal(s) have no follow-up date set."
        action = "Set a follow-up date on every open deal."

    return {
        "score": score,
        "state": _state(score),
        "why": why,
        "action": action,
        "metrics": {"overdue_tasks": len(overdue), "deals_without_followup": len(uncontacted)},
    }


SECTIONS = (
    ("content", content_engine),
    ("monetization", monetization_engine),
    ("revenue", revenue_health),
    ("consistency", consistency),
    ("operations", operations),
)


STATE_STYLES = {
    "strong": "good",
    "steady": "ok",
    "needs_attention": "warn",
    "critical": "bad",
}


def business_health(db: Session, user_id: int) -> dict:
    sections = []
    for key, fn in SECTIONS:
        section = fn(db, user_id)
        section["key"] = key
        section["state_style"] = STATE_STYLES.get(section["state"], "ok")
        sections.append(section)

    overall = round(sum(s["score"] for s in sections) / len(sections))
    weakest = min(sections, key=lambda s: s["score"])
    return {
        "overall": overall,
        "label": _state(overall),
        "weakest": weakest,
        "sections": sections,
    }
