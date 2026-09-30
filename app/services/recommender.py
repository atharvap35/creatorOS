"""Explainable recommendation engine.

score = urgency + impact + goal_alignment + deadline_pressure - effort
Every candidate carries the exact reasons that produced its score, so the UI can
show the user *why* instead of asserting that an algorithm knows better.
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.content import ContentItem, Status
from app.models.creator_preference import CreatorPreference
from app.models.deal import BrandDeal
from app.models.goal import CreatorGoal
from app.models.idea import Idea, IdeaStatus
from app.models.opportunity import MonetizationOpportunity
from app.models.recommendation import Recommendation
from app.models.repurpose import ContentRepurpose
from app.models.task import Task, TaskStatus
from app.services import insights

GOAL_ALIGNMENT = {
    "get_sponsorships": {"deal", "money", "rate_card"},
    "make_money": {"money", "deal", "opportunity"},
    "grow_audience": {"content", "idea", "repurpose"},
    "build_product": {"idea", "opportunity", "content"},
    "become_consistent": {"content", "workflow"},
    "build_business": {"deal", "money", "opportunity", "content"},
}


def _open_deliverables(db: Session, deal_id: int) -> list:
    from app.models.deal_support import DealDeliverable

    return (
        db.query(DealDeliverable)
        .filter(
            DealDeliverable.deal_id == deal_id,
            DealDeliverable.status.in_(["pending", "in_progress"]),
        )
        .all()
    )


def preference_for(db: Session, user_id: int) -> CreatorPreference:
    pref = db.query(CreatorPreference).filter(CreatorPreference.user_id == user_id).first()
    if not pref:
        pref = CreatorPreference(user_id=user_id)
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref


def _urgency(due: datetime | None, now: datetime) -> tuple:
    if due is None:
        return 0, "no deadline"
    delta = (due - now).total_seconds() / 3600
    if delta < 0:
        return 50, f"overdue by {abs(int(delta))}h"
    if delta < 24:
        return 45, "due within 24 hours"
    if delta < 72:
        return 32, "due within 3 days"
    if delta < 168:
        return 20, "due this week"
    return 8, "scheduled ahead"


def _goal_alignment(db: Session, user_id: int, kinds: set) -> tuple:
    pref = preference_for(db, user_id)
    goal = pref.primary_goal or "build_business"
    return (15 if kinds & GOAL_ALIGNMENT.get(goal, set()) else 5, goal)


def _build(db, user_id, *, kind, title, reasons, benefit, effort, entity_type, entity_id, url, cta, impact, due=None, source="rules", consequence=None, actions=None, amount=None):
    now = datetime.now()
    urgency, urgency_reason = _urgency(due, now)
    alignment, goal = _goal_alignment(db, user_id, {kind})
    effort_penalty = min(int((effort or 15) / 5), 15)
    score = max(0.0, urgency + impact + alignment - effort_penalty)

    breakdown = ", ".join(
        [
            f"urgency {urgency} ({urgency_reason})",
            f"impact {impact}",
            f"goal alignment {alignment} (goal: {goal.replace('_', ' ')})",
            f"effort -{effort_penalty} ({effort or 15} min)",
        ]
    )
    return {
        "kind": kind,
        "title": title,
        "reason": reasons,
        "benefit": benefit,
        "effort_minutes": effort,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "url": url,
        "cta": cta,
        "score": score,
        "score_breakdown": breakdown,
        "source": source,
        # 3.0: the full "why this matters" structure
        "what": title,
        "why": reasons,
        "consequence": consequence or "If this slips, it stays on tomorrow's list too.",
        "actions": actions or [],
        "amount": amount,
    }


def generate(db: Session, user_id: int, limit: int = 12) -> list:
    now = datetime.now()
    today = date.today()
    candidates = []

    open_tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.status != TaskStatus.completed)
        .all()
    )
    for task in open_tasks:
        if not task.due_date:
            continue
        priority_impact = {"urgent": 30, "high": 24, "medium": 16, "low": 8}.get(
            getattr(task.priority, "value", str(task.priority)), 14
        )
        _, urgency_reason = _urgency(task.due_date, now)
        candidates.append(
            _build(
                db,
                user_id,
                kind="workflow",
                title=task.title,
                reasons=f"Your task is {urgency_reason}.",
                benefit="Clearing it unblocks everything scheduled behind it.",
                effort=task.estimated_minutes or 15,
                entity_type="task",
                entity_id=task.id,
                url=f"/workflow?focus={task.id}",
                cta="Open task",
                impact=priority_impact,
                due=task.due_date,
                consequence=f"{task.title} is still open and it is {urgency_reason}.",
                actions=[{"slug": "complete_task", "label": "Mark done", "entities": {"task_id": task.id}}],
            )
        )

    deals = (
        db.query(BrandDeal)
        .filter(BrandDeal.user_id == user_id, BrandDeal.stage.notin_(["completed", "cancelled", "declined"]))
        .all()
    )
    for deal in deals:
        if deal.payment_status == "overdue" or (
            deal.payment_due_date and deal.payment_due_date < now and deal.payment_status != "paid"
        ):
            days = (now - deal.payment_due_date).days if deal.payment_due_date else 0
            candidates.append(
                _build(
                    db,
                    user_id,
                    kind="money",
                    title=f"Follow up with {deal.brand_name} — {deal.currency} {round(deal.deal_value or 0)} overdue",
                    reasons=(
                        f"Payment is {days} day(s) past its due date, and the campaign "
                        f"has {len(_open_deliverables(db, deal.id))} unfinished deliverable(s)."
                        if _open_deliverables(db, deal.id)
                        else f"Payment is {days} day(s) past its due date."
                    ),
                    benefit=f"Potentially unlocks {deal.currency} {round(deal.deal_value or 0)} of cashflow you have already earned.",
                    effort=10,
                    entity_type="deal",
                    entity_id=deal.id,
                    url=f"/deals/{deal.id}",
                    cta="Open deal",
                    impact=30,
                    due=deal.payment_due_date,
                    consequence=(
                        f"Overdue payments are the most common way a creator's cashflow stalls. "
                        f"{deal.brand_name} still owes {deal.currency} {round(deal.deal_value or 0)}."
                    ),
                    amount=deal.deal_value,
                    actions=[
                        {"slug": "draft_follow_up", "label": "Draft follow-up", "entities": {"deal_id": deal.id}},
                        {"slug": "draft_invoice", "label": "Draft invoice", "entities": {"deal_id": deal.id}},
                    ],
                )
            )
        elif deal.stage in ("lead", "contacted", "negotiating") and not deal.follow_up_date:
            candidates.append(
                _build(
                    db,
                    user_id,
                    kind="deal",
                    title=f"Schedule a follow-up with {deal.brand_name}",
                    reasons=f"This deal is at '{deal.stage}' stage with no follow-up date set, so it will go quiet.",
                    benefit="A scheduled follow-up is the difference between a deal and a dead lead.",
                    effort=5,
                    entity_type="deal",
                    entity_id=deal.id,
                    url=f"/deals/{deal.id}",
                    cta="Open deal",
                    impact=22,
                    consequence=(
                        f"{deal.brand_name} is worth {deal.currency} {round(deal.deal_value or 0)} "
                        "and currently has nobody scheduled to chase it."
                    ),
                    amount=deal.deal_value,
                    actions=[
                        {"slug": "draft_follow_up", "label": "Draft follow-up", "entities": {"deal_id": deal.id}}
                    ],
                )
            )

    published = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == user_id, ContentItem.status == Status.published)
        .all()
    )
    for item in published:
        derivatives = (
            db.query(ContentRepurpose)
            .filter(ContentRepurpose.content_id == item.id)
            .count()
        )
        if derivatives == 0:
            age = (now - item.published_at).days if item.published_at else 0
            candidates.append(
                _build(
                    db,
                    user_id,
                    kind="repurpose",
                    title=f"Repurpose “{item.title}”",
                    reasons=(
                        f"This was published {age} day(s) ago and has no derivatives planned yet."
                        if age
                        else "This is published and has no derivatives planned yet."
                    ),
                    benefit="One recording can become 3-5 more pieces of content for very little extra time.",
                    effort=15,
                entity_type="content",
                entity_id=item.id,
                url=f"/content/{item.id}/repurpose",
                cta="Create repurposing plan",
                impact=26,
                consequence=(
                    f"“{item.title}” is {age} day(s) old and has produced nothing beyond the "
                    "original. The material is at its most reusable right now."
                ),
                actions=[
                    {"slug": "atomize", "label": "Generate repurposing plan", "entities": {"content_id": item.id}}
                ],
            )
        )

    for idea in insights.unconverted_ideas(db, user_id, limit=3):
        potential = getattr(idea.potential, "value", str(idea.potential))
        effort = getattr(idea.effort, "value", str(idea.effort))
        if potential == "high" and effort in ("low", "medium"):
            candidates.append(
                _build(
                    db,
                    user_id,
                    kind="idea",
                    title=f"Turn “{idea.title}” into content",
                    reasons=f"Potential is {potential} and effort is {effort} — the cheapest wins in your idea bank.",
                    benefit="Moves an idea that is already half-decided into an actual deliverable.",
                    effort=20,
                entity_type="idea",
                entity_id=idea.id,
                url=f"/ideas/{idea.id}",
                cta="Open idea",
                impact=24,
                consequence=(
                    f"“{idea.title}” is sitting in your idea bank. Ideas decay — this one is "
                    "already scored as a cheap win."
                ),
                actions=[
                    {"slug": "create_content_plan", "label": "Create content plan", "entities": {"idea_id": idea.id}}
                ],
            )
        )

    gaps = insights.pillar_gaps(db, user_id)
    for gap in gaps[:2]:
        pillar_name = gap["pillar"].name
        reason = (
            f"Nothing published under '{pillar_name}' in {gap['days_since']} days."
            if gap["days_since"]
            else f"'{pillar_name}' has never been published."
        )
        candidates.append(
            _build(
                db,
                user_id,
                kind="content",
                title=f"Plan a {pillar_name} piece",
                reasons=reason,
                benefit="Closes a content-mix gap before your audience forgets that theme.",
                effort=25,
                entity_type="pillar",
                entity_id=gap["pillar"].id,
                url="/content/pillars",
                cta="Open pillars",
                impact=18,
            )
        )

    for owed in insights.payments_owed(db, user_id)[:2]:
        if owed["severity"] != "overdue":
            candidates.append(
                _build(
                    db,
                    user_id,
                    kind="money",
                    title=f"Payment due soon: {owed['entry'].description or owed['entry'].source.value}",
                    reasons=f"Marked pending and due in {owed['days_outstanding']} day(s).",
                    benefit="Confirming it early protects your cashflow and the relationship.",
                    effort=10,
                    entity_type="revenue",
                    entity_id=owed["entry"].id,
                    url="/money?status_filter=pending",
                    cta="Open money",
                    impact=20,
                    due=owed["due"],
                    consequence=f"{owed['entry'].currency} {round(owed['amount'])} stops being money you can plan around.",
                    amount=owed["amount"],
                    actions=[
                        {"slug": "draft_reminder", "label": "Draft reminder", "entities": {"revenue_id": owed["entry"].id}},
                        {"slug": "mark_paid", "label": "Mark received", "entities": {"revenue_id": owed["entry"].id}},
                    ],
                )
            )

    workload = weekly_workload(db, user_id)
    if workload["over_capacity"]:
        candidates.append(
            _build(
                db,
                user_id,
                kind="workflow",
                title="You are overcommitted — rebalance this week",
                reasons=workload["explanation"],
                benefit="Fewer commitments finished properly beats more commitments abandoned.",
                effort=10,
                entity_type="plan",
                entity_id=None,
                url="/workflow?view=week",
                cta="Rebalance week",
                impact=24,
                consequence=(
                    f"You have {workload['overload_hours']}h more work than you have hours. "
                    "Something will slip, and it is better to choose what slips now."
                ),
                actions=[{"slug": "rebalance_week", "label": "Rebalance week", "entities": {}}],
            )
        )

    for goal in db.query(CreatorGoal).filter(CreatorGoal.user_id == user_id, CreatorGoal.status == "active").all():
        if goal.target_value and goal.current_value / goal.target_value < 0.4:
            candidates.append(
                _build(
                    db,
                    user_id,
                    kind="goal",
                    title=f"Push on: {goal.title}",
                    reasons=f"You are at {round(goal.current_value)} of {round(goal.target_value)} {goal.unit or ''}.".strip(),
                    benefit="Goals only move when there is a concrete next action attached.",
                    effort=20,
                    entity_type="goal",
                    entity_id=goal.id,
                    url="/goals",
                    cta="Open goals",
                    impact=22,
                )
            )

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:limit]


def best_next_thing(db: Session, user_id: int, minutes: int = 30) -> dict | None:
    """The 'one thing' for the next N minutes: highest score that actually fits."""
    ranked = generate(db, user_id, limit=20)
    if not ranked:
        return None
    fitting = [c for c in ranked if (c["effort_minutes"] or 0) <= minutes]
    return (fitting or ranked)[:1][0] if fitting else ranked[0]


def persist_for_day(db: Session, user_id: int, day: date) -> list:
    """Store today's recommendations so dismissed/done state survives a reload."""
    stored = (
        db.query(Recommendation)
        .filter(Recommendation.user_id == user_id, Recommendation.day == day)
        .all()
    )
    for item in stored:
        db.delete(item)
    db.flush()

    for candidate in generate(db, user_id, limit=12):
        db.add(
            Recommendation(
                user_id=user_id,
                day=day,
                kind=candidate["kind"],
                title=candidate["title"],
                reason=candidate["reason"],
                benefit=candidate["benefit"],
                effort_minutes=candidate["effort_minutes"],
                entity_type=candidate["entity_type"],
                entity_id=candidate["entity_id"],
                cta=candidate["cta"],
                cta_url=candidate["url"],
                score=candidate["score"],
                score_breakdown=candidate["score_breakdown"],
                source=candidate["source"],
            )
        )
    db.commit()
    return stored


def weekly_workload(db: Session, user_id: int, moment: datetime | None = None) -> dict:
    """Planned hours vs. the creator's declared capacity for this week."""
    pref = preference_for(db, user_id)
    moment = moment or datetime.now()
    week_start = moment - timedelta(days=moment.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)

    tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.status != TaskStatus.completed,
            Task.due_date.isnot(None),
            Task.due_date >= week_start,
            Task.due_date < week_end,
        )
        .all()
    )
    content = (
        db.query(ContentItem)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.status != Status.published,
            ContentItem.due_date.isnot(None),
            ContentItem.due_date >= week_start,
            ContentItem.due_date < week_end,
        )
        .all()
    )
    planned_minutes = sum(t.estimated_minutes or 0 for t in tasks) + sum(c.estimated_minutes or 0 for c in content)

    working_days = pref.working_day_list() or [0, 1, 2, 3, 4]
    available_minutes = max(1, len(working_days) * int(pref.hours_per_day or 4) * 60)
    planned_hours = round(planned_minutes / 60, 1)
    available_hours = round(available_minutes / 60, 1)
    capacity = round(planned_minutes / available_minutes * 100)
    overload_hours = round(max(0, planned_minutes - available_minutes) / 60, 1)

    if capacity > 100:
        explanation = (
            f"You have {overload_hours}h more work than you have hours this week "
            f"({capacity}% of capacity). Something will slip — choose what now."
        )
    else:
        explanation = f"You've planned {planned_hours}h against {available_hours}h available ({capacity}% capacity)."

    return {
        "planned_minutes": planned_minutes,
        "planned_hours": planned_hours,
        "available_hours": available_hours,
        "overload_hours": overload_hours,
        "capacity": capacity,
        "over_capacity": capacity > 100,
        "explanation": explanation,
        "task_count": len(tasks),
        "content_count": len(content),
    }
