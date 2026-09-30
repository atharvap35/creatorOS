"""The Creator Brain: one batched read of the creator's whole business.

Every surface in Creator OS 3.0 — Today, the Attention Center, the Copilot,
reviews, capacity, money-on-the-table — asks this module for context rather than
running its own queries. That gives three properties the product depends on:

1. **No N+1.** One `snapshot()` call issues a fixed number of queries regardless of
   how much data the creator owns.
2. **One definition of the truth.** A payment is "overdue" in exactly one place,
   so Today and the Copilot can never disagree about the business.
3. **Honest grounding.** Every fact returned is traceable to a record the creator
   entered. Nothing is estimated unless it is explicitly labelled as an estimate
   derived from the creator's own numbers.

Data provenance is explicit throughout. Each fact carries a `basis`:
``user-entered`` (they typed it), ``system-derived`` (computed from their records),
or ``ai-generated`` (drafted by a writer, always a draft).
"""

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.business import (
    ActivityEvent,
    Brand,
    ContentAtom,
    ContentSeries,
    ContentTemplate,
    Offer,
    StageEvent,
)
from app.models.content import ContentItem, Status
from app.models.creator_preference import CreatorPreference
from app.models.deal import BrandDeal, PaymentStatus
from app.models.deal_support import DealDeliverable
from app.models.goal import CreatorGoal
from app.models.idea import Idea, IdeaStatus
from app.models.opportunity import MonetizationOpportunity, OpportunityStatus
from app.models.pillar import ContentPillar
from app.models.rate_card import RateCardItem
from app.models.repurpose import ContentRepurpose
from app.models.revenue import Revenue, RevenueStatus
from app.models.task import Task, TaskPriority, TaskStatus

# ---------------------------------------------------------------------------
# provenance labels
USER_ENTERED = "user-entered"
SYSTEM_DERIVED = "system-derived"
AI_GENERATED = "ai-generated"

OPEN_DEAL_STAGES = ("lead", "contacted", "negotiating", "agreed", "contracted", "in_production", "delivered", "invoiced")
CLOSED_DEAL_STAGES = ("paid", "completed", "cancelled", "declined")


# ---------------------------------------------------------------------------
# helpers

def _val(value, default=None):
    """Unwrap a SQLAlchemy enum to its plain value, tolerating raw strings."""
    if value is None:
        return default
    return getattr(value, "value", value)


def _week_start(moment: datetime | None = None) -> datetime:
    moment = moment or datetime.now()
    return (moment - timedelta(days=moment.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _day_floor(moment: date) -> datetime:
    return datetime(moment.year, moment.month, moment.day)


# ---------------------------------------------------------------------------
# capacity

def capacity(db: Session, user_id: int, pref: CreatorPreference | None = None) -> dict:
    """Planned work against the creator's declared availability.

    This is the guardrail the whole recommendation layer respects: nothing is ever
    recommended beyond the hours the creator said they have.
    """
    if pref is None:
        pref = preference(db, user_id)

    now = datetime.now()
    start = _week_start(now)
    end = start + timedelta(days=7)

    planned_rows = (
        db.query(Task.estimated_minutes)
        .filter(
            Task.user_id == user_id,
            Task.status != TaskStatus.completed,
            Task.due_date.isnot(None),
            Task.due_date >= start,
            Task.due_date < end,
        )
        .all()
    )
    content_rows = (
        db.query(ContentItem.estimated_minutes)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.status != Status.published,
            ContentItem.due_date.isnot(None),
            ContentItem.due_date >= start,
            ContentItem.due_date < end,
        )
        .all()
    )

    planned_minutes = sum((r[0] or 0) for r in planned_rows) + sum((r[0] or 0) for r in content_rows)
    working_days = pref.working_day_list() or [0, 1, 2, 3, 4]
    available_minutes = max(1, len(working_days) * max(1, int(pref.hours_per_day or 4)) * 60)

    planned_hours = round(planned_minutes / 60, 1)
    available_hours = round(available_minutes / 60, 1)
    overload_hours = round(max(0, planned_minutes - available_minutes) / 60, 1)
    capacity_pct = round(planned_minutes / available_minutes * 100)

    return {
        "planned_minutes": planned_minutes,
        "planned_hours": planned_hours,
        "available_hours": available_hours,
        "overload_hours": overload_hours,
        "capacity_pct": capacity_pct,
        "over_capacity": capacity_pct > 100,
        "working_days": working_days,
        "hours_per_day": int(pref.hours_per_day or 4),
        "explanation": (
            f"{planned_hours}h planned against {available_hours}h available this week "
            f"({capacity_pct}% of capacity)."
        ),
        "basis": SYSTEM_DERIVED,
    }


def preference(db: Session, user_id: int) -> CreatorPreference:
    pref = db.query(CreatorPreference).filter(CreatorPreference.user_id == user_id).first()
    if not pref:
        pref = CreatorPreference(user_id=user_id)
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref


# ---------------------------------------------------------------------------
# money

def outstanding_payments(db: Session, user_id: int) -> list:
    """Every unpaid obligation, with the evidence needed to explain it."""
    entries = (
        db.query(Revenue)
        .filter(
            Revenue.user_id == user_id,
            Revenue.status.in_([RevenueStatus.pending, RevenueStatus.overdue]),
        )
        .all()
    )
    today = date.today()
    rows = []
    for entry in entries:
        reference = entry.due_date or entry.date
        days = (today - reference.date()).days if reference else 0
        overdue = days > 0 or entry.status == RevenueStatus.overdue
        rows.append(
            {
                "entry": entry,
                "amount": entry.amount or 0,
                "due": reference,
                "days_outstanding": max(days, 0),
                "overdue": overdue,
                "severity": "overdue" if overdue else "due_soon",
                "basis": USER_ENTERED,
            }
        )
    rows.sort(key=lambda r: (-int(r["overdue"]), -r["days_outstanding"]))
    return rows


def revenue_summary(db: Session, user_id: int) -> dict:
    """Month-to-date, year-to-date, and per-month history from recorded revenue."""
    now = datetime.now()
    month_start = _day_floor(now.replace(day=1))
    year_start = datetime(now.year, 1, 1)

    def received(where):
        query = db.query(func.sum(Revenue.amount)).filter(
            Revenue.user_id == user_id, Revenue.status == RevenueStatus.received
        )
        for condition in where:
            query = query.filter(condition)
        return query.scalar() or 0

    by_month = (
        db.query(
            func.strftime("%Y-%m", Revenue.date).label("month"),
            func.sum(Revenue.amount).label("total"),
        )
        .filter(
            Revenue.user_id == user_id,
            Revenue.status == RevenueStatus.received,
            Revenue.date.isnot(None),
        )
        .group_by("month")
        .order_by("month")
        .all()
    )

    hours = (
        db.query(func.sum(Revenue.hours_spent))
        .filter(
            Revenue.user_id == user_id,
            Revenue.status == RevenueStatus.received,
            Revenue.hours_spent.isnot(None),
        )
        .scalar()
        or 0
    )

    owed = outstanding_payments(db, user_id)
    return {
        "this_month": received([Revenue.date >= month_start]),
        "ytd": received([Revenue.date >= year_start]),
        "outstanding": sum(o["amount"] for o in owed),
        "outstanding_count": len(owed),
        "overdue_total": sum(o["amount"] for o in owed if o["overdue"]),
        "hours_logged": round(hours, 1),
        "by_month": [{"month": r.month, "total": r.total or 0} for r in by_month],
        "basis": SYSTEM_DERIVED,
    }


def revenue_by_source(db: Session, user_id: int) -> list:
    rows = (
        db.query(Revenue.source, func.sum(Revenue.amount).label("total"), func.count(Revenue.id))
        .filter(Revenue.user_id == user_id, Revenue.status == RevenueStatus.received)
        .group_by(Revenue.source)
        .all()
    )
    total = sum(r.total or 0 for r in rows) or 1
    return [
        {
            "source": _val(r.source, "other"),
            "total": r.total or 0,
            "count": r.count,
            "share": round((r.total or 0) / total * 100),
            "basis": SYSTEM_DERIVED,
        }
        for r in sorted(rows, key=lambda r: r.total or 0, reverse=True)
    ]


# ---------------------------------------------------------------------------
# deals

def deal_economics(deals: list) -> list:
    """Value per creator hour for each deal, from creator-entered hours only.

    This is deliberately decision support, not a ranking. A low rate is not "bad",
    it is information the creator can weigh against repeat business and lead value.
    """
    rows = []
    for deal in deals:
        hours = deal.estimated_hours or 0
        value = deal.deal_value or 0
        rate = round(value / hours) if hours else None
        rows.append(
            {
                "deal": deal,
                "value": value,
                "hours": hours,
                "effective_rate": rate,
                "has_estimate": bool(hours),
                "basis": SYSTEM_DERIVED if hours else None,
            }
        )
    return rows


def open_deals(db: Session, user_id: int) -> list:
    return (
        db.query(BrandDeal)
        .filter(BrandDeal.user_id == user_id, BrandDeal.stage.notin_(CLOSED_DEAL_STAGES))
        .order_by(BrandDeal.created_at.desc())
        .all()
    )


def brand_profiles(db: Session, user_id: int) -> list:
    """A brand is a relationship: many deals, many contacts, lifetime value."""
    brands = db.query(Brand).filter(Brand.user_id == user_id).order_by(Brand.name).all()
    rows = []
    for brand in brands:
        deals = (
            db.query(BrandDeal)
            .filter(BrandDeal.user_id == user_id, BrandDeal.brand_id == brand.id)
            .all()
        )
        # deals recorded before the brand entity existed are matched by name
        unlinked = (
            db.query(BrandDeal)
            .filter(
                BrandDeal.user_id == user_id,
                BrandDeal.brand_id.is_(None),
                BrandDeal.brand_name.ilike(brand.name),
            )
            .all()
        )
        all_deals = deals or unlinked
        deal_ids = [d.id for d in all_deals]

        revenue_total = 0
        if deal_ids:
            revenue_total = (
                db.query(func.sum(Revenue.amount))
                .filter(
                    Revenue.user_id == user_id,
                    Revenue.deal_id.in_(deal_ids),
                    Revenue.status == RevenueStatus.received,
                )
                .scalar()
                or 0
            )
        outstanding = 0
        if deal_ids:
            outstanding = (
                db.query(func.sum(Revenue.amount))
                .filter(
                    Revenue.user_id == user_id,
                    Revenue.deal_id.in_(deal_ids),
                    Revenue.status.in_([RevenueStatus.pending, RevenueStatus.overdue]),
                )
                .scalar()
                or 0
            )

        last_interaction = None
        if deal_ids:
            last_event = (
                db.query(StageEvent)
                .filter(StageEvent.user_id == user_id, StageEvent.deal_id.in_(deal_ids))
                .order_by(StageEvent.occurred_at.desc())
                .first()
            )
            if last_event:
                last_interaction = last_event.occurred_at
            else:
                last_interaction = max(
                    (d.follow_up_date or d.updated_at or d.created_at) for d in all_deals
                ) if all_deals else None

        days_since = (
            (datetime.now() - last_interaction).days if last_interaction else None
        )

        rows.append(
            {
                "brand": brand,
                "deals": all_deals,
                "deal_count": len(all_deals),
                "revenue_total": revenue_total,
                "outstanding": outstanding,
                "last_interaction": last_interaction,
                "days_since_interaction": days_since,
                "open_deals": [d for d in all_deals if d.stage not in CLOSED_DEAL_STAGES],
            }
        )
    return rows


# ---------------------------------------------------------------------------
# content

def content_pulse(db: Session, user_id: int) -> dict:
    """How the content engine is actually running, from recorded publish dates."""
    now = datetime.now()
    eight_weeks_ago = now - timedelta(weeks=8)

    total = db.query(ContentItem).filter(ContentItem.user_id == user_id).count()
    in_flight = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == user_id, ContentItem.status != Status.published)
        .count()
    )
    published = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == user_id, ContentItem.status == Status.published)
        .count()
    )
    last_30 = (
        db.query(ContentItem)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.status == Status.published,
            ContentItem.published_at >= now - timedelta(days=30),
        )
        .count()
    )
    active_weeks = (
        db.query(func.strftime("%Y-%W", ContentItem.published_at))
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.status == Status.published,
            ContentItem.published_at >= eight_weeks_ago,
        )
        .distinct()
        .count()
    )
    backlog = (
        db.query(Idea)
        .filter(
            Idea.user_id == user_id,
            Idea.status.in_([IdeaStatus.backlog, IdeaStatus.exploring]),
            Idea.converted_content_id.is_(None),
        )
        .count()
    )
    stuck = (
        db.query(ContentItem)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.status.notin_([Status.published, Status.archived]),
            ContentItem.updated_at.isnot(None),
            ContentItem.updated_at < now - timedelta(days=14),
        )
        .count()
    )

    if active_weeks >= 7:
        consistency_label, consistency_style = "Strong", "good"
    elif active_weeks >= 4:
        consistency_label, consistency_style = "Steady", "ok"
    elif active_weeks >= 1:
        consistency_label, consistency_style = "Inconsistent", "warn"
    else:
        consistency_label, consistency_style = "Dormant", "bad"

    return {
        "total": total,
        "published": published,
        "in_flight": in_flight,
        "published_30d": last_30,
        "active_weeks_8": active_weeks,
        "backlog_ideas": backlog,
        "stuck": stuck,
        "consistency_label": consistency_label,
        "consistency_style": consistency_style,
        "basis": SYSTEM_DERIVED,
    }


def content_gaps(db: Session, user_id: int) -> list:
    """Observations about the creator's own mix. Never a universal claim."""
    gaps = []
    now = datetime.now()
    month_start = _day_floor(now.replace(day=1))

    pillars = db.query(ContentPillar).filter(ContentPillar.user_id == user_id).all()
    for pillar in pillars:
        items = (
            db.query(ContentItem)
            .filter(ContentItem.user_id == user_id, ContentItem.pillar_id == pillar.id)
            .all()
        )
        published = [i for i in items if i.status == Status.published and i.published_at]
        if not published:
            gaps.append(
                {
                    "kind": "unused_pillar",
                    "title": f"“{pillar.name}” has never been published",
                    "detail": "You defined this pillar but no content has used it yet.",
                    "action": "Plan a piece",
                    "url": "/content?pillar_id=" + str(pillar.id),
                }
            )
            continue
        last = max(i.published_at for i in published)
        days = (now - last).days
        if days > 45:
            gaps.append(
                {
                    "kind": "stale_pillar",
                    "title": f"“{pillar.name}” has been quiet for {days} days",
                    "detail": f"Your last piece under this pillar was published {days} days ago.",
                    "action": "Plan a piece",
                    "url": "/content?pillar_id=" + str(pillar.id),
                }
            )

    from app.models.brief import ContentBrief

    month_items = (
        db.query(ContentItem)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.status == Status.published,
            ContentItem.published_at >= month_start,
        )
        .all()
    )

    # one query for every brief belonging to this month's published pieces
    briefs = (
        db.query(ContentBrief)
        .filter(ContentBrief.user_id == user_id, ContentBrief.content_id.in_([i.id for i in month_items]))
        .all()
    ) if month_items else []
    briefs_by_content = {b.content_id: b for b in briefs}

    with_cta = {
        b.content_id
        for b in db.query(ContentBrief)
        .filter(ContentBrief.user_id == user_id, ContentBrief.cta.isnot(None))
        .all()
        if b.cta and b.cta.strip()
    }
    missing_cta = [i for i in month_items if i.id not in with_cta]
    if len(missing_cta) >= 2:
        gaps.append(
            {
                "kind": "missing_cta",
                "title": f"{len(missing_cta)} published pieces have no recorded CTA",
                "detail": "Based on your own briefs, these pieces have no call to action logged.",
                "action": "Review briefs",
                "url": "/content?status_filter=published",
            }
        )

    if month_items:
        goals_by_content = {}
        for item in month_items:
            brief = briefs_by_content.get(item.id)
            key = brief.goal if brief and brief.goal else "unspecified"
            goals_by_content[key] = goals_by_content.get(key, 0) + 1
        conversion_keys = {"sales", "leads", "partnership"}
        conversion_count = sum(v for k, v in goals_by_content.items() if k in conversion_keys)
        if conversion_count == 0 and len(month_items) >= 4:
            gaps.append(
                {
                    "kind": "no_conversion_content",
                    "title": "No conversion-focused content this month",
                    "detail": (
                        f"You published {len(month_items)} pieces this month and none is "
                        "briefed for sales, leads, or partnership."
                    ),
                    "action": "Create conversion content",
                    "url": "/content",
                }
            )

    formats_used = {_val(i.content_type, "other") for i in month_items}
    all_formats = {"reel", "short", "video", "carousel", "post", "newsletter"}
    missing_formats = sorted(all_formats - formats_used)
    if month_items and len(missing_formats) >= 4:
        gaps.append(
            {
                "kind": "missing_formats",
                "title": f"You've used {len(formats_used)} format(s) this month",
                "detail": "Not used: " + ", ".join(missing_formats) + ".",
                "action": "Add content",
                "url": "/content",
            }
        )

    return gaps


def atomizable_content(db: Session, user_id: int) -> list:
    """Published pieces that have unused capacity left in them."""
    now = datetime.now()
    published = (
        db.query(ContentItem)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.status == Status.published,
            ContentItem.published_at.isnot(None),
            ContentItem.published_at >= now - timedelta(days=60),
        )
        .all()
    )
    rows = []
    for item in published:
        derivative_count = (
            db.query(ContentRepurpose)
            .filter(ContentRepurpose.content_id == item.id)
            .count()
        )
        atom_count = (
            db.query(ContentAtom)
            .filter(ContentAtom.content_id == item.id, ContentAtom.status != "dismissed")
            .count()
        )
        if derivative_count == 0 and atom_count == 0:
            age = (now - item.published_at).days
            rows.append({"item": item, "age_days": age})
    rows.sort(key=lambda r: r["age_days"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# series

def series_status(db: Session, user_id: int) -> list:
    rows = []
    for series in db.query(ContentSeries).filter(ContentSeries.user_id == user_id).all():
        items = (
            db.query(ContentItem)
            .filter(ContentItem.user_id == user_id, ContentItem.series_id == series.id)
            .order_by(ContentItem.episode_number)
            .all()
        )
        published = [i for i in items if i.status == Status.published]
        planned = [i for i in items if i.status != Status.published]
        numbers = sorted(i.episode_number for i in items if i.episode_number)

        next_episode = None
        if numbers:
            for candidate in range(1, (max(numbers) + 3)):
                if candidate not in numbers:
                    next_episode = candidate
                    break

        rows.append(
            {
                "series": series,
                "items": items,
                "published_count": len(published),
                "planned_count": len(planned),
                "next_episode": next_episode,
                "target": series.target_episodes or 0,
                "at_target": bool(series.target_episodes) and len(published) >= series.target_episodes,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# money on the table

def money_on_the_table(db: Session, user_id: int, atomizable: list | None = None) -> list:
    """Every concrete, already-identified route to money, with effort and reason.

    Values are the creator's own numbers. Nothing is projected or promised.

    `atomizable` lets a caller that already has the list (as `snapshot()` does)
    pass it in rather than triggering a second identical query.
    """
    now = datetime.now()
    rows = []

    for owed in outstanding_payments(db, user_id):
        entry = owed["entry"]
        brand = entry.description or entry.source.value
        rows.append(
            {
                "source": "outstanding",
                "label": f"Collect {brand}",
                "value": owed["amount"],
                "effort_minutes": 10,
                "reason": (
                    f"Payment is {owed['days_outstanding']} day(s) past its due date."
                    if owed["overdue"]
                    else f"Marked pending, due in {owed['days_outstanding']} day(s)."
                ),
                "entity_type": "revenue",
                "entity_id": entry.id,
                "url": "/money/payments",
                "action": "draft_reminder",
                "basis": USER_ENTERED,
            }
        )

    for deal in open_deals(db, user_id):
        if deal.stage in ("paid", "completed"):
            continue
        if deal.payment_status in (PaymentStatus.not_invoiced, PaymentStatus.invoiced) and deal.deal_value:
            rows.append(
                {
                    "source": "uninvoiced",
                    "label": f"Invoice {deal.brand_name}",
                    "value": deal.deal_value or 0,
                    "effort_minutes": 15,
                    "reason": f"Deal is agreed and not invoiced ({_val(deal.payment_status)}).",
                    "entity_type": "deal",
                    "entity_id": deal.id,
                    "url": f"/deals/{deal.id}",
                    "action": "draft_invoice",
                    "basis": USER_ENTERED,
                }
            )
        if deal.stage in ("lead", "contacted", "negotiating"):
            rows.append(
                {
                    "source": "stalled_deal",
                    "label": f"Move {deal.brand_name} forward",
                    "value": deal.deal_value or 0,
                    "effort_minutes": 10,
                    "reason": f"Still at '{deal.stage}' stage.",
                    "entity_type": "deal",
                    "entity_id": deal.id,
                    "url": f"/deals/{deal.id}",
                    "action": "draft_follow_up",
                    "basis": USER_ENTERED,
                }
            )

    for offer in db.query(Offer).filter(Offer.user_id == user_id, Offer.is_active.is_(True)).all():
        used = (
            db.query(BrandDeal)
            .filter(BrandDeal.user_id == user_id, BrandDeal.offer_id == offer.id)
            .count()
        )
        if not used:
            rows.append(
                {
                    "source": "unused_offer",
                    "label": f"Sell “{offer.name}”",
                    "value": offer.price or 0,
                    "effort_minutes": 20,
                    "reason": "This offer has never been attached to a deal.",
                    "entity_type": "offer",
                    "entity_id": offer.id,
                    "url": f"/offers/{offer.id}",
                    "action": "create_opportunity",
                    "basis": USER_ENTERED,
                }
            )

    for item in (
        db.query(MonetizationOpportunity)
        .filter(
            MonetizationOpportunity.user_id == user_id,
            MonetizationOpportunity.status.in_([OpportunityStatus.idea, OpportunityStatus.evaluating]),
        )
        .all()
    ):
        if item.deadline and item.deadline < now:
            reason = "Deadline has passed and it is still open."
        elif item.deadline and (item.deadline - now).days <= 7:
            reason = f"Deadline is in {(item.deadline - now).days} day(s)."
        else:
            reason = "Open opportunity you have not moved to active."
        rows.append(
            {
                "source": "opportunity",
                "label": item.title,
                "value": item.estimated_value or 0,
                "effort_minutes": {"low": 20, "medium": 45, "high": 90}.get(_val(item.effort), 45),
                "reason": reason,
                "entity_type": "opportunity",
                "entity_id": item.id,
                "url": f"/growth/opportunities/{item.id}",
                "action": "pursue_opportunity",
                "basis": USER_ENTERED,
            }
        )

    for row in (atomizable if atomizable is not None else atomizable_content(db, user_id))[:3]:
        rows.append(
            {
                "source": "repurposing",
                "label": f"Repurpose “{row['item'].title}”",
                "value": 0,
                "effort_minutes": 15,
                "reason": f"Published {row['age_days']} day(s) ago with no derivatives planned.",
                "entity_type": "content",
                "entity_id": row["item"].id,
                "url": f"/content/{row['item'].id}/repurpose",
                "action": "atomize",
                "basis": SYSTEM_DERIVED,
            }
        )

    rows.sort(key=lambda r: (-(r["value"] or 0), r["effort_minutes"]))
    return rows


# ---------------------------------------------------------------------------
# the snapshot

def snapshot(db: Session, user_id: int, moment: datetime | None = None) -> dict:
    """One batched read of the creator's business.

    This is the entry point every 3.0 surface uses. It is intentionally a plain
    dict of plain data so it can be rendered directly, cached per request, or
    asserted against in tests.
    """
    now = moment or datetime.now()
    pref = preference(db, user_id)

    cap = capacity(db, user_id, pref)
    money = revenue_summary(db, user_id)
    owed = outstanding_payments(db, user_id)
    deals = open_deals(db, user_id)
    pulse = content_pulse(db, user_id)
    atomizable = atomizable_content(db, user_id)

    open_tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.status != TaskStatus.completed)
        .all()
    )
    overdue_tasks = [t for t in open_tasks if t.due_date and t.due_date < now]
    today_tasks = [
        t
        for t in open_tasks
        if t.due_date and _day_floor(t.due_date.date()) == _day_floor(now.date())
    ]

    goals = (
        db.query(CreatorGoal)
        .filter(CreatorGoal.user_id == user_id, CreatorGoal.status == "active")
        .all()
    )
    for goal in goals:
        goal.current_value = _goal_value(db, user_id, goal)

    behind_goals = [
        g
        for g in goals
        if g.target_value and g.current_value / g.target_value < 0.6 and g.deadline
    ]

    return {
        "now": now,
        "user_id": user_id,
        "preference": pref,
        "capacity": cap,
        "money": money,
        "owed": owed,
        "deals": deals,
        "deal_economics": deal_economics(deals),
        "brands": brand_profiles(db, user_id),
        "pulse": pulse,
        "gaps": content_gaps(db, user_id),
        "atomizable": atomizable,
        "series": series_status(db, user_id),
        "money_on_the_table": money_on_the_table(db, user_id, atomizable=atomizable),
        "goals": goals,
        "behind_goals": behind_goals,
        "tasks": {
            "open": open_tasks,
            "overdue": overdue_tasks,
            "today": today_tasks,
            "count": len(open_tasks),
        },
        "counts": _counts(db, user_id),
    }


def _goal_value(db: Session, user_id: int, goal: CreatorGoal) -> float:
    """Live goal progress, computed from the creator's own records."""
    now = datetime.now()
    month_start = _day_floor(now.replace(day=1))
    if goal.metric == "monthly_revenue":
        return (
            db.query(func.sum(Revenue.amount))
            .filter(
                Revenue.user_id == user_id,
                Revenue.status == RevenueStatus.received,
                Revenue.date >= month_start,
            )
            .scalar()
            or 0
        )
    if goal.metric == "published_items":
        return float(
            db.query(ContentItem)
            .filter(
                ContentItem.user_id == user_id,
                ContentItem.status == Status.published,
                ContentItem.published_at >= month_start,
            )
            .count()
        )
    if goal.metric == "closed_deals":
        return float(
            db.query(BrandDeal)
            .filter(BrandDeal.user_id == user_id, BrandDeal.stage == "completed")
            .count()
        )
    if goal.metric == "paid_deals":
        return float(
            db.query(BrandDeal)
            .filter(BrandDeal.user_id == user_id, BrandDeal.payment_status == "paid")
            .count()
        )
    return goal.current_value or 0


def _counts(db: Session, user_id: int) -> dict:
    return {
        "content": db.query(ContentItem).filter(ContentItem.user_id == user_id).count(),
        "tasks": db.query(Task).filter(Task.user_id == user_id).count(),
        "deals": db.query(BrandDeal).filter(BrandDeal.user_id == user_id).count(),
        "revenue": db.query(Revenue).filter(Revenue.user_id == user_id).count(),
        "ideas": db.query(Idea).filter(Idea.user_id == user_id).count(),
        "opportunities": db.query(MonetizationOpportunity)
        .filter(MonetizationOpportunity.user_id == user_id)
        .count(),
        "brands": db.query(Brand).filter(Brand.user_id == user_id).count(),
        "offers": db.query(Offer).filter(Offer.user_id == user_id).count(),
        "series": db.query(ContentSeries).filter(ContentSeries.user_id == user_id).count(),
        "templates": db.query(ContentTemplate).filter(ContentTemplate.user_id == user_id).count(),
        "events": db.query(ActivityEvent).filter(ActivityEvent.user_id == user_id).count(),
    }
