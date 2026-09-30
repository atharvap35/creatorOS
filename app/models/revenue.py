from sqlalchemy import Column, Integer, String, DateTime, Enum, Float, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime
import enum

class RevenueSource(str, enum.Enum):
    sponsorship = "sponsorship"
    affiliate = "affiliate"
    digital_product = "digital_product"
    membership = "membership"
    services = "services"
    ads = "ads"
    other = "other"

class RevenueStatus(str, enum.Enum):
    pending = "pending"
    received = "received"
    overdue = "overdue"

class Revenue(Base):
    __tablename__ = "revenue"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(Enum(RevenueSource), default=RevenueSource.other)
    description = Column(String)
    amount = Column(Float, default=0.0)
    currency = Column(String, default="USD")
    date = Column(DateTime, default=datetime.now)
    status = Column(Enum(RevenueStatus), default=RevenueStatus.pending)
    deal_id = Column(Integer, ForeignKey("brand_deals.id", ondelete="SET NULL"))
    notes = Column(String)
    created_at = Column(DateTime, server_default=func.now())

    # money centre
    due_date = Column(DateTime)
    recurring = Column(Integer, default=0)
    received_at = Column(DateTime)

    # 3.0: attribution
    content_id = Column(Integer, ForeignKey("content_items.id", ondelete="SET NULL"), index=True)
    hours_spent = Column(Float)          # creator-entered, enables revenue-per-hour
    invoiced = Column(Integer, default=0)
