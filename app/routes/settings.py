from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.content import ContentItem
from app.models.deal import BrandDeal
from app.models.idea import Idea
from app.models.opportunity import MonetizationOpportunity
from app.models.profile import Profile
from app.models.revenue import Revenue
from app.models.task import Task
from app.route_utils import clean
from app.services import brain
from app.services.seed import seed_db

from app.templating import templates

router = APIRouter()

CURRENCIES = ["USD", "EUR", "GBP", "INR", "AUD", "CAD"]
TIMEZONES = ["UTC", "America/New_York", "Europe/London", "Asia/Kolkata", "Asia/Singapore"]
DAY_KEYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@router.get("/settings")
def settings(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    saved: str = "",
):
    profile = db.query(Profile).filter(Profile.user_id == user.id).first()
    counts = {
        "content": db.query(ContentItem).filter(ContentItem.user_id == user.id).count(),
        "tasks": db.query(Task).filter(Task.user_id == user.id).count(),
        "deals": db.query(BrandDeal).filter(BrandDeal.user_id == user.id).count(),
        "revenue": db.query(Revenue).filter(Revenue.user_id == user.id).count(),
        "ideas": db.query(Idea).filter(Idea.user_id == user.id).count(),
        "opportunities": db.query(MonetizationOpportunity)
        .filter(MonetizationOpportunity.user_id == user.id)
        .count(),
    }

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "user": user,
            "profile": profile,
            "counts": counts,
            "currencies": CURRENCIES,
            "timezones": TIMEZONES,
            "saved": saved,
            "preference": brain.preference(db, user.id),
            "capacity": brain.capacity(db, user.id),
        },
    )


@router.post("/settings/capacity")
def update_capacity(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    working_days: list[str] = Form(default=[]),
    hours_per_day: str = Form("4"),
    peak_hour: str = Form(""),
    monthly_revenue_target: str = Form("0"),
    series_length_default: str = Form(""),
    timezone: str = Form(""),
):
    """The creator's own working rhythm.

    Every capacity and rebalancing number in the product is derived from these
    fields, so they are editable here rather than hard-coded anywhere.
    """
    pref = brain.preference(db, user.id)
    days = [d.strip() for d in working_days if d.strip() in DAY_KEYS]
    # keep the canonical order so the stored value reads predictably
    days.sort(key=DAY_KEYS.index)
    pref.working_days = ",".join(days) if days else "Mon,Tue,Wed,Thu,Fri"
    try:
        pref.hours_per_day = max(0, min(int(hours_per_day or 4), 24))
    except ValueError:
        pref.hours_per_day = 4
    try:
        pref.peak_hour = max(0, min(int(peak_hour), 23)) if peak_hour.strip() != "" else None
    except ValueError:
        pref.peak_hour = None
    try:
        pref.monthly_revenue_target = max(0.0, float(monthly_revenue_target or 0))
    except ValueError:
        pref.monthly_revenue_target = 0.0
    try:
        pref.series_length_default = max(1, min(int(series_length_default), 500)) if series_length_default.strip() else None
    except ValueError:
        pref.series_length_default = None
    if timezone in TIMEZONES:
        pref.timezone = timezone
    db.commit()
    return RedirectResponse(url="/settings?saved=capacity", status_code=303)


@router.post("/settings/profile")
def update_profile(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    name: str = Form(...),
    phone: str = Form(""),
    niche: str = Form(""),
    bio: str = Form(""),
    timezone: str = Form("UTC"),
    currency: str = Form("USD"),
):
    profile = db.query(Profile).filter(Profile.user_id == user.id).first()
    if not profile:
        profile = Profile(user_id=user.id, email=user.email, name=user.name)
        db.add(profile)

    profile.name = name.strip() or user.name
    profile.phone = clean(phone)
    profile.niche = clean(niche)
    profile.bio = clean(bio)
    profile.timezone = timezone if timezone in TIMEZONES else "UTC"
    profile.currency = currency if currency in CURRENCIES else "USD"
    profile.email = user.email

    user.name = profile.name
    db.commit()
    return RedirectResponse(url="/settings?saved=1", status_code=303)


@router.post("/settings/seed")
def reseed_database(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    seed_db(db, user_id=user.id, name=user.name, email=user.email)
    return RedirectResponse(url="/settings?saved=seed", status_code=303)
