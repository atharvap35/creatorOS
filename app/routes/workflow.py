import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.business import WeekPlan
from app.models.task import Task, TaskCategory, TaskPriority, TaskStatus
from app.route_utils import clean, parse_enum, parse_optional_datetime, parse_optional_int
from app.services import actions, brain, recommender
from app.templating import templates

router = APIRouter()

VIEWS = {
    "today": "Today",
    "upcoming": "Upcoming",
    "overdue": "Overdue",
    "completed": "Completed",
}


@router.get("/workflow/plan")
def week_plan(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Propose a week, then let the creator accept, change, or refuse it.

    Nothing is scheduled until the plan is accepted, and accepting only writes
    the plan day onto records the creator already owns.
    """
    plans = (
        db.query(WeekPlan)
        .filter(WeekPlan.user_id == user.id, WeekPlan.status == "proposed")
        .order_by(WeekPlan.created_at.desc())
        .all()
    )
    plan = plans[0] if plans else None
    payload = json.loads(plan.payload) if plan and plan.payload else None

    rebalance = None
    ctx = brain.snapshot(db, user.id)
    if ctx["capacity"]["over_capacity"]:
        rebalance = actions.rebalance_week(db, user.id)

    return templates.TemplateResponse(
        request=request,
        name="week_plan.html",
        context={
            "user": user,
            "plan": plan,
            "payload": payload,
            "capacity": ctx["capacity"],
            "rebalance": rebalance,
            "preference": ctx["preference"],
        },
    )


@router.post("/workflow/plan/propose")
def propose_week(db: Session = Depends(get_db), user=Depends(get_current_user)):
    actions.propose_week(db, user.id)
    return RedirectResponse(url="/workflow/plan", status_code=303)


@router.post("/workflow/plan/accept")
def accept_week(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    plan_id: str = Form(""),
):
    if plan_id.isdigit():
        actions.accept_week(db, user.id, int(plan_id))
    return RedirectResponse(url="/workflow?view=week", status_code=303)


@router.post("/workflow/plan/dismiss")
def dismiss_plan(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    plan_id: str = Form(""),
):
    plan = (
        db.query(WeekPlan)
        .filter(WeekPlan.id == plan_id, WeekPlan.user_id == user.id)
        .first()
        if plan_id.isdigit()
        else None
    )
    if plan:
        plan.status = "dismissed"
        db.commit()
    return RedirectResponse(url="/workflow/plan", status_code=303)


def _bucket(db: Session, user_id: int, view: str) -> list:
    now = datetime.now()
    today = now.date()
    query = db.query(Task).filter(Task.user_id == user_id)

    if view == "today":
        return query.filter(
            Task.status != TaskStatus.completed,
            Task.due_date.isnot(None),
            Task.due_date < datetime(today.year, today.month, today.day) + timedelta(days=1),
        ).order_by(Task.due_date).all()
    if view == "overdue":
        return query.filter(
            Task.status != TaskStatus.completed, Task.due_date.isnot(None), Task.due_date < now
        ).order_by(Task.due_date).all()
    if view == "completed":
        return query.filter(Task.status == TaskStatus.completed).order_by(Task.completed_at.desc()).all()
    return query.filter(
        Task.status != TaskStatus.completed,
        Task.due_date.isnot(None),
        Task.due_date >= datetime(today.year, today.month, today.day),
    ).order_by(Task.due_date).all()


@router.get("/workflow")
def workflow(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    view: str = "today",
    q: str = "",
    created: str = "",
):
    if view not in VIEWS:
        view = "today"

    items = _bucket(db, user.id, view)
    if q.strip():
        term = f"%{q.strip()}%"
        items = [t for t in items if term.lower()[1:-1] in (t.title or "").lower()]

    counts = {key: len(_bucket(db, user.id, key)) for key in VIEWS}
    return templates.TemplateResponse(
        request=request,
        name="workflow.html",
        context={
            "user": user,
            "items": items,
            "views": VIEWS,
            "view": view,
            "counts": counts,
            "q": q,
            "created": created,
            "workload": recommender.weekly_workload(db, user.id),
        },
    )


@router.get("/tasks")
def tasks_alias(user=Depends(get_current_user)):
    return RedirectResponse(url="/workflow", status_code=303)


@router.get("/workflow/focus")
def focus_mode(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    focus: str = "",
):
    """One task. No navigation. Finish it or skip it."""
    task = None
    if focus.isdigit():
        task = (
            db.query(Task)
            .filter(Task.id == int(focus), Task.user_id == user.id)
            .first()
        )
    if task is None:
        task = (
            db.query(Task)
            .filter(Task.user_id == user.id, Task.status != TaskStatus.completed, Task.due_date.isnot(None))
            .order_by(Task.due_date)
            .first()
        )
    return templates.TemplateResponse(
        request=request,
        name="focus.html",
        context={"user": user, "task": task, "workload": recommender.weekly_workload(db, user.id)},
    )


@router.post("/workflow/focus/{task_id}")
def complete_from_focus(
    task_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    action: str = Form("complete"),
):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if task:
        if action == "skip":
            task.status = TaskStatus.in_progress
        else:
            task.status = TaskStatus.completed
            task.completed_at = datetime.now()
        db.commit()
    return RedirectResponse(url="/workflow/focus", status_code=303)


@router.post("/workflow")
@router.post("/tasks")
def create_task(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form("content"),
    priority: str = Form("medium"),
    due_date: str = Form(""),
    estimated_minutes: str = Form("20"),
):
    db.add(
        Task(
            user_id=user.id,
            title=title.strip(),
            description=clean(description),
            category=parse_enum(TaskCategory, category, TaskCategory.content),
            priority=parse_enum(TaskPriority, priority, TaskPriority.medium),
            status=TaskStatus.todo,
            due_date=parse_optional_datetime(due_date) or (datetime.now() if not due_date else None),
            estimated_minutes=parse_optional_int(estimated_minutes, 20),
        )
    )
    db.commit()
    return RedirectResponse(url="/workflow", status_code=303)


@router.post("/workflow/{task_id}/complete")
@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if task:
        if task.status == TaskStatus.completed:
            task.status = TaskStatus.todo
            task.completed_at = None
        else:
            task.status = TaskStatus.completed
            task.completed_at = datetime.now()
        db.commit()
    return RedirectResponse(url="/workflow", status_code=303)


@router.post("/workflow/{task_id}/status")
def set_task_status(
    task_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    status: str = Form(...),
):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if task:
        new_status = parse_enum(TaskStatus, status, task.status)
        task.status = new_status
        task.completed_at = datetime.now() if new_status == TaskStatus.completed else None
        db.commit()
    return RedirectResponse(url="/workflow", status_code=303)


@router.post("/workflow/{task_id}/delete")
@router.post("/tasks/{task_id}/delete")
def delete_task(task_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if task:
        db.delete(task)
        db.commit()
    return RedirectResponse(url="/workflow", status_code=303)
