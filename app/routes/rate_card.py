from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.rate_card import RateCardItem
from app.route_utils import clean, parse_optional_float
from app.templating import templates

router = APIRouter()

FORMATS = [
    "Instagram Reel",
    "Instagram Post",
    "Instagram Story set",
    "YouTube integration",
    "YouTube dedicated video",
    "TikTok video",
    "LinkedIn post",
    "Newsletter issue",
    "UGC video",
    "Bundle deal",
]


@router.get("/rate-card")
def rate_card(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = (
        db.query(RateCardItem)
        .filter(RateCardItem.user_id == user.id)
        .order_by(RateCardItem.platform, RateCardItem.name)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="rate_card.html",
        context={"user": user, "items": items, "formats": FORMATS},
    )


@router.post("/rate-card")
def create_item(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    name: str = Form(...),
    platform: str = Form("instagram"),
    starting_price: str = Form("0"),
    typical_price: str = Form("0"),
    premium_price: str = Form("0"),
    turnaround_days: str = Form(""),
    notes: str = Form(""),
):
    if name.strip():
        db.add(
            RateCardItem(
                user_id=user.id,
                name=name.strip(),
                platform=platform,
                starting_price=parse_optional_float(starting_price, 0.0),
                typical_price=parse_optional_float(typical_price, 0.0),
                premium_price=parse_optional_float(premium_price, 0.0),
                turnaround_days=int(turnaround_days) if turnaround_days.isdigit() else None,
                notes=clean(notes),
            )
        )
        db.commit()
    return RedirectResponse(url="/rate-card", status_code=303)


@router.post("/rate-card/{item_id}/delete")
def delete_item(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.query(RateCardItem).filter(RateCardItem.id == item_id, RateCardItem.user_id == user.id).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/rate-card", status_code=303)
