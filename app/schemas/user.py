from pydantic import BaseModel, field_validator
from typing import Optional


def _validate_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long")
    return value


class UserCreate(BaseModel):
    name: str
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return _validate_password(value)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    niche: Optional[str] = None
    bio: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
