from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.workspace import Asset
from app.route_utils import clean
from app.templating import templates

router = APIRouter()

KIND_LABELS = {
    "hook": "Hook library",
    "template": "Template",
    "brief": "Brief template",
    "resource": "Resource",
    "brand": "Brand kit",
}

STARTER_ASSETS = [
    ("Hook: the honest reframe", "hook", "I was wrong about {topic} — here's what changed my mind."),
    ("Hook: the number", "hook", "The exact number that fixed my {topic} problem."),
    ("Sponsored integration outline", "template", "Intro (brand problem) → my honest experience → 3 use cases → CTA → disclosure."),
    ("Deal follow-up template", "template", "Hi {name} — checking in on {campaign}. Where are we at?"),
]


@router.get("/library")
def library(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    kind: str = "",
    q: str = "",
):
    query = db.query(Asset).filter(Asset.user_id == user.id)
    if kind:
        query = query.filter(Asset.kind == kind)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(Asset.title.ilike(term) | Asset.body.ilike(term))
    assets = query.order_by(Asset.is_favorite.desc(), Asset.created_at.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context={
            "user": user,
            "assets": assets,
            "kinds": KIND_LABELS,
            "kind": kind,
            "q": q,
            "starter": STARTER_ASSETS,
        },
    )


@router.post("/library")
def create_asset(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    title: str = Form(...),
    kind: str = Form("template"),
    body: str = Form(""),
    tags: str = Form(""),
):
    if title.strip():
        db.add(Asset(user_id=user.id, title=title.strip(), kind=kind, body=body, tags=clean(tags)))
        db.commit()
    return RedirectResponse(url="/library", status_code=303)


@router.post("/library/{asset_id}/delete")
def delete_asset(asset_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.user_id == user.id).first()
    if asset:
        db.delete(asset)
        db.commit()
    return RedirectResponse(url="/library", status_code=303)
