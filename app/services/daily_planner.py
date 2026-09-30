from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.content import ContentItem, Status
from app.models.deal import BrandDeal, DealStatus
from app.models.opportunity import MonetizationOpportunity, OpportunityStatus
from app.models.task import Task, TaskCategory, TaskPriority, TaskStatus

PRIORITY_WEIGHTS = {
    TaskPriority.urgent: 25,
    TaskPriority.high: 15,
    TaskPriority.medium: 5,
    TaskPriority.low: 0,
}

CATEGORY_WEIGHTS = {
    TaskCategory.monetization: 20,
    TaskCategory.business: 12,
    TaskCategory.content: 10,
    TaskCategory.audience: 6,
    TaskCategory.admin: 2,
}


def _urgency_score(due_date: Optional[datetime]) -> tuple:
    if due_date is None:
        return 0, "No deadline set yet."
    now = datetime.now()
    if due_date < now:
        return 50, "This task is overdue."
    if due_date.date() == now.date():
        return 45, "This task is due today."
    if (due_date - now).days <= 2:
        return 30, "Due in the next couple of days."
    if (due_date - now).days <= 7:
        return 15, "Due this week."
    return 5, "Scheduled ahead."


def generate_daily_plan(db: Session, user_id: int, limit: int = 7) -> list:
    recommendations = []
    now = datetime.now()

    tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.status != TaskStatus.completed)
        .all()
    )
    for item in tasks:
        score, reason = _urgency_score(item.due_date)
        score += CATEGORY_WEIGHTS.get(item.category, 0)
        score += PRIORITY_WEIGHTS.get(item.priority, 0)
        if item.category == TaskCategory.monetization:
            reason = "This moves money in your business."
        recommendations.append(
            {
                "rank": 0,
                "title": item.title,
                "category": item.category,
                "reason": reason,
                "priority_score": score,
                "estimated_minutes": item.estimated_minutes,
                "entity_type": "task",
                "entity_id": item.id,
            }
        )

    content_items = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == user_id, ContentItem.status != Status.published)
        .all()
    )
    for item in content_items:
        score, reason = _urgency_score(item.due_date)
        if item.status in (Status.ready, Status.editing):
            score += 20
            reason = "This is close to shipping."
        recommendations.append(
            {
                "rank": 0,
                "title": item.title,
                "category": item.content_type,
                "reason": reason,
                "priority_score": score,
                "estimated_minutes": item.estimated_minutes,
                "entity_type": "content",
                "entity_id": item.id,
            }
        )

    deals = (
        db.query(BrandDeal)
        .filter(
            BrandDeal.user_id == user_id,
            BrandDeal.status.notin_([DealStatus.completed, DealStatus.cancelled]),
        )
        .all()
    )
    for item in deals:
        score, reason = _urgency_score(item.deadline)
        if item.payment_status == "overdue":
            score += 35
            reason = "Payment for this deal is overdue."
        elif item.payment_status == "pending":
            score += 20
            reason = "Waiting on payment for this deal."
        recommendations.append(
            {
                "rank": 0,
                "title": f"{item.brand_name} — {item.campaign_name}",
                "category": "sponsorship",
                "reason": reason,
                "priority_score": score,
                "estimated_minutes": None,
                "entity_type": "deal",
                "entity_id": item.id,
            }
        )

    opportunities = (
        db.query(MonetizationOpportunity)
        .filter(
            MonetizationOpportunity.user_id == user_id,
            MonetizationOpportunity.status.in_(
                [OpportunityStatus.idea, OpportunityStatus.evaluating]
            ),
        )
        .all()
    )
    for item in opportunities:
        recommendations.append(
            {
                "rank": 0,
                "title": item.title,
                "category": item.type,
                "reason": item.next_action or "Evaluate this opportunity.",
                "priority_score": 18,
                "estimated_minutes": None,
                "entity_type": "opportunity",
                "entity_id": item.id,
            }
        )

    recommendations.sort(key=lambda rec: rec["priority_score"], reverse=True)
    top = recommendations[:limit]
    for index, rec in enumerate(top, start=1):
        rec["rank"] = index
    return top
