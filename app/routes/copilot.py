"""Creator Copilot endpoints.

The copilot answers questions about the creator's own records. It never
fabricates a metric, never cites data the creator has not entered, and never
changes a record without an explicit POST action.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.services import copilot
from app.templating import templates

router = APIRouter()


@router.get("/copilot")
def copilot_view(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return templates.TemplateResponse(
        request=request,
        name="copilot.html",
        context={
            "user": user,
            "history": copilot.history(db, user.id, limit=30),
            "suggestions": copilot.SUGGESTED_QUESTIONS,
        },
    )


@router.post("/copilot/ask")
def ask(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    question: str = Form(...),
):
    question = (question or "").strip()
    if not question:
        return RedirectResponse(url="/copilot", status_code=303)
    copilot.ask(db, user.id, question)
    return RedirectResponse(url="/copilot", status_code=303)
