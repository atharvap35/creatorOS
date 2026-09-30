from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import COOKIE_SECURE, SESSION_TTL_DAYS
from app.database import get_db
from app.security import (
    SESSION_COOKIE_NAME,
    authenticate,
    create_session,
    create_user,
    delete_session,
    get_user_by_email,
    is_valid_email,
)
from app.services.seed import seed_db
from app.templating import templates

router = APIRouter()

PROTECTED_PATHS = {
    "/dashboard",
    "/today",
    "/content",
    "/content/pipeline",
    "/content/pillars",
    "/tasks",
    "/workflow",
    "/workflow/focus",
    "/deals",
    "/money",
    "/money/payments",
    "/rate-card",
    "/revenue",
    "/ideas",
    "/growth",
    "/growth/opportunities",
    "/opportunities",
    "/library",
    "/goals",
    "/reviews/weekly",
    "/reviews/monthly",
    "/calendar",
    "/search",
    "/quick",
    "/onboarding",
    "/assistant",
    "/settings",
}


def _safe_next(raw: str) -> str:
    """Only allow same-site redirects to known app pages."""
    if raw in PROTECTED_PATHS:
        return raw
    return "/today"


def _start_session(response: RedirectResponse, token: str) -> RedirectResponse:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=60 * 60 * 24 * SESSION_TTL_DAYS,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    return response


@router.get("/login")
def login_page(request: Request, next: str = ""):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "", "next_url": _safe_next(next)},
    )


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/today"),
    db: Session = Depends(get_db),
):
    user = authenticate(db, email, password)
    if not user:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "That email and password combination didn't work.",
                "next_url": _safe_next(next),
            },
            status_code=401,
        )

    session = create_session(db, user)
    return _start_session(
        RedirectResponse(url=_safe_next(next), status_code=303), session.token
    )


@router.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={"error": ""},
    )


@router.post("/register")
def register_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    name = name.strip()
    error = None

    if len(name) < 2:
        error = "Please tell us your name."
    elif not is_valid_email(email):
        error = "Please enter a valid email address."
    elif len(password) < 8:
        error = "Password must be at least 8 characters long."
    elif get_user_by_email(db, email):
        error = "An account with that email already exists."

    if error:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": error},
            status_code=400,
        )

    user = create_user(db, email=email, name=name, password=password)
    seed_db(db, user_id=user.id, name=user.name, email=user.email)

    session = create_session(db, user)
    return _start_session(RedirectResponse(url="/today", status_code=303), session.token)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    delete_session(db, request.cookies.get(SESSION_COOKIE_NAME))
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
