from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.deal import BrandDeal, DealStatus, PaymentStatus
from app.models.deal_support import BrandContact, DealDeliverable
from app.models.task import Task
from app.route_utils import clean, parse_enum, parse_optional_datetime, parse_optional_float
from app.services import activity
from app.templating import templates

router = APIRouter()

STAGES = [
    ("lead", "Lead"),
    ("contacted", "Contacted"),
    ("negotiating", "Negotiating"),
    ("agreed", "Agreed"),
    ("contracted", "Contracted"),
    ("in_production", "In production"),
    ("delivered", "Delivered"),
    ("invoiced", "Invoiced"),
    ("paid", "Paid"),
    ("completed", "Completed"),
]

STAGE_TO_STATUS = {
    "lead": DealStatus.lead,
    "contacted": DealStatus.lead,
    "negotiating": DealStatus.negotiation,
    "agreed": DealStatus.active,
    "contracted": DealStatus.active,
    "in_production": DealStatus.active,
    "delivered": DealStatus.active,
    "invoiced": DealStatus.active,
    "paid": DealStatus.completed,
    "completed": DealStatus.completed,
}

HEALTH = {
    "healthy": ("Healthy", "good"),
    "attention": ("Needs attention", "warn"),
    "risk": ("At risk", "bad"),
}


def deal_health(deal: BrandDeal, deliverables: list) -> dict:
    """Health is derived from dates and deliverable state — never a mystery."""
    now = datetime.now()
    reasons = []
    risk = False
    attention = False

    if deal.payment_status == "overdue" or (
        deal.payment_due_date
        and deal.payment_due_date < now
        and deal.payment_status != PaymentStatus.paid
    ):
        days = (now - deal.payment_due_date).days if deal.payment_due_date else 0
        reasons.append(f"Payment is {days} day(s) past due.")
        risk = True

    pending = [d for d in deliverables if d.status in ("pending", "in_progress")]
    if deal.deadline and deal.stage not in ("paid", "completed"):
        days_left = (deal.deadline - now).days
        if days_left < 0 and pending:
            reasons.append(f"Deadline passed with {len(pending)} deliverable(s) unfinished.")
            risk = True
        elif days_left <= 3 and pending:
            reasons.append(f"Deadline in {days_left} day(s) with {len(pending)} deliverable(s) open.")
            attention = True

    if deal.stage in ("lead", "contacted", "negotiating") and not deal.follow_up_date:
        reasons.append("No follow-up date is set, so this deal will go quiet.")
        attention = True
    elif deal.follow_up_date and deal.follow_up_date < now and deal.stage not in ("paid", "completed"):
        reasons.append(f"Follow-up was due {deal.follow_up_date.strftime('%d %b')} and hasn't happened.")
        attention = True

    if not deal.next_action:
        reasons.append("No next action written down.")
        attention = True

    if risk:
        state = "risk"
    elif attention or reasons:
        state = "attention"
    else:
        state = "healthy"

    label, style = HEALTH[state]
    return {
        "state": state,
        "label": label,
        "style": style,
        "reasons": reasons or ["On track — no risks detected from your dates and deliverables."],
    }


@router.get("/deals")
def list_deals(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    q: str = "",
    status_filter: str = "",
):
    query = db.query(BrandDeal).filter(BrandDeal.user_id == user.id)

    if q:
        query = query.filter(BrandDeal.brand_name.ilike(f"%{q.strip()}%"))
    if status_filter:
        query = query.filter(BrandDeal.stage == status_filter)

    items = query.order_by(BrandDeal.created_at.desc()).all()
    deliverable_counts = {
        d.id: db.query(DealDeliverable).filter(DealDeliverable.deal_id == d.id).count() for d in items
    }
    pipeline_value = sum(item.deal_value or 0 for item in items if item.stage not in ("paid", "completed"))

    return templates.TemplateResponse(
        request=request,
        name="deals.html",
        context={
            "user": user,
            "items": items,
            "q": q,
            "status_filter": status_filter,
            "pipeline_value": pipeline_value,
            "stages": STAGES,
            "deliverable_counts": deliverable_counts,
        },
    )


@router.post("/deals")
def create_deal(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    brand_name: str = Form(...),
    campaign_name: str = Form(...),
    description: str = Form(""),
    deal_value: str = Form("0"),
    currency: str = Form("USD"),
    status: str = Form("lead"),
    payment_status: str = Form("not_invoiced"),
    deadline: str = Form(""),
    stage: str = Form("lead"),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    next_action: str = Form(""),
    follow_up_date: str = Form(""),
    payment_due_date: str = Form(""),
    payment_terms: str = Form(""),
):
    chosen_stage = stage if stage in dict(STAGES) else "lead"
    deal = BrandDeal(
        user_id=user.id,
        brand_name=brand_name.strip(),
        campaign_name=campaign_name.strip(),
        description=clean(description),
        deal_value=parse_optional_float(deal_value, 0.0),
        currency=currency.strip() or "USD",
        status=parse_enum(DealStatus, status, STAGE_TO_STATUS[chosen_stage]),
        stage=chosen_stage,
        payment_status=parse_enum(PaymentStatus, payment_status, PaymentStatus.not_invoiced),
        deadline=parse_optional_datetime(deadline),
        payment_due_date=parse_optional_datetime(payment_due_date),
        contact_name=clean(contact_name),
        contact_email=clean(contact_email),
        next_action=clean(next_action),
        follow_up_date=parse_optional_datetime(follow_up_date),
        payment_terms=clean(payment_terms),
    )
    db.add(deal)
    db.commit()

    if deal.contact_name or deal.contact_email:
        db.add(
            BrandContact(
                user_id=user.id,
                deal_id=deal.id,
                brand_name=deal.brand_name,
                contact_name=deal.contact_name,
                email=deal.contact_email,
            )
        )
        db.commit()
    return RedirectResponse(url=f"/deals/{deal.id}", status_code=303)


@router.get("/deals/{deal_id}")
def deal_detail(deal_id: int, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    deal = _get_deal(db, user.id, deal_id)
    if not deal:
        return RedirectResponse(url="/deals", status_code=303)

    deliverables = (
        db.query(DealDeliverable).filter(DealDeliverable.deal_id == deal.id).all()
    )
    tasks = db.query(Task).filter(Task.deal_id == deal.id).all()
    return templates.TemplateResponse(
        request=request,
        name="deal_detail.html",
        context={
            "user": user,
            "deal": deal,
            "deliverables": deliverables,
            "tasks": tasks,
            "contacts": db.query(BrandContact)
            .filter(BrandContact.user_id == user.id, BrandContact.deal_id == deal.id)
            .all(),
            "stages": STAGES,
            "health": deal_health(deal, deliverables),
        },
    )


@router.post("/deals/{deal_id}")
def update_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    brand_name: str = Form(...),
    campaign_name: str = Form(...),
    description: str = Form(""),
    deal_value: str = Form("0"),
    stage: str = Form("lead"),
    payment_status: str = Form("not_invoiced"),
    deadline: str = Form(""),
    payment_due_date: str = Form(""),
    follow_up_date: str = Form(""),
    next_action: str = Form(""),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    payment_terms: str = Form(""),
    notes: str = Form(""),
):
    deal = _get_deal(db, user.id, deal_id)
    if not deal:
        return RedirectResponse(url="/deals", status_code=303)

    previous_stage = deal.stage
    previous_payment = deal.payment_status

    deal.brand_name = brand_name.strip()
    deal.campaign_name = campaign_name.strip()
    deal.description = clean(description)
    deal.deal_value = parse_optional_float(deal_value, deal.deal_value)
    deal.stage = stage if stage in dict(STAGES) else deal.stage
    deal.status = STAGE_TO_STATUS.get(deal.stage, deal.status)
    deal.payment_status = parse_enum(PaymentStatus, payment_status, deal.payment_status)
    deal.deadline = parse_optional_datetime(deadline)
    deal.payment_due_date = parse_optional_datetime(payment_due_date)
    deal.follow_up_date = parse_optional_datetime(follow_up_date)
    deal.next_action = clean(next_action)
    deal.contact_name = clean(contact_name)
    deal.contact_email = clean(contact_email)
    deal.payment_terms = clean(payment_terms)
    deal.notes = clean(notes)
    if deal.stage in ("paid", "completed"):
        deal.completed_at = deal.completed_at or datetime.now()
    db.commit()

    if previous_stage and deal.stage != previous_stage:
        _record_stage_change(db, user.id, deal, previous_stage, deal.stage)
    if previous_payment != deal.payment_status:
        activity.record(
            db,
            user.id,
            "deal",
            f"{deal.brand_name}: payment marked {deal.payment_status.value.replace('_', ' ')}",
            entity_type="deal",
            entity_id=deal.id,
            amount=deal.deal_value,
            detail=f"Stage is {deal.stage}.",
        )
    return RedirectResponse(url=f"/deals/{deal.id}", status_code=303)


def _record_stage_change(db: Session, user_id: int, deal: BrandDeal, from_stage: str, to_stage: str):
    """A stage change is a business decision, so it belongs in the history."""
    from app.models.business import StageEvent

    db.add(
        StageEvent(
            user_id=user_id,
            deal_id=deal.id,
            kind="stage_change",
            summary=(
                f"{deal.brand_name} · {deal.campaign_name}: {from_stage} → {to_stage} "
                f"({deal.currency} {round(deal.deal_value or 0)})"
            ),
            occurred_at=datetime.now(),
        )
    )
    db.commit()
    activity.record(
        db,
        user_id,
        "deal",
        f"{deal.brand_name} moved {from_stage} → {to_stage}",
        entity_type="deal",
        entity_id=deal.id,
        amount=deal.deal_value,
        detail=f"{deal.campaign_name} is now at {to_stage}.",
    )


@router.post("/deals/{deal_id}/deliverables")
def add_deliverable(
    deal_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    title: str = Form(...),
    deadline: str = Form(""),
    notes: str = Form(""),
):
    deal = _get_deal(db, user.id, deal_id)
    if not deal or not title.strip():
        return RedirectResponse(url="/deals", status_code=303)

    db.add(
        DealDeliverable(
            user_id=user.id,
            deal_id=deal.id,
            title=title.strip(),
            deadline=parse_optional_datetime(deadline) or deal.deadline,
            notes=clean(notes),
        )
    )
    db.commit()
    return RedirectResponse(url=f"/deals/{deal.id}", status_code=303)


@router.post("/deliverables/{deliverable_id}/status")
def update_deliverable(
    deliverable_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    status: str = Form(...),
):
    item = (
        db.query(DealDeliverable)
        .filter(DealDeliverable.id == deliverable_id, DealDeliverable.user_id == user.id)
        .first()
    )
    if item:
        previous = item.status
        if status not in ("pending", "in_progress", "submitted", "approved"):
            status = "pending"
        item.status = status
        db.commit()
        if previous != status:
            activity.record(
                db,
                user.id,
                "deliverable",
                f"Deliverable “{item.title}” → {status.replace('_', ' ')}",
                entity_type="deal",
                entity_id=item.deal_id,
                detail=f"{previous.replace('_', ' ')} → {status.replace('_', ' ')}",
            )
    return RedirectResponse(url=f"/deals/{item.deal_id}", status_code=303)


@router.post("/deliverables/{deliverable_id}/delete")
def delete_deliverable(deliverable_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = (
        db.query(DealDeliverable)
        .filter(DealDeliverable.id == deliverable_id, DealDeliverable.user_id == user.id)
        .first()
    )
    if item:
        deal_id = item.deal_id
        db.delete(item)
        db.commit()
        return RedirectResponse(url=f"/deals/{deal_id}", status_code=303)
    return RedirectResponse(url="/deals", status_code=303)


@router.post("/deals/{deal_id}/delete")
def delete_deal(deal_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    deal = _get_deal(db, user.id, deal_id)
    if deal:
        db.query(DealDeliverable).filter(DealDeliverable.deal_id == deal.id).delete()
        db.delete(deal)
        db.commit()
    return RedirectResponse(url="/deals", status_code=303)


def _get_deal(db: Session, user_id: int, deal_id: int):
    return db.query(BrandDeal).filter(BrandDeal.id == deal_id, BrandDeal.user_id == user_id).first()
