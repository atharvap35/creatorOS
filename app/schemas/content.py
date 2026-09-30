from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.content import ContentType, Platform, Status, Priority

class ContentBase(BaseModel):
    title: str
    description: Optional[str] = None
    content_type: ContentType = ContentType.other
    platform: Platform = Platform.other
    status: Status = Status.idea
    priority: Priority = Priority.medium
    due_date: Optional[datetime] = None
    estimated_minutes: Optional[int] = None
    topic: Optional[str] = None
    notes: Optional[str] = None

class ContentCreate(ContentBase):
    pass

class ContentUpdate(ContentBase):
    title: Optional[str] = None

class Content(ContentBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None

    class Config:
        orm_mode = True
