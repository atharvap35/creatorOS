from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.idea import IdeaType, IdeaPotential, IdeaEffort, IdeaStatus

class IdeaBase(BaseModel):
    title: str
    description: Optional[str] = None
    type: IdeaType = IdeaType.content
    potential: IdeaPotential = IdeaPotential.medium
    effort: IdeaEffort = IdeaEffort.medium
    status: IdeaStatus = IdeaStatus.backlog
    notes: Optional[str] = None

class IdeaCreate(IdeaBase):
    pass

class Idea(IdeaBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
