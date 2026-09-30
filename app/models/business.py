"""3.0 business models: brands, series, content atoms, offers, activity, plans.

Every table is additive — no existing column is renamed or dropped, so upgrading
a 2.0 database preserves all data. Every row carries `user_id` and the route layer
filters on it, matching the rest of the application's tenant model.
"""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class Brand(Base):
    """A brand relationship, independent of any single campaign."""

    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    website = Column(String)
    contact_name = Column(String)
    contact_email = Column(String)
    relationship_status = Column(String, default="active")   # active | dormant | prospect | churned
    notes = Column(Text)
    last_interaction_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def label(self) -> str:
        return self.name


class ContentSeries(Base):
    """A named sequence of content the creator intends to keep publishing."""

    __tablename__ = "content_series"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    pillar_id = Column(Integer, ForeignKey("content_pillars.id", ondelete="SET NULL"))
    platform = Column(String, default="youtube")
    target_episodes = Column(Integer, default=0)   # 0 means "no declared length"
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ContentAtom(Base):
    """One extractable idea pulled out of an original piece of content.

    Atoms are the unit of repurposing: the atomization step proposes them, the
    creator selects which to keep, and converting an atom creates a real content
    record. Nothing is ever published automatically.
    """

    __tablename__ = "content_atoms"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content_id = Column(
        Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(String, default="short_form")   # core_idea | hook | short_form | carousel | text_post | story | future_idea
    title = Column(String, nullable=False)
    body = Column(Text)
    platform = Column(String, default="instagram")
    content_type = Column(String, default="other")
    status = Column(String, default="proposed")   # proposed | created | dismissed
    derivative_content_id = Column(
        Integer, ForeignKey("content_items.id", ondelete="SET NULL")
    )
    created_at = Column(DateTime, server_default=func.now())


class ContentTemplate(Base):
    """A reusable content structure the creator can apply to a new piece."""

    __tablename__ = "content_templates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    category = Column(String, default="educational")  # educational | review | story | sales | other
    summary = Column(String)
    sections = Column(Text)        # newline separated step labels
    body = Column(Text)            # the filled-in example / instructions
    is_favorite = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Offer(Base):
    """A packageable thing the creator sells: sponsorship, UGC, consulting, etc."""

    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    offer_type = Column(String, default="sponsored_content")
    description = Column(Text)
    deliverables = Column(Text)
    price = Column(Float, default=0.0)
    turnaround_days = Column(Integer)
    terms = Column(Text)
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ActivityEvent(Base):
    """One entry in the creator business timeline.

    This is the connective tissue of the product: it records that an idea became
    content, that a deal was created, that a payment landed. It is written by the
    service layer, never by the UI, so the timeline cannot be faked.
    """

    __tablename__ = "activity_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)
    # idea | content | deal | deliverable | revenue | task | opportunity | goal | series | offer
    entity_type = Column(String)
    entity_id = Column(Integer)
    title = Column(String, nullable=False)
    detail = Column(String)
    amount = Column(Float)
    occurred_at = Column(DateTime, server_default=func.now(), index=True)
    created_at = Column(DateTime, server_default=func.now())


class WeekPlan(Base):
    """A proposed weekly schedule the creator can accept in one click."""

    __tablename__ = "week_plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    week_start = Column(DateTime, nullable=False, index=True)
    status = Column(String, default="proposed")   # proposed | accepted | dismissed
    payload = Column(Text)
    accepted_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


class CopilotMessage(Base):
    """Conversation history for the Creator Copilot.

    Stored so the copilot can refer back to what the creator already asked, and
    so every grounded answer stays auditable.
    """

    __tablename__ = "copilot_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    intent = Column(String, default="unknown")
    # system | user-entered | rules | ai-assisted
    basis = Column(String, default="system-derived")
    grounded = Column(Boolean, default=True)
    citations = Column(Text)      # comma separated entity references used
    actions = Column(Text)         # serialized action slugs
    created_at = Column(DateTime, server_default=func.now(), index=True)


class StageEvent(Base):
    """Brand interaction log, used to power the follow-up engine honestly."""

    __tablename__ = "stage_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    deal_id = Column(Integer, ForeignKey("brand_deals.id", ondelete="CASCADE"), index=True)
    kind = Column(String, nullable=False)   # contacted | replied | pitched | delivered | invoiced | paid | note
    summary = Column(String)
    occurred_at = Column(DateTime, server_default=func.now(), index=True)
    created_at = Column(DateTime, server_default=func.now())
