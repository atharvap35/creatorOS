from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.recommendation import Recommendation
from app.models.task import Task, TaskStatus
from app.services import activity, attention, brain, health, recommender
from app.templating import templates

router = APIRouter()


def today_context(db: Session, user) -> dict:
    """Everything Today needs, from one snapshot and one ranked pass.

    Today 3.0 is a decision surface, not a dashboard: one decision, three
    next moves, and the reasoning behind each. Every number here comes from the
    creator's own records via the brain snapshot.
    """
    ctx = brain.snapshot(db, user.id)
    items = attention.attention_center(db, user.id, ctx=ctx)
    attention_summary = attention.summary(items)

    ranked = recommender.generate(db, user.id, limit=12)
    recommender.persist_for_day(db, user.id, date.today())
    stored = (
        db.query(Recommendation)
        .filter(Recommendation.user_id == user.id, Recommendation.day == date.today())
        .order_by(Recommendation.score.desc())
        .all()
    )
    seen = {(r["entity_type"], r["entity_id"]) for r in ranked}
    merged = [
        {
            "id": s.id,
            "kind": s.entity_type,
            "title": s.title,
            "reason": s.reason,
            "benefit": s.benefit,
            "effort_minutes": s.effort_minutes,
            "entity_type": s.entity_type,
            "entity_id": s.entity_id,
            "cta": s.cta,
            "url": s.cta_url,
            "score": s.score,
            "score_breakdown": s.score_breakdown,
            "status": s.status,
        }
        for s in stored
    ]

    # three next moves, each with what / why / impact / effort / consequence
    next_moves = []
    for candidate in ranked:
        if len(next_moves) >= 3:
            break
        next_moves.append(candidate)

    return {
        "user": user,
        "now": datetime.now(),
        "ctx": ctx,
        # the single decision
        "one_thing": recommender.best_next_thing(db, user.id, 30),
        "next_moves": next_moves,
        "attention_items": items[:6],
        "attention_summary": attention_summary,
        "focus": merged[:3],
        "all_recommendations": merged,
        "health": health.business_health(db, user.id),
        "workload": recommender.weekly_workload(db, user.id),
        "capacity": ctx["capacity"],
        # named `cash`, not `money`: a context key called `money` would shadow the
        # `money()` currency formatter the template needs
        "cash": ctx["money"],
        "owed": ctx["owed"][:4],
        "money_on_the_table": ctx["money_on_the_table"][:5],
        "recent_events": activity.recent(db, user.id, days=7)[:6],
        "overflow": len([m for m in merged if (m["entity_type"], m["entity_id"]) not in seen]),
    }


@router.get("/today")
def today(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request, name="today.html", context=today_context(db, user)
    )


@router.get("/dashboard")
def dashboard_redirect(user=Depends(get_current_user)):
    return RedirectResponse(url="/today", status_code=303)


@router.post("/today/recommendations/{rec_id}")
def update_recommendation(
    rec_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    action: str = "dismissed",
):
    rec = (
        db.query(Recommendation)
        .filter(Recommendation.id == rec_id, Recommendation.user_id == user.id)
        .first()
    )
    if not rec:
        return RedirectResponse(url="/today", status_code=303)

    if action == "done" and rec.entity_type == "task":
        task = (
            db.query(Task)
            .filter(Task.id == rec.entity_id, Task.user_id == user.id)
            .first()
        )
        if task:
            task.status = TaskStatus.completed
            task.completed_at = datetime.now()
            db.commit()
    rec.status = "done" if action == "done" else "dismissed"
    db.commit()
    return RedirectResponse(url="/today", status_code=303)
