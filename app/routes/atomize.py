"""Content atomization: turn one published piece into many new drafts."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.content import ContentItem
from app.models.business import ContentAtom
from app.services import atomize, activity
from app.templating import templates

router = APIRouter()


@router.get("/content/{content_id}/atomize")
def atomize_view(
    content_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    item = (
        db.query(ContentItem)
        .filter(ContentItem.id == content_id, ContentItem.user_id == user.id)
        .first()
    )
    if not item:
        return RedirectResponse(url="/content", status_code=303)

    groups = _groups(db, user.id, content_id)
    return templates.TemplateResponse(
        request=request,
        name="atomize.html",
        context={
            "user": user,
            "item": item,
            "groups": groups,
            "total": sum(len(g["atoms"]) for g in groups),
            "kinds": atomize.ATOM_KINDS,
        },
    )


@router.post("/content/{content_id}/atomize")
def generate_atoms(
    content_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    use_ai: str = Form("on"),
):
    item = (
        db.query(ContentItem)
        .filter(ContentItem.id == content_id, ContentItem.user_id == user.id)
        .first()
    )
    if not item:
        return RedirectResponse(url="/content", status_code=303)
    atomize.propose(db, user.id, content_id, use_ai=bool(use_ai))
    return RedirectResponse(url=f"/content/{content_id}/atomize", status_code=303)


@router.post("/content/{content_id}/atomize/create")
def create_selected(
    content_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    atom_id: list[int] = Form([]),
    due_within_days: str = Form("7"),
):
    item = (
        db.query(ContentItem)
        .filter(ContentItem.id == content_id, ContentItem.user_id == user.id)
        .first()
    )
    if not item:
        return RedirectResponse(url="/content", status_code=303)

    try:
        days = max(1, min(int(due_within_days or 7), 90))
    except ValueError:
        days = 7

    created = atomize.create_drafts(db, user.id, content_id, atom_id, due_within_days=days)
    if created:
        activity.record(
            db,
            user.id,
            "content",
            f"Created {len(created)} draft(s) from “{item.title}”",
            entity_type="content",
            entity_id=item.id,
            detail="Derivatives saved as ideas. Nothing was published.",
        )
    return RedirectResponse(url=f"/content/{content_id}/atomize", status_code=303)


@router.post("/atom/{atom_id}/dismiss")
def dismiss_atom(
    atom_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    next: str = Form(""),
):
    atom = (
        db.query(ContentAtom)
        .filter(ContentAtom.id == atom_id, ContentAtom.user_id == user.id)
        .first()
    )
    if atom:
        atom.status = "dismissed"
        db.commit()
    return RedirectResponse(url=next or "/content", status_code=303)


def _groups(db: Session, user_id: int, content_id: int) -> list:
    """Atoms grouped by kind, ordered as the creator sees them in the pipeline."""
    atoms = (
        db.query(ContentAtom)
        .filter(
            ContentAtom.user_id == user_id,
            ContentAtom.content_id == content_id,
            ContentAtom.status != "dismissed",
        )
        .order_by(ContentAtom.id)
        .all()
    )
    groups = []
    for kind in atomize.ATOM_KINDS:
        rows = [a for a in atoms if a.kind == kind]
        if rows:
            groups.append({"kind": kind, "atoms": rows})
    # any kind not in the canonical order still gets shown rather than hidden
    for kind in sorted({a.kind for a in atoms} - {k for k in atomize.ATOM_KINDS}):
        groups.append({"kind": kind, "atoms": [a for a in atoms if a.kind == kind]})
    return groups
