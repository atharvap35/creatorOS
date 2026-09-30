"""Brands, series, and offers — the three records that make the business real.

A brand is a *relationship* (many deals, lifetime value, last touch), a series is
a *commitment* (episodes published against a target), and an offer is something
the creator actually sells. All three are creator-entered; nothing here is
derived from external data.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.business import Brand, ContentSeries, Offer
from app.route_utils import clean, parse_optional_datetime, parse_optional_float
from app.services import activity, brain
from app.templating import templates

router = APIRouter()

RELATIONSHIP_STATES = ["prospect", "contacted", "active", "paused", "former"]


# ---------------------------------------------------------------------------
# brands

@router.get("/brands")
def list_brands(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    profiles = brain.brand_profiles(db, user.id)
    total_revenue = sum(p["revenue_total"] for p in profiles)
    total_outstanding = sum(p["outstanding"] for p in profiles)
    return templates.TemplateResponse(
        request=request,
        name="brands.html",
        context={
            "user": user,
            "brands": profiles,
            "total_revenue": total_revenue,
            "total_outstanding": total_outstanding,
            "states": RELATIONSHIP_STATES,
        },
    )


@router.get("/brands/{brand_id}")
def brand_detail(
    brand_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    brand = (
        db.query(Brand)
        .filter(Brand.id == brand_id, Brand.user_id == user.id)
        .first()
    )
    if not brand:
        return RedirectResponse(url="/brands", status_code=303)

    profiles = [p for p in brain.brand_profiles(db, user.id) if p["brand"].id == brand.id]
    profile = profiles[0] if profiles else None
    return templates.TemplateResponse(
        request=request,
        name="brand_detail.html",
        context={
            "user": user,
            "brand": brand,
            "profile": profile,
            "deals": profile["deals"] if profile else [],
            "events": _brand_events(db, user.id, brand.id),
            "states": RELATIONSHIP_STATES,
        },
    )


@router.post("/brands")
def create_brand(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    name: str = Form(...),
    website: str = Form(""),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    relationship_status: str = Form("prospect"),
    notes: str = Form(""),
):
    brand = Brand(
        user_id=user.id,
        name=clean(name),
        website=clean(website),
        contact_name=clean(contact_name),
        contact_email=clean(contact_email),
        relationship_status=relationship_status
        if relationship_status in RELATIONSHIP_STATES
        else "prospect",
        notes=clean(notes),
    )
    db.add(brand)
    db.commit()
    activity.record(
        db,
        user.id,
        "deal",
        f"Added brand {brand.name}",
        entity_type="brand",
        entity_id=brand.id,
        detail="Brand relationship created.",
    )
    return RedirectResponse(url=f"/brands/{brand.id}", status_code=303)


@router.post("/brands/{brand_id}/update")
def update_brand(
    brand_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    name: str = Form(...),
    website: str = Form(""),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    relationship_status: str = Form("prospect"),
    notes: str = Form(""),
):
    brand = (
        db.query(Brand)
        .filter(Brand.id == brand_id, Brand.user_id == user.id)
        .first()
    )
    if not brand:
        return RedirectResponse(url="/brands", status_code=303)
    brand.name = clean(name)
    brand.website = clean(website)
    brand.contact_name = clean(contact_name)
    brand.contact_email = clean(contact_email)
    brand.relationship_status = (
        relationship_status if relationship_status in RELATIONSHIP_STATES else brand.relationship_status
    )
    brand.notes = clean(notes)
    brand.last_interaction_at = brand.last_interaction_at or datetime.now()
    db.commit()
    return RedirectResponse(url=f"/brands/{brand.id}", status_code=303)


# ---------------------------------------------------------------------------
# series

@router.get("/series")
def list_series(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = brain.series_status(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="series.html",
        context={"user": user, "series": rows},
    )


@router.get("/series/{series_id}")
def series_detail(
    series_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    series = (
        db.query(ContentSeries)
        .filter(ContentSeries.id == series_id, ContentSeries.user_id == user.id)
        .first()
    )
    if not series:
        return RedirectResponse(url="/series", status_code=303)
    row = next((r for r in brain.series_status(db, user.id) if r["series"].id == series.id), None)
    return templates.TemplateResponse(
        request=request,
        name="series_detail.html",
        context={
            "user": user,
            "series": series,
            "items": row["items"] if row else [],
            "next_episode": row["next_episode"] if row else None,
            "at_target": row["at_target"] if row else False,
        },
    )


@router.post("/series")
def create_series(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    name: str = Form(...),
    description: str = Form(""),
    platform: str = Form(""),
    target_episodes: str = Form(""),
):
    series = ContentSeries(
        user_id=user.id,
        name=clean(name),
        description=clean(description),
        platform=clean(platform),
        target_episodes=int(parse_optional_float(target_episodes, 0) or 0) or None,
        is_active=True,
    )
    db.add(series)
    db.commit()
    activity.record(
        db,
        user.id,
        "series",
        f"Started series “{series.name}”",
        entity_type="series",
        entity_id=series.id,
        detail=f"Target: {series.target_episodes or 'no'} episodes.",
    )
    return RedirectResponse(url=f"/series/{series.id}", status_code=303)


# ---------------------------------------------------------------------------
# offers

@router.get("/offers")
def list_offers(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    offers = (
        db.query(Offer)
        .filter(Offer.user_id == user.id)
        .order_by(Offer.is_active.desc(), Offer.name)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="offers.html",
        context={
            "user": user,
            "offers": offers,
            "usage": _offer_usage(db, user.id),
        },
    )


@router.get("/offers/{offer_id}")
def offer_detail(
    offer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.models.deal import BrandDeal

    offer = (
        db.query(Offer)
        .filter(Offer.id == offer_id, Offer.user_id == user.id)
        .first()
    )
    if not offer:
        return RedirectResponse(url="/offers", status_code=303)
    deals = (
        db.query(BrandDeal)
        .filter(BrandDeal.user_id == user.id, BrandDeal.offer_id == offer.id)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="offer_detail.html",
        context={"user": user, "offer": offer, "deals": deals},
    )


@router.post("/offers")
def create_offer(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    name: str = Form(...),
    offer_type: str = Form("sponsorship"),
    description: str = Form(""),
    deliverables: str = Form(""),
    price: str = Form("0"),
    turnaround_days: str = Form(""),
    terms: str = Form(""),
):
    offer = Offer(
        user_id=user.id,
        name=clean(name),
        offer_type=offer_type or "sponsorship",
        description=clean(description),
        deliverables=clean(deliverables),
        price=parse_optional_float(price, 0.0),
        turnaround_days=int(parse_optional_float(turnaround_days, 0) or 0) or None,
        terms=clean(terms),
        is_active=True,
    )
    db.add(offer)
    db.commit()
    activity.record(
        db,
        user.id,
        "offer",
        f"Created offer “{offer.name}”",
        entity_type="offer",
        entity_id=offer.id,
        amount=offer.price,
    )
    return RedirectResponse(url="/offers", status_code=303)


@router.post("/offers/{offer_id}/toggle")
def toggle_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    offer = (
        db.query(Offer)
        .filter(Offer.id == offer_id, Offer.user_id == user.id)
        .first()
    )
    if offer:
        offer.is_active = not offer.is_active
        db.commit()
    return RedirectResponse(url="/offers", status_code=303)


# ---------------------------------------------------------------------------

def _brand_events(db: Session, user_id: int, brand_id: int) -> list:
    from app.models.business import ActivityEvent

    return (
        db.query(ActivityEvent)
        .filter(
            ActivityEvent.user_id == user_id,
            ActivityEvent.entity_type == "brand",
            ActivityEvent.entity_id == brand_id,
        )
        .order_by(ActivityEvent.occurred_at.desc())
        .all()
    )


def _offer_usage(db: Session, user_id: int) -> dict:
    """How many deals each offer has actually been attached to."""
    from sqlalchemy import func

    from app.models.deal import BrandDeal

    rows = (
        db.query(BrandDeal.offer_id, func.count(BrandDeal.id))
        .filter(BrandDeal.user_id == user_id, BrandDeal.offer_id.isnot(None))
        .group_by(BrandDeal.offer_id)
        .all()
    )
    return {offer_id: count for offer_id, count in rows}
