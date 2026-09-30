from pydantic import BaseModel
from typing import Optional


class ProfileCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    niche: Optional[str] = None
    bio: Optional[str] = None
    timezone: str = "UTC"
    currency: str = "USD"
