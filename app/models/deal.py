from sqlalchemy import Column, Integer, String, DateTime, Enum, Float, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import enum

class DealStatus(str, enum.Enum):
    lead = "lead"
    negotiation = "negotiation"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"

class PaymentStatus(str, enum.Enum):
    not_invoiced = "not_invoiced"
    invoiced = "invoiced"
    pending = "pending"
    paid = "paid"
    overdue = "overdue"

class BrandDeal(Base):
    __tablename__ = "brand_deals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    brand_name = Column(String, nullable=False)
    campaign_name = Column(String, nullable=False)
    description = Column(String)
    deal_value = Column(Float, default=0.0)
    currency = Column(String, default="USD")
    status = Column(Enum(DealStatus), default=DealStatus.lead)
    deadline = Column(DateTime)
    payment_due_date = Column(DateTime)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.not_invoiced)
    deliverables = Column(String)
    notes = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    completed_at = Column(DateTime)

    # CRM layer
    stage = Column(String, default="lead")
    contact_name = Column(String)
    contact_email = Column(String)
    next_action = Column(String)
    follow_up_date = Column(DateTime)
    payment_terms = Column(String)
    invoiced_amount = Column(Float, default=0.0)
    paid_amount = Column(Float, default=0.0)

    # 3.0: relationship + economics
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    estimated_hours = Column(Float)          # creator-entered effort estimate
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="SET NULL"))
