"""The activity timeline: a chronological record of the creator business.

Events are written by the service layer when something real happens — an idea is
converted, a deal is created, a payment lands, content is published. The timeline
is therefore a genuine history, not a generated narrative.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.business import ActivityEvent

KIND_LABELS = {
    "idea": "Idea",
    "content": "Content",
    "deal": "Deal",
    "deliverable": "Deliverable",
    "revenue": "Money",
    "task": "Workflow",
    "opportunity": "Opportunity",
    "goal": "Goal",
    "series": "Series",
    "offer": "Offer",
}


def record(
    db: Session,
    user_id: int,
    kind: str,
    title: str,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    detail: str | None = None,
    amount: float | None = None,
    occurred_at: datetime | None = None,
    commit: bool = True,
) -> ActivityEvent:
    """Append one event to the creator's business timeline."""
    event = ActivityEvent(
        user_id=user_id,
        kind=kind,
        entity_type=entity_type,
        entity_id=entity_id,
        title=title,
        detail=detail,
        amount=amount,
        occurred_at=occurred_at or datetime.now(),
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    else:
        db.flush()
    return event


def timeline(
    db: Session,
    user_id: int,
    *,
    limit: int = 60,
    before: datetime | None = None,
    kinds: tuple | None = None,
    days: int | None = None,
) -> list:
    query = db.query(ActivityEvent).filter(ActivityEvent.user_id == user_id)
    if before:
        query = query.filter(ActivityEvent.occurred_at < before)
    if days:
        query = query.filter(ActivityEvent.occurred_at >= datetime.now() - timedelta(days=days))
    if kinds:
        query = query.filter(ActivityEvent.kind.in_(kinds))
    return query.order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc()).limit(limit).all()


def grouped(db: Session, user_id: int, *, limit: int = 60, days: int | None = None, kind: str | None = None) -> list:
    """Events grouped by day, newest first, for a readable timeline."""
    rows = []
    for event in timeline(
        db, user_id, limit=limit, days=days, kinds=(kind,) if kind else None
    ):
        day = event.occurred_at.date()
        if not rows or rows[-1]["day"] != day:
            rows.append({"day": day, "events": []})
        rows[-1]["events"].append(event)
    return rows


def recent(db: Session, user_id: int, *, days: int = 7) -> list:
    since = datetime.now() - timedelta(days=days)
    return (
        db.query(ActivityEvent)
        .filter(ActivityEvent.user_id == user_id, ActivityEvent.occurred_at >= since)
        .order_by(ActivityEvent.occurred_at.desc())
        .all()
    )
