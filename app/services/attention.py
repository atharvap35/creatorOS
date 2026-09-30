"""Attention Center: everything decaying, waiting, or slipping, in one honest list.

The rule this module enforces: an item only appears here if the creator's own
records prove it. A payment is here because a `Revenue` row is unpaid past its
date. A deal is here because a `BrandDeal` has no follow-up date. A goal is here
because recorded revenue is behind the target the creator set.

Nothing is invented, nothing is estimated, and nothing is duplicated: a single
"payment overdue" produces one item, not one per surface it might appear on.
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.content import ContentItem, Status
from app.models.deal import BrandDeal, DealStatus, PaymentStatus
from app.models.idea import Idea
from app.models.task import Task, TaskStatus
from app.services import brain

USER_ENTERED = "user-entered"
SYSTEM_DERIVED = "system-derived"

# ordering: money first, then things that get worse with time
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _val(value, default=None):
    if value is None:
        return default
    if hasattr(value, "value"):
        return value.value
    return value


def _as_date(value):
    """Deal and task dates are stored as datetimes; compare them as dates."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _item(kind, severity, title, detail, *, entity_type, entity_id, url,
          age_days=None, amount=None, action=None, basis=SYSTEM_DERIVED, group=None):
    return {
        "kind": kind,
        "severity": severity,
        "title": title,
        "detail": detail,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "url": url,
        "age_days": age_days,
        "amount": amount,
        "action": action,
        "basis": basis,
        # a shared identity key, so two records that describe the same obligation can
        # be recognised as one without relying on the wording of their titles
        "group": group,
    }


# ---------------------------------------------------------------------------
# the individual checks

def _money_attention(owed: list) -> list:
    items = []
    for row in owed:
        entry = row["entry"]
        days = row["days_outstanding"]
        name = entry.description or _val(entry.source, "payment")
        if row["overdue"]:
            severity = "critical" if days >= 14 else "high"
            detail = f"Overdue by {days} day(s) — logged on {row['due'].date().isoformat()}."
        else:
            severity = "medium"
            detail = f"Not received; due in {days} day(s)."
        items.append(
            _item(
                "payment",
                severity,
                f"{entry.currency} {round(row['amount']):,} unpaid — {name}",
                detail,
                entity_type="revenue",
                entity_id=entry.id,
                url="/money/payments",
                age_days=days,
                amount=row["amount"],
                action="draft_reminder",
                basis=USER_ENTERED,
                group=_group(name, row["amount"]),
            )
        )
    return items


def _deal_attention(deals: list, today: date, owed: list) -> list:
    # a deal whose money is already shown as an unpaid payment row must not be
    # reported a second time as a separate money crisis
    deals_already_shown = {o["entry"].deal_id for o in owed if o["entry"].deal_id}
    items = []
    for deal in deals:
        stage = _val(deal.stage) or _val(deal.status)
        if _val(deal.status) == DealStatus.completed:
            continue
        if _val(deal.status) == DealStatus.cancelled:
            continue

        if (
            deal.payment_status == PaymentStatus.overdue
            and deal.deal_value
            and deal.id not in deals_already_shown
        ):
            items.append(
                _item(
                    "deal",
                    "critical",
                    f"{deal.brand_name} is overdue on {deal.currency} {round(deal.deal_value):,}",
                    f"Deal '{deal.campaign_name}' is marked overdue for payment.",
                    entity_type="deal",
                    entity_id=deal.id,
                    url=f"/deals/{deal.id}",
                    amount=deal.deal_value,
                    action="draft_follow_up",
                    basis=USER_ENTERED,
                    group=_group(deal.brand_name, deal.deal_value),
                )
            )

        if stage in ("lead", "contacted", "negotiating") and not deal.follow_up_date:
            items.append(
                _item(
                    "deal",
                    "high",
                    f"{deal.brand_name} has no follow-up scheduled",
                    f"Stage is '{stage}' and no follow-up date is set, so this deal goes quiet.",
                    entity_type="deal",
                    entity_id=deal.id,
                    url=f"/deals/{deal.id}",
                    action="draft_follow_up",
                    basis=USER_ENTERED,
                )
            )

        deadline = _as_date(deal.deadline)
        if deadline and deadline < today and stage not in ("paid", "completed"):
            days = (today - deadline).days
            items.append(
                _item(
                    "deal",
                    "high",
                    f"{deal.brand_name} campaign deadline passed {days} day(s) ago",
                    f"'{deal.campaign_name}' was due {deadline.isoformat()} and is still open.",
                    entity_type="deal",
                    entity_id=deal.id,
                    url=f"/deals/{deal.id}",
                    age_days=days,
                    basis=USER_ENTERED,
                )
            )

        if (
            deal.deal_value
            and deal.payment_status == PaymentStatus.invoiced
            and not deal.paid_amount
            and deal.id not in deals_already_shown
        ):
            items.append(
                _item(
                    "deal",
                    "medium",
                    f"{deal.currency} {round(deal.deal_value):,} invoiced but not recorded as received",
                    "You logged this as invoiced; no received payment has been recorded against it.",
                    entity_type="deal",
                    entity_id=deal.id,
                    url=f"/deals/{deal.id}",
                    amount=deal.deal_value,
                    action="mark_paid",
                    basis=USER_ENTERED,
                )
            )
    return items


def _task_attention(tasks: dict, today: date) -> list:
    items = []
    for task in tasks.get("overdue", []):
        due = _as_date(task.due_date)
        days = (today - due).days if due else 0
        items.append(
            _item(
                "task",
                "high" if days > 2 else "medium",
                f"Overdue task: {task.title}",
                f"Was due {due.isoformat() if due else 'an earlier date'}, {days} day(s) ago.",
                entity_type="task",
                entity_id=task.id,
                url=f"/workflow?focus={task.id}",
                age_days=days,
                action="complete_task",
                basis=USER_ENTERED,
            )
        )
    return items


def _content_attention(db: Session, user_id: int, today: date) -> list:
    items = []
    in_flight = (
        db.query(ContentItem)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.status.notin_([Status.published, Status.archived]),
        )
        .all()
    )
    now = datetime.now()
    for item in in_flight:
        due = _as_date(item.due_date)
        if due and due < today:
            days = (today - due).days
            items.append(
                _item(
                    "content",
                    "medium",
                    f"Past its date and not published: {item.title}",
                    f"Due {due.isoformat()}, still at '{_val(item.status)}'.",
                    entity_type="content",
                    entity_id=item.id,
                    url=f"/content/{item.id}",
                    age_days=days,
                    basis=USER_ENTERED,
                )
            )
            continue
        if item.status in (Status.scripting, Status.editing) and item.updated_at:
            stalled = (now - item.updated_at).days
            if stalled >= 7:
                items.append(
                    _item(
                        "content",
                        "medium",
                        f"Stalled at '{_val(item.status)}': {item.title}",
                        f"No update in {stalled} day(s). Stalled work is the most common reason "
                        "a content plan collapses.",
                        entity_type="content",
                        entity_id=item.id,
                        url=f"/content/{item.id}",
                        age_days=stalled,
                        basis=SYSTEM_DERIVED,
                    )
                )
    return items


RANK = {"high": 2, "medium": 1, "low": 0}


def _rank(value) -> int:
    return RANK.get(_val(value, "medium"), 1)


def _idea_rank(idea):
    """Rank by potential, then cheapness — both are creator-entered fields."""
    return (_rank(idea.potential), -_rank(idea.effort))


def _idea_attention(db: Session, user_id: int) -> list:
    ideas = (
        db.query(Idea)
        .filter(Idea.user_id == user_id, Idea.converted_content_id.is_(None))
        .all()
    )
    if not ideas:
        return []
    best = max(ideas, key=_idea_rank)
    age = (datetime.now() - best.created_at).days if best.created_at else 0
    return [
        _item(
            "idea",
            "medium" if age >= 14 else "low",
            f"{len(ideas)} captured idea(s) never turned into content",
            f"Highest scored is “{best.title}” (potential {_val(best.potential)}), captured {age} day(s) ago.",
            entity_type="idea",
            entity_id=best.id,
            url="/ideas",
            age_days=age,
            action="create_content_plan",
            basis=USER_ENTERED,
        )
    ]


def _goal_attention(goals: list) -> list:
    items = []
    today = date.today()
    for goal in goals:
        if goal.status != "active" or not goal.target_value:
            continue
        if goal.current_value >= goal.target_value:
            continue
        remaining = goal.target_value - goal.current_value
        deadline = _as_date(goal.deadline)
        days_left = (deadline - today).days if deadline else None
        pace_note = (
            f"{days_left} day(s) remain" if days_left is not None else "no deadline set"
        )
        if days_left is not None and days_left < 0:
            severity, detail = "high", f"Deadline passed {abs(days_left)} day(s) ago."
        elif days_left is not None and days_left <= 14:
            severity = "high"
            detail = f"{pace_note}; {round(remaining)} still to go."
        else:
            severity = "low"
            detail = f"{pace_note}; {round(remaining)} still to go."
        items.append(
            _item(
                "goal",
                severity,
                f"Behind target: {goal.title}",
                f"{round(goal.current_value)} of {round(goal.target_value)} {goal.unit or ''}. {detail}",
                entity_type="goal",
                entity_id=goal.id,
                url="/goals",
                amount=remaining,
                basis=SYSTEM_DERIVED,
            )
        )
    return items


def _capacity_attention(capacity: dict) -> list:
    if not capacity.get("over_capacity"):
        return []
    return [
        _item(
            "capacity",
            "high",
            "This week is overcommitted",
            capacity["explanation"],
            entity_type="plan",
            entity_id=None,
            url="/workflow?view=week",
            action="rebalance_week",
            basis=SYSTEM_DERIVED,
        )
    ]


def _offer_attention(ctx: dict) -> list:
    rows = [r for r in ctx["money_on_the_table"] if r["source"] == "unused_offer"]
    if not rows:
        return []
    return [
        _item(
            "offer",
            "low",
            _quoted(r["label"]) + " has never been used in a deal",
            r["reason"],
            entity_type=r["entity_type"],
            entity_id=r["entity_id"],
            url=r["url"],
            amount=r["value"],
            action="create_opportunity",
            basis=USER_ENTERED,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# entry point

def attention_center(db: Session, user_id: int, ctx: dict | None = None) -> list:
    """Everything that needs the creator's attention, most urgent first.

    Accepts a pre-built brain snapshot so the Attention Center can be rendered
    inside Today without repeating the underlying reads.
    """
    ctx = ctx or brain.snapshot(db, user_id)
    today = date.today()

    items = []
    items += _money_attention(ctx["owed"])
    items += _deal_attention(ctx["deals"], today, ctx["owed"])
    items += _task_attention(ctx["tasks"], today)
    items += _content_attention(db, user_id, today)
    items += _idea_attention(db, user_id)
    items += _goal_attention(ctx["goals"])
    items += _capacity_attention(ctx["capacity"])
    items += _offer_attention(ctx)

    # a deal that is already reported as an overdue payment should not be counted
    # a second time as a separate "no follow-up" crisis
    seen = set()
    unique = []
    for item in items:
        key = (item["kind"], item["entity_type"], item["entity_id"], item["title"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    unique = _collapse_same_money(unique)

    unique.sort(
        key=lambda i: (SEVERITY_ORDER.get(i["severity"], 9), -(i["age_days"] or 0))
    )
    return unique


def _quoted(label: str) -> str:
    """Wrap a creator's own label in quotes, without doubling ones it already has."""
    text = (label or "").strip()
    if not text:
        return ""
    if any(ch in text for ch in "“”\"'"):
        # the label already carries its own quoting — leave the creator's wording alone
        return text
    return f"“{text}”"


def _group(name: str, amount) -> str | None:
    """Identity of a money obligation: who owes what.

    Two records only collapse when both the counterparty and the amount match, so
    two genuinely separate invoices of the same size are both still reported.
    """
    who = (name or "").strip().lower()
    if not who or not amount:
        return None
    return f"{who}|{round(float(amount), 2)}"


def _collapse_same_money(items: list) -> list:
    """One obligation, one row.

    An unpaid payment and an "overdue deal" often describe the same money — a
    creator may have logged the invoice without linking the two records. The
    payment row is the more precise of the two, so the deal-level money row is
    dropped and its non-money signals (deadline, follow-up) are kept.

    Matching is on the counterparty *and* the amount, never on the amount alone:
    if two different brands each owe the same figure, both obligations are real
    and both must be shown.
    """
    paid_groups = {
        i["group"]
        for i in items
        if i["kind"] == "payment" and i.get("group")
    }
    if not paid_groups:
        return items

    kept = []
    for item in items:
        is_deal_money = (
            item["entity_type"] == "deal" and item["kind"] == "deal" and item.get("amount")
        )
        if is_deal_money and item.get("group") in paid_groups:
            continue
        kept.append(item)
    return kept


def summary(items: list) -> dict:
    counts = {k: 0 for k in ("critical", "high", "medium", "low")}
    money = 0.0
    for item in items:
        counts[item["severity"]] = counts.get(item["severity"], 0) + 1
        if item["kind"] == "payment":
            money += item["amount"] or 0
    return {
        "total": len(items),
        "counts": counts,
        "money_at_risk": money,
        "headline": (
            f"{counts['critical'] + counts['high']} need attention now"
            if counts["critical"] or counts["high"]
            else ("Nothing urgent" if not items else f"{len(items)} things worth a look")
        ),
    }
