from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.brief import ContentBrief
from app.models.content import ContentItem, ContentType, Platform, Status
from app.models.pillar import ContentPillar
from app.models.repurpose import ContentRepurpose
from app.models.task import Task, TaskStatus
from app.route_utils import clean, parse_enum, parse_optional_datetime
from app.services import activity
from app.services import ai as ai_service
from app.templating import templates

router = APIRouter()

PIPELINE_STAGES = ["idea", "scripting", "filming", "editing", "ready", "published"]

REPURPOSE_KINDS = [
    ("reel", "Instagram Reel", "instagram"),
    ("short", "Short-form hook", "tiktok"),
    ("post", "LinkedIn post", "linkedin"),
    ("thread", "X thread", "x"),
    ("carousel", "Carousel", "instagram"),
    ("story", "Story set", "instagram"),
    ("newsletter", "Newsletter topic", "newsletter"),
    ("community", "Community discussion", "other"),
]


@router.get("/content")
def list_content(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    q: str = "",
    status_filter: str = "",
    view: str = "list",
):
    query = db.query(ContentItem).filter(ContentItem.user_id == user.id)

    if q:
        query = query.filter(ContentItem.title.ilike(f"%{q.strip()}%"))
    if status_filter:
        parsed = parse_enum(Status, status_filter)
        if parsed:
            query = query.filter(ContentItem.status == parsed)

    items = query.order_by(ContentItem.created_at.desc()).all()
    pillars = db.query(ContentPillar).filter(ContentPillar.user_id == user.id).all()

    return templates.TemplateResponse(
        request=request,
        name="content.html",
        context={
            "items": items,
            "q": q,
            "status_filter": status_filter,
            "user": user,
            "view": view,
            "pillars": pillars,
            "stages": PIPELINE_STAGES,
        },
    )


@router.get("/content/pipeline")
def pipeline_board(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = (
        db.query(ContentItem)
        .filter(ContentItem.user_id == user.id, ContentItem.status != Status.archived)
        .order_by(ContentItem.due_date.is_(None), ContentItem.due_date)
        .all()
    )
    columns = {stage: [i for i in items if getattr(i.status, "value", i.status) == stage] for stage in PIPELINE_STAGES}
    return templates.TemplateResponse(
        request=request,
        name="pipeline.html",
        context={"user": user, "columns": columns, "stages": PIPELINE_STAGES, "today": date.today()},
    )


@router.post("/content")
def create_content(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    title: str = Form(...),
    platform: str = Form(...),
    content_type: str = Form(...),
    status: str = Form("idea"),
    topic: str = Form(""),
    due_date: str = Form(""),
    pillar_id: str = Form(""),
    estimated_minutes: str = Form(""),
):
    new_item = ContentItem(
        user_id=user.id,
        title=title.strip(),
        platform=parse_enum(Platform, platform, Platform.other),
        content_type=parse_enum(ContentType, content_type, ContentType.other),
        status=parse_enum(Status, status, Status.idea),
        topic=clean(topic),
        due_date=parse_optional_datetime(due_date),
        pillar_id=int(pillar_id) if pillar_id.isdigit() else None,
        estimated_minutes=int(estimated_minutes) if estimated_minutes.isdigit() else None,
    )
    db.add(new_item)
    db.commit()

    db.add(ContentBrief(user_id=user.id, content_id=new_item.id))
    db.commit()
    return RedirectResponse(url="/content", status_code=303)


@router.get("/content/{content_id}")
def content_detail(
    content_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    item = _get_content(db, user.id, content_id)
    if not item:
        return RedirectResponse(url="/content", status_code=303)

    brief = db.query(ContentBrief).filter(ContentBrief.content_id == item.id).first()
    derivatives = db.query(ContentRepurpose).filter(ContentRepurpose.content_id == item.id).all()
    tasks = db.query(Task).filter(Task.content_id == item.id).all()
    originals = (
        db.query(ContentItem).filter(ContentItem.repurposed_from_id == item.id).all() if derivatives else []
    )
    return templates.TemplateResponse(
        request=request,
        name="content_detail.html",
        context={
            "user": user,
            "item": item,
            "brief": brief,
            "derivatives": derivatives,
            "tasks": tasks,
            "originals": originals,
            "pillars": db.query(ContentPillar).filter(ContentPillar.user_id == user.id).all(),
            "ai": ai_service.ai_status(),
        },
    )


@router.post("/content/{content_id}")
def update_content(
    content_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    title: str = Form(...),
    status: str = Form("idea"),
    platform: str = Form(""),
    content_type: str = Form(""),
    due_date: str = Form(""),
    topic: str = Form(""),
    pillar_id: str = Form(""),
    hook: str = Form(""),
    caption: str = Form(""),
    script: str = Form(""),
    notes: str = Form(""),
    performance_rating: str = Form("0"),
    performance_note: str = Form(""),
    brief_goal: str = Form("reach"),
    brief_audience: str = Form(""),
    brief_core_idea: str = Form(""),
    brief_proof: str = Form(""),
    brief_cta: str = Form(""),
    brief_distribution: str = Form(""),
    brief_repurposing: str = Form(""),
):
    item = _get_content(db, user.id, content_id)
    if not item:
        return RedirectResponse(url="/content", status_code=303)

    item.title = title.strip()
    new_status = parse_enum(Status, status, item.status)
    if new_status == Status.published and not item.published_at:
        item.published_at = datetime.now()
    if new_status != Status.published and item.status == Status.published:
        item.published_at = None
    item.status = new_status
    item.platform = parse_enum(Platform, platform, item.platform)
    item.content_type = parse_enum(ContentType, content_type, item.content_type)
    item.due_date = parse_optional_datetime(due_date)
    item.topic = clean(topic)
    item.pillar_id = int(pillar_id) if pillar_id.isdigit() else None
    item.hook = clean(hook)
    item.caption = clean(caption)
    item.script = clean(script)
    item.notes = clean(notes)
    item.performance_rating = int(performance_rating) if performance_rating.isdigit() else 0
    item.performance_note = clean(performance_note)

    brief = db.query(ContentBrief).filter(ContentBrief.content_id == item.id).first()
    if not brief:
        brief = ContentBrief(user_id=user.id, content_id=item.id)
        db.add(brief)
    brief.goal = brief_goal or "reach"
    brief.audience = clean(brief_audience)
    brief.hook = clean(brief_audience) or item.hook
    brief.core_idea = clean(brief_core_idea)
    brief.proof = clean(brief_proof)
    brief.cta = clean(brief_cta)
    brief.distribution = clean(brief_distribution)
    brief.repurposing_plan = clean(brief_repurposing)
    db.commit()
    return RedirectResponse(url=f"/content/{item.id}", status_code=303)


@router.get("/content/{content_id}/repurpose")
def repurpose_workspace(
    content_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    source_text: str = "",
):
    item = _get_content(db, user.id, content_id)
    if not item:
        return RedirectResponse(url="/content", status_code=303)

    existing = db.query(ContentRepurpose).filter(ContentRepurpose.content_id == item.id).all()
    return templates.TemplateResponse(
        request=request,
        name="repurpose.html",
        context={
            "user": user,
            "item": item,
            "derivatives": existing,
            "kinds": REPURPOSE_KINDS,
            "source_text": source_text or (item.script or item.description or ""),
            "ai": ai_service.ai_status(),
            "plan": None,
        },
    )


@router.post("/content/{content_id}/repurpose")
def generate_repurposing(
    content_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    action: str = Form("plan"),
    source_text: str = Form(""),
):
    item = _get_content(db, user.id, content_id)
    if not item:
        return RedirectResponse(url="/content", status_code=303)

    if action == "plan":
        provider = ai_service.get_provider()
        plan = provider.complete(
            f"Create a repurposing plan for this content:\n{source_text or item.title}"
        )
        _record_ai(db, user.id, "repurpose", item.title, plan, provider.name)
        return _repurpose_response(
            request, db=db, user=user, item=item, plan=plan, source_text=source_text
        )

    kind, platform, title = action.partition("::")
    label, default_platform = next(
        ((name, p) for k, name, p in REPURPOSE_KINDS if k == kind), (kind, "instagram")
    )
    db.add(
        ContentRepurpose(
            user_id=user.id,
            content_id=item.id,
            kind=kind,
            platform=platform or default_platform,
            title=clean(title) or f"{item.title} — {label}",
            status="planned",
        )
    )
    db.commit()
    return RedirectResponse(url=f"/content/{item.id}/repurpose", status_code=303)


def _repurpose_response(request: Request, *, db, user, item, plan, source_text):
    """Re-render the repurposing workspace with a generated plan attached."""
    derivatives = db.query(ContentRepurpose).filter(ContentRepurpose.content_id == item.id).all()
    return templates.TemplateResponse(
        request=request,
        name="repurpose.html",
        context={
            "user": user,
            "item": item,
            "derivatives": derivatives,
            "kinds": REPURPOSE_KINDS,
            "source_text": source_text,
            "ai": ai_service.ai_status(),
            "plan": plan,
        },
    )


def _record_ai(db: Session, user_id: int, kind: str, prompt: str, response: str, provider: str) -> None:
    from app.models.workspace import AIInteraction

    db.add(
        AIInteraction(user_id=user_id, kind=kind, provider=provider, prompt=prompt, response=response)
    )
    db.commit()


@router.post("/content/{content_id}/derivatives/{derivative_id}/convert")
def convert_derivative(
    content_id: int,
    derivative_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Turn a planned derivative into a real content item. No retyping."""
    derivative = (
        db.query(ContentRepurpose)
        .filter(ContentRepurpose.id == derivative_id, ContentRepurpose.content_id == content_id)
        .first()
    )
    item = _get_content(db, user.id, content_id)
    if not derivative or not item:
        return RedirectResponse(url="/content", status_code=303)

    new_item = ContentItem(
        user_id=user.id,
        title=derivative.title,
        platform=parse_enum(Platform, derivative.platform, Platform.other),
        content_type=parse_enum(ContentType, derivative.kind, ContentType.other),
        status=Status.idea,
        source="repurpose",
        repurposed_from_id=item.id,
        topic=item.topic,
        pillar_id=item.pillar_id,
        hook=item.hook,
        estimated_minutes=15,
    )
    db.add(new_item)
    derivative.status = "in_progress"
    db.commit()

    db.add(ContentBrief(user_id=user.id, content_id=new_item.id, hook=item.hook, audience=item.description))
    db.commit()

    activity.record(
        db,
        user.id,
        "content",
        f"Created derivative “{new_item.title}”",
        entity_type="content",
        entity_id=new_item.id,
        detail=f"Repurposed from “{item.title}”. Saved as a draft; nothing was published.",
    )
    return RedirectResponse(url=f"/content/{new_item.id}", status_code=303)


@router.post("/content/{content_id}/status")
def set_content_status(
    content_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    status: str = Form(...),
):
    item = _get_content(db, user.id, content_id)
    if item:
        was_published = item.status == Status.published
        new_status = parse_enum(Status, status, item.status)
        item.status = new_status
        if new_status == Status.published and not item.published_at:
            item.published_at = datetime.now()
        if new_status != Status.published and item.status == Status.published:
            item.published_at = None
        db.commit()
        if new_status == Status.published and not was_published:
            activity.record(
                db,
                user.id,
                "content",
                f"Published “{item.title}”",
                entity_type="content",
                entity_id=item.id,
                detail=f"Marked published on {item.platform.value if hasattr(item.platform, 'value') else item.platform}.",
            )
    return RedirectResponse(url="/content", status_code=303)


@router.post("/content/{content_id}/tasks")
def add_production_task(
    content_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    title: str = Form(...),
    estimated_minutes: str = Form("30"),
    due_date: str = Form(""),
):
    item = _get_content(db, user.id, content_id)
    if not item:
        return RedirectResponse(url="/content", status_code=303)
    db.add(
        Task(
            user_id=user.id,
            title=title.strip(),
            content_id=item.id,
            estimated_minutes=int(estimated_minutes) if estimated_minutes.isdigit() else 30,
            due_date=parse_optional_datetime(due_date) or (item.due_date or datetime.now() + timedelta(days=2)),
        )
    )
    db.commit()
    return RedirectResponse(url=f"/content/{item.id}", status_code=303)


@router.post("/content/{content_id}/delete")
def delete_content(
    content_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    item = _get_content(db, user.id, content_id)
    if item:
        db.query(ContentBrief).filter(ContentBrief.content_id == item.id).delete()
        db.query(ContentRepurpose).filter(ContentRepurpose.content_id == item.id).delete()
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/content", status_code=303)


def _get_content(db: Session, user_id: int, content_id: int):
    return (
        db.query(ContentItem)
        .filter(ContentItem.id == content_id, ContentItem.user_id == user_id)
        .first()
    )
