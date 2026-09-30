"""Content atomization: turn one published piece into a set of draft derivatives.

The proposal step is deterministic when no AI provider is configured, and
provider-backed when one is. Either way the output is the *same shape*: a list of
proposed atoms grouped by kind. The creator selects which ones to keep, and only
then are real content records created. Nothing is ever published automatically.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.brief import ContentBrief
from app.models.business import ContentAtom
from app.models.content import ContentItem, ContentType, Platform, Status
from app.models.pillar import ContentPillar
from app.models.repurpose import ContentRepurpose

ATOM_KINDS = [
    ("core_idea", "Core ideas"),
    ("hook", "Hooks"),
    ("short_form", "Short-form ideas"),
    ("carousel", "Carousel ideas"),
    ("text_post", "Text posts"),
    ("story", "Story ideas"),
    ("future_idea", "Future content ideas"),
]

ATOM_DEFAULTS = {
    "core_idea": ("video", "instagram", 3),
    "hook": ("short", "tiktok", 5),
    "short_form": ("short", "tiktok", 3),
    "carousel": ("carousel", "instagram", 2),
    "text_post": ("post", "linkedin", 3),
    "story": ("story", "instagram", 3),
    "future_idea": ("video", "youtube", 2),
}

# Deterministic fallbacks. These are structural templates, not invented facts:
# they describe *how to cut* the creator's own material, never new claims.
STRUCTURED_ATOMS = {
    "core_idea": [
        "The single argument this piece makes, stated in one sentence",
        "The step that surprised you while making it",
        "The mistake you made that the audience will recognise",
        "The detail you'd defend if someone argued with you",
    ],
    "hook": [
        "Open with the number: “The exact number that changed my {topic}.”",
        "Open with the reframe: “I was wrong about {topic}.”",
        "Open with the tension: “Everyone does {topic} this way. It doesn't work.”",
        "Open with the result: “This took 30 days. Here's what held up.”",
        "Open with the question: “Why does {topic} keep breaking?”",
    ],
    "short_form": [
        "One idea, one claim, 30 seconds",
        "The before/after of {topic}",
        "The three-point version of the full piece",
        "The counter-intuitive take from this episode",
    ],
    "carousel": [
        "Slide-by-slide: the problem, then the three fixes",
        "Swipeable checklist pulled from this piece",
        "Myth vs reality, sourced from your own argument",
    ],
    "text_post": [
        "The lesson in first person, 150 words",
        "What I would do differently next time",
        "The framework version, for LinkedIn",
    ],
    "story": [
        "Poll: which mistake have you made?",
        "Question sticker: what should I cover next?",
        "Countdown to the long-form version",
    ],
    "future_idea": [
        "The sub-point that got the most comments",
        "The question this piece raised but didn't answer",
        "The tool or process behind this piece",
        "The beginner version of this topic",
    ],
}


def source_text(item: ContentItem, brief: ContentBrief | None) -> str:
    """Everything the creator has written about this piece, joined for the writer."""
    parts = [
        item.title,
        item.description or "",
        item.hook or "",
        item.script or "",
        item.caption or "",
        item.topic or "",
    ]
    if brief:
        parts += [brief.core_idea or "", brief.proof or "", brief.cta or ""]
    return "\n".join(p for p in parts if p).strip()


def propose(
    db: Session,
    user_id: int,
    content_id: int,
    *,
    use_ai: bool = True,
) -> dict:
    """Generate atom candidates for one content item. Persists them as drafts.

    Returns the proposal grouped by kind so the UI can render it directly.
    """
    item = (
        db.query(ContentItem)
        .filter(ContentItem.id == content_id, ContentItem.user_id == user_id)
        .first()
    )
    if not item:
        return {"item": None, "groups": [], "provider": None}

    brief = db.query(ContentBrief).filter(ContentBrief.content_id == item.id).first()
    text = source_text(item, brief)

    # clear any previous *proposed* atoms so re-running does not duplicate
    db.query(ContentAtom).filter(
        ContentAtom.user_id == user_id,
        ContentAtom.content_id == item.id,
        ContentAtom.status == "proposed",
    ).delete()
    db.commit()

    provider_name = "builtin"
    if use_ai and text:
        from app.services import ai as ai_service

        provider = ai_service.get_provider()
        provider_name = provider.name
        try:
            drafted = provider.complete(
                f"hooks: {item.title}\n\n{text}"
            )
            extra = _hooks_from_ai(drafted, item.title)
        except Exception:
            # a provider failure must never block repurposing
            extra = []
    else:
        extra = []

    topic = item.topic or item.title
    created = []
    for kind, _label in ATOM_KINDS:
        content_type, platform, count = ATOM_DEFAULTS[kind]
        titles = list(STRUCTURED_ATOMS[kind])
        if kind == "hook" and extra:
            titles = extra + titles[max(0, len(extra)) :]
        for title in titles[:count]:
            atom = ContentAtom(
                user_id=user_id,
                content_id=item.id,
                kind=kind,
                title=title.replace("{topic}", topic),
                body="",
                platform=platform,
                content_type=content_type,
                status="proposed",
            )
            db.add(atom)
            created.append(atom)
    db.commit()

    groups = []
    for kind, label in ATOM_KINDS:
        atoms = [a for a in created if a.kind == kind]
        if atoms:
            groups.append({"kind": kind, "label": label, "atoms": atoms})

    return {"item": item, "groups": groups, "provider": provider_name, "source_text": text}


def _hooks_from_ai(draft: str, topic: str) -> list:
    """Parse numbered lines out of a provider draft, ignoring anything odd."""
    hooks = []
    for line in (draft or "").splitlines():
        line = line.strip()
        if not line:
            continue
        cleaned = line
        for prefix in ("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "-", "*"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip()
                break
        if len(cleaned) > 8:
            hooks.append(cleaned)
        if len(hooks) >= 5:
            break
    return hooks


def atoms_for(db: Session, user_id: int, content_id: int) -> list:
    return (
        db.query(ContentAtom)
        .filter(
            ContentAtom.user_id == user_id,
            ContentAtom.content_id == content_id,
            ContentAtom.status != "dismissed",
        )
        .order_by(ContentAtom.id)
        .all()
    )


def create_drafts(
    db: Session,
    user_id: int,
    content_id: int,
    atom_ids: list,
    *,
    due_within_days: int = 7,
) -> list:
    """Turn selected atoms into real content records (status = idea).

    This is the only step that persists, and it deliberately stops at 'idea': the
    creator still decides what actually gets produced and published.
    """
    item = (
        db.query(ContentItem)
        .filter(ContentItem.id == content_id, ContentItem.user_id == user_id)
        .first()
    )
    if not item:
        return []

    ids = [int(i) for i in atom_ids if str(i).isdigit()]
    if not ids:
        return []

    atoms = (
        db.query(ContentAtom)
        .filter(
            ContentAtom.user_id == user_id,
            ContentAtom.content_id == content_id,
            ContentAtom.id.in_(ids),
        )
        .all()
    )

    deadline = datetime.now() + timedelta(days=due_within_days)
    created = []
    for atom in atoms:
        new_item = ContentItem(
            user_id=user_id,
            title=atom.title[:200],
            description=f"Atomized from “{item.title}”",
            content_type=_enum(ContentType, atom.content_type),
            platform=_enum(Platform, atom.platform),
            status=Status.idea,
            source="repurpose",
            repurposed_from_id=item.id,
            topic=item.topic,
            pillar_id=item.pillar_id,
            estimated_minutes=15,
            due_date=deadline,
        )
        db.add(new_item)
        db.flush()

        db.add(
            ContentBrief(
                user_id=user_id,
                content_id=new_item.id,
                audience=item.topic or "",
                hook=atom.title[:200],
                core_idea=f"Derived from “{item.title}”.",
            )
        )
        db.add(
            ContentRepurpose(
                user_id=user_id,
                content_id=item.id,
                kind=atom.kind,
                platform=atom.platform,
                title=new_item.title,
                status="in_progress",
            )
        )

        atom.status = "created"
        atom.derivative_content_id = new_item.id
        created.append(new_item)

    db.commit()
    return created


def _enum(enum_cls, raw: str, fallback=None):
    try:
        return enum_cls(raw)
    except (ValueError, KeyError, TypeError):
        try:
            return enum_cls[str(raw)]
        except KeyError:
            return fallback or enum_cls.other


def default_pillar_id(db: Session, user_id: int) -> int | None:
    pillar = db.query(ContentPillar).filter(ContentPillar.user_id == user_id).first()
    return pillar.id if pillar else None
