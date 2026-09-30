from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class ContentRepurpose(Base):
    """A derivative piece planned from an original content item."""

    __tablename__ = "content_repurposes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content_id = Column(
        Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(String, nullable=False)          # reel | short | thread | carousel | story | newsletter | post | community
    platform = Column(String, default="instagram")
    title = Column(String, nullable=False)
    hook = Column(String)
    status = Column(String, default="planned")     # planned | in_progress | published | skipped
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
