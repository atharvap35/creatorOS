from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class CreatorBase(BaseModel):
    name: str
    email: EmailStr
    niche: Optional[str] = None
    bio: Optional[str] = None
    timezone: str = "UTC"
    currency: str = "USD"

class CreatorCreate(CreatorBase):
    pass

class Creator(CreatorBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
