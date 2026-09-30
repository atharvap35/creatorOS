"""AI assistant endpoint. Output is returned for editing — never auto-saved."""

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.services import ai as ai_service
from app.templating import templates

router = APIRouter()

ACTIONS = {
    "hooks": "Generate hooks",
    "outline": "Generate an outline",
    "script": "Generate a script",
    "caption": "Write a caption",
    "repurpose": "Create a repurposing plan",
    "follow_up": "Draft a follow-up",
    "summarize": "Summarize a transcript",
}


@router.get("/assistant")
def assistant_page(request: Request, user=Depends(get_current_user), action: str = "hooks", subject: str = ""):
    return templates.TemplateResponse(
        request=request,
        name="assistant.html",
        context={
            "user": user,
            "actions": ACTIONS,
            "action": action if action in ACTIONS else "hooks",
            "subject": subject,
            "output": None,
            "status": ai_service.ai_status(),
        },
    )


@router.post("/assistant")
def run_assistant(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    action: str = Form("hooks"),
    subject: str = Form(""),
    context_text: str = Form(""),
):
    from app.models.workspace import AIInteraction

    action = action if action in ACTIONS else "hooks"
    prompt = f"{action}: {subject}"
    if context_text.strip():
        prompt += f"\n\n{context_text.strip()}"

    provider = ai_service.get_provider()
    try:
        output = provider.complete(prompt)
        failed = False
    except Exception as exc:  # never let an external provider break the app
        output = (
            f"The {provider.name} provider could not be reached ({type(exc).__name__}). "
            "Your data is safe — try again, or keep writing manually."
        )
        failed = True

    if not failed:
        db.add(
            AIInteraction(
                user_id=user.id, kind=action, provider=provider.name, prompt=prompt, response=output
            )
        )
        db.commit()

    return templates.TemplateResponse(
        request=request,
        name="assistant.html",
        context={
            "user": user,
            "actions": ACTIONS,
            "action": action,
            "subject": subject,
            "output": output,
            "failed": failed,
            "status": ai_service.ai_status(),
        },
    )
