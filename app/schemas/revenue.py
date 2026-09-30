from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.revenue import RevenueSource, RevenueStatus

class RevenueBase(BaseModel):
    source: RevenueSource = RevenueSource.other
    description: Optional[str] = None
    amount: float = 0.0
    currency: str = "USD"
    date: Optional[datetime] = None
    status: RevenueStatus = RevenueStatus.pending
    deal_id: Optional[int] = None
    notes: Optional[str] = None

class RevenueCreate(RevenueBase):
    pass

class Revenue(RevenueBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
