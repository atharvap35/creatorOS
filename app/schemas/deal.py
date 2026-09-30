from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.deal import DealStatus, PaymentStatus

class DealBase(BaseModel):
    brand_name: str
    campaign_name: str
    description: Optional[str] = None
    deal_value: float
    currency: str = "USD"
    status: DealStatus = DealStatus.lead
    deadline: Optional[datetime] = None
    payment_due_date: Optional[datetime] = None
    payment_status: PaymentStatus = PaymentStatus.not_invoiced
    deliverables: Optional[str] = None
    notes: Optional[str] = None

class DealCreate(DealBase):
    pass

class DealUpdate(DealBase):
    brand_name: Optional[str] = None

class Deal(DealBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        orm_mode = True
