"""Action execution endpoints.

Every actionable suggestion in the product — a recommendation, an attention
item, a money-on-the-table row, a Copilot suggestion — resolves to a slug handled
here. The UI POSTs the slug plus its entity ids; the service does the work.

Two guarantees hold for every endpoint in this file:

* **Tenant scoped.** `user_id` is taken from the session, never from the form,
  so a crafted POST cannot reach another creator's records.
* **No silent side effects.** A handler either performs a real, described change
  and returns a destination, or returns a draft of text for the creator to
  review. Drafts are never saved as content, and no AI provider failure mutates
  data.
"""

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.services import actions
from app.templating import templates

router = APIRouter()

# which entity type each slug needs, so a bare id from an inline button is
# routed to the right parameter without the form having to say so
SLUG_ENTITY = {
    "draft_follow_up": "deal",
    "draft_invoice": "deal",
    "draft_reminder": "revenue",
    "mark_paid": "revenue",
    "complete_task": "task",
    "create_content_plan": "idea",
    "atomize": "content",
    "create_drafts": "content",
    "pursue_opportunity": "opportunity",
    "create_opportunity": "offer",
    "plan_next_episode": "series",
    "accept_week": "plan",
}


def _respond(request: Request, user, result: dict, fallback: str = "/today"):
    """A draft is shown for review; a real change redirects to where it landed."""
    if not result.get("ok"):
        return templates.TemplateResponse(
            request=request,
            name="action_result.html",
            context={"user": user, "result": result, "fallback": fallback},
            status_code=400,
        )
    if result.get("draft"):
        return templates.TemplateResponse(
            request=request,
            name="action_result.html",
            context={"user": user, "result": result, "fallback": fallback},
        )
    return RedirectResponse(url=result.get("url") or fallback, status_code=303)


def _collect(entity_id: str, entities: str) -> dict:
    params = {}
    if entities:
        try:
            parsed = json.loads(entities)
            if isinstance(parsed, dict):
                params.update(parsed)
        except ValueError:
            pass
    return params


@router.get("/actions")
def action_index(request: Request, user=Depends(get_current_user)):
    """The full action registry, so the command palette can offer the same verbs."""
    return {
        "actions": [
            {"slug": slug, "label": label, "entity": SLUG_ENTITY.get(slug)}
            for slug, label in actions.ACTION_LABELS.items()
        ]
    }


@router.post("/actions/run")
def run_action(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    slug: str = Form(...),
    entity_type: str = Form(""),
    entity_id: str = Form(""),
    entities: str = Form(""),
    next: str = Form(""),
):
    params = _collect(entity_id, entities)
    if entity_id and not entities:
        params.setdefault(
            f"{entity_type or SLUG_ENTITY.get(slug, 'entity')}_id",
            int(entity_id) if entity_id.lstrip("-").isdigit() else entity_id,
        )
    result = actions.run(db, user.id, slug, params)
    return _respond(request, user, result, fallback=next or "/today")


@router.post("/action/{slug}")
def run_named_action(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    entity_id: str = Form(""),
    entities: str = Form(""),
    next: str = Form(""),
):
    """Inline-button alias: POST /action/draft_follow_up with entity_id."""
    params = _collect(entity_id, entities)
    if entity_id and not entities:
        kind = SLUG_ENTITY.get(slug)
        if kind:
            params.setdefault(
                f"{kind}_id", int(entity_id) if entity_id.lstrip("-").isdigit() else entity_id
            )
    result = actions.run(db, user.id, slug, params)
    return _respond(request, user, result, fallback=next or "/today")


def _summarise_buckets(buckets: dict) -> dict:
    """Flatten a triage result into plain JSON.

    `clear_slate` returns live ORM objects, which cannot be serialised and are
    meaningless to a spoken answer anyway. What the caller needs is the label and
    the reason, so those are the only things carried across.
    """
    plain = {}
    for name, items in (buckets or {}).items():
        rows = []
        for item in items:
            label = item.get("title")
            if not label:
                task = item.get("task")
                label = getattr(task, "title", None) if task is not None else None
            rows.append({"title": label or "(untitled)", "reason": item.get("reason", "")})
        plain[name] = rows
    return plain


@router.post("/api/actions/run")
def run_action_json(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    slug: str = Form(...),
    entity_id: str = Form(""),
    entities: str = Form(""),
):
    """The same action dispatch, as JSON, for the voice layer.

    This is not a second way to run an action — it calls `actions.run` with the
    identical slug and parameters, so a spoken action can never do more than the
    button that sits next to it. `user_id` comes from the session dependency, never
    from the form, so this route is scoped to one account exactly as the HTML ones
    are.
    """
    params = _collect(entity_id, entities)
    if entity_id and not entities:
        kind = SLUG_ENTITY.get(slug)
        if kind:
            params.setdefault(
                f"{kind}_id", int(entity_id) if entity_id.lstrip("-").isdigit() else entity_id
            )

    result = actions.run(db, user.id, slug, params)
    payload = {
        "slug": slug,
        "ok": bool(result.get("ok")),
        "message": result.get("message", ""),
        "url": result.get("url") or "",
        "draft": result.get("draft") or "",
        # A draft is text for the creator to review, so it is returned rather
        # than summarised, and it is never saved by this route.
        "buckets": _summarise_buckets(result.get("buckets")),
    }
    # An unknown slug is a bad request, not a server fault.
    return JSONResponse(content=payload, status_code=200 if payload["ok"] else 400)
