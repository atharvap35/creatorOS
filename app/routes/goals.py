from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.content import ContentItem, Status
from app.models.deal import BrandDeal
from app.models.goal import CreatorGoal
from app.models.revenue import Revenue, RevenueStatus
from app.route_utils import clean, parse_optional_datetime, parse_optional_float
from app.templating import templates

router = APIRouter()

CATEGORIES = {
    "revenue": "Revenue",
    "content": "Content",
    "deals": "Deals",
    "product": "Product",
    "consistency": "Consistency",
}


def _progress(db: Session, goal: CreatorGoal) -> float:
    if not goal.target_value:
        return 0.0
    return min(round(goal.current_value / goal.target_value * 100), 100)


def _refresh_current_values(db: Session, user_id: int) -> None:
    """Recompute live progress from the creator's own data."""
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for goal in db.query(CreatorGoal).filter(CreatorGoal.user_id == user_id, CreatorGoal.status == "active").all():
        if goal.metric == "monthly_revenue":
            goal.current_value = (
                db.query(Revenue)
                .filter(
                    Revenue.user_id == user_id,
                    Revenue.status == RevenueStatus.received,
                    Revenue.date >= month_start,
                )
                .with_entities(Revenue.amount)
                .all()
            )
            goal.current_value = sum(row[0] or 0 for row in goal.current_value)
        elif goal.metric == "published_items":
            goal.current_value = (
                db.query(ContentItem)
                .filter(
                    ContentItem.user_id == user_id,
                    ContentItem.status == Status.published,
                    ContentItem.published_at >= month_start,
                )
                .count()
            )
        elif goal.metric == "closed_deals":
            goal.current_value = (
                db.query(BrandDeal)
                .filter(BrandDeal.user_id == user_id, BrandDeal.stage == "completed")
                .count()
            )
        elif goal.metric == "paid_deals":
            goal.current_value = (
                db.query(BrandDeal)
                .filter(BrandDeal.user_id == user_id, BrandDeal.payment_status == "paid")
                .count()
            )
        if goal.deadline and goal.deadline < date.today() and goal.current_value < goal.target_value:
            goal.status = "archived"
    db.commit()


@router.get("/goals")
def list_goals(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _refresh_current_values(db, user.id)
    goals = db.query(CreatorGoal).filter(CreatorGoal.user_id == user.id).order_by(CreatorGoal.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="goals.html",
        context={
            "user": user,
            "goals": goals,
            "categories": CATEGORIES,
            "progress": {g.id: _progress(db, g) for g in goals},
        },
    )


@router.post("/goals")
def create_goal(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    title: str = Form(...),
    category: str = Form("revenue"),
    metric: str = Form(""),
    target_value: str = Form("0"),
    unit: str = Form(""),
    deadline: str = Form(""),
    notes: str = Form(""),
):
    db.add(
        CreatorGoal(
            user_id=user.id,
            title=title.strip(),
            category=category,
            metric=metric,
            target_value=parse_optional_float(target_value, 0.0),
            current_value=0.0,
            unit=unit.strip(),
            deadline=parse_optional_datetime(deadline).date() if parse_optional_datetime(deadline) else None,
            notes=clean(notes),
        )
    )
    db.commit()
    return RedirectResponse(url="/goals", status_code=303)


@router.post("/goals/{goal_id}/update")
def update_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    current_value: str = Form(""),
    status: str = Form("active"),
):
    goal = db.query(CreatorGoal).filter(CreatorGoal.id == goal_id, CreatorGoal.user_id == user.id).first()
    if goal:
        if current_value != "":
            goal.current_value = parse_optional_float(current_value, goal.current_value)
        if status in ("active", "achieved", "paused", "archived"):
            goal.status = status
        db.commit()
    return RedirectResponse(url="/goals", status_code=303)


@router.post("/goals/{goal_id}/delete")
def delete_goal(goal_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    goal = db.query(CreatorGoal).filter(CreatorGoal.id == goal_id, CreatorGoal.user_id == user.id).first()
    if goal:
        db.delete(goal)
        db.commit()
    return RedirectResponse(url="/goals", status_code=303)
