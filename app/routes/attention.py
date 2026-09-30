"""Attention Center and activity timeline."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.services import activity, attention, brain
from app.templating import templates

router = APIRouter()


@router.get("/attention")
def attention_view(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    kind: str = "",
):
    """Everything decaying, waiting, or slipping — most urgent first.

    Grouped by severity rather than by surface, so the same problem is never
    reported twice from two different pages.
    """
    ctx = brain.snapshot(db, user.id)
    items = attention.attention_center(db, user.id, ctx=ctx)
    if kind:
        items = [i for i in items if i["kind"] == kind]

    groups = {}
    for item in items:
        groups.setdefault(item["severity"], []).append(item)

    return templates.TemplateResponse(
        request=request,
        name="attention.html",
        context={
            "user": user,
            "items": items,
            "groups": [(s, groups[s]) for s in ("critical", "high", "medium", "low") if s in groups],
            "summary": attention.summary(items),
            "kinds": sorted({i["kind"] for i in items}),
            "active_kind": kind,
            "capacity": ctx["capacity"],
        },
    )


@router.get("/timeline")
def timeline_view(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    kind: str = "",
    days: int = 30,
):
    """The creator's real history, newest first, grouped by day."""
    days = max(1, min(int(days or 30), 365))
    grouped = activity.grouped(db, user.id, days=days, kind=kind or None, limit=200)
    events = [e for row in grouped for e in row["events"]]
    return templates.TemplateResponse(
        request=request,
        name="timeline.html",
        context={
            "user": user,
            "grouped": grouped,
            "event_count": len(events),
            "days": days,
            "kinds": sorted({e.kind for e in events}),
            "active_kind": kind,
        },
    )
