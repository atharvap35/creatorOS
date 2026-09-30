from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy import DateTime
from app.database import Base


class ContentPillar(Base):
    __tablename__ = "content_pillars"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(String)
    color = Column(String, default="#7764d8")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
