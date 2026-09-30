from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class ReviewSnapshot(Base):
    """Stored weekly / monthly creator review so history is browsable."""

    __tablename__ = "review_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    period_type = Column(String, nullable=False)  # weekly | monthly
    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False)
    payload = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class Asset(Base):
    """Reusable hooks, templates and brand resources (Library)."""

    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    kind = Column(String, default="template")    # hook | template | brief | resource | brand
    body = Column(Text)
    tags = Column(String)
    is_favorite = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


class AIInteraction(Base):
    """Audit trail of every AI-assisted action; output is always editable."""

    __tablename__ = "ai_interactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String, nullable=False)         # hooks | outline | script | caption | repurpose | follow_up | summary
    provider = Column(String, default="builtin")
    prompt = Column(Text)
    response = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
