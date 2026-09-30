"""Creator Copilot endpoints.

The copilot answers questions about the creator's own records. It never
fabricates a metric, never cites data the creator has not entered, and never
changes a record without an explicit POST action.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
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


@router.post("/api/copilot/ask")
def ask_json(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    question: str = Form(...),
):
    """The same grounded answer, as JSON, for the voice layer.

    This is not a second way to get an answer — it calls `copilot.ask` and
    returns exactly what the page would render, so a spoken answer can never
    be more capable (or more inventive) than the typed one. It runs under the
    same `get_current_user` dependency, so it is scoped to one account exactly
    as the HTML route is.
    """
    result = copilot.ask(db, user.id, (question or "").strip())
    return JSONResponse(
        content={
            "question": result.get("question", ""),
            "answer": result.get("answer", ""),
            "intent": result.get("intent", "unknown"),
            "grounded": bool(result.get("grounded", False)),
            "citations": result.get("citations", []) or [],
            "actions": result.get("actions", []) or [],
        }
    )
