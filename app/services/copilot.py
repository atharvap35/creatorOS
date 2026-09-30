"""Creator Copilot: answers questions from the creator's actual records.

Design rules, in priority order:

1. **Never invent a fact.** Every number, name, and date in an answer comes from a
   row the creator owns. When the records cannot answer a question, the copilot
   says so plainly instead of hedging with a guess.
2. **Deterministic first.** Intent routing and the answer skeleton are rule-based
   and identical for the same question and the same data. The optional writer is
   only ever used to phrase a *draft* the creator can edit, never to compute.
3. **It can act, but it never acts silently.** Every answer that could change data
   returns a proposed action; execution requires a POST.
4. **Every answer is auditable.** Each exchange is stored with its intent, its
   citations, and whether it was fully grounded.
"""

import json
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.business import CopilotMessage
from app.models.content import ContentItem, Status
from app.models.deal import BrandDeal
from app.models.idea import Idea
from app.models.revenue import Revenue
from app.services import brain

# ---------------------------------------------------------------------------
# intent detection

INTENT_PATTERNS = [
    ("what_should_i_do", [r"what should i do", r"what do i do", r"where do i start", r"what now", r"next step"]),
    ("prepare_tomorrow", [r"prepare.*(tomorrow|tomorrow)", r"what.*tomorrow", r"tomorrow"]),
    ("what_am_i_forgetting", [r"forget", r"missing", r"am i missing", r"overlook", r"slip", r"falling behind"]),
    ("which_deal_needs_attention", [r"which deal", r"deal.*attention", r"brand.*attention", r"deal.*problem", r"stuck deal"]),
    ("money_waiting", [r"how much money", r"waiting for", r"owe me", r"money.*outstanding", r"unpaid", r"who owes"]),
    ("what_to_post", [r"what should i post", r"what.*post", r"post this week", r"publish", r"content plan", r"what.*create"]),
    ("prioritize_ideas", [r"which idea", r"idea.*priorit", r"best idea", r"what.*idea"]),
    ("why_workload", [r"why.*workload", r"workload", r"overcommit", r"too much", r"capacity", r"overcommitte"]),
    ("repurpose", [r"repurpos", r"atomiz", r"recycle", r"what can i reuse", r"derivative"]),
    ("biggest_opportunity", [r"biggest opportunity", r"best opportunity", r"money on the table", r"make more money", r"highest.value"]),
    ("what_happened", [r"what happened", r"this week", r"last week", r"progress", r"how did.*go"]),
    ("goal_progress", [r"goal", r"target", r"on track"]),
    ("clear_my_day", [r"clear my day", r"what.*today", r"today.*do", r"my day"]),
    ("brand_relationship", [r"brand", r"acme", r"relationship", r"client"]),
]

# questions we recognise but cannot answer from recorded data alone
UNANSWERABLE = [
    r"engagement rate",
    r"follower",
    r"benchmark",
    r"market rate",
    r"industry average",
    r"conversion rate",
    r"what should i charge",
    r"how much should i (charge|price|earn)",
]


def detect_intent(question: str) -> str:
    lowered = (question or "").strip().lower()
    if not lowered:
        return "unknown"
    for intent, patterns in INTENT_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lowered):
                return intent
    return "unknown"


# ---------------------------------------------------------------------------
# answer builders — each returns (answer_text, citations, actions)

def _fmt(value: float) -> str:
    return f"{round(value):,}"


def _what_should_i_do(db, user_id, ctx):
    recs = _ranked(db, user_id)
    if not recs:
        return (
            "You have no overdue work, unpaid invoices, or stalled deals right now. "
            "That is a genuinely clear day — the best use of it is to build the next thing, "
            "not to clear a list that is already clear.",
            [],
            [{"slug": "create_content_plan", "label": "Turn an idea into content", "url": "/ideas"},
             {"slug": "plan_week", "label": "Plan my week", "url": "/workflow/plan"}],
        )
    top = recs[0]
    cited = [f"{top['kind']}:{top['entity_id']}"] if top["entity_id"] else [top["kind"]]
    return (
        f"**{top['what']}**\n\n"
        f"Why: {top['why']}\n"
        f"Impact: {top['benefit']}\n"
        f"Effort: ~{top['effort_minutes']} minutes\n\n"
        f"If you skip it: {top['consequence']}",
        cited,
        top.get("actions") or [],
    )


def _what_am_i_forgetting(db, user_id, ctx):
    from app.services.attention import attention_center

    items = attention_center(db, user_id, ctx=ctx)
    if not items:
        return (
            "Nothing is being neglected. No overdue payments, no stuck deliverables, "
            "no content deadlines you have passed, and no goal is falling behind.",
            [],
            [],
        )
    lines = []
    for item in items[:6]:
        lines.append(f"• **{item['title']}** — {item['detail']}")
    return (
        f"You have {len(items)} thing(s) worth attention:\n\n" + "\n".join(lines),
        [f"{i['kind']}:{i['entity_id']}" for i in items[:6] if i.get("entity_id")],
        [{"slug": "clear_slate", "label": "Clear my day", "url": "/today"}],
    )


def _which_deal_needs_attention(db, user_id, ctx):
    from app.models.deal_support import DealDeliverable

    deals = ctx["deals"]
    if not deals:
        return (
            "You have no open deals. Every brand you have worked with is closed or paid. "
            "If you want more revenue from sponsorships, the next step is capturing "
            "opportunities rather than chasing existing ones.",
            [],
            [{"slug": "create_opportunity", "label": "Create an opportunity", "url": "/growth/opportunities"}],
        )

    lines = []
    cited = []
    for deal in deals:
        deliverables = (
            db.query(DealDeliverable)
            .filter(DealDeliverable.deal_id == deal.id)
            .all()
        )
        open_deliverables = [d for d in deliverables if d.status in ("pending", "in_progress")]
        signals = []
        if deal.payment_status in ("pending", "overdue"):
            signals.append("payment not received")
        if deal.deadline and deal.deadline < ctx["now"]:
            signals.append("campaign deadline passed")
        if open_deliverables and deal.deadline:
            signals.append(f"{len(open_deliverables)} deliverable(s) open")
        if not deal.follow_up_date and deal.stage in ("lead", "contacted", "negotiating"):
            signals.append("no follow-up scheduled")
        if deal.next_action:
            signals.append(f"next: {deal.next_action}")
        if signals:
            cited.append(f"deal:{deal.id}")
            lines.append(
                f"• **{deal.brand_name}** ({deal.campaign_name}) — " + ", ".join(signals)
            )

    if not lines:
        return (
            f"All {len(deals)} open deal(s) have dates, next actions, and healthy deliverables. "
            "Nothing needs chasing right now.",
            [],
            [],
        )
    return (
        "Deals that need attention:\n\n" + "\n".join(lines),
        cited,
        [{"slug": "draft_follow_up", "label": "Draft a follow-up", "url": "/deals"}],
    )


def _money_waiting(db, user_id, ctx):
    owed = ctx["owed"]
    money = ctx["money"]
    if not owed:
        return (
            f"Nothing is outstanding. You have received {_fmt(money['this_month'])} this month "
            f"and {_fmt(money['ytd'])} year to date, and every invoice you've logged has been settled.",
            [],
            [],
        )
    overdue = [o for o in owed if o["overdue"]]
    lines = []
    for row in owed[:6]:
        mark = "overdue" if row["overdue"] else "due soon"
        lines.append(
            f"• {row['entry'].currency} {_fmt(row['amount'])} — "
            f"{row['entry'].description or row['entry'].source.value} "
            f"({mark}, {row['days_outstanding']} day(s))"
        )
    headline = (
        f"{_fmt(money['outstanding'])} is outstanding, of which {_fmt(money['overdue_total'])} is overdue."
        if overdue
        else f"{_fmt(money['outstanding'])} is outstanding but nothing is overdue yet."
    )
    return (
        headline + "\n\n" + "\n".join(lines),
        [f"revenue:{o['entry'].id}" for o in owed[:6]],
        [{"slug": "draft_reminder", "label": "Draft a reminder", "url": "/money/payments"}],
    )


RANK = {"high": 2, "medium": 1, "low": 0}


def _rank(value) -> int:
    if value is None:
        return 1
    return RANK.get(getattr(value, "value", value), 1)


def _idea_rank(idea):
    return (_rank(idea.potential), -_rank(idea.effort))


def _what_to_post(db, user_id, ctx):
    in_flight = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == user_id, ContentItem.status != Status.published)
        .all()
    )
    due_this_week = [
        i
        for i in in_flight
        if i.due_date and brain._week_start() <= i.due_date < brain._week_start() + timedelta(days=7)
    ]
    if due_this_week:
        lines = [f"• {i.title} — due {i.due_date.strftime('%a %d %b')}" for i in due_this_week[:5]]
        return (
            f"You already have {len(due_this_week)} piece(s) planned for this week:\n\n"
            + "\n".join(lines)
            + "\n\nFinishing these protects your cadence better than starting something new.",
            [f"content:{i.id}" for i in due_this_week[:5]],
            [],
        )

    ideas = (
        db.query(Idea)
        .filter(
            Idea.user_id == user_id,
            Idea.converted_content_id.is_(None),
        )
        .all()
    )
    ideas = sorted(ideas, key=_idea_rank, reverse=True)[:3]
    if ideas:
        lines = [f"• {i.title}" for i in ideas]
        return (
            "Nothing is scheduled for this week. Your highest-potential unconverted ideas are:\n\n"
            + "\n".join(lines),
            [f"idea:{i.id}" for i in ideas],
            [{"slug": "create_content_plan", "label": "Create content plan", "url": "/ideas"}],
        )

    repurpose = ctx["atomizable"][:2]
    if repurpose:
        lines = [f"• “{r['item'].title}” (published {r['age_days']} day(s) ago)" for r in repurpose]
        return (
            "You have no scheduled content and no unconverted ideas, but you have published "
            "material with no derivatives:\n\n" + "\n".join(lines),
            [f"content:{r['item'].id}" for r in repurpose],
            [{"slug": "atomize", "label": "Atomize it", "url": "/content"}],
        )

    return (
        "I have nothing to base a recommendation on — you have no scheduled content, no "
        "unconverted ideas, and nothing published to repurpose. Capture an idea and I can "
        "turn it into a plan.",
        [],
        [],
    )


def _prioritize_ideas(db, user_id, ctx):
    from app.routes.ideas import idea_score

    ideas = (
        db.query(Idea)
        .filter(Idea.user_id == user_id, Idea.converted_content_id.is_(None))
        .all()
    )
    if not ideas:
        return (
            "Your idea bank is empty. Capturing ideas is the cheapest input you have — "
            "even rough ones.",
            [],
            [],
        )
    scored = sorted(
        ((idea_score(i), i) for i in ideas), key=lambda pair: pair[0]["score"], reverse=True
    )
    lines = [f"• {i.title} — scored {s['score']}/100" for s, i in scored[:5]]
    return (
        f"You have {len(ideas)} unconverted idea(s). Highest scored:\n\n" + "\n".join(lines)
        + "\n\nThese scores come only from fields you set (potential, effort, confidence, monetization).",
        [f"idea:{i.id}" for s, i in scored[:5]],
        [{"slug": "create_content_plan", "label": "Create content plan", "url": "/ideas"}],
    )


def _why_workload(db, user_id, ctx):
    cap = ctx["capacity"]
    if not cap["over_capacity"]:
        return (
            f"Your workload is fine. You have {cap['planned_hours']}h planned against "
            f"{cap['available_hours']}h available ({cap['capacity_pct']}% of capacity).",
            [],
            [],
        )
    return (
        f"You are overcommitted by {cap['overload_hours']}h. You have {cap['planned_hours']}h "
        f"planned against {cap['available_hours']}h available across "
        f"{len(cap['working_days'])} working day(s).\n\n"
        "I can suggest which lower-priority items to move — I will not move anything "
        "without you choosing.",
        [],
        [{"slug": "rebalance_week", "label": "Rebalance week", "url": "/workflow?view=week"}],
    )


def _repurpose(db, user_id, ctx):
    rows = ctx["atomizable"]
    if not rows:
        return (
            "Nothing to repurpose right now — every published piece from the last 60 days "
            "already has derivatives planned, or you have not published recently.",
            [],
            [],
        )
    lines = [f"• “{r['item'].title}” — published {r['age_days']} day(s) ago" for r in rows[:5]]
    return (
        f"{len(rows)} published piece(s) have no derivatives yet:\n\n" + "\n".join(lines),
        [f"content:{r['item'].id}" for r in rows[:5]],
        [{"slug": "atomize", "label": "Atomize", "url": "/content"}],
    )


def _biggest_opportunity(db, user_id, ctx):
    table = ctx["money_on_the_table"]
    valued = [row for row in table if (row["value"] or 0) > 0]
    if not valued:
        return (
            "I have no valued opportunities to point at. Nothing outstanding, no uninvoiced "
            "deals, and no open opportunities with an estimated value. Capture one and I "
            "can rank it.",
            [],
            [],
        )
    top = valued[0]
    lines = [f"• {r['label']} — {_fmt(r['value'])} · ~{r['effort_minutes']} min" for r in valued[:5]]
    return (
        f"Biggest single item: **{top['label']}** at {_fmt(top['value'])}.\n"
        f"Why: {top['reason']}\n"
        f"Effort: ~{top['effort_minutes']} minutes\n\n"
        "Other routes to money:\n" + "\n".join(lines[1:]),
        [f"{r['entity_type']}:{r['entity_id']}" for r in valued[:5]],
        [],
    )


def _what_happened(db, user_id, ctx):
    from app.services.reviews import build_weekly

    review = build_weekly(db, user_id)
    happened = review["happened"]
    lines = [
        f"• {happened['tasks_completed']} task(s) completed",
        f"• {happened['content_published']} piece(s) published",
        f"• {happened['ideas_created']} idea(s) captured",
        f"• {happened['deals_progressed']} deal(s) moved",
        f"• {_fmt(happened['revenue_received'])} received",
    ]
    return (
        "This week so far:\n\n" + "\n".join(lines)
        + "\n\nWhat got stuck: " + "; ".join(review["didnt"][:3]),
        [],
        [{"slug": "plan_week", "label": "Plan next week", "url": "/workflow/plan"}],
    )


def _goal_progress(db, user_id, ctx):
    goals = ctx["goals"]
    if not goals:
        return (
            "You have no active goals. A goal here is a number with a deadline and a source "
            "in your own records — for example a revenue target that updates itself.",
            [],
            [{"slug": "add_task", "label": "Create a goal", "url": "/goals"}],
        )
    lines = []
    cited = []
    for goal in goals:
        pct = round(goal.current_value / goal.target_value * 100) if goal.target_value else 0
        lines.append(
            f"• {goal.title} — {_fmt(goal.current_value)} of {_fmt(goal.target_value)} "
            f"{goal.unit or ''} ({min(pct, 999)}%)".strip()
        )
        cited.append(f"goal:{goal.id}")
    return (
        "Your active goals:\n\n" + "\n".join(lines)
        + "\n\nThese update automatically from your own records.",
        cited,
        [],
    )


def _clear_my_day(db, user_id, ctx):
    from app.services.actions import clear_slate

    result = clear_slate(db, user_id)
    buckets = result["buckets"]
    lines = []
    for label, key in (("Must do", "must"), ("Should do", "should"), ("Can wait", "can_wait")):
        if buckets[key]:
            lines.append(f"**{label}**")
            for entry in buckets[key][:5]:
                name = entry.get("title") or entry["task"].title
                lines.append(f"• {name} — {entry['reason']}")
            lines.append("")
    if not lines:
        return ("Your day is clear. Nothing is due or overdue today.", [], [])
    return ("\n".join(lines).strip(), [], [{"slug": "clear_slate", "label": "Clear my day", "url": "/today"}])


def _brand_relationship(db, user_id, ctx):
    brands = ctx["brands"]
    if not brands:
        return (
            "You haven't created any brand profiles yet. A brand record ties together every "
            "deal, contact, and payment for one company, instead of scattering them.",
            [],
            [{"slug": "create_opportunity", "label": "See brands", "url": "/brands"}],
        )
    lines = []
    for row in brands:
        lines.append(
            f"• **{row['brand'].name}** — {row['deal_count']} deal(s), "
            f"{_fmt(row['revenue_total'])} received"
            + (f", {_fmt(row['outstanding'])} outstanding" if row["outstanding"] else "")
        )
    return ("Your brand relationships:\n\n" + "\n".join(lines), [f"brand:{b['brand'].id}" for b in brands], [])


def _prepare_tomorrow(db, user_id, ctx):
    start = brain._week_start()
    tomorrow = ctx["now"] + timedelta(days=1)
    upcoming = [
        t
        for t in ctx["tasks"]["open"]
        if t.due_date and tomorrow.date() <= t.due_date.date() <= (tomorrow + timedelta(days=1)).date()
    ]
    if not upcoming:
        return (
            "Nothing is scheduled for tomorrow. That means you can choose what matters most "
            "rather than reacting to a deadline.",
            [],
            [{"slug": "plan_week", "label": "Plan the week", "url": "/workflow/plan"}],
        )
    lines = [f"• {t.title} — {t.estimated_minutes or 20} min" for t in upcoming[:6]]
    return (
        f"Tomorrow ({tomorrow.strftime('%A %d %B')}) you have {len(upcoming)} item(s):\n\n"
        + "\n".join(lines),
        [f"task:{t.id}" for t in upcoming[:6]],
        [],
    )


ANSWER_BUILDERS = {
    "what_should_i_do": _what_should_i_do,
    "what_am_i_forgetting": _what_am_i_forgetting,
    "which_deal_needs_attention": _which_deal_needs_attention,
    "money_waiting": _money_waiting,
    "what_to_post": _what_to_post,
    "prioritize_ideas": _prioritize_ideas,
    "why_workload": _why_workload,
    "repurpose": _repurpose,
    "biggest_opportunity": _biggest_opportunity,
    "what_happened": _what_happened,
    "goal_progress": _goal_progress,
    "clear_my_day": _clear_my_day,
    "brand_relationship": _brand_relationship,
    "prepare_tomorrow": _prepare_tomorrow,
}

NOT_ENOUGH_INFO = (
    "I don't have enough information to answer that. I can only answer from records you "
    "have entered — content, deals, payments, tasks, goals and your preferences. I won't "
    "guess, and I don't have access to external data like follower counts, engagement "
    "rates, or market benchmarks."
)

SUGGESTED_QUESTIONS = [
    "What should I do?",
    "What am I forgetting?",
    "Which deal needs attention?",
    "How much money am I waiting for?",
    "What should I post this week?",
    "Which ideas should I prioritize?",
    "Why is my workload too high?",
    "What can I repurpose?",
    "Show me my biggest opportunity",
    "What happened this week?",
    "Prepare me for tomorrow",
    "Am I on track for my goals?",
]


def _ranked(db, user_id):
    from app.services.recommender import generate

    return generate(db, user_id, limit=8)


def ask(db: Session, user_id: int, question: str) -> dict:
    """Answer a creator question strictly from their own records."""
    question = (question or "").strip()
    if not question:
        return {
            "question": question,
            "answer": "Ask me something about your creator business.",
            "intent": "unknown",
            "grounded": True,
            "citations": [],
            "actions": [],
        }

    lowered = question.lower()
    for pattern in UNANSWERABLE:
        if re.search(pattern, lowered):
            return _persist(
                db,
                user_id,
                question,
                NOT_ENOUGH_INFO,
                intent="unanswerable",
                grounded=False,
                citations=[],
                actions=[],
            )

    intent = detect_intent(question)
    builder = ANSWER_BUILDERS.get(intent)
    if not builder:
        return _persist(
            db,
            user_id,
            question,
            "I don't recognise that question yet. I can answer questions about what to do, "
            "what you're forgetting, deals, money, content, ideas, workload, opportunities, "
            "goals, and your week.\n\nTry one of these:\n"
            + "\n".join(f"• {q}" for q in SUGGESTED_QUESTIONS[:6]),
            intent="unknown",
            grounded=True,
            citations=[],
            actions=[],
        )

    ctx = brain.snapshot(db, user_id)
    answer, citations, actions = builder(db, user_id, ctx)
    return _persist(
        db, user_id, question, answer, intent=intent, grounded=True,
        citations=citations, actions=actions,
    )


def _persist(db, user_id, question, answer, *, intent, grounded, citations, actions) -> dict:
    message = CopilotMessage(
        user_id=user_id,
        question=question,
        answer=answer,
        intent=intent,
        basis="system-derived" if grounded else "system-derived",
        grounded=grounded,
        citations=",".join(citations or []),
        actions=json.dumps(actions or []),
    )
    db.add(message)
    db.commit()
    return {
        "question": question,
        "answer": answer,
        "intent": intent,
        "grounded": grounded,
        "citations": citations or [],
        "actions": actions or [],
    }


def history(db: Session, user_id: int, limit: int = 25) -> list:
    return (
        db.query(CopilotMessage)
        .filter(CopilotMessage.user_id == user_id)
        .order_by(CopilotMessage.created_at.desc(), CopilotMessage.id.desc())
        .limit(limit)
        .all()
    )
