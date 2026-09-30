from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.security import SESSION_COOKIE_NAME, get_session_user


def _user_from_request(request: Request, db: Session):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    return get_session_user(db, token)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)):
    return _user_from_request(request, db)
