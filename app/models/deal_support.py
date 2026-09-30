from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class BrandContact(Base):
    __tablename__ = "brand_contacts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    deal_id = Column(Integer, ForeignKey("brand_deals.id", ondelete="CASCADE"), index=True)
    brand_name = Column(String, nullable=False)
    contact_name = Column(String)
    role = Column(String)
    email = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class DealDeliverable(Base):
    __tablename__ = "deal_deliverables"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    deal_id = Column(
        Integer, ForeignKey("brand_deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String, nullable=False)
    status = Column(String, default="pending")    # pending | in_progress | submitted | approved
    deadline = Column(DateTime)
    content_id = Column(Integer, ForeignKey("content_items.id", ondelete="SET NULL"))
    notes = Column(String)
    created_at = Column(DateTime, server_default=func.now())
