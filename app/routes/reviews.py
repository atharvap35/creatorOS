from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.services import reviews as review_service
from app.templating import templates

router = APIRouter()


@router.get("/reviews/weekly")
def weekly_review(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    payload = review_service.build_weekly_ceo(db, user.id)
    review_service.save_snapshot(db, user.id, payload)
    return templates.TemplateResponse(
        request=request, name="weekly_review.html", context={"user": user, "review": payload}
    )


@router.get("/reviews/monthly")
def monthly_review(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    payload = review_service.build_monthly(db, user.id)
    review_service.save_snapshot(db, user.id, payload)
    return templates.TemplateResponse(
        request=request, name="monthly_review.html", context={"user": user, "review": payload}
    )


@router.get("/reviews/business")
def business_review(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """The CEO review: revenue, content engine, brand portfolio, risks, priorities."""
    payload = review_service.build_business_review(db, user.id)
    return templates.TemplateResponse(
        request=request, name="business_review.html", context={"user": user, "review": payload}
    )


@router.post("/reviews/start-week")
def start_next_week(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    title: str = Form(""),
    reason: str = Form(""),
    minutes: str = Form("20"),
):
    actions = [{"title": title, "reason": reason, "effort_minutes": minutes}] if title else []
    created = review_service.start_next_week(db, user.id, actions)
    return RedirectResponse(url=f"/workflow?created={created}", status_code=303)
