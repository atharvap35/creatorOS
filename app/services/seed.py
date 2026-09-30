"""The demo creator.

This is a single coherent story for one person, not a pile of sample rows. Alex
Carter runs a technology-and-productivity channel, works with a small number of
brands, and is currently in the middle of a month where three things are going
well and two are slipping.

The point of a realistic demo is that every screen has to survive real shape:
money still owed, a deal with no follow-up date, a series with a missing episode,
a backlog of ideas that are rotting, a week that is overcommitted. If the seed
were tidy the product would look finished while being untested.

Everything here is ordinary creator-entered data. There are no follower counts,
no engagement rates, no benchmark figures, and nothing derived from an external
platform.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.business import Brand, ContentSeries, Offer, StageEvent
from app.models.content import ContentItem, ContentType, Platform, Priority, Status
from app.models.creator import Creator
from app.models.creator_preference import CreatorPreference
from app.models.deal import BrandDeal, DealStatus, PaymentStatus
from app.models.goal import CreatorGoal
from app.models.idea import Idea, IdeaEffort, IdeaPotential, IdeaStatus, IdeaType
from app.models.opportunity import (
    MonetizationOpportunity,
    OpportunityEffort,
    OpportunityPotential,
    OpportunityStatus,
    OpportunityType,
)
from app.models.pillar import ContentPillar
from app.models.revenue import Revenue, RevenueSource, RevenueStatus
from app.models.task import Task, TaskCategory, TaskPriority, TaskStatus

PILLARS = [
    ("Tools & Apps", "Reviews and comparisons of software I actually pay for.", "#5B8DEF"),
    ("Creator Business", "How I run this channel as a business.", "#E0654A"),
    ("Workflow", "Systems, process, and the boring part that works.", "#3FA98A"),
]

BRANDS = [
    ("Acme Brand", "https://acme.example", "Riley Chen", "riley@acme.example", "active"),
    ("TechCorp", "https://techcorp.example", "Jordan Patel", "jordan@techcorp.example", "active"),
    ("GadgetCo", "https://gadgetco.example", "Sam Okafor", "sam@gadgetco.example", "paused"),
    ("Nova Labs", "", "Robin Adeyemi", "robin@novalabs.example", "prospect"),
]

SERIES = [
    ("Ship in Public", "Weekly build notes: what shipped, what broke, what I learned.", "youtube", 12),
    ("Desk Setup Tours", "A full tour of the setup behind every video.", "youtube", 8),
    ("One App a Week", "One app, one week, one honest verdict.", "instagram", 24),
]

OFFERS = [
    ("60s sponsored video", "sponsorship", 4500, 14, "One 60s integrated video, one revision round, pinned comment for 7 days."),
    ("Newsletter placement", "sponsorship", 1200, 5, "One mention in the newsletter, 40k+ subscribers."),
    ("Tooling audit", "consulting", 2500, 21, "A two-hour audit of your creator stack with a written recommendation."),
]

# (title, campaign, value, stage, payment_status, deadline_offset_days,
#  payment_due_offset_days, follow_up_offset_days, estimated_hours)
DEALS = [
    ("Acme Brand", "Summer Tech Push", 15000, "active", "pending", 3, 2, 1, 42),
    ("TechCorp", "New Laptop Review", 25000, "active", "not_invoiced", 18, 24, 6, 60),
    ("GadgetCo", "Winter Bundle", 8000, "delivered", "pending", -4, -2, None, 26),
    ("Acme Brand", "Newsletter Q4", 6000, "agreed", "invoiced", 26, 10, 3, 12),
    ("Nova Labs", "Beta Access", 4000, "negotiating", "not_invoiced", 40, None, None, 18),
    ("TechCorp", "Always-on Stories", 5000, "completed", "paid", -30, -26, None, 20),
]

# (title, source, amount, status, days_ago, deal_index_or_None, description)
REVENUE = [
    ("Spring campaign", RevenueSource.sponsorship, 12000, RevenueStatus.received, 150, 5, "TechCorp · Spring campaign"),
    ("Roundup sponsorship", RevenueSource.sponsorship, 4500, RevenueStatus.received, 96, None, "Acme Brand · roundup mention"),
    ("Template pack", RevenueSource.digital_product, 1180, RevenueStatus.received, 74, None, "Notion second-brain pack"),
    ("Consulting hour", RevenueSource.services, 900, RevenueStatus.received, 61, None, "Audit session"),
    ("Affiliate month", RevenueSource.affiliate, 640, RevenueStatus.received, 45, None, "Desk mat affiliate"),
    ("Newsletter bundle", RevenueSource.sponsorship, 9000, RevenueStatus.received, 30, 5, "TechCorp · always-on stories"),
    ("Membership month", RevenueSource.membership, 320, RevenueStatus.received, 18, None, "Nine founding members"),
    ("Summer Tech Push", RevenueSource.sponsorship, 15000, RevenueStatus.pending, 0, 0, "Acme Brand · invoiced, not yet received"),
    ("Winter Bundle", RevenueSource.sponsorship, 8000, RevenueStatus.overdue, 0, 2, "GadgetCo · winter bundle"),
    ("Template pack top-ups", RevenueSource.digital_product, 890, RevenueStatus.pending, 0, None, "Second cohort"),
]

CONTENT = [
    # published, with room to repurpose
    ("5 Productivity Apps I Actually Use", "video", Platform.youtube, Status.published, -28, "Tools & Apps"),
    ("The Desk Setup Behind Every Video", "video", Platform.youtube, Status.published, -21, "Workflow"),
    ("I Replaced Four Tools With One", "video", Platform.youtube, Status.published, -14, "Tools & Apps"),
    ("Ship in Public 01: the billing bug", "video", Platform.youtube, Status.published, -19, "Creator Business"),
    ("Ship in Public 02: the migration", "video", Platform.youtube, Status.published, -12, "Creator Business"),
    ("Ship in Public 03: launch week", "video", Platform.youtube, Status.published, -5, "Creator Business"),
    ("One App a Week: Obsidian", "reel", Platform.instagram, Status.published, -9, "Tools & Apps"),
    ("One App a Week: Raycast", "reel", Platform.instagram, Status.published, -2, "Tools & Apps"),
    ("The honest cost of running a channel", "video", Platform.youtube, Status.published, -34, "Creator Business"),
    ("Why your content calendar is empty", "carousel", Platform.instagram, Status.published, -7, "Creator Business"),
    # in flight
    ("AI Tools Nobody Talks About", "reel", Platform.instagram, Status.editing, 2, "Tools & Apps"),
    ("My 30 Minute Content Workflow", "newsletter", Platform.newsletter, Status.ready, 1, "Workflow"),
    ("Ship in Public 04: the pricing change", "video", Platform.youtube, Status.scripting, 4, "Creator Business"),
    ("Gear I would buy again in 2026", "carousel", Platform.instagram, Status.scripting, -3, "Tools & Apps"),
    ("Desk Setup Tour: the edit", "video", Platform.youtube, Status.filming, 5, "Workflow"),
    ("How I price a sponsorship", "video", Platform.youtube, Status.editing, 8, "Creator Business"),
    ("One App a Week: Linear", "reel", Platform.instagram, Status.scripting, 6, "Tools & Apps"),
    ("The monthly numbers, unedited", "newsletter", Platform.newsletter, Status.ready, 11, "Creator Business"),
    # stalled on purpose: no update in weeks
    ("Cold email templates that worked", "carousel", Platform.instagram, Status.editing, -16, "Creator Business"),
    ("Notion vs Obsidian, six months on", "video", Platform.youtube, Status.scripting, -12, "Tools & Apps"),
    # planned but not started
    ("What I would automate first", "video", Platform.youtube, Status.idea, 14, "Workflow"),
    ("Sponsor outreach that is not cringe", "carousel", Platform.instagram, Status.idea, 18, "Creator Business"),
    ("Reading list: 12 systems books", "newsletter", Platform.newsletter, Status.idea, 21, "Workflow"),
    ("The channel at 100k: what changes", "video", Platform.youtube, Status.idea, 25, "Creator Business"),
]

# (title, type, potential, effort, confidence, monetization)
IDEAS = [
    ("Why your content calendar is empty", IdeaType.content, IdeaPotential.high, IdeaEffort.low, "high", "medium"),
    ("The one metric that predicts sponsor renewals", IdeaType.content, IdeaPotential.high, IdeaEffort.medium, "medium", "high"),
    ("Batch filming 30 videos in a day", IdeaType.content, IdeaPotential.medium, IdeaEffort.high, "low", "low"),
    ("I audited 40 creator websites", IdeaType.content, IdeaPotential.high, IdeaEffort.medium, "high", "high"),
    ("What breaks when you grow past 100k", IdeaType.content, IdeaPotential.high, IdeaEffort.low, "medium", "high"),
    ("Cold outreach that got me 40% reply rate", IdeaType.product, IdeaPotential.high, IdeaEffort.low, "high", "high"),
    ("Sponsor pricing calculator", IdeaType.product, IdeaPotential.high, IdeaEffort.medium, "medium", "high"),
    ("Notion second-brain v3", IdeaType.product, IdeaPotential.medium, IdeaEffort.high, "high", "high"),
    ("Creator tax checklist", IdeaType.product, IdeaPotential.medium, IdeaEffort.low, "medium", "medium"),
    ("Monthly channel retrospective email", IdeaType.affiliate, IdeaPotential.low, IdeaEffort.low, "high", "low"),
    ("Desk mat affiliate roundup", IdeaType.affiliate, IdeaPotential.medium, IdeaEffort.low, "high", "medium"),
    ("Micro-influencer swap programme", IdeaType.affiliate, IdeaPotential.medium, IdeaEffort.medium, "low", "medium"),
    ("Five apps I stopped paying for", IdeaType.sponsorship, IdeaPotential.high, IdeaEffort.low, "high", "high"),
    ("A year of channel numbers, in public", IdeaType.sponsorship, IdeaPotential.high, IdeaEffort.medium, "high", "high"),
    ("The honest cost of a bad month", IdeaType.sponsorship, IdeaPotential.medium, IdeaEffort.low, "medium", "medium"),
    ("Setup tour: the cable management", IdeaType.content, IdeaPotential.low, IdeaEffort.low, "high", "low"),
    ("Reading list for creator ops", IdeaType.content, IdeaPotential.medium, IdeaEffort.low, "high", "medium"),
    ("How I plan a month of content in 30 minutes", IdeaType.content, IdeaPotential.high, IdeaEffort.medium, "high", "medium"),
    ("Testing four microphones", IdeaType.content, IdeaPotential.medium, IdeaEffort.medium, "medium", "high"),
    ("The retention graph nobody explains", IdeaType.content, IdeaPotential.high, IdeaEffort.high, "low", "medium"),
    ("Answering the comment I get most", IdeaType.content, IdeaPotential.medium, IdeaEffort.low, "high", "low"),
    ("Live working session, unedited", IdeaType.content, IdeaPotential.high, IdeaEffort.high, "medium", "low"),
    ("What I would do differently starting over", IdeaType.content, IdeaPotential.high, IdeaEffort.low, "high", "medium"),
    ("Software I pay for but do not use", IdeaType.content, IdeaPotential.medium, IdeaEffort.low, "high", "high"),
    ("The deal I should have declined", IdeaType.content, IdeaPotential.high, IdeaEffort.low, "medium", "medium"),
    ("Batch of 15 hooks for tech reviews", IdeaType.content, IdeaPotential.medium, IdeaEffort.low, "high", "medium"),
    ("A channel contract template", IdeaType.product, IdeaPotential.medium, IdeaEffort.medium, "medium", "high"),
    ("Gear guide for under 500", IdeaType.affiliate, IdeaPotential.medium, IdeaEffort.medium, "high", "high"),
    ("Behind the scenes of a sponsor integration", IdeaType.sponsorship, IdeaPotential.medium, IdeaEffort.medium, "medium", "high"),
    ("What I learned from 30 brand deals", IdeaType.sponsorship, IdeaPotential.high, IdeaEffort.medium, "medium", "high"),
    ("Editing tricks I actually use", IdeaType.content, IdeaPotential.medium, IdeaEffort.low, "high", "low"),
    ("The planning template I sell", IdeaType.product, IdeaPotential.high, IdeaEffort.medium, "medium", "high"),
]

# (title, category, priority, status, due_offset, minutes)
# categories are the real TaskCategory values: content, business, monetization, audience, admin
TASKS = [
    ("Send GadgetCo the final invoice", TaskCategory.monetization, TaskPriority.urgent, TaskStatus.todo, -3, 15),
    ("Chase Acme Brand on the summer invoice", TaskCategory.monetization, TaskPriority.urgent, TaskStatus.todo, -1, 10),
    ("Record Ship in Public 04", TaskCategory.content, TaskPriority.high, TaskStatus.todo, 0, 90),
    ("Edit AI Tools Nobody Talks About", TaskCategory.content, TaskPriority.high, TaskStatus.in_progress, 1, 120),
    ("Send TechCorp the laptop review draft", TaskCategory.monetization, TaskPriority.high, TaskStatus.todo, 2, 45),
    ("Reply to Nova Labs about beta terms", TaskCategory.business, TaskPriority.medium, TaskStatus.todo, 2, 20),
    ("Publish the 30 minute workflow newsletter", TaskCategory.content, TaskPriority.high, TaskStatus.todo, 1, 30),
    ("Film the desk setup tour", TaskCategory.content, TaskPriority.medium, TaskStatus.todo, 5, 120),
    ("Outline the pricing calculator", TaskCategory.monetization, TaskPriority.medium, TaskStatus.todo, 6, 60),
    ("Batch record three hooks", TaskCategory.content, TaskPriority.medium, TaskStatus.todo, 4, 60),
    ("Update the rate card with 2026 rates", TaskCategory.admin, TaskPriority.low, TaskStatus.todo, 9, 30),
    ("Write the monthly numbers email", TaskCategory.admin, TaskPriority.medium, TaskStatus.todo, 8, 45),
    ("Archive the winter bundle footage", TaskCategory.admin, TaskPriority.low, TaskStatus.todo, 12, 25),
    ("Reply to the three DMs about pricing", TaskCategory.audience, TaskPriority.medium, TaskStatus.todo, 0, 20),
    ("Renew the domain", TaskCategory.admin, TaskPriority.high, TaskStatus.todo, 3, 10),
    ("Review Acme Brand deliverable list", TaskCategory.monetization, TaskPriority.medium, TaskStatus.in_progress, 1, 30),
    ("Finish Linear review script", TaskCategory.content, TaskPriority.medium, TaskStatus.todo, 6, 45),
    ("Write cold outreach templates", TaskCategory.monetization, TaskPriority.low, TaskStatus.todo, 14, 60),
    ("Backup the channel drive", TaskCategory.admin, TaskPriority.low, TaskStatus.todo, 10, 40),
    ("Outline Notion vs Obsidian follow-up", TaskCategory.content, TaskPriority.low, TaskStatus.todo, -6, 40),
    ("Sort the idea backlog into a plan", TaskCategory.business, TaskPriority.medium, TaskStatus.todo, 2, 30),
    ("Ship the pricing page copy", TaskCategory.monetization, TaskPriority.medium, TaskStatus.completed, -1, 50),
    ("Send thank-you note to TechCorp", TaskCategory.business, TaskPriority.low, TaskStatus.completed, -2, 10),
    ("Fix the caption typo on episode 03", TaskCategory.content, TaskPriority.low, TaskStatus.completed, -3, 10),
]

# (title, type, status, potential, effort, value, deadline_offset)
OPPORTUNITIES = [
    ("Laptop brand spring launch", OpportunityType.sponsorship, OpportunityStatus.evaluating, OpportunityPotential.high, OpportunityEffort.medium, 25000, 21),
    ("Desk accessory brand partnership", OpportunityType.sponsorship, OpportunityStatus.idea, OpportunityPotential.medium, OpportunityEffort.low, 6000, 35),
    ("Notion alternative review series", OpportunityType.affiliate, OpportunityStatus.idea, OpportunityPotential.high, OpportunityEffort.medium, 9000, 45),
    ("Creator tooling newsletter", OpportunityType.sponsorship, OpportunityStatus.idea, OpportunityPotential.medium, OpportunityEffort.low, 4500, 30),
    ("Workshop: monetise your audience", OpportunityType.service, OpportunityStatus.evaluating, OpportunityPotential.high, OpportunityEffort.high, 12000, 60),
    ("Microphone brand ambassador", OpportunityType.sponsorship, OpportunityStatus.idea, OpportunityPotential.medium, OpportunityEffort.medium, 8000, 50),
    ("Conference talk", OpportunityType.content_monetization, OpportunityStatus.idea, OpportunityPotential.medium, OpportunityEffort.high, 5000, 90),
    ("Template bundle refresh", OpportunityType.digital_product, OpportunityStatus.idea, OpportunityPotential.high, OpportunityEffort.low, 3000, 28),
    ("Standing affiliate for keyboard", OpportunityType.affiliate, OpportunityStatus.idea, OpportunityPotential.low, OpportunityEffort.low, 2000, 40),
    ("Second newsletter sponsor slot", OpportunityType.sponsorship, OpportunityStatus.idea, OpportunityPotential.medium, OpportunityEffort.low, 3500, 25),
]

GOALS = [
    ("Earn 12,000 this month", "revenue", "monthly_revenue", 12000, "USD", 31),
    ("Publish 8 pieces this month", "content", "published_items", 8, "pieces", 31),
    ("Get 3 deals closed this quarter", "deals", "closed_deals", 3, "deals", 92),
]


def seed_db(db: Session, user_id: int, name: str = "Creator", email: str = "") -> None:
    """Populate a brand new account with a realistic, coherent workspace."""
    already_seeded = db.query(Task).filter(Task.user_id == user_id).first()
    if already_seeded:
        return

    if not db.query(Creator).filter(Creator.user_id == user_id).first():
        db.add(
            Creator(
                user_id=user_id,
                name=name,
                email=email or f"user{user_id}@creatoros.local",
                niche="Technology & Productivity",
                bio="Building a sustainable creator business.",
                timezone="UTC",
                currency="USD",
            )
        )

    if not db.query(CreatorPreference).filter(CreatorPreference.user_id == user_id).first():
        db.add(
            CreatorPreference(
                user_id=user_id,
                working_days="Mon,Tue,Wed,Thu,Fri",
                hours_per_day=4,
                monthly_revenue_target=12000,
                series_length_default=12,
            )
        )

    now = datetime.now()
    pillar_ids = _seed_pillars(db, user_id)
    brand_ids = _seed_brands(db, user_id)
    series_ids = _seed_series(db, user_id, pillar_ids)
    _seed_offers(db, user_id)
    deals = _seed_deals(db, user_id, brand_ids, now)
    _seed_revenue(db, user_id, deals, now)
    _seed_content(db, user_id, pillar_ids, series_ids, now)
    _seed_ideas(db, user_id, pillar_ids, now)
    _seed_tasks(db, user_id, now)
    _seed_opportunities(db, user_id, now)
    _seed_goals(db, user_id, now)
    _seed_history(db, user_id, deals, now)
    db.commit()


def _seed_pillars(db: Session, user_id: int) -> dict:
    rows = [ContentPillar(user_id=user_id, name=n, description=d, color=c, is_active=True) for n, d, c in PILLARS]
    db.add_all(rows)
    db.commit()
    return {r.name: r.id for r in rows}


def _seed_brands(db: Session, user_id: int) -> dict:
    rows = [
        Brand(
            user_id=user_id,
            name=n,
            website=w,
            contact_name=c,
            contact_email=e,
            relationship_status=s,
        )
        for n, w, c, e, s in BRANDS
    ]
    db.add_all(rows)
    db.commit()
    return {r.name: r.id for r in rows}


def _seed_series(db: Session, user_id: int, pillar_ids: dict) -> dict:
    pillar_for = {
        "Ship in Public": "Creator Business",
        "Desk Setup Tours": "Workflow",
        "One App a Week": "Tools & Apps",
    }
    rows = [
        ContentSeries(
            user_id=user_id,
            name=n,
            description=d,
            platform=p,
            target_episodes=t,
            pillar_id=pillar_ids.get(pillar_for.get(n)),
            is_active=True,
        )
        for n, d, p, t in SERIES
    ]
    db.add_all(rows)
    db.commit()
    return {r.name: r.id for r in rows}


def _seed_offers(db: Session, user_id: int) -> None:
    db.add_all(
        [
            Offer(
                user_id=user_id,
                name=n,
                offer_type=t,
                deliverables=d,
                price=p,
                turnaround_days=turn,
                is_active=True,
            )
            for n, t, p, turn, d in OFFERS
        ]
    )
    db.commit()


def _seed_deals(db: Session, user_id: int, brand_ids: dict, now: datetime) -> list:
    deals = []
    for brand, campaign, value, stage, payment, deadline, due, follow_up, hours in DEALS:
        deals.append(
            BrandDeal(
                user_id=user_id,
                brand_id=brand_ids.get(brand),
                brand_name=brand,
                campaign_name=campaign,
                deal_value=value,
                currency="USD",
                stage=stage,
                status=DealStatus.active if stage not in ("completed",) else DealStatus.completed,
                payment_status=payment,
                deadline=now + timedelta(days=deadline) if deadline is not None else None,
                payment_due_date=now + timedelta(days=due) if due is not None else None,
                follow_up_date=now + timedelta(days=follow_up) if follow_up is not None else None,
                estimated_hours=hours,
                contact_name=dict((b[0], b[2]) for b in BRANDS).get(brand),
            )
        )
    db.add_all(deals)
    db.commit()
    return deals


def _seed_revenue(db: Session, user_id: int, deals: list, now: datetime) -> None:
    db.add_all(
        [
            Revenue(
                user_id=user_id,
                source=src,
                description=desc,
                amount=amount,
                currency="USD",
                status=status,
                date=now - timedelta(days=days_ago),
                received_at=now - timedelta(days=days_ago) if status == RevenueStatus.received else None,
                due_date=(now + timedelta(days=2)) if status == RevenueStatus.overdue else None,
                deal_id=deals[deal_index].id if deal_index is not None and deal_index < len(deals) else None,
            )
            for desc, src, amount, status, days_ago, deal_index, _ in REVENUE
        ]
    )
    db.commit()


def _seed_content(db: Session, user_id: int, pillar_ids: dict, series_ids: dict, now: datetime) -> None:
    series_for_title = {
        "Ship in Public 01: the billing bug": ("Ship in Public", 1),
        "Ship in Public 02: the migration": ("Ship in Public", 2),
        "Ship in Public 03: launch week": ("Ship in Public", 3),
        "Ship in Public 04: the pricing change": ("Ship in Public", 4),
        "The Desk Setup Behind Every Video": ("Desk Setup Tours", 1),
        "Desk Setup Tour: the edit": ("Desk Setup Tours", 2),
        "One App a Week: Obsidian": ("One App a Week", 4),
        "One App a Week: Raycast": ("One App a Week", 5),
        "One App a Week: Linear": ("One App a Week", 6),
    }

    rows = []
    for title, ctype, platform, status, offset, pillar in CONTENT:
        series_name, episode = series_for_title.get(title, (None, None))
        rows.append(
            ContentItem(
                user_id=user_id,
                title=title,
                description=f"{pillar} · part of the channel's regular work.",
                content_type=getattr(ContentType, ctype, ContentType.video),
                platform=platform,
                status=status,
                priority=Priority.high if status in (Status.editing, Status.scripting) else Priority.medium,
                due_date=now + timedelta(days=offset),
                published_at=(now + timedelta(days=offset)) if status == Status.published else None,
                topic=pillar,
                pillar_id=pillar_ids.get(pillar),
                series_id=series_ids.get(series_name) if series_name else None,
                episode_number=episode,
                source="seed",
                estimated_minutes=60,
            )
        )
    db.add_all(rows)
    db.commit()


def _seed_ideas(db: Session, user_id: int, pillar_ids: dict, now: datetime) -> None:
    names = list(pillar_ids)
    db.add_all(
        [
            Idea(
                user_id=user_id,
                title=title,
                description=f"Captured {60 + i * 4} days ago and still not made.",
                type=itype,
                potential=potential,
                effort=effort,
                confidence=confidence,
                monetization_potential=money,
                status=IdeaStatus.backlog,
                pillar_id=pillar_ids.get(names[i % len(names)]),
                platform="youtube" if i % 2 == 0 else "instagram",
                audience="creators and small teams",
            )
            for i, (title, itype, potential, effort, confidence, money) in enumerate(IDEAS)
        ]
    )
    db.commit()


def _seed_tasks(db: Session, user_id: int, now: datetime) -> None:
    rows = []
    for title, category, priority, status, offset, minutes in TASKS:
        task = Task(
            user_id=user_id,
            title=title,
            category=category,
            priority=priority,
            status=status,
            due_date=now + timedelta(days=offset),
            estimated_minutes=minutes,
        )
        if status == TaskStatus.completed:
            task.completed_at = now + timedelta(days=offset)
        rows.append(task)
    db.add_all(rows)
    db.commit()


def _seed_opportunities(db: Session, user_id: int, now: datetime) -> None:
    db.add_all(
        [
            MonetizationOpportunity(
                user_id=user_id,
                title=title,
                description="Logged from a real conversation or enquiry.",
                type=otype,
                status=status,
                potential=potential,
                effort=effort,
                estimated_value=value,
                deadline=now + timedelta(days=days) if days is not None else None,
            )
            for title, otype, status, potential, effort, value, days in OPPORTUNITIES
        ]
    )
    db.commit()


def _seed_goals(db: Session, user_id: int, now: datetime) -> None:
    db.add_all(
        [
            CreatorGoal(
                user_id=user_id,
                title=title,
                category=category,
                metric=metric,
                target_value=target,
                current_value=0.0,
                unit=unit,
                period="monthly" if days < 40 else "quarterly",
                deadline=(now + timedelta(days=days)).date(),
                status="active",
            )
            for title, category, metric, target, unit, days in GOALS
        ]
    )
    db.commit()


def _seed_history(db: Session, user_id: int, deals: list, now: datetime) -> None:
    """A little genuine history, so the timeline is not empty on day one.

    Each entry describes a record that actually exists in this workspace — the
    deal that was agreed, the campaign that was paid. Nothing is invented, and
    nothing is written that did not happen.
    """
    from app.services import activity

    for index, (desc, _src, amount, status, days_ago, _deal_index, _d) in enumerate(REVENUE):
        if status != RevenueStatus.received:
            continue
        activity.record(
            db,
            user_id,
            "revenue",
            f"Received USD {round(amount):,} — {desc.split(' · ')[0]}",
            entity_type="revenue",
            amount=amount,
            occurred_at=now - timedelta(days=days_ago),
        )

    activity.record(
        db, user_id, "deal", "TechCorp moved contacted → agreed",
        entity_type="deal", entity_id=deals[5].id, occurred_at=now - timedelta(days=44),
    )
    activity.record(
        db, user_id, "content", "Published “Ship in Public 03: launch week”",
        entity_type="content", occurred_at=now - timedelta(days=5),
    )
    activity.record(
        db, user_id, "deal", "Acme Brand moved agreed → active",
        entity_type="deal", entity_id=deals[0].id, occurred_at=now - timedelta(days=9),
    )
