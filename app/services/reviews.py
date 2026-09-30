"""Weekly and monthly creator reviews, generated from real records only."""

import json
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.content import ContentItem, Status
from app.models.deal import BrandDeal
from app.models.idea import Idea
from app.models.revenue import Revenue, RevenueStatus
from app.models.recommendation import Recommendation
from app.models.workspace import ReviewSnapshot
from app.models.task import Task, TaskStatus
from app.services import insights, recommender


def _week_bounds(moment: date):
    start = moment - timedelta(days=moment.weekday())
    return start, start + timedelta(days=6)


def _month_bounds(moment: date):
    start = moment.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return start, end


def build_weekly(db: Session, user_id: int, moment: date = None) -> dict:
    moment = moment or date.today()
    start, end = _week_bounds(moment)
    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day) + timedelta(days=1)

    completed_tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.status == TaskStatus.completed,
            Task.completed_at.isnot(None),
            Task.completed_at >= start_dt,
            Task.completed_at < end_dt,
        )
        .count()
    )
    created_ideas = db.query(Idea).filter(Idea.user_id == user_id, Idea.created_at >= start_dt, Idea.created_at < end_dt).count()
    published = (
        db.query(ContentItem)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.status == Status.published,
            ContentItem.published_at >= start_dt,
            ContentItem.published_at < end_dt,
        )
        .count()
    )
    progressed_deals = (
        db.query(BrandDeal)
        .filter(BrandDeal.user_id == user_id, BrandDeal.updated_at >= start_dt, BrandDeal.updated_at < end_dt)
        .count()
    )
    revenue_rows = (
        db.query(Revenue)
        .filter(Revenue.user_id == user_id, Revenue.date >= start_dt, Revenue.date < end_dt)
        .all()
    )
    received = sum(r.amount or 0 for r in revenue_rows if r.status == RevenueStatus.received)
    collected = sum(r.amount or 0 for r in revenue_rows if r.status == RevenueStatus.received and r.recurring)

    overdue_tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.status != TaskStatus.completed,
            Task.due_date.isnot(None),
            Task.due_date < datetime.now(),
        )
        .count()
    )
    stalled_deals = [
        d
        for d in db.query(BrandDeal)
        .filter(BrandDeal.user_id == user_id, BrandDeal.stage.notin_(["completed", "cancelled"]))
        .all()
        if not d.follow_up_date
    ]
    unused_ideas = insights.unconverted_ideas(db, user_id, limit=5)
    workload = recommender.weekly_workload(db, user_id)

    pillars = [row for row in insights.pillar_mix(db, user_id) if row["published"]]
    top_pillar = max(pillars, key=lambda r: r["published"]) if pillars else None

    worked = []
    if published:
        worked.append(f"Published {published} piece(s) this week.")
    if completed_tasks:
        worked.append(f"Completed {completed_tasks} task(s).")
    if received:
        worked.append(f"Received {round(received)} in revenue.")
    if top_pillar:
        worked.append(f"'{top_pillar['pillar'].name}' is your most active pillar with {top_pillar['published']} published piece(s).")
    if not worked:
        worked.append("Nothing was recorded as completed this week — that is the signal, not a failure.")

    didnt = []
    if overdue_tasks:
        didnt.append(f"{overdue_tasks} overdue task(s) are still open.")
    if stalled_deals:
        didnt.append(f"{len(stalled_deals)} open deal(s) have no follow-up date.")
    if unused_ideas:
        didnt.append(f"{len(unused_ideas)} idea(s) are still unconverted.")
    if workload["over_capacity"]:
        didnt.append(workload["explanation"])
    if not didnt:
        didnt.append("Nothing is slipping. Keep the current rhythm.")

    actions = [
        {
            "title": c["title"],
            "reason": c["reason"],
            "effort_minutes": c["effort_minutes"],
            "url": c["url"],
            "cta": c["cta"],
        }
        for c in recommender.generate(db, user_id, limit=5)
    ]

    return {
        "period_type": "weekly",
        "period_start": start,
        "period_end": end,
        "happened": {
            "tasks_completed": completed_tasks,
            "content_published": published,
            "ideas_created": created_ideas,
            "deals_progressed": progressed_deals,
            "revenue_received": received,
            "recurring_collected": collected,
        },
        "worked": worked,
        "didnt": didnt,
        "next_actions": actions,
    }


def build_monthly(db: Session, user_id: int, moment: date = None) -> dict:
    moment = moment or date.today()
    start, end = _month_bounds(moment)
    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day) + timedelta(days=1)
    prev_start = (start - timedelta(days=1)).replace(day=1)
    prev_end = (start - timedelta(days=1))

    def totals(from_dt, to_dt):
        received = (
            db.query(func.sum(Revenue.amount))
            .filter(
                Revenue.user_id == user_id,
                Revenue.status == RevenueStatus.received,
                Revenue.date >= from_dt,
                Revenue.date < to_dt,
            )
            .scalar()
            or 0
        )
        published = (
            db.query(ContentItem)
            .filter(
                ContentItem.user_id == user_id,
                ContentItem.status == Status.published,
                ContentItem.published_at >= from_dt,
                ContentItem.published_at < to_dt,
            )
            .count()
        )
        return received, published

    received, published = totals(start_dt, end_dt)
    prev_received, prev_published = totals(
        datetime(prev_start.year, prev_start.month, prev_start.day),
        datetime(prev_end.year, prev_end.month, prev_end.day) + timedelta(days=1),
    )

    new_deals = db.query(BrandDeal).filter(BrandDeal.user_id == user_id, BrandDeal.created_at >= start_dt, BrandDeal.created_at < end_dt).count()
    completed_deals = db.query(BrandDeal).filter(BrandDeal.user_id == user_id, BrandDeal.stage == "completed", BrandDeal.completed_at >= start_dt, BrandDeal.completed_at < end_dt).count()
    paid_deals = db.query(BrandDeal).filter(BrandDeal.user_id == user_id, BrandDeal.payment_status == "paid", BrandDeal.updated_at >= start_dt, BrandDeal.updated_at < end_dt).count()
    owed = insights.payments_owed(db, user_id)
    upcoming = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == user_id, ContentItem.status != Status.published, ContentItem.due_date >= end_dt)
        .order_by(ContentItem.due_date)
        .limit(6)
        .all()
    )

    def change(current, previous):
        if not previous:
            return None
        return round((current - previous) / previous * 100)

    return {
        "period_type": "monthly",
        "period_start": start,
        "period_end": end,
        "summary": {
            "revenue": received,
            "revenue_change": change(received, prev_received),
            "published": published,
            "published_change": change(published, prev_published),
            "new_deals": new_deals,
            "deals_completed": completed_deals,
            "deals_paid": paid_deals,
            "outstanding": sum(o["amount"] for o in owed),
            "outstanding_count": len(owed),
        },
        "previous": {"revenue": prev_received, "published": prev_published},
        "sources": insights.revenue_by_source(db, user_id),
        "upcoming": upcoming,
        "next_actions": [
            {"title": c["title"], "reason": c["reason"], "effort_minutes": c["effort_minutes"], "url": c["url"], "cta": c["cta"]}
            for c in recommender.generate(db, user_id, limit=5)
        ],
    }


def save_snapshot(db: Session, user_id: int, payload: dict) -> ReviewSnapshot:
    serialised = json.dumps(
        {
            key: (value.isoformat() if isinstance(value, (date, datetime)) else value)
            for key, value in payload.items()
            if not isinstance(value, (date, datetime))
        },
        default=str,
    )
    existing = (
        db.query(ReviewSnapshot)
        .filter(
            ReviewSnapshot.user_id == user_id,
            ReviewSnapshot.period_type == payload["period_type"],
            ReviewSnapshot.period_start == payload["period_start"],
        )
        .first()
    )
    if existing:
        existing.payload = serialised
        snapshot = existing
    else:
        snapshot = ReviewSnapshot(
            user_id=user_id,
            period_type=payload["period_type"],
            period_start=payload["period_start"],
            period_end=payload["period_end"],
            payload=serialised,
        )
        db.add(snapshot)
    db.commit()
    return snapshot


def start_next_week(db: Session, user_id: int, actions: list) -> int:
    """Turn review recommendations into real work items."""
    created = 0
    for action in actions:
        if not action.get("title"):
            continue
        db.add(
            Task(
                user_id=user_id,
                title=action["title"],
                description=action.get("reason"),
                estimated_minutes=action.get("effort_minutes") or 20,
                source="weekly_review",
            )
        )
        created += 1
    db.commit()
    return created

# ---------------------------------------------------------------------------
# CEO review layer

# These build on build_weekly/build_monthly rather than replacing them: the
# numbers stay identical, and the extra sections are derived from the same
# records so the review can never disagree with the dashboard.


def _decisions_in_period(db: Session, user_id: int, start: date, end: date) -> list:
    """Real decisions: money received and deals that moved.

    A "decision" is only listed if a record proves it happened — a payment was
    marked received, or a deal changed stage. Nothing is inferred.
    """
    from app.models.business import StageEvent

    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day) + timedelta(days=1)

    decisions = []

    for entry in (
        db.query(Revenue)
        .filter(
            Revenue.user_id == user_id,
            Revenue.status == RevenueStatus.received,
            Revenue.received_at.isnot(None),
            Revenue.received_at >= start_dt,
            Revenue.received_at < end_dt,
        )
        .all()
    ):
        decisions.append(
            {
                "kind": "revenue",
                "title": f"Received {entry.currency} {round(entry.amount or 0):,} from {entry.description or entry.source.value}",
                "when": entry.received_at,
                "amount": entry.amount or 0,
            }
        )

    for event in (
        db.query(StageEvent)
        .filter(
            StageEvent.user_id == user_id,
            StageEvent.occurred_at >= start_dt,
            StageEvent.occurred_at < end_dt,
        )
        .order_by(StageEvent.occurred_at.desc())
        .all()
    ):
        decisions.append(
            {
                "kind": "deal",
                "title": event.summary or "Deal changed",
                "when": event.occurred_at,
                "amount": None,
            }
        )

    decisions.sort(key=lambda d: d["when"], reverse=True)
    return decisions


def _slipped(db: Session, user_id: int, moment: date) -> list:
    """Things that were due in the period and did not happen."""
    start, end = _week_bounds(moment)
    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day) + timedelta(days=1)

    missed_tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.due_date.isnot(None),
            Task.due_date >= start_dt,
            Task.due_date < end_dt,
            Task.status != TaskStatus.completed,
        )
        .all()
    )
    missed_content = (
        db.query(ContentItem)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.due_date.isnot(None),
            ContentItem.due_date >= start_dt,
            ContentItem.due_date < end_dt,
            ContentItem.status != Status.published,
        )
        .all()
    )
    return [
        {"kind": "task", "title": t.title, "due": t.due_date} for t in missed_tasks
    ] + [
        {"kind": "content", "title": c.title, "due": c.due_date} for c in missed_content
    ]


def build_weekly_ceo(db: Session, user_id: int, moment: date = None) -> dict:
    """Weekly Review: what worked, what didn't, what slipped, what to do next."""
    from app.services import attention, brain

    moment = moment or date.today()
    base = build_weekly(db, user_id, moment)
    start, end = base["period_start"], base["period_end"]
    ctx = brain.snapshot(db, user_id)
    items = attention.attention_center(db, user_id, ctx=ctx)

    capacity = ctx["capacity"]
    return {
        **base,
        "review_type": "weekly",
        "worked": base["worked"],
        "didnt": base["didnt"],
        "slipped": _slipped(db, user_id, moment),
        "decisions": _decisions_in_period(db, user_id, start, end),
        "capacity": capacity,
        "attention": attention.summary(items),
        "focus": [
            {
                "title": move["title"],
                "why": move.get("why") or move["reason"],
                "impact": move["benefit"],
                "consequence": move.get("consequence"),
                "actions": move.get("actions") or [],
                "url": move["url"],
            }
            for move in ctx and recommender.generate(db, user_id, limit=3)
        ],
        "basis": "system-derived",
    }


def build_business_review(db: Session, user_id: int, moment: date = None) -> dict:
    """CEO review: revenue, content engine, brand portfolio, risks, priorities.

    Period defaults to the current quarter so the review compares like with like.
    """
    from app.services import attention, brain

    moment = moment or date.today()
    quarter_start_month = ((moment.month - 1) // 3) * 3 + 1
    start = date(moment.year, quarter_start_month, 1)
    end = (start + timedelta(days=92)).replace(day=1) - timedelta(days=1)

    ctx = brain.snapshot(db, user_id)
    items = attention.attention_center(db, user_id, ctx=ctx)
    capacity = ctx["capacity"]
    monthly = build_monthly(db, user_id, moment)
    money = ctx["money"]

    # brand portfolio: concentration is a real business risk
    brands = ctx["brands"]
    total_received = money["ytd"] or 0
    concentration = []
    for row in brands:
        share = (row["revenue_total"] / total_received * 100) if total_received else 0
        if share:
            concentration.append({"name": row["brand"].name, "share": round(share, 1)})
    concentration.sort(key=lambda c: -c["share"])
    top_share = concentration[0]["share"] if concentration else 0

    risks = []
    if money["overdue_total"]:
        risks.append(
            {
                "title": f"{round(money['overdue_total']):,} is overdue",
                "detail": "Overdue invoices are the most common cause of a creator's cashflow crunch.",
                "severity": "critical",
            }
        )
    if top_share >= 60 and top_share < 100:
        risks.append(
            {
                "title": f"{concentration[0]['name']} is {top_share}% of your recorded revenue",
                "detail": "Heavy dependence on one brand means one lost deal changes your month.",
                "severity": "high",
            }
        )
    if capacity["over_capacity"]:
        risks.append(
            {
                "title": f"You are {capacity['overload_hours']}h overcommitted this week",
                "detail": capacity["explanation"],
                "severity": "high",
            }
        )
    if ctx["behind_goals"]:
        risks.append(
            {
                "title": f"{len(ctx['behind_goals'])} goal(s) behind target",
                "detail": "Behind schedule against numbers you set yourself.",
                "severity": "medium",
            }
        )

    return {
        "review_type": "business",
        "period_start": start,
        "period_end": end,
        "revenue": {
            "this_month": money["this_month"],
            "ytd": money["ytd"],
            "by_month": money["by_month"],
            "outstanding": money["outstanding"],
            "overdue": money["overdue_total"],
            "month_over_month": monthly["summary"].get("revenue_change"),
            "by_source": brain.revenue_by_source(db, user_id),
        },
        "content_engine": {
            "total": ctx["pulse"]["total"],
            "published": ctx["pulse"]["published"],
            "in_flight": ctx["pulse"]["in_flight"],
            "stuck": ctx["pulse"]["stuck"],
            "consistency": ctx["pulse"]["consistency_label"],
            "series": ctx["series"],
            "atomizable": len(ctx["atomizable"]),
        },
        "brand_portfolio": {
            "brands": brands,
            "concentration": concentration,
            "top_share": top_share,
            "open_deals": len(ctx["deals"]),
        },
        "risks": risks,
        "attention": attention.summary(items),
        "decisions": _decisions_in_period(db, user_id, start, end),
        "priorities": [
            {
                "title": row["label"],
                "why": row["reason"],
                "value": row["value"],
                "effort_minutes": row["effort_minutes"],
                "url": row["url"],
                "action": row.get("action"),
                "entity_type": row.get("entity_type"),
                "entity_id": row.get("entity_id"),
            }
            for row in ctx["money_on_the_table"][:5]
        ],
        "basis": "system-derived",
    }
