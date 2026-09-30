from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.pillar import ContentPillar
from app.route_utils import clean
from app.services import insights
from app.templating import templates

router = APIRouter()

PALETTE = ["#7764d8", "#4f9d78", "#d1793f", "#c2566b", "#3f8ac2", "#b3903a"]


@router.get("/content/pillars")
def list_pillars(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    mix = insights.pillar_mix(db, user.id)
    covered = {row["pillar"].id for row in mix}
    suggestions = (
        db.query(ContentPillar)
        .filter(ContentPillar.user_id == user.id)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="pillars.html",
        context={
            "user": user,
            "mix": mix,
            "gaps": insights.pillar_gaps(db, user.id),
            "suggestions": suggestions,
            "covered": covered,
            "palette": PALETTE,
        },
    )


@router.post("/content/pillars")
def create_pillar(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    name: str = Form(...),
    description: str = Form(""),
    color: str = Form(PALETTE[0]),
):
    name = name.strip()
    if not name:
        return RedirectResponse(url="/content/pillars", status_code=303)
    existing = (
        db.query(ContentPillar)
        .filter(ContentPillar.user_id == user.id, ContentPillar.name.ilike(name))
        .first()
    )
    if existing:
        return RedirectResponse(url="/content/pillars", status_code=303)

    db.add(
        ContentPillar(
            user_id=user.id,
            name=name,
            description=clean(description),
            color=color if color in PALETTE else PALETTE[0],
        )
    )
    db.commit()
    return RedirectResponse(url="/content/pillars", status_code=303)


@router.post("/content/pillars/{pillar_id}/delete")
def delete_pillar(pillar_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    pillar = db.query(ContentPillar).filter(ContentPillar.id == pillar_id, ContentPillar.user_id == user.id).first()
    if pillar:
        db.delete(pillar)
        db.commit()
    return RedirectResponse(url="/content/pillars", status_code=303)
