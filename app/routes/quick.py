"""Quick capture: one small form, six object types, seconds to save."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.content import ContentItem, ContentType, Platform, Status
from app.models.deal import BrandDeal, DealStatus, PaymentStatus
from app.models.idea import Idea, IdeaEffort, IdeaPotential, IdeaStatus, IdeaType
from app.models.opportunity import (
    MonetizationOpportunity,
    OpportunityEffort,
    OpportunityPotential,
    OpportunityStatus,
    OpportunityType,
)
from app.models.revenue import Revenue, RevenueSource, RevenueStatus
from app.models.task import Task, TaskCategory, TaskPriority, TaskStatus
from app.route_utils import clean, parse_enum, parse_optional_float
from app.services.recommender import preference_for
from app.templating import templates

router = APIRouter()

TYPES = {
    "idea": {"label": "Idea", "hint": "What's the spark?"},
    "content": {"label": "Content", "hint": "What are you making?"},
    "task": {"label": "Task", "hint": "What's the next step?"},
    "deal": {"label": "Deal", "hint": "Who is the brand?"},
    "revenue": {"label": "Revenue", "hint": "What money came in?"},
    "opportunity": {"label": "Opportunity", "hint": "What could you pursue?"},
}

REDIRECTS = {
    "idea": "/ideas",
    "content": "/content",
    "task": "/workflow",
    "deal": "/deals",
    "revenue": "/money",
    "opportunity": "/growth/opportunities",
}


@router.get("/quick")
def quick_capture(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    type: str = "idea",
):
    if type not in TYPES:
        type = "idea"
    pref = preference_for(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="quick.html",
        context={
            "user": user,
            "capture_type": type,
            "types": TYPES,
            "pref": pref,
            "defaults": {
                "platform": (pref.platform_list() or ["instagram"])[0],
                "format": (pref.format_list() or ["reel"])[0],
            },
        },
    )


@router.post("/quick")
def quick_save(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    type: str = Form(...),
    title: str = Form(...),
    body: str = Form(""),
    amount: str = Form(""),
    category: str = Form(""),
    platform: str = Form(""),
):
    title = title.strip()
    if not title:
        return RedirectResponse(url="/quick?type=" + type, status_code=303)

    if type == "idea":
        db.add(
            Idea(
                user_id=user.id,
                title=title,
                description=clean(body),
                type=parse_enum(IdeaType, category, IdeaType.content),
                potential=IdeaPotential.medium,
                effort=IdeaEffort.medium,
                status=IdeaStatus.backlog,
            )
        )
    elif type == "content":
        db.add(
            ContentItem(
                user_id=user.id,
                title=title,
                description=clean(body),
                platform=parse_enum(Platform, platform, Platform.other),
                content_type=parse_enum(ContentType, category, ContentType.other),
                status=Status.idea,
            )
        )
    elif type == "task":
        db.add(
            Task(
                user_id=user.id,
                title=title,
                description=clean(body),
                category=parse_enum(TaskCategory, category, TaskCategory.content),
                priority=TaskPriority.medium,
                status=TaskStatus.todo,
                estimated_minutes=20,
            )
        )
    elif type == "deal":
        db.add(
            BrandDeal(
                user_id=user.id,
                brand_name=title,
                campaign_name=clean(body) or "Untitled campaign",
                deal_value=parse_optional_float(amount, 0.0),
                status=DealStatus.lead,
                stage="lead",
                payment_status=PaymentStatus.not_invoiced,
            )
        )
    elif type == "revenue":
        db.add(
            Revenue(
                user_id=user.id,
                source=parse_enum(RevenueSource, category, RevenueSource.other),
                description=clean(body) or title,
                amount=parse_optional_float(amount, 0.0),
                status=RevenueStatus.pending,
            )
        )
    elif type == "opportunity":
        db.add(
            MonetizationOpportunity(
                user_id=user.id,
                title=title,
                description=clean(body),
                type=parse_enum(OpportunityType, category, OpportunityType.other),
                estimated_value=parse_optional_float(amount, 0.0),
                effort=OpportunityEffort.medium,
                potential=OpportunityPotential.medium,
                status=OpportunityStatus.idea,
            )
        )

    db.commit()
    return RedirectResponse(url=REDIRECTS.get(type, "/today"), status_code=303)
