from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import enum

class TaskCategory(str, enum.Enum):
    content = "content"
    business = "business"
    monetization = "monetization"
    audience = "audience"
    admin = "admin"

class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    completed = "completed"

class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(String)
    category = Column(Enum(TaskCategory), default=TaskCategory.content)
    priority = Column(Enum(TaskPriority), default=TaskPriority.medium)
    status = Column(Enum(TaskStatus), default=TaskStatus.todo)
    due_date = Column(DateTime)
    estimated_minutes = Column(Integer)
    content_id = Column(Integer, ForeignKey("content_items.id", ondelete="SET NULL"))
    deal_id = Column(Integer, ForeignKey("brand_deals.id", ondelete="SET NULL"))
    opportunity_id = Column(Integer, ForeignKey("monetization_opportunities.id", ondelete="SET NULL"))
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime)

    goal_id = Column(Integer, ForeignKey("creator_goals.id", ondelete="SET NULL"))
    idea_id = Column(Integer, ForeignKey("ideas.id", ondelete="SET NULL"))
    source = Column(String, default="manual")
    notes = Column(String)

    # 3.0: week planning
    plan_day = Column(DateTime)          # set when a creator accepts a proposed week plan
    deferred_count = Column(Integer, default=0)
