"""Aggregates that power Today, Growth and the review engine.

Every function returns plain data plus the reason it matters, so the UI never
has to invent a number or a label.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.content import ContentItem, Status
from app.models.deal import BrandDeal
from app.models.idea import Idea, IdeaStatus
from app.models.opportunity import MonetizationOpportunity
from app.models.pillar import ContentPillar
from app.models.revenue import Revenue, RevenueStatus
from app.models.task import Task, TaskStatus

PUBLISHED = Status.published


def day_bounds(moment: date = None):
    moment = moment or date.today()
    return datetime(moment.year, moment.month, moment.day), datetime(moment.year, moment.month, moment.day) + timedelta(days=1)


def month_bounds(moment: date = None):
    moment = moment or date.today()
    start = datetime(moment.year, moment.month, 1)
    end = datetime(moment.year + (1 if moment.month == 12 else 0), 1 if moment.month == 12 else moment.month + 1, 1)
    return start, end


# --------------------------------------------------------------------------- money

def revenue_totals(db: Session, user_id: int) -> dict:
    now = datetime.now()
    this_start, this_end = month_bounds(now.date())
    last_month_date = (this_start - timedelta(days=1)).date()
    last_start, last_end = month_bounds(last_month_date)
    year_start = datetime(now.year, 1, 1)

    def received(*conditions):
        query = db.query(func.sum(Revenue.amount)).filter(
            Revenue.user_id == user_id, Revenue.status == RevenueStatus.received
        )
        for condition in conditions:
            query = query.filter(condition)
        return query.scalar() or 0

    outstanding = (
        db.query(func.sum(Revenue.amount))
        .filter(
            Revenue.user_id == user_id,
            Revenue.status.in_([RevenueStatus.pending, RevenueStatus.overdue]),
        )
        .scalar()
        or 0
    )
    recurring = (
        db.query(func.sum(Revenue.amount))
        .filter(
            Revenue.user_id == user_id,
            Revenue.status == RevenueStatus.received,
            Revenue.recurring == 1,
        )
        .scalar()
        or 0
    )
    months_with_revenue = db.query(
        func.strftime("%Y-%m", Revenue.date)
    ).filter(Revenue.user_id == user_id, Revenue.status == RevenueStatus.received).distinct().count()

    received_this = received(Revenue.date >= this_start)
    average_month = (received_this if months_with_revenue <= 1 else None)

    return {
        "this_month": received_this,
        "last_month": received(Revenue.date >= last_start, Revenue.date < last_end),
        "ytd": received(Revenue.date >= year_start),
        "outstanding": outstanding,
        "recurring": recurring,
        "average_month": average_month or 0.0,
        "months_tracked": months_with_revenue,
    }


def revenue_by_source(db: Session, user_id: int) -> list:
    rows = (
        db.query(Revenue.source, func.sum(Revenue.amount).label("total"), func.count(Revenue.id))
        .filter(Revenue.user_id == user_id, Revenue.status == RevenueStatus.received)
        .group_by(Revenue.source)
        .all()
    )
    total = sum(row.total or 0 for row in rows) or 1
    return [
        {
            "source": row.source.value if hasattr(row.source, "value") else str(row.source),
            "total": row.total or 0,
            "count": row.count,
            "share": round((row.total or 0) / total * 100),
        }
        for row in sorted(rows, key=lambda r: r.total or 0, reverse=True)
    ]


def payments_owed(db: Session, user_id: int) -> list:
    """Every unpaid obligation, with how many days it has been outstanding."""
    entries = (
        db.query(Revenue)
        .filter(
            Revenue.user_id == user_id,
            Revenue.status.in_([RevenueStatus.pending, RevenueStatus.overdue]),
        )
        .order_by(Revenue.due_date.is_(None), Revenue.due_date, Revenue.date)
        .all()
    )
    today = date.today()
    owed = []
    for entry in entries:
        reference = entry.due_date or entry.date
        days = (today - reference.date()).days if reference else 0
        owed.append(
            {
                "entry": entry,
                "amount": entry.amount or 0,
                "due": reference,
                "days_outstanding": max(days, 0),
                "severity": "overdue" if days > 0 or entry.status == RevenueStatus.overdue else "due_soon",
            }
        )
    return owed


def cashflow_forecast(db: Session, user_id: int) -> dict:
    """Explicitly-labelled projections built only from the creator's own records."""
    outstanding = payments_owed(db, user_id)
    confirmed = (
        db.query(BrandDeal)
        .filter(
            BrandDeal.user_id == user_id,
            BrandDeal.stage.notin_(["cancelled", "declined"]),
            BrandDeal.deal_value > 0,
        )
        .all()
    )
    expected_30 = sum(o["amount"] for o in outstanding if o["days_outstanding"] <= 30)
    expected_60 = sum(o["amount"] for o in outstanding if o["days_outstanding"] <= 60)
    pipeline = sum(d.deal_value or 0 for d in confirmed if d.payment_status != "paid")

    return {
        "outstanding_total": sum(o["amount"] for o in outstanding),
        "expected_30": expected_30,
        "expected_60": expected_60,
        "pipeline_value": pipeline,
        "confirmed_deals": len(confirmed),
        "basis": "Based on your own unpaid revenue entries and open deal values — no bank or external data.",
    }


# --------------------------------------------------------------------------- content

def publishing_consistency(db: Session, user_id: int, weeks: int = 8) -> dict:
    now = datetime.now()
    week_counts = []
    for offset in range(weeks - 1, -1, -1):
        start = (now - timedelta(weeks=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(weeks=1)
        count = (
            db.query(ContentItem)
            .filter(
                ContentItem.user_id == user_id,
                ContentItem.status == PUBLISHED,
                ContentItem.published_at >= start,
                ContentItem.published_at < end,
            )
            .count()
        )
        week_counts.append({"label": start.strftime("%d %b"), "count": count})

    active = [w["count"] for w in week_counts if w["count"] > 0]
    return {
        "weeks": week_counts,
        "total": sum(week_counts[w]["count"] for w in range(weeks)),
        "active_weeks": len(active),
        "average_per_active_week": round(sum(active) / len(active), 1) if active else 0,
        "current_streak": 0,
    }


def pillar_mix(db: Session, user_id: int) -> list:
    pillars = db.query(ContentPillar).filter(ContentPillar.user_id == user_id).all()
    if not pillars:
        return []

    now = datetime.now()
    mix = []
    for pillar in pillars:
        items = (
            db.query(ContentItem)
            .filter(ContentItem.user_id == user_id, ContentItem.pillar_id == pillar.id)
            .all()
        )
        published = [i for i in items if i.status == PUBLISHED and i.published_at]
        in_flight = [i for i in items if i.status != PUBLISHED]
        last_published = max((i.published_at for i in published), default=None)
        mix.append(
            {
                "pillar": pillar,
                "total": len(items),
                "published": len(published),
                "in_flight": len(in_flight),
                "ideas": db.query(Idea)
                .filter(Idea.user_id == user_id, Idea.pillar_id == pillar.id)
                .count(),
                "last_published": last_published,
                "days_since": (now - last_published).days if last_published else None,
            }
        )
    return mix


def pillar_gaps(db: Session, user_id: int, days: int = 30) -> list:
    return [
        row
        for row in pillar_mix(db, user_id)
        if row["days_since"] is None or row["days_since"] > days
    ]


def stuck_content(db: Session, user_id: int, days: int = 14) -> list:
    cutoff = datetime.now() - timedelta(days=days)
    return (
        db.query(ContentItem)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.status.notin_([PUBLISHED, Status.archived]),
            ContentItem.updated_at.isnot(None),
            ContentItem.updated_at < cutoff,
        )
        .all()
    )


def unconverted_ideas(db: Session, user_id: int, limit: int = 5) -> list:
    return (
        db.query(Idea)
        .filter(
            Idea.user_id == user_id,
            Idea.status.in_([IdeaStatus.backlog, IdeaStatus.exploring]),
            Idea.converted_content_id.is_(None),
        )
        .order_by(Idea.potential.desc(), Idea.effort.asc())
        .limit(limit)
        .all()
    )


def revenue_attached_to_content(db: Session, user_id: int) -> dict:
    """Revenue that can be traced back to a deal (and therefore to content)."""
    deals = (
        db.query(BrandDeal)
        .filter(BrandDeal.user_id == user_id, BrandDeal.payment_status == "paid")
        .all()
    )
    by_brand = {d.brand_name: d for d in deals}
    rows = (
        db.query(Revenue)
        .filter(Revenue.user_id == user_id, Revenue.status == RevenueStatus.received)
        .all()
    )
    attached = sum(r.amount or 0 for r in rows if r.description and any(b in r.description for b in by_brand))
    return {"paid_deals": len(deals), "attached_revenue": attached}
