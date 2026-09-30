"""Content calendar: month / week / list, with conflict warnings."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.content import ContentItem, Status
from app.models.deal import BrandDeal
from app.models.task import Task, TaskStatus
from app.templating import templates

router = APIRouter()

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _month_grid(moment: date) -> list:
    first = moment.replace(day=1)
    offset = first.weekday()
    start = first - timedelta(days=offset)
    return [start + timedelta(days=i) for i in range(42)]


def _collect(db: Session, user_id: int, start: date, end: date) -> dict:
    content = (
        db.query(ContentItem)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.due_date.isnot(None),
            ContentItem.due_date >= datetime(start.year, start.month, start.day),
            ContentItem.due_date < datetime(end.year, end.month, end.day) + timedelta(days=1),
        )
        .all()
    )
    publishing = (
        db.query(ContentItem)
        .filter(
            ContentItem.user_id == user_id,
            ContentItem.published_at.isnot(None),
            ContentItem.published_at >= datetime(start.year, start.month, start.day),
            ContentItem.published_at < datetime(end.year, end.month, end.day) + timedelta(days=1),
        )
        .all()
    )
    tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.due_date.isnot(None),
            Task.status != TaskStatus.completed,
            Task.due_date >= datetime(start.year, start.month, start.day),
            Task.due_date < datetime(end.year, end.month, end.day) + timedelta(days=1),
        )
        .all()
    )
    deals = (
        db.query(BrandDeal)
        .filter(
            BrandDeal.user_id == user_id,
            BrandDeal.deadline.isnot(None),
            BrandDeal.deadline >= datetime(start.year, start.month, start.day),
            BrandDeal.deadline < datetime(end.year, end.month, end.day) + timedelta(days=1),
        )
        .all()
    )
    return {"content": content, "publishing": publishing, "tasks": tasks, "deals": deals}


@router.get("/calendar")
def calendar(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    view: str = "month",
    date_param: str = "",
):
    try:
        anchor = datetime.strptime(date_param, "%Y-%m-%d").date() if date_param else date.today()
    except ValueError:
        anchor = date.today()

    if view == "week":
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
        days = [(start + timedelta(days=i), WEEKDAYS[i]) for i in range(7)]
    elif view == "list":
        start = anchor - timedelta(days=30)
        end = anchor + timedelta(days=90)
        days = []
    else:
        start = anchor.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        days = [(d, WEEKDAYS[d.weekday()]) for d in _month_grid(anchor)]

    items = _collect(db, user.id, start, end)

    by_day = {}
    for entry in items["content"]:
        by_day.setdefault(entry.due_date.date(), []).append(("content", entry))
    for entry in items["publishing"]:
        by_day.setdefault(entry.published_at.date(), []).append(("published", entry))
    for entry in items["tasks"]:
        by_day.setdefault(entry.due_date.date(), []).append(("task", entry))
    for entry in items["deals"]:
        by_day.setdefault(entry.deadline.date(), []).append(("deal", entry))

    conflicts = []
    for day, entries in by_day.items():
        commitments = [e for kind, e in entries if kind in ("content", "deal")]
        if len(commitments) >= 4:
            conflicts.append({"day": day, "count": len(commitments)})

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "user": user,
            "view": view,
            "anchor": anchor,
            "start": start,
            "end": end,
            "days": days,
            "by_day": by_day,
            "conflicts": conflicts,
            "counts": {k: len(v) for k, v in items.items()},
            "prev": (start - timedelta(days=1)).isoformat(),
            "next": (end + timedelta(days=1)).isoformat(),
        },
    )
