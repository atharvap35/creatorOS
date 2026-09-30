from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base
import enum

class ContentType(str, enum.Enum):
    reel = "reel"
    short = "short"
    video = "video"
    carousel = "carousel"
    post = "post"
    story = "story"
    newsletter = "newsletter"
    podcast = "podcast"
    other = "other"

class Platform(str, enum.Enum):
    instagram = "Instagram"
    youtube = "YouTube"
    tiktok = "TikTok"
    linkedin = "LinkedIn"
    x = "X"
    newsletter = "Newsletter"
    other = "Other"

class Status(str, enum.Enum):
    idea = "idea"
    scripting = "scripting"
    filming = "filming"
    editing = "editing"
    ready = "ready"
    published = "published"
    archived = "archived"

class Priority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"

class ContentItem(Base):
    __tablename__ = "content_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(String)
    content_type = Column(Enum(ContentType), default=ContentType.other)
    platform = Column(Enum(Platform), default=Platform.other)
    status = Column(Enum(Status), default=Status.idea)
    priority = Column(Enum(Priority), default=Priority.medium)
    due_date = Column(DateTime)
    estimated_minutes = Column(Integer)
    topic = Column(String)
    notes = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    published_at = Column(DateTime)

    # production system
    pillar_id = Column(Integer, ForeignKey("content_pillars.id", ondelete="SET NULL"), index=True)
    hook = Column(String)
    caption = Column(Text)
    script = Column(Text)
    repurposed_from_id = Column(Integer, ForeignKey("content_items.id", ondelete="SET NULL"))
    performance_rating = Column(Integer, default=0)   # 0 unknown, 1..5
    performance_note = Column(Text)
    source = Column(String, default="manual")         # manual | idea | repurpose | recommendation

    # 3.0: series + goal linkage
    series_id = Column(Integer, ForeignKey("content_series.id", ondelete="SET NULL"), index=True)
    episode_number = Column(Integer)
    template_id = Column(Integer, ForeignKey("content_templates.id", ondelete="SET NULL"))
