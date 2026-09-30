from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class RateCardItem(Base):
    __tablename__ = "rate_card_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    platform = Column(String, default="instagram")
    format = Column(String, default="reel")
    starting_price = Column(Float, default=0.0)
    typical_price = Column(Float, default=0.0)
    premium_price = Column(Float, default=0.0)
    turnaround_days = Column(Integer)
    notes = Column(String)
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
