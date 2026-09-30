"""Creator memory: onboarding that personalises the workspace."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.pillar import ContentPillar
from app.route_utils import clean
from app.services import ai, recommender
from app.services.seed import seed_db
from app.templating import templates

router = APIRouter()

STEPS = [
    {
        "key": "identity",
        "title": "Who are you?",
        "subtitle": "This is how Creator OS will talk to you and greet you each morning.",
    },
    {
        "key": "niche",
        "title": "What is your niche?",
        "subtitle": "Your niche focuses recommendations on the topics you actually post about.",
    },
    {
        "key": "platforms",
        "title": "Where do you publish?",
        "subtitle": "We'll default new content to these platforms.",
    },
    {
        "key": "goal",
        "title": "What is your primary goal right now?",
        "subtitle": "This reorders your Today screen. You can change it any time.",
    },
    {
        "key": "pillars",
        "title": "Pick your content pillars",
        "subtitle": "Pillars are the themes you repeat. We'll flag gaps when one goes quiet.",
    },
    {
        "key": "capacity",
        "title": "How much time do you have?",
        "subtitle": "We use this to warn you when you plan more work than you have hours.",
    },
    {
        "key": "monetization",
        "title": "How do you make money?",
        "subtitle": "So the radar can prioritise opportunities that fit your model.",
    },
]

GOALS = {
    "get_sponsorships": "Get sponsorships",
    "make_money": "Make money",
    "grow_audience": "Grow my audience",
    "build_product": "Build a product",
    "become_consistent": "Become consistent",
    "build_business": "Build a real business",
}

MONETIZATION = ["Sponsorships", "Affiliate", "Digital products", "Memberships", "Services", "Ads", "Licensing"]

SUGGESTED_PILLARS = ["AI", "Productivity", "Career", "Technology", "Lifestyle", "Business", "Health", "Money"]


@router.get("/onboarding")
def onboarding(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    step: int = 0,
):
    pref = recommender.preference_for(db, user.id)
    index = max(0, min(step, len(STEPS) - 1))
    existing_pillars = (
        db.query(ContentPillar)
        .filter(ContentPillar.user_id == user.id)
        .order_by(ContentPillar.name)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="onboarding.html",
        context={
            "user": user,
            "pref": pref,
            "existing_pillars": existing_pillars,
            "steps": STEPS,
            "index": index,
            "current": STEPS[index],
            "total": len(STEPS),
            "goals": GOALS,
            "monetization": MONETIZATION,
            "pillar_suggestions": SUGGESTED_PILLARS,
            "ai": ai.ai_status(),
        },
    )


@router.post("/onboarding")
def save_step(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    step: int = Form(...),
    name: str = Form(""),
    niche: str = Form(""),
    audience: str = Form(""),
    tone: str = Form(""),
    platforms: str = Form(""),
    primary_goal: str = Form(""),
    pillars: str = Form(""),
    working_days: str = Form("0,1,2,3,4"),
    hours_per_day: str = Form("4"),
    monetization_methods: str = Form(""),
    brand_preferences: str = Form(""),
    finish: str = Form(""),
):
    pref = recommender.preference_for(db, user.id)
    pref.niche = clean(niche)
    pref.audience = clean(audience)
    pref.tone = clean(tone)
    pref.platforms = platforms or pref.platforms
    pref.primary_goal = primary_goal or pref.primary_goal
    pref.monetization_methods = monetization_methods
    pref.brand_preferences = clean(brand_preferences)
    pref.working_days = working_days or "0,1,2,3,4"
    pref.hours_per_day = max(1, min(int(hours_per_day or 4), 16))
    pref.daily_capacity_hours = pref.hours_per_day
    pref.onboarding_step = step
    pref.onboarding_complete = bool(finish)
    user.name = clean(name) or user.name
    db.commit()

    for pillar in [p.strip() for p in pillars.split(",") if p.strip()]:
        exists = (
            db.query(ContentPillar)
            .filter(ContentPillar.user_id == user.id, ContentPillar.name.ilike(pillar))
            .first()
        )
        if not exists:
            db.add(ContentPillar(user_id=user.id, name=pillar))
    if pillars.strip():
        db.commit()

    if finish:
        seed_db(db, user_id=user.id, name=user.name, email=user.email)
        return RedirectResponse(url="/today", status_code=303)

    return RedirectResponse(url=f"/onboarding?step={step + 1}", status_code=303)
