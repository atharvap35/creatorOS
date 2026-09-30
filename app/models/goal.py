from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class CreatorGoal(Base):
    __tablename__ = "creator_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    category = Column(String, default="revenue")  # revenue | content | deals | product | consistency
    metric = Column(String, default="")           # monthly_revenue | published_items | closed_deals
    target_value = Column(Float, default=0.0)
    current_value = Column(Float, default=0.0)
    unit = Column(String, default="")
    period = Column(String, default="monthly")     # monthly | quarterly | yearly | one_off
    deadline = Column(Date)
    status = Column(String, default="active")      # active | achieved | paused | archived
    notes = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
