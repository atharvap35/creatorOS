import secrets
import hashlib
import hmac
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import PBKDF2_ITERATIONS, SESSION_TTL_DAYS
from app.models.user import User
from app.models.session import SessionToken
from app.route_utils import utcnow

SESSION_COOKIE_NAME = "creator_os_session"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(expected, bytes.fromhex(digest_hex))
    except (ValueError, AttributeError):
        return False


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    email = email.strip()
    if email.count("@") != 1:
        return False
    local, _, domain = email.partition("@")
    return bool(local) and "." in domain and " " not in email


def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == normalize_email(email)).first()


def authenticate(db: Session, email: str, password: str):
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(db: Session, email: str, name: str, password: str) -> User:
    user = User(
        email=normalize_email(email),
        name=name.strip(),
        hashed_password=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_session(db: Session, user: User) -> SessionToken:
    purge_expired_sessions(db)
    session = SessionToken(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        expires_at=utcnow() + timedelta(days=SESSION_TTL_DAYS),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session_user(db: Session, token: str):
    if not token:
        return None
    session = db.query(SessionToken).filter(SessionToken.token == token).first()
    if not session:
        return None
    if session.expires_at < utcnow():
        db.delete(session)
        db.commit()
        return None
    return db.query(User).filter(User.id == session.user_id).first()


def delete_session(db: Session, token: str) -> None:
    if not token:
        return
    session = db.query(SessionToken).filter(SessionToken.token == token).first()
    if session:
        db.delete(session)
        db.commit()


def purge_expired_sessions(db: Session) -> None:
    db.query(SessionToken).filter(SessionToken.expires_at < utcnow()).delete()
    db.commit()
