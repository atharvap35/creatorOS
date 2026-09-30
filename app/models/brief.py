from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class ContentBrief(Base):
    """The structured creative brief attached to a content item."""

    __tablename__ = "content_briefs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content_id = Column(
        Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal = Column(String, default="reach")        # reach | engagement | authority | leads | sales | community | partnership
    audience = Column(String)
    hook = Column(String)
    core_idea = Column(Text)
    proof = Column(String)
    cta = Column(String)
    distribution = Column(String)
    repurposing_plan = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
