from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.brief import ContentBrief
from app.models.content import ContentItem, ContentType, Platform, Status
from app.models.idea import Idea, IdeaEffort, IdeaPotential, IdeaStatus, IdeaType
from app.models.pillar import ContentPillar
from app.models.task import Task, TaskCategory, TaskPriority, TaskStatus
from app.route_utils import clean, parse_enum
from app.services import activity
from app.templating import templates

router = APIRouter()


def idea_score(idea: Idea) -> dict:
    """Explainable idea score. Every input is visible to the creator."""
    potential = getattr(idea.potential, "value", str(idea.potential))
    effort = getattr(idea.effort, "value", str(idea.effort))
    confidence = getattr(idea.confidence, "value", idea.confidence) or "medium"
    monetization = getattr(idea.monetization_potential, "value", idea.monetization_potential) or "medium"

    parts = []
    score = 0

    points = {"high": 40, "medium": 25, "low": 10}
    score += points.get(potential, 25)
    parts.append({"label": "Potential", "value": potential, "points": points.get(potential, 25)})

    points = {"low": 20, "medium": 12, "high": 5}
    score += points.get(effort, 12)
    parts.append({"label": "Effort", "value": effort, "points": points.get(effort, 12)})

    points = {"high": 20, "medium": 12, "low": 5}
    score += points.get(confidence, 12)
    parts.append({"label": "Confidence", "value": confidence, "points": points.get(confidence, 12)})

    points = {"high": 15, "medium": 9, "low": 4}
    score += points.get(monetization, 9)
    parts.append({"label": "Monetization", "value": monetization, "points": points.get(monetization, 9)})

    gap = 5 if idea.description else 0
    score += gap
    parts.append({"label": "Defined", "value": "has a description" if idea.description else "needs a problem statement", "points": gap})

    return {"score": min(score, 100), "parts": parts}


@router.get("/ideas")
def list_ideas(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    q: str = "",
    status_filter: str = "",
):
    query = db.query(Idea).filter(Idea.user_id == user.id)

    if q:
        query = query.filter(Idea.title.ilike(f"%{q.strip()}%"))
    if status_filter:
        parsed = parse_enum(IdeaStatus, status_filter)
        if parsed:
            query = query.filter(Idea.status == parsed)

    ideas = query.order_by(Idea.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="ideas.html",
        context={
            "user": user,
            "ideas": ideas,
            "q": q,
            "status_filter": status_filter,
            "scores": {i.id: idea_score(i) for i in ideas},
            "pillars": db.query(ContentPillar).filter(ContentPillar.user_id == user.id).all(),
        },
    )


@router.post("/ideas")
def create_idea(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    title: str = Form(...),
    description: str = Form(""),
    type: str = Form("content"),
    potential: str = Form("medium"),
    effort: str = Form("medium"),
    problem: str = Form(""),
    audience: str = Form(""),
    platform: str = Form(""),
    confidence: str = Form("medium"),
    monetization_potential: str = Form("medium"),
):
    new_idea = Idea(
        user_id=user.id,
        title=title.strip(),
        description=clean(description),
        type=parse_enum(IdeaType, type, IdeaType.other),
        potential=parse_enum(IdeaPotential, potential, IdeaPotential.medium),
        effort=parse_enum(IdeaEffort, effort, IdeaEffort.medium),
        status=IdeaStatus.backlog,
        problem=clean(problem),
        audience=clean(audience),
        platform=clean(platform),
        confidence=confidence,
        monetization_potential=monetization_potential,
    )
    db.add(new_idea)
    db.commit()
    return RedirectResponse(url="/ideas", status_code=303)


@router.get("/ideas/{idea_id}")
def idea_detail(idea_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    idea = db.query(Idea).filter(Idea.id == idea_id, Idea.user_id == user.id).first()
    if not idea:
        return RedirectResponse(url="/ideas", status_code=303)

    converted = None
    if idea.converted_content_id:
        converted = (
            db.query(ContentItem)
            .filter(ContentItem.id == idea.converted_content_id, ContentItem.user_id == user.id)
            .first()
        )
    return templates.TemplateResponse(
        request=request,
        name="idea_detail.html",
        context={
            "user": user,
            "idea": idea,
            "score": idea_score(idea),
            "converted": converted,
            "pillars": db.query(ContentPillar).filter(ContentPillar.user_id == user.id).all(),
        },
    )


@router.post("/ideas/{idea_id}/turn-into-content")
def turn_into_content(
    idea_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    platform: str = Form(""),
    content_type: str = Form(""),
    due_date: str = Form(""),
):
    """One click: content record + brief + first production task."""
    idea = db.query(Idea).filter(Idea.id == idea_id, Idea.user_id == user.id).first()
    if not idea:
        return RedirectResponse(url="/ideas", status_code=303)

    chosen_platform = platform or idea.platform or "instagram"
    chosen_type = content_type or (idea.type.value if hasattr(idea.type, "value") else "video")
    deadline = datetime.now() + timedelta(days=7)

    item = ContentItem(
        user_id=user.id,
        title=idea.title,
        description=idea.problem or idea.description,
        platform=parse_enum(Platform, chosen_platform, Platform.other),
        content_type=parse_enum(ContentType, chosen_type, ContentType.other),
        status=Status.idea,
        source="idea",
        topic=idea.audience,
        pillar_id=idea.pillar_id,
        due_date=datetime.strptime(due_date, "%Y-%m-%d") if due_date else deadline,
    )
    db.add(item)
    db.commit()

    db.add(
        ContentBrief(
            user_id=user.id,
            content_id=item.id,
            audience=idea.audience,
            core_idea=idea.description or idea.problem,
        )
    )
    db.add(
        Task(
            user_id=user.id,
            title=f"Outline and script: {idea.title}",
            description=idea.problem or "Start with the outline from the content brief.",
            category=TaskCategory.content,
            priority=TaskPriority.high,
            status=TaskStatus.todo,
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
        user.id,
        "idea",
        f"Converted idea “{idea.title}” into a content plan",
        entity_type="content",
        entity_id=item.id,
        detail="Created the content record, a brief, and the first production task.",
    )
    return RedirectResponse(url=f"/content/{item.id}", status_code=303)


@router.post("/ideas/{idea_id}/status")
def set_idea_status(
    idea_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    status: str = Form(...),
):
    idea = db.query(Idea).filter(Idea.id == idea_id, Idea.user_id == user.id).first()
    if idea:
        idea.status = parse_enum(IdeaStatus, status, idea.status)
        db.commit()
    return RedirectResponse(url="/ideas", status_code=303)


@router.post("/ideas/{idea_id}/delete")
def delete_idea(idea_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    idea = db.query(Idea).filter(Idea.id == idea_id, Idea.user_id == user.id).first()
    if idea:
        db.delete(idea)
        db.commit()
    return RedirectResponse(url="/ideas", status_code=303)
