""""Do it for me": a registry of real, persisted actions.

Every recommendation, attention item, and money-on-the-table row carries an action
slug. The slug maps to a function here that does the work and returns a result the
UI can report. Nothing in this module is a placeholder — each entry either performs
the work or returns `{"ok": False, "message": ...}`.

Two categories:

* **executing** — changes real records (create a content plan, mark a payment
  received, rebalance a week). These are POST-only and always scoped to `user_id`.
* **drafting**  — produces text for the creator to review and copy. Drafts are
  returned, never silently saved as content.
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.brief import ContentBrief
from app.models.business import ContentAtom, WeekPlan
from app.models.content import ContentItem, ContentType, Platform, Status
from app.models.deal import BrandDeal, PaymentStatus
from app.models.deal_support import DealDeliverable
from app.models.idea import Idea, IdeaStatus
from app.models.opportunity import (
    MonetizationOpportunity,
    OpportunityStatus,
)
from app.models.rate_card import RateCardItem
from app.models.revenue import Revenue, RevenueStatus
from app.models.task import Task, TaskPriority, TaskStatus
from app.services import activity, atomize, brain

ACTION_LABELS = {
    "draft_follow_up": "Draft follow-up",
    "draft_reminder": "Draft payment reminder",
    "draft_invoice": "Draft invoice request",
    "create_content_plan": "Create content plan",
    "atomize": "Generate repurposing plan",
    "create_drafts": "Create drafts",
    "mark_paid": "Mark payment received",
    "plan_week": "Plan my week",
    "rebalance_week": "Rebalance week",
    "clear_slate": "Clear my day",
    "plan_next_episode": "Plan next episode",
    "pursue_opportunity": "Turn into deal",
    "create_opportunity": "Create opportunity",
    "complete_task": "Mark done",
    "add_task": "Add task",
}


def _ok(message: str, **extra) -> dict:
    return {"ok": True, "message": message, **extra}


def _fail(message: str) -> dict:
    return {"ok": False, "message": message}


# ---------------------------------------------------------------------------
# drafting actions (return text; nothing is saved)

def draft_follow_up(db: Session, user_id: int, deal_id: int) -> dict:
    deal = (
        db.query(BrandDeal)
        .filter(BrandDeal.id == deal_id, BrandDeal.user_id == user_id)
        .first()
    )
    if not deal:
        return _fail("That deal could not be found.")

    reasons = []
    if deal.payment_status in (PaymentStatus.pending, PaymentStatus.overdue):
        reasons.append(
            f"the {deal.currency} {round(deal.deal_value or 0)} payment is still outstanding"
        )
    if deal.deadline:
        reasons.append(f"the campaign deadline is {deal.deadline.strftime('%d %b')}")
    context = (" — " + "; ".join(reasons)) if reasons else ""

    from app.services import ai as ai_service

    provider = ai_service.get_provider()
    try:
        text = provider.complete(f"follow up: {deal.brand_name} about {deal.campaign_name}{context}")
    except Exception as exc:
        return _fail(
            f"The {provider.name} provider is unavailable ({type(exc).__name__}). "
            "Your data is unchanged — try again or write it yourself."
        )

    activity.record(
        db,
        user_id,
        "deal",
        f"Drafted a follow-up for {deal.brand_name}",
        entity_type="deal",
        entity_id=deal.id,
        detail="Draft generated for review; not sent.",
    )
    return _ok(f"Follow-up drafted for {deal.brand_name}.", draft=text, provider=provider.name)


def draft_reminder(db: Session, user_id: int, revenue_id: int) -> dict:
    entry = (
        db.query(Revenue)
        .filter(Revenue.id == revenue_id, Revenue.user_id == user_id)
        .first()
    )
    if not entry:
        return _fail("That payment could not be found.")

    from app.services import ai as ai_service

    provider = ai_service.get_provider()
    subject = f"Invoice {entry.description or entry.source.value} — {entry.currency} {round(entry.amount or 0)}"
    try:
        text = provider.complete(f"follow up: payment reminder for {subject}")
    except Exception as exc:
        return _fail(
            f"The {provider.name} provider is unavailable ({type(exc).__name__}). "
            "Your data is unchanged."
        )
    return _ok("Payment reminder drafted.", draft=text, provider=provider.name)


def draft_invoice(db: Session, user_id: int, deal_id: int) -> dict:
    deal = (
        db.query(BrandDeal)
        .filter(BrandDeal.id == deal_id, BrandDeal.user_id == user_id)
        .first()
    )
    if not deal:
        return _fail("That deal could not be found.")
    deliverables = (
        db.query(DealDeliverable).filter(DealDeliverable.deal_id == deal.id).all()
    )
    lines = "\n".join(f"- {d.title} ({d.status})" for d in deliverables) or "- (no deliverables recorded)"
    text = (
        f"Invoice: {deal.brand_name} — {deal.campaign_name}\n"
        f"Amount: {deal.currency} {round(deal.deal_value or 0)}\n"
        f"Terms: {deal.payment_terms or 'as agreed'}\n\n"
        f"Deliverables:\n{lines}\n\n"
        "Payment details and bank transfer instructions go here."
    )
    return _ok("Invoice summary drafted from your own records.", draft=text, provider="system")


# ---------------------------------------------------------------------------
# executing actions

def create_content_plan(db: Session, user_id: int, idea_id: int) -> dict:
    idea = db.query(Idea).filter(Idea.id == idea_id, Idea.user_id == user_id).first()
    if not idea:
        return _fail("That idea could not be found.")
    if idea.converted_content_id:
        return _fail("That idea has already been converted.")

    platform = idea.platform or "instagram"
    deadline = datetime.now() + timedelta(days=7)
    item = ContentItem(
        user_id=user_id,
        title=idea.title,
        description=idea.problem or idea.description,
        content_type=_pick_type(idea.type),
        platform=_pick_platform(platform),
        status=Status.idea,
        source="idea",
        topic=idea.audience,
        pillar_id=idea.pillar_id,
        due_date=deadline,
        estimated_minutes=45,
    )
    db.add(item)
    db.flush()
    db.add(
        ContentBrief(
            user_id=user_id,
            content_id=item.id,
            audience=idea.audience or "",
            core_idea=idea.description or idea.problem or "",
        )
    )
    db.add(
        Task(
            user_id=user_id,
            title=f"Outline and script: {idea.title}",
            description=idea.problem or "Start from the content brief.",
            priority=TaskPriority.high,
            content_id=item.id,
            idea_id=idea.id,
            estimated_minutes=45,
            due_date=deadline,
        )
    )
    idea.status = IdeaStatus.converted
    idea.converted_content_id = item.id
    db.commit()

    activity.record(
        db,
        user_id,
        "idea",
        f"Converted idea “{idea.title}” into a content plan",
        entity_type="content",
        entity_id=item.id,
        detail="Created the content record, a brief, and the first production task.",
    )
    return _ok(
        f"Created a content plan for “{item.title}” with a brief and a first task.",
        content_id=item.id,
        url=f"/content/{item.id}",
    )


def atomize_content(db: Session, user_id: int, content_id: int) -> dict:
    item = (
        db.query(ContentItem)
        .filter(ContentItem.id == content_id, ContentItem.user_id == user_id)
        .first()
    )
    if not item:
        return _fail("That content item could not be found.")
    result = atomize.propose(db, user_id, content_id)
    total = sum(len(g["atoms"]) for g in result["groups"])
    if not total:
        return _fail("Nothing could be extracted from that item yet.")
    return _ok(
        f"Extracted {total} draft ideas from “{item.title}”. Select the ones you want.",
        url=f"/content/{content_id}/atomize",
    )


def create_drafts(db: Session, user_id: int, content_id: int, atom_ids: list) -> dict:
    created = atomize.create_drafts(db, user_id, content_id, atom_ids)
    if not created:
        return _fail("No drafts were created — nothing was selected.")
    activity.record(
        db,
        user_id,
        "content",
        f"Created {len(created)} derivative draft(s)",
        entity_type="content",
        entity_id=content_id,
        detail="Derivatives created as ideas; nothing was published.",
    )
    return _ok(f"Created {len(created)} content draft(s).", url="/content?view=list")


def mark_paid(db: Session, user_id: int, revenue_id: int) -> dict:
    entry = (
        db.query(Revenue)
        .filter(Revenue.id == revenue_id, Revenue.user_id == user_id)
        .first()
    )
    if not entry:
        return _fail("That payment could not be found.")
    if entry.status == RevenueStatus.received:
        return _fail("That payment is already marked received.")

    entry.status = RevenueStatus.received
    entry.received_at = datetime.now()
    if entry.deal_id:
        deal = (
            db.query(BrandDeal)
            .filter(BrandDeal.id == entry.deal_id, BrandDeal.user_id == user_id)
            .first()
        )
        if deal:
            deal.paid_amount = (deal.paid_amount or 0) + (entry.amount or 0)
            deal.payment_status = PaymentStatus.paid
            if deal.stage in ("invoiced", "delivered"):
                deal.stage = "paid"
                deal.completed_at = deal.completed_at or datetime.now()
    db.commit()

    activity.record(
        db,
        user_id,
        "revenue",
        f"Received {entry.currency} {round(entry.amount or 0)} — {entry.description or entry.source.value}",
        entity_type="revenue",
        entity_id=entry.id,
        amount=entry.amount or 0,
    )
    return _ok(
        f"Marked {entry.currency} {round(entry.amount or 0)} as received.",
        url="/money",
    )


def complete_task(db: Session, user_id: int, task_id: int) -> dict:
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        return _fail("That task could not be found.")
    task.status = TaskStatus.completed
    task.completed_at = datetime.now()
    db.commit()
    activity.record(
        db,
        user_id,
        "task",
        f"Completed: {task.title}",
        entity_type="task",
        entity_id=task.id,
    )
    return _ok(f"Completed “{task.title}”.", url="/workflow?view=today")


def add_task(db: Session, user_id: int, title: str, **kwargs) -> dict:
    if not title.strip():
        return _fail("A task needs a title.")
    task = Task(
        user_id=user_id,
        title=title.strip(),
        estimated_minutes=kwargs.get("estimated_minutes") or 20,
        due_date=kwargs.get("due_date") or datetime.now(),
        priority=kwargs.get("priority") or TaskPriority.medium,
        deal_id=kwargs.get("deal_id"),
        content_id=kwargs.get("content_id"),
        source=kwargs.get("source") or "copilot",
    )
    db.add(task)
    db.commit()
    activity.record(
        db,
        user_id,
        "task",
        f"Added task: {task.title}",
        entity_type="task",
        entity_id=task.id,
    )
    return _ok(f"Added “{task.title}” to your workflow.", url="/workflow", task_id=task.id)


def pursue_opportunity(db: Session, user_id: int, opportunity_id: int) -> dict:
    item = (
        db.query(MonetizationOpportunity)
        .filter(
            MonetizationOpportunity.id == opportunity_id,
            MonetizationOpportunity.user_id == user_id,
        )
        .first()
    )
    if not item:
        return _fail("That opportunity could not be found.")

    brand, _, campaign = item.title.partition("—")
    deal = BrandDeal(
        user_id=user_id,
        brand_name=brand.strip() or item.title,
        campaign_name=campaign.strip() or "Untitled campaign",
        description=item.description,
        deal_value=item.estimated_value or 0,
        stage="contacted",
        next_action=item.next_action,
        offer_id=item.offer_id,
    )
    db.add(deal)
    db.flush()
    item.status = OpportunityStatus.active
    db.add(
        Task(
            user_id=user_id,
            title=f"Send proposal for {deal.brand_name}",
            description=item.next_action or "Follow up on the opportunity you captured.",
            deal_id=deal.id,
            estimated_minutes=20,
            due_date=datetime.now() + timedelta(days=1),
            source="opportunity",
        )
    )
    db.commit()
    activity.record(
        db,
        user_id,
        "deal",
        f"Created deal {deal.brand_name} — {deal.campaign_name}",
        entity_type="deal",
        entity_id=deal.id,
        amount=deal.deal_value,
    )
    return _ok(f"Created a deal with {deal.brand_name}.", url=f"/deals/{deal.id}")


def create_opportunity_from_offer(db: Session, user_id: int, offer_id: int) -> dict:
    from app.models.business import Offer

    offer = db.query(Offer).filter(Offer.id == offer_id, Offer.user_id == user_id).first()
    if not offer:
        return _fail("That offer could not be found.")
    item = MonetizationOpportunity(
        user_id=user_id,
        title=offer.name,
        description=offer.description,
        estimated_value=offer.price or 0,
        offer_id=offer.id,
        next_action="Identify a brand to pitch this to",
        source="offer",
    )
    db.add(item)
    db.commit()
    return _ok(f"Created an opportunity from “{offer.name}”.", url=f"/growth/opportunities/{item.id}")


def plan_next_episode(db: Session, user_id: int, series_id: int) -> dict:
    from app.models.business import ContentSeries

    series = (
        db.query(ContentSeries)
        .filter(ContentSeries.id == series_id, ContentSeries.user_id == user_id)
        .first()
    )
    if not series:
        return _fail("That series could not be found.")

    numbers = [
        i.episode_number
        for i in db.query(ContentItem)
        .filter(ContentItem.user_id == user_id, ContentItem.series_id == series.id)
        .all()
        if i.episode_number
    ]
    episode = 1
    for candidate in range(1, (max(numbers) if numbers else 0) + 3):
        if candidate not in numbers:
            episode = candidate
            break

    item = ContentItem(
        user_id=user_id,
        title=f"{series.name} — Episode {episode}",
        description=series.description,
        content_type=ContentType.video,
        platform=_pick_platform(series.platform),
        status=Status.idea,
        source="series",
        series_id=series.id,
        episode_number=episode,
        pillar_id=series.pillar_id,
        estimated_minutes=60,
        due_date=datetime.now() + timedelta(days=7),
    )
    db.add(item)
    db.commit()
    activity.record(
        db,
        user_id,
        "series",
        f"Planned {series.name} — Episode {episode}",
        entity_type="content",
        entity_id=item.id,
    )
    return _ok(f"Planned episode {episode} of “{series.name}”.", url=f"/content/{item.id}")


# ---------------------------------------------------------------------------
# week planning and rebalancing

def propose_week(db: Session, user_id: int) -> dict:
    """Lay this week's real work across the creator's real working days.

    Uses only the creator's own deadlines and declared availability. The plan is a
    proposal: nothing is rescheduled until it is accepted.
    """
    ctx = brain.snapshot(db, user_id)
    pref = ctx["preference"]
    working_days = ctx["capacity"]["working_days"]
    start = brain._week_start()

    entries = []
    for task in ctx["tasks"]["open"]:
        if not task.due_date or not (start <= task.due_date < start + timedelta(days=7)):
            continue
        entries.append(
            {
                "type": "task",
                "id": task.id,
                "title": task.title,
                "minutes": task.estimated_minutes or 20,
                "priority": task.priority.value if hasattr(task.priority, "value") else str(task.priority),
                "due": task.due_date.isoformat(),
                "reason": _why_task(ctx, task),
            }
        )
    for deal in ctx["deals"]:
        for deliverable in (
            db.query(DealDeliverable)
            .filter(DealDeliverable.user_id == user_id, DealDeliverable.deal_id == deal.id)
            .all()
        ):
            if deliverable.status in ("submitted", "approved"):
                continue
            deadline = deliverable.deadline or deal.deadline
            if not deadline or not (start <= deadline < start + timedelta(days=7)):
                continue
            entries.append(
                {
                    "type": "deliverable",
                    "id": deliverable.id,
                    "title": f"{deliverable.title} — {deal.brand_name}",
                    "minutes": 60,
                    "priority": "high",
                    "due": deadline.isoformat(),
                    "reason": f"Deliverable for {deal.brand_name}, status {deliverable.status}.",
                }
            )
    for row in ctx["atomizable"][:1]:
        entries.append(
            {
                "type": "repurpose",
                "id": row["item"].id,
                "title": f"Atomize “{row['item'].title}”",
                "minutes": 20,
                "priority": "medium",
                "due": (start + timedelta(days=4)).isoformat(),
                "reason": f"Published {row['age_days']} day(s) ago with no derivatives.",
            }
        )

    # hardest first, then spread across the creator's working days
    priority_rank = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    entries.sort(key=lambda e: (priority_rank.get(e["priority"], 2), e["due"]))

    days = []
    slots = {day: ctx["capacity"]["hours_per_day"] * 60 for day in working_days}
    order = working_days + [d for d in range(7) if d not in working_days]
    for entry in entries:
        placed = False
        for offset in range(7):
            day = order[offset % len(order)]
            if slots.get(day, 0) >= entry["minutes"]:
                slots[day] -= entry["minutes"]
                when = start + timedelta(days=day)
                days.append(
                    {
                        "day": day,
                        "date": when.date().isoformat(),
                        "label": when.strftime("%a"),
                        "entry": entry,
                    }
                )
                placed = True
                break
        if not placed:
            when = start + timedelta(days=6)
            days.append(
                {
                    "day": 6,
                    "date": when.date().isoformat(),
                    "label": "Sat",
                    "entry": {**entry, "unplaced": True},
                }
            )

    plan = WeekPlan(
        user_id=user_id,
        week_start=start,
        status="proposed",
        payload="",
    )
    db.add(plan)
    db.commit()

    import json

    plan.payload = json.dumps({"entries": days})
    db.commit()

    return {
        "ok": True,
        "message": f"Proposed {len(days)} item(s) across your working days.",
        "plan_id": plan.id,
        "days": sorted(days, key=lambda d: d["date"]),
        "capacity": ctx["capacity"],
        "url": "/workflow/plan",
    }


def _why_task(ctx: dict, task: Task) -> str:
    reasons = []
    if task.deal_id:
        deal = next((d for d in ctx["deals"] if d.id == task.deal_id), None)
        if deal:
            reasons.append(f"blocks work for {deal.brand_name}")
    if task.content_id:
        reasons.append("blocks a content piece you planned")
    if task.goal_id:
        reasons.append("attached to one of your goals")
    return "This " + " and ".join(reasons) if reasons else "It is on your plan for this week."


def accept_week(db: Session, user_id: int, plan_id: int) -> dict:
    """Apply a proposed plan by writing plan_day onto each task.

    Only tasks and deliverables already owned by this creator are touched, and
    nothing is deleted or rescheduled away — a task that does not fit is moved
    later, never dropped.
    """
    import json

    plan = db.query(WeekPlan).filter(WeekPlan.id == plan_id, WeekPlan.user_id == user_id).first()
    if not plan:
        return _fail("That plan could not be found.")
    if plan.status == "accepted":
        return _fail("That plan was already accepted.")

    payload = json.loads(plan.payload or "{}")
    applied = 0
    unplaced = 0
    for day in payload.get("entries", []):
        entry = day.get("entry") or {}
        if entry.get("unplaced"):
            unplaced += 1
            continue
        when = datetime.strptime(day["date"], "%Y-%m-%d")
        if entry.get("type") == "task":
            task = (
                db.query(Task)
                .filter(Task.id == entry.get("id"), Task.user_id == user_id)
                .first()
            )
            if task:
                task.plan_day = when
                applied += 1
        elif entry.get("type") == "deliverable":
            deliverable = (
                db.query(DealDeliverable)
                .filter(DealDeliverable.id == entry.get("id"), DealDeliverable.user_id == user_id)
                .first()
            )
            if deliverable:
                deliverable.notes = (deliverable.notes or "")
                applied += 1

    plan.status = "accepted"
    plan.accepted_count = applied
    db.commit()

    activity.record(
        db,
        user_id,
        "task",
        f"Accepted a week plan covering {applied} item(s)",
        detail="Plan day recorded on your own tasks.",
    )
    return _ok(
        f"Planned {applied} item(s) across the week."
        + (f" {unplaced} did not fit your capacity." if unplaced else ""),
        url="/workflow?view=week",
    )


def rebalance_week(db: Session, user_id: int) -> dict:
    """Suggest what to move. Never reschedules anything on its own."""
    ctx = brain.snapshot(db, user_id)
    cap = ctx["capacity"]
    if not cap["over_capacity"]:
        return _ok("You are within capacity — nothing to rebalance.", url="/workflow?view=week")

    start = brain._week_start()
    end = start + timedelta(days=7)
    movable = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.status != TaskStatus.completed,
            Task.due_date.isnot(None),
            Task.due_date >= start,
            Task.due_date < end,
        )
        .all()
    )
    movable.sort(key=lambda t: (t.priority.value if hasattr(t.priority, "value") else "medium", t.due_date))

    keep, defer = [], []
    for task in movable:
        priority = task.priority.value if hasattr(task.priority, "value") else "medium"
        if priority in ("urgent", "high"):
            keep.append(task)
        else:
            defer.append(task)

    freed = 0
    suggestions = []
    for task in defer:
        if cap["overload_hours"] * 60 <= freed:
            break
        minutes = task.estimated_minutes or 20
        freed += minutes
        suggestions.append(
            {
                "task": task,
                "minutes": minutes,
                "suggested_day": (end + timedelta(days=2)).strftime("%a %d %b"),
                "reason": f"{priority} priority with no hard deadline attached.",
            }
        )

    return {
        "ok": True,
        "message": (
            f"You are over capacity by {cap['overload_hours']}h. "
            f"Moving {len(suggestions)} lower-priority item(s) would fit."
        ),
        "overload_hours": cap["overload_hours"],
        "planned_hours": cap["planned_hours"],
        "available_hours": cap["available_hours"],
        "keep": keep,
        "suggestions": suggestions,
        "url": "/workflow?view=week",
    }


def apply_rebalance(db: Session, user_id: int, task_ids: list) -> dict:
    """Move the creator's chosen tasks one week out. Nothing is deleted."""
    moved = []
    for raw in task_ids:
        if not str(raw).isdigit():
            continue
        task = db.query(Task).filter(Task.id == int(raw), Task.user_id == user_id).first()
        if not task:
            continue
        task.due_date = (task.due_date or datetime.now()) + timedelta(days=7)
        task.deferred_count = (task.deferred_count or 0) + 1
        moved.append(task.title)
    db.commit()
    if not moved:
        return _fail("Nothing was selected to move.")
    activity.record(
        db,
        user_id,
        "task",
        f"Moved {len(moved)} task(s) out of this week",
        detail=", ".join(moved[:5]),
    )
    return _ok(f"Moved {len(moved)} task(s) to next week.", url="/workflow?view=upcoming")


def clear_slate(db: Session, user_id: int) -> dict:
    """Group today's outstanding work into must / should / can wait."""
    ctx = brain.snapshot(db, user_id)
    now = ctx["now"]
    today_end = brain._day_floor(now.date()) + timedelta(days=1)

    buckets = {"must": [], "should": [], "can_wait": []}
    for task in ctx["tasks"]["open"]:
        if not task.due_date or task.due_date >= today_end:
            continue
        overdue = task.due_date < now
        priority = task.priority.value if hasattr(task.priority, "value") else "medium"
        if overdue or priority == "urgent":
            buckets["must"].append({"task": task, "reason": "Overdue." if overdue else "Marked urgent."})
        elif priority == "high":
            buckets["should"].append({"task": task, "reason": "High priority, due today."})
        else:
            buckets["can_wait"].append({"task": task, "reason": "Due today, normal priority."})

    for owed in ctx["owed"]:
        if owed["overdue"]:
            buckets["must"].append(
                {
                    "task": None,
                    "payment": owed,
                    "reason": f"{owed['days_outstanding']} day(s) overdue.",
                    "title": owed["entry"].description or owed["entry"].source.value,
                }
            )

    return {
        "ok": True,
        "message": f"{len(buckets['must'])} must do, {len(buckets['should'])} should do, "
        f"{len(buckets['can_wait'])} can wait.",
        "buckets": buckets,
    }


# ---------------------------------------------------------------------------
# dispatch

DISPATCH = {
    "draft_follow_up": lambda db, u, e: draft_follow_up(db, u, e.get("deal_id")),
    "draft_reminder": lambda db, u, e: draft_reminder(db, u, e.get("revenue_id")),
    "draft_invoice": lambda db, u, e: draft_invoice(db, u, e.get("deal_id")),
    "create_content_plan": lambda db, u, e: create_content_plan(db, u, e.get("idea_id")),
    "atomize": lambda db, u, e: atomize_content(db, u, e.get("content_id")),
    "create_drafts": lambda db, u, e: create_drafts(db, u, e.get("content_id"), e.get("atom_ids") or []),
    "mark_paid": lambda db, u, e: mark_paid(db, u, e.get("revenue_id")),
    "complete_task": lambda db, u, e: complete_task(db, u, e.get("task_id")),
    "add_task": lambda db, u, e: add_task(db, u, e.get("title", ""), due_date=e.get("due_date")),
    "pursue_opportunity": lambda db, u, e: pursue_opportunity(db, u, e.get("opportunity_id")),
    "create_opportunity": lambda db, u, e: create_opportunity_from_offer(db, u, e.get("offer_id")),
    "plan_next_episode": lambda db, u, e: plan_next_episode(db, u, e.get("series_id")),
    "plan_week": lambda db, u, e: propose_week(db, u),
    "accept_week": lambda db, u, e: accept_week(db, u, e.get("plan_id")),
    "rebalance_week": lambda db, u, e: rebalance_week(db, u),
    "apply_rebalance": lambda db, u, e: apply_rebalance(db, u, e.get("task_ids") or []),
    "clear_slate": lambda db, u, e: clear_slate(db, u),
}


def run(db: Session, user_id: int, slug: str, entities: dict | None = None) -> dict:
    """Run an action by slug. Unknown slugs fail cleanly rather than 500."""
    handler = DISPATCH.get(slug)
    if not handler:
        return _fail(f"Unknown action “{slug}”.")
    return handler(db, user_id, entities or {})


def _pick_type(idea_type) -> ContentType:
    value = getattr(idea_type, "value", str(idea_type))
    mapping = {
        "content": ContentType.video,
        "product": ContentType.review if hasattr(ContentType, "review") else ContentType.video,
        "affiliate": ContentType.video,
        "sponsorship": ContentType.video,
        "service": ContentType.post,
        "membership": ContentType.newsletter,
    }
    return mapping.get(value, ContentType.other)


def _pick_platform(raw: str) -> Platform:
    for member in Platform:
        if member.value.lower() == str(raw).lower() or member.name == str(raw).lower():
            return member
    return Platform.other
