from sqlalchemy import Column, Integer, String, DateTime, Enum, Float, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import enum

class OpportunityType(str, enum.Enum):
    sponsorship = "sponsorship"
    affiliate = "affiliate"
    digital_product = "digital_product"
    service = "service"
    membership = "membership"
    content_monetization = "content_monetization"
    other = "other"

class OpportunityPotential(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"

class OpportunityEffort(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"

class OpportunityStatus(str, enum.Enum):
    idea = "idea"
    evaluating = "evaluating"
    active = "active"
    completed = "completed"
    rejected = "rejected"

class MonetizationOpportunity(Base):
    __tablename__ = "monetization_opportunities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(String)
    type = Column(Enum(OpportunityType), default=OpportunityType.other)
    estimated_value = Column(Float, default=0.0)
    effort = Column(Enum(OpportunityEffort), default=OpportunityEffort.medium)
    potential = Column(Enum(OpportunityPotential), default=OpportunityPotential.medium)
    status = Column(Enum(OpportunityStatus), default=OpportunityStatus.idea)
    source = Column(String, default="creator_input")
    next_action = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    deadline = Column(DateTime)
    confidence = Column(String, default="medium")
    source_detail = Column(String)
    revenue_id = Column(Integer, ForeignKey("revenue.id", ondelete="SET NULL"))
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="SET NULL"))
