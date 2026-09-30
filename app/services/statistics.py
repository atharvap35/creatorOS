from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.content import ContentItem, Status
from app.models.deal import BrandDeal, DealStatus, PaymentStatus
from app.models.idea import Idea
from app.models.opportunity import MonetizationOpportunity, OpportunityStatus
from app.models.revenue import Revenue, RevenueStatus
from app.models.task import Task, TaskStatus
from datetime import datetime, timedelta


def _start_of_month() -> datetime:
    now = datetime.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def get_content_summary(db: Session, user_id: int) -> dict:
    base = db.query(ContentItem).filter(ContentItem.user_id == user_id)
    return {
        "total": base.count(),
        "in_progress": base.filter(
            ContentItem.status.in_([Status.scripting, Status.filming, Status.editing])
        ).count(),
        "ready": base.filter(ContentItem.status == Status.ready).count(),
        "published": base.filter(ContentItem.status == Status.published).count(),
        "overdue": base.filter(
            ContentItem.due_date.isnot(None),
            ContentItem.due_date < datetime.now(),
            ContentItem.status != Status.published,
        ).count(),
    }


def get_task_summary(db: Session, user_id: int) -> dict:
    base = db.query(Task).filter(Task.user_id == user_id)
    return {
        "total": base.count(),
        "todo": base.filter(Task.status == TaskStatus.todo).count(),
        "in_progress": base.filter(Task.status == TaskStatus.in_progress).count(),
        "completed": base.filter(Task.status == TaskStatus.completed).count(),
        "overdue": base.filter(
            Task.due_date.isnot(None),
            Task.due_date < datetime.now(),
            Task.status != TaskStatus.completed,
        ).count(),
    }


def get_deal_summary(db: Session, user_id: int) -> dict:
    base = db.query(BrandDeal).filter(BrandDeal.user_id == user_id)
    now = datetime.now()
    return {
        "total": base.count(),
        "active": base.filter(BrandDeal.status == DealStatus.active).count(),
        "unpaid": base.filter(
            BrandDeal.payment_status.in_(
                [PaymentStatus.invoiced, PaymentStatus.pending, PaymentStatus.overdue]
            )
        ).count(),
        "outstanding_value": base.filter(
            BrandDeal.payment_status != PaymentStatus.paid
        ).with_entities(func.sum(BrandDeal.deal_value)).scalar() or 0,
        "deadlines_this_week": base.filter(
            BrandDeal.deadline.isnot(None),
            BrandDeal.deadline >= now,
            BrandDeal.deadline <= now + timedelta(days=7),
        ).count(),
    }


def get_revenue_summary(db: Session, user_id: int) -> dict:
    base = db.query(Revenue).filter(Revenue.user_id == user_id)

    def total_for(status):
        return base.filter(Revenue.status == status).with_entities(
            func.sum(Revenue.amount)
        ).scalar() or 0

    return {
        "received": total_for(RevenueStatus.received),
        "pending": total_for(RevenueStatus.pending),
        "overdue": total_for(RevenueStatus.overdue),
    }


def get_opportunity_summary(db: Session, user_id: int) -> dict:
    base = db.query(MonetizationOpportunity).filter(
        MonetizationOpportunity.user_id == user_id
    )
    return {
        "total": base.count(),
        "active": base.filter(
            MonetizationOpportunity.status == OpportunityStatus.active
        ).count(),
        "pipeline_value": base.with_entities(
            func.sum(MonetizationOpportunity.estimated_value)
        ).scalar() or 0,
    }


def get_idea_summary(db: Session, user_id: int) -> dict:
    base = db.query(Idea).filter(Idea.user_id == user_id)
    return {"total": base.count(), "high_potential": base.filter(Idea.potential == "high").count()}


def get_monthly_revenue(db: Session, user_id: int) -> float:
    return (
        db.query(Revenue)
        .filter(
            Revenue.user_id == user_id,
            Revenue.status == RevenueStatus.received,
            Revenue.date >= _start_of_month(),
        )
        .with_entities(func.sum(Revenue.amount))
        .scalar()
        or 0
    )


def get_revenue_trend(db: Session, user_id: int, months: int = 6) -> list:
    """Monthly received revenue for the last N months, oldest first."""
    now = datetime.now()
    buckets = []
    for offset in range(months - 1, -1, -1):
        year = now.year
        month = now.month - offset
        while month <= 0:
            month += 12
            year -= 1
        start = datetime(year, month, 1)
        end = datetime(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
        value = (
            db.query(Revenue)
            .filter(
                Revenue.user_id == user_id,
                Revenue.status == RevenueStatus.received,
                Revenue.date >= start,
                Revenue.date < end,
            )
            .with_entities(func.sum(Revenue.amount))
            .scalar()
            or 0
        )
        buckets.append({"label": start.strftime("%b"), "value": value})
    return buckets


def get_pending_payments(db: Session, user_id: int) -> list:
    return (
        db.query(Revenue)
        .filter(Revenue.user_id == user_id, Revenue.status == RevenueStatus.pending)
        .order_by(Revenue.date.desc())
        .all()
    )


def get_overdue_items(db: Session, user_id: int) -> dict:
    now = datetime.now()
    return {
        "content": (
            db.query(ContentItem)
            .filter(
                ContentItem.user_id == user_id,
                ContentItem.due_date.isnot(None),
                ContentItem.due_date < now,
                ContentItem.status != Status.published,
            )
            .all()
        ),
        "tasks": (
            db.query(Task)
            .filter(
                Task.user_id == user_id,
                Task.due_date.isnot(None),
                Task.due_date < now,
                Task.status != TaskStatus.completed,
            )
            .all()
        ),
    }


def get_dashboard_snapshot(db: Session, user_id: int) -> dict:
    return {
        "content_stats": get_content_summary(db, user_id),
        "task_stats": get_task_summary(db, user_id),
        "deal_stats": get_deal_summary(db, user_id),
        "revenue_stats": get_revenue_summary(db, user_id),
        "opportunity_stats": get_opportunity_summary(db, user_id),
        "idea_stats": get_idea_summary(db, user_id),
        "monthly_rev": get_monthly_revenue(db, user_id),
        "revenue_trend": get_revenue_trend(db, user_id),
    }
