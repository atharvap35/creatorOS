from sqlalchemy import Column, Integer, String, Text, Float, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class Recommendation(Base):
    """A stored, explainable suggestion for a specific day."""

    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    day = Column(Date, nullable=False, index=True)
    kind = Column(String, default="action")       # action | money | content | idea | deal
    title = Column(String, nullable=False)
    reason = Column(Text)
    benefit = Column(String)
    effort_minutes = Column(Integer, default=15)
    entity_type = Column(String)
    entity_id = Column(Integer)
    cta = Column(String)
    cta_url = Column(String)
    score = Column(Float, default=0.0)
    score_breakdown = Column(Text)
    status = Column(String, default="new")        # new | done | dismissed
    source = Column(String, default="rules")      # rules | ai | weekly_review
    created_at = Column(DateTime, server_default=func.now())
