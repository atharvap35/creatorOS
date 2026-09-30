from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.revenue import Revenue, RevenueSource, RevenueStatus
from app.route_utils import clean, parse_enum, parse_optional_datetime, parse_optional_float
from app.services import activity, insights
from app.templating import templates

router = APIRouter()


@router.get("/money")
def money_centre(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    status_filter: str = "",
):
    query = db.query(Revenue).filter(Revenue.user_id == user.id)
    if status_filter:
        parsed = parse_enum(RevenueStatus, status_filter)
        if parsed:
            query = query.filter(Revenue.status == parsed)

    entries = query.order_by(Revenue.date.desc(), Revenue.id.desc()).all()
    totals = insights.revenue_totals(db, user.id)
    owed = insights.payments_owed(db, user.id)

    return templates.TemplateResponse(
        request=request,
        name="money.html",
        context={
            "user": user,
            "revenue": entries,
            "status_filter": status_filter,
            "totals": totals,
            "sources": insights.revenue_by_source(db, user.id),
            "owed": owed,
            "forecast": insights.cashflow_forecast(db, user.id),
        },
    )


@router.get("/revenue")
def revenue_alias(user=Depends(get_current_user)):
    return RedirectResponse(url="/money", status_code=303)


@router.get("/money/payments")
def payment_tracker(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    owed = insights.payments_owed(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="payments.html",
        context={
            "user": user,
            "owed": owed,
            "total": sum(o["amount"] for o in owed),
            "overdue_total": sum(o["amount"] for o in owed if o["severity"] == "overdue"),
        },
    )


@router.post("/money")
@router.post("/revenue")
def create_revenue(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    source: str = Form(...),
    description: str = Form(""),
    amount: str = Form(...),
    currency: str = Form("USD"),
    status: str = Form("pending"),
    date: str = Form(""),
    due_date: str = Form(""),
    recurring: str = Form(""),
):
    entry = Revenue(
        user_id=user.id,
        source=parse_enum(RevenueSource, source, RevenueSource.other),
        description=clean(description),
        amount=parse_optional_float(amount, 0.0),
        currency=currency.strip() or "USD",
        status=parse_enum(RevenueStatus, status, RevenueStatus.pending),
        date=parse_optional_datetime(date) or datetime.now(),
        due_date=parse_optional_datetime(due_date),
        recurring=1 if recurring else 0,
    )
    db.add(entry)
    db.commit()
    return RedirectResponse(url="/money", status_code=303)


@router.post("/money/{revenue_id}/status")
def set_revenue_status(
    revenue_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    status: str = Form(...),
):
    entry = (
        db.query(Revenue)
        .filter(Revenue.id == revenue_id, Revenue.user_id == user.id)
        .first()
    )
    if entry:
        previous = entry.status
        new_status = parse_enum(RevenueStatus, status, entry.status)
        entry.status = new_status
        entry.received_at = datetime.now() if new_status == RevenueStatus.received else None
        db.commit()
        if new_status != previous:
            if new_status == RevenueStatus.received:
                activity.record(
                    db,
                    user.id,
                    "revenue",
                    f"Received {entry.currency} {round(entry.amount or 0):,} — {entry.description or entry.source.value}",
                    entity_type="revenue",
                    entity_id=entry.id,
                    amount=entry.amount or 0,
                )
            else:
                activity.record(
                    db,
                    user.id,
                    "revenue",
                    f"{entry.currency} {round(entry.amount or 0):,} marked {new_status.value}",
                    entity_type="revenue",
                    entity_id=entry.id,
                    amount=entry.amount or 0,
                )
    return RedirectResponse(url="/money", status_code=303)


@router.post("/money/{revenue_id}/delete")
def delete_revenue(revenue_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    entry = (
        db.query(Revenue)
        .filter(Revenue.id == revenue_id, Revenue.user_id == user.id)
        .first()
    )
    if entry:
        db.delete(entry)
        db.commit()
    return RedirectResponse(url="/money", status_code=303)
