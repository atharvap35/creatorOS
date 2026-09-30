from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.task import TaskCategory, TaskPriority, TaskStatus

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    category: TaskCategory = TaskCategory.content
    priority: TaskPriority = TaskPriority.medium
    status: TaskStatus = TaskStatus.todo
    due_date: Optional[datetime] = None
    estimated_minutes: Optional[int] = None
    content_id: Optional[int] = None
    deal_id: Optional[int] = None
    opportunity_id: Optional[int] = None

class TaskCreate(TaskBase):
    pass

class TaskUpdate(TaskBase):
    title: Optional[str] = None

class Task(TaskBase):
    id: int
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        orm_mode = True
