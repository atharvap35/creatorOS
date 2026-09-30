from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base
import enum

class IdeaType(str, enum.Enum):
    content = "content"
    product = "product"
    affiliate = "affiliate"
    sponsorship = "sponsorship"
    service = "service"
    membership = "membership"
    other = "other"

class IdeaPotential(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"

class IdeaEffort(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"

class IdeaStatus(str, enum.Enum):
    backlog = "backlog"
    exploring = "exploring"
    validated = "validated"
    converted = "converted"
    archived = "archived"

class Idea(Base):
    __tablename__ = "ideas"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(String)
    type = Column(Enum(IdeaType), default=IdeaType.other)
    potential = Column(Enum(IdeaPotential), default=IdeaPotential.medium)
    effort = Column(Enum(IdeaEffort), default=IdeaEffort.medium)
    status = Column(Enum(IdeaStatus), default=IdeaStatus.backlog)
    notes = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # idea lab
    problem = Column(Text)
    audience = Column(String)
    platform = Column(String)
    pillar_id = Column(Integer, ForeignKey("content_pillars.id", ondelete="SET NULL"), index=True)
    confidence = Column(String, default="medium")   # low | medium | high
    monetization_potential = Column(String, default="medium")
    freshness = Column(String, default="new")       # new | warming | stale
    converted_content_id = Column(Integer, ForeignKey("content_items.id", ondelete="SET NULL"))
    series_id = Column(Integer, ForeignKey("content_series.id", ondelete="SET NULL"))
