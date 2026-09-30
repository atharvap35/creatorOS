from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.services import search as search_service
from app.templating import templates

router = APIRouter()


@router.get("/search")
def search_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    q: str = "",
):
    groups = search_service.search_all(db, user.id, q)
    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={"user": user, "q": q, "groups": groups, "total": sum(len(g["items"]) for g in groups)},
    )


@router.get("/api/search")
def api_search(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    q: str = "",
):
    return {"results": search_service.quick_search(db, user.id, q)}


@router.get("/api/commands")
def api_commands(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {"commands": search_service.command_items(db, user.id)}


@router.get("/api/today")
def api_today(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.services.recommender import best_next_thing, weekly_workload

    return {
        "one_thing": best_next_thing(db, user.id, 30),
        "workload": weekly_workload(db, user.id),
    }
