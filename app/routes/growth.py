from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.content import ContentItem, Status
from app.models.deal import BrandDeal
from app.models.idea import Idea
from app.models.opportunity import (
    MonetizationOpportunity,
    OpportunityEffort,
    OpportunityPotential,
    OpportunityStatus,
    OpportunityType,
)
from app.models.recommendation import Recommendation
from app.models.revenue import Revenue, RevenueStatus
from app.models.task import Task, TaskStatus
from app.route_utils import clean, parse_enum, parse_optional_datetime, parse_optional_float
from app.services import health, insights, recommender
from app.templating import templates

router = APIRouter()

STATE_STYLES = {
    "strong": ("Strong", "good"),
    "steady": ("Steady", "ok"),
    "needs_attention": ("Needs attention", "warn"),
    "critical": ("Critical", "bad"),
}

OPPORTUNITY_CATEGORIES = {
    "sponsorship": "Brand deals",
    "affiliate": "Affiliate",
    "digital_product": "Digital products",
    "service": "Services",
    "membership": "Membership",
    "content_monetization": "Content monetization",
    "other": "Other",
    "course": "Courses",
    "newsletter": "Newsletter",
    "ugc": "UGC",
    "licensing": "Licensing",
}


def _opportunity_radar(db: Session, user_id: int) -> list:
    """Rank opportunities with an explicit reason, never a bare score."""
    items = (
        db.query(MonetizationOpportunity)
        .filter(
            MonetizationOpportunity.user_id == user_id,
            MonetizationOpportunity.status.in_([OpportunityStatus.idea, OpportunityStatus.evaluating]),
        )
        .all()
    )
    ranked = []
    for item in items:
        score = 0
        reasons = []
        potential = getattr(item.potential, "value", str(item.potential))
        effort = getattr(item.effort, "value", str(item.effort))
        if potential == "high":
            score += 30
            reasons.append("high potential")
        elif potential == "medium":
            score += 18
        if effort == "low":
            score += 20
            reasons.append("low effort")
        elif effort == "medium":
            score += 10
        if item.estimated_value:
            score += min(int(item.estimated_value / 1000), 20)
            reasons.append(f"{round(item.estimated_value)} estimated value")
        if item.deadline and item.deadline < datetime.now():
            score += 25
            reasons.append("past its deadline")
        elif item.deadline and (item.deadline - datetime.now()).days <= 7:
            score += 15
            reasons.append("deadline within a week")
        if item.next_action:
            score += 10
            reasons.append("already has a next action")
        ranked.append(
            {
                "item": item,
                "score": score,
                "why": " · ".join(reasons) if reasons else "no signals yet — add a value or next action to prioritise it",
            }
        )
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked


@router.get("/growth")
def growth(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    business = health.business_health(db, user.id)
    sections = []
    for section in business["sections"]:
        label, style = STATE_STYLES.get(section["state"], ("Steady", "ok"))
        sections.append({**section, "state_label": label, "state_style": style})

    return templates.TemplateResponse(
        request=request,
        name="growth.html",
        context={
            "user": user,
            "health": business,
            "sections": sections,
            "consistency": insights.publishing_consistency(db, user.id),
            "mix": insights.pillar_mix(db, user.id),
            "gaps": insights.pillar_gaps(db, user.id),
            "sources": insights.revenue_by_source(db, user.id),
            "workload": recommender.weekly_workload(db, user.id),
            "stuck": insights.stuck_content(db, user.id),
            "deals": db.query(BrandDeal)
            .filter(BrandDeal.user_id == user.id, BrandDeal.stage.notin_(["completed", "cancelled"]))
            .all(),
            "opportunities": _opportunity_radar(db, user.id)[:5],
            "owed": insights.payments_owed(db, user.id),
            "forecast": insights.cashflow_forecast(db, user.id),
        },
    )


@router.get("/growth/opportunities")
def opportunity_radar(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    q: str = "",
):
    ranked = _opportunity_radar(db, user.id)
    if q.strip():
        term = f"%{q.strip()}%"
        ranked = [
            r for r in ranked if r["item"].title.ilike(term) or (r["item"].description or "").ilike(term)
        ]
    return templates.TemplateResponse(
        request=request,
        name="opportunities.html",
        context={
            "user": user,
            "ranked": ranked,
            "q": q,
            "categories": OPPORTUNITY_CATEGORIES,
            "all_items": db.query(MonetizationOpportunity)
            .filter(MonetizationOpportunity.user_id == user.id)
            .order_by(MonetizationOpportunity.created_at.desc())
            .all(),
        },
    )


@router.get("/growth/opportunities/{opportunity_id}")
def opportunity_detail(opportunity_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = (
        db.query(MonetizationOpportunity)
        .filter(MonetizationOpportunity.id == opportunity_id, MonetizationOpportunity.user_id == user.id)
        .first()
    )
    if not item:
        return RedirectResponse(url="/growth/opportunities", status_code=303)
    ranking = next((r for r in _opportunity_radar(db, user.id) if r["item"].id == item.id), None)
    return templates.TemplateResponse(
        request=request,
        name="opportunity_detail.html",
        context={"user": user, "item": item, "ranking": ranking},
    )


@router.post("/growth/opportunities/{opportunity_id}")
def update_opportunity(
    opportunity_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    title: str = Form(...),
    description: str = Form(""),
    status: str = Form("idea"),
    next_action: str = Form(""),
    estimated_value: str = Form("0"),
    effort: str = Form("medium"),
    potential: str = Form("medium"),
    confidence: str = Form("medium"),
    deadline: str = Form(""),
):
    item = (
        db.query(MonetizationOpportunity)
        .filter(MonetizationOpportunity.id == opportunity_id, MonetizationOpportunity.user_id == user.id)
        .first()
    )
    if not item:
        return RedirectResponse(url="/growth/opportunities", status_code=303)

    item.title = title.strip()
    item.description = clean(description)
    item.status = parse_enum(OpportunityStatus, status, item.status)
    item.next_action = clean(next_action)
    item.estimated_value = parse_optional_float(estimated_value, item.estimated_value)
    item.effort = parse_enum(OpportunityEffort, effort, item.effort)
    item.potential = parse_enum(OpportunityPotential, potential, item.potential)
    item.confidence = confidence
    item.deadline = parse_optional_datetime(deadline)
    db.commit()
    return RedirectResponse(url=f"/growth/opportunities/{item.id}", status_code=303)


@router.post("/growth/opportunities/{opportunity_id}/to-deal")
def convert_to_deal(opportunity_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Convert an opportunity into a real deal instead of retyping it."""
    item = (
        db.query(MonetizationOpportunity)
        .filter(MonetizationOpportunity.id == opportunity_id, MonetizationOpportunity.user_id == user.id)
        .first()
    )
    if not item:
        return RedirectResponse(url="/growth/opportunities", status_code=303)

    brand, _, campaign = item.title.partition("—")
    deal = BrandDeal(
        user_id=user.id,
        brand_name=brand.strip() or item.title,
        campaign_name=campaign.strip() or "Untitled campaign",
        description=item.description,
        deal_value=item.estimated_value or 0.0,
        stage="contacted",
        next_action=item.next_action,
    )
    db.add(deal)
    db.commit()

    item.status = OpportunityStatus.active
    db.add(
        Task(
            user_id=user.id,
            title=f"Send proposal for {deal.brand_name}",
            description=item.next_action or "Follow up on the opportunity you captured.",
            deal_id=deal.id,
            estimated_minutes=20,
        )
    )
    db.commit()
    return RedirectResponse(url=f"/deals/{deal.id}", status_code=303)


@router.get("/opportunities")
def opportunities_legacy(user=Depends(get_current_user)):
    return RedirectResponse(url="/growth/opportunities", status_code=303)


@router.post("/growth/opportunities/{opportunity_id}/delete")
def delete_opportunity(opportunity_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = (
        db.query(MonetizationOpportunity)
        .filter(MonetizationOpportunity.id == opportunity_id, MonetizationOpportunity.user_id == user.id)
        .first()
    )
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/growth/opportunities", status_code=303)


@router.post("/opportunities")
def create_opportunity(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    title: str = Form(...),
    description: str = Form(""),
    type: str = Form("sponsorship"),
    estimated_value: str = Form("0"),
    effort: str = Form("medium"),
    potential: str = Form("medium"),
    next_action: str = Form(""),
):
    """Kept for backwards compatibility with the original product surface."""
    from app.route_utils import parse_optional_float

    db.add(
        MonetizationOpportunity(
            user_id=user.id,
            title=title.strip(),
            description=clean(description),
            type=parse_enum(OpportunityType, type, OpportunityType.other),
            estimated_value=parse_optional_float(estimated_value, 0.0),
            effort=parse_enum(OpportunityEffort, effort, OpportunityEffort.medium),
            potential=parse_enum(OpportunityPotential, potential, OpportunityPotential.medium),
            next_action=clean(next_action),
            status=OpportunityStatus.idea,
        )
    )
    db.commit()
    return RedirectResponse(url="/growth/opportunities", status_code=303)
