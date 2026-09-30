import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (registers every table before create_all)
from app.config import APP_NAME, BASE_DIR
from app.currency import current_currency
from app.database import Base, SessionLocal, _apply_sqlite_migrations, engine, get_db
from app.dependencies import get_optional_user
from app.models.profile import Profile
from app.security import SESSION_COOKIE_NAME, get_session_user
from app.routes import (
    actions,
    assistant,
    atomize,
    attention,
    auth,
    business,
    calendar,
    content,
    copilot,
    deals,
    goals,
    growth,
    ideas,
    library,
    money,
    onboarding,
    pillars,
    quick,
    rate_card,
    reviews,
    search,
    settings,
    today,
    workflow,
)

PUBLIC_PATHS = {"/", "/login", "/register"}


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
    _apply_sqlite_migrations()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    yield


app = FastAPI(title=APP_NAME, version="3.0.0", lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "app", "static")),
    name="static",
)

# Pillars must be registered before content: `/content/pillars` would otherwise be
# swallowed by the `/content/{content_id}` path converter. Atomize likewise must
# precede content so `/content/{id}/atomize` resolves before generic converters.
for module in (
    auth,
    onboarding,
    today,
    quick,
    search,
    pillars,
    atomize,
    content,
    ideas,
    workflow,
    deals,
    money,
    calendar,
    rate_card,
    growth,
    business,
    goals,
    reviews,
    attention,
    copilot,
    actions,
    library,
    assistant,
    settings,
):
    app.include_router(module.router)


@app.middleware("http")
async def load_currency(request: Request, call_next):
    """Make the signed-in account's preferred currency available to templates."""
    code = "USD"
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        with SessionLocal() as db:
            user = get_session_user(db, token)
            if user:
                profile = db.query(Profile).filter(Profile.user_id == user.id).first()
                code = (profile.currency if profile and profile.currency else "USD").upper()
                request.state.user = user

    ctx = current_currency.set(code)
    try:
        return await call_next(request)
    finally:
        current_currency.reset(ctx)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Turn auth failures on browser pages into a friendly login redirect."""
    if exc.status_code == 401 and request.method == "GET" and request.url.path not in PUBLIC_PATHS:
        return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/", include_in_schema=False)
def read_root(user=Depends(get_optional_user)):
    return RedirectResponse(url="/today" if user else "/login", status_code=303)


@app.get("/health", include_in_schema=False)
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
