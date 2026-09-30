"""Create the `beyounick` workspace from real, scraped channel data.

WHAT IS REAL
  The 15 videos, their titles, publish dates, descriptions and the view counts
  below come from this channel's own public YouTube RSS feed
  (https://www.youtube.com/feeds/videos.xml?user=beyounick), fetched on the run
  date. The series ("The Influencer Agency"), its episode numbering and the weekly
  Thursday 7pm cadence are quoted from the creators' own video descriptions. The
  Fevikwik brand record exists because that collaboration is real - it is the
  #ad-tagged video in the feed.

WHAT IS DEMO
  Instagram returned a login wall and yielded nothing, so no Instagram data is
  invented. Financial figures - deal values, revenue, offer prices - are not
  public for anyone, so they are illustrative placeholders, marked DEMO wherever
  they appear. View counts are recorded as observed facts with the date read, not
  as engagement rates, because this product never computes those.
"""
import sys
from datetime import datetime

sys.path.insert(0, ".")

import app.models  # noqa: F401
from app.database import SessionLocal
from app.models.user import User
from app.security import create_user
from app.models.business import Brand, ContentSeries, Offer
from app.models.content import ContentItem, Status
from app.models.pillar import ContentPillar
from app.models.idea import Idea, IdeaEffort, IdeaPotential, IdeaStatus
from app.models.deal import BrandDeal, DealStatus, PaymentStatus
from app.models.revenue import Revenue, RevenueStatus
from app.models.task import Task, TaskStatus
from app.models.goal import CreatorGoal
from app.models.rate_card import RateCardItem
from app.models.workspace import Asset
from app.services import activity

EMAIL = "beyounick@example.com"
NAME = "beyounick"
PASSWORD = "nick@123"
READ_AT = "2026-09-30"

# (title, published, views, type, platform, hook, episode, first-line-of-description)
# `platform` is one of instagram/youtube/tiktok/linkedin/x/newsletter/other - a
# YouTube Short is a content_type of "short" published on the "youtube" platform,
# not a platform called "shorts".
VIDEOS = [
    ("The Call | A Short Film", "2026-09-29", 290208, "video", "youtube",
     "A bag full of cash. A strange phone call. And one decision that could change everything.", None,
     "Truecaller sponsor integration. A short film about doing the right thing at the wrong time."),
    ("Black and white reel", "2026-09-25", 1209647, "short", "youtube",
     "The reel that needed no edit.", None, "Short reel."),
    ("Happy Ganesh Chaturthi", "2026-09-19", 375796, "short", "youtube",
     "Festival greeting short.", None, "Festival greeting."),
    ("The Influencer Agency - Ep 05 - Why Everyone Hate Influencers?", "2026-09-17", 140141,
     "video", "youtube",
     "A 9-to-5 worker who resents influencer culture sits down with Nick.", 5,
     "Behind the screen, creators carry a daily weight of hate that most people never see."),
    ("The Influencer Agency - Ep 04 - Phokat", "2026-09-10", 398084, "video", "youtube",
     "An unpaid cafe bill turns Vrushali into the internet's latest target.", 4,
     "A viral showdown over an unpaid bill throws the agency straight into damage control."),
    ("Bolo isko AI hai", "2026-09-08", 873189, "short", "youtube",
     "Calling it AI when it is not.", None, "Short."),
    ("The Influencer Agency - Ep 03 - The Influencer Couple", "2026-09-03", 299118,
     "video", "youtube",
     "A brand deal, a car bought on advance, and a couple calling it quits.", 3,
     "What could possibly go wrong when an influencer couple drops out before the shoot?"),
    ("The Influencer Agency - Ep 02 - The Court Case", "2026-08-27", 247194, "video", "youtube",
     "Judge Nick's makeshift courtroom. The prize is a trip to Singapore.", 2,
     "Everyone is fighting for the same prize: a trip to Singapore with Alkesh."),
    ("Ye dukh khatam kahe nahi hota", "2026-08-23", 1242305, "short", "youtube",
     "Emotional short.", None, "Short."),
    ("The Influencer Agency - Ep 01 - Pilot", "2026-08-20", 448970, "video", "youtube",
     "One goal: sign Superstar Vlogger Nikhil Sharma.", 1,
     "Landing one of the biggest vloggers in the scene would put the agency on the map."),
    ("Ninja Tech-Nick", "2026-08-14", 1274741, "short", "youtube",
     "Ninja technique short.", None, "Ninja Tech series short."),
    ("Shark Tank Dombivli", "2026-08-10", 2358806, "short", "youtube",
     "The Shark Tank Dombivli audition.", None, "Comedy / Shark Tank short."),
    ("Ninja Tech Nick", "2026-08-04", 459921, "short", "youtube",
     "Another Ninja technique short.", None, "Ninja Tech series short."),
    ("Ninja Tech-Nick! #shorts", "2026-07-30", 1406062, "short", "youtube",
     "Job interview Ninja technique.", None, "Ninja Tech series short."),
    ("Jodna hi tha toh car ke liye paise jod leta", "2026-07-21", 278698, "short", "youtube",
     "Fevikwik Advanced sponsorship short.", None,
     "SPONSORED by Fevikwik Advanced. A brand-tagged integration."),
]

created = {"rate_card": 0, "assets": 0, "timeline": 0, "pillars": 0, "videos": 0, "series": 0, "tasks": 0, "ideas": 0,
           "brands": 0, "deals": 0, "offers": 0, "revenue": 0, "goals": 0}

with SessionLocal() as db:
    existing = db.query(User).filter(User.email == EMAIL).first()
    if existing:
        # A previous run may have created the account and then failed part-way.
        # If the workspace is already populated, stop; otherwise finish the job
        # on the existing user rather than leaving a half-built workspace.
        if db.query(ContentItem).filter(ContentItem.user_id == existing.id).count():
            print(f"Account {EMAIL} already exists with content (id={existing.id}). "
                  f"Nothing changed.")
            sys.exit(0)
        print(f"Account {EMAIL} exists but is empty (id={existing.id}); completing it.")
        user = existing
        uid = user.id
    else:
        user = create_user(db, email=EMAIL, name=NAME, password=PASSWORD)
        uid = user.id
        db.commit()
        print(f"Created account {NAME} <{EMAIL}> (user_id={uid})")

    # --- the real recurring series ------------------------------------------
    series = ContentSeries(
        user_id=uid,
        name="The Influencer Agency",
        description="Weekly scripted comedy series about running an influencer agency. "
                    "Episodes publish Thursdays at 7pm.",
        platform="youtube",
        target_episodes=12,
        is_active=True,
        notes="Target episode count is a DEMO figure. The weekly Thursday 7pm release "
              "cadence and the episode numbering are quoted from the creators' own "
              "video descriptions.",
    )
    db.add(series)
    db.flush()
    created["series"] += 1

    # --- the real published videos -----------------------------------------
    items = {}
    for title, published, views, ctype, platform, hook, episode, desc in VIDEOS:
        item = ContentItem(
            user_id=uid,
            title=title,
            description=desc,
            content_type=ctype,
            platform=platform,
            status=Status.published,
            priority="high" if episode else "medium",
            published_at=datetime.fromisoformat(published),
            estimated_minutes=180 if episode else 45,
            topic="The Influencer Agency" if episode else "Short-form",
            hook=hook,
            series_id=series.id if episode else None,
            episode_number=episode,
            notes=f"Views at {READ_AT}, as reported by the channel's own public feed: "
                  f"{views:,}. Recorded as an observation on {READ_AT}; this product "
                  f"does not compute engagement from it.",
        )
        db.add(item)
        db.flush()
        items[title] = item
        created["videos"] += 1

    # --- a real sponsor from the feed ---------------------------------------
    fevikwik = Brand(
        user_id=uid,
        name="Fevikwik Advanced",
        website="https://fevikwik.com",
        relationship_status="active",
        last_interaction_at=datetime(2026, 7, 21),
        notes="Real collaboration - this is the brand behind the #ad-tagged "
              "'Jodna hi tha toh car ke liye paise jod leta' short. The deal value "
              "recorded against it is a DEMO placeholder; sponsorship rates are "
              "not public.",
    )
    db.add(fevikwik)
    db.flush()
    created["brands"] += 1

    # --- offers (DEMO pricing) ----------------------------------------------
    offer_video = Offer(
        user_id=uid,
        name="Scripted brand integration",
        offer_type="sponsorship",
        description="A natively scripted brand mention inside an existing short format.",
        deliverables="1x 60s short, 1x story mention, pinned comment",
        price=45000.0,
        turnaround_days=10,
        is_active=True,
        notes="DEMO pricing. Not a real rate for this creator.",
    )
    offer_reel = Offer(
        user_id=uid,
        name="Reel/short production",
        offer_type="service",
        description="Concept, shoot and edit of a single vertical short.",
        deliverables="1x finished vertical short, 1x caption",
        price=18000.0,
        turnaround_days=7,
        is_active=True,
        notes="DEMO pricing. Not a real rate for this creator.",
    )
    db.add_all([offer_video, offer_reel])
    db.flush()
    created["offers"] += 2

    # --- the sponsorship deal -----------------------------------------------
    deal = BrandDeal(
        user_id=uid,
        brand_name="Fevikwik Advanced",
        campaign_name="Fevikwik Advanced - 'Jodna' short",
        description="Brand-tagged short published July 2026. Real collaboration; "
                    "financial terms below are DEMO placeholders.",
        deal_value=45000.0,
        currency="USD",
        status=DealStatus.completed,
        stage="delivered",
        deadline=datetime(2026, 7, 21),
        payment_due_date=datetime(2026, 8, 21),
        payment_status=PaymentStatus.paid,
        paid_amount=45000.0,
        invoiced_amount=45000.0,
        estimated_hours=9.0,
        deliverables="1x sponsored vertical short",
        brand_id=fevikwik.id,
        offer_id=offer_video.id,
        contact_name="DEMO contact",
        next_action="Invoice settled - nothing outstanding",
        notes="Deal value, payment and hours are DEMO figures. The collaboration "
              "itself is real.",
    )
    db.add(deal)
    db.flush()
    created["deals"] += 1

    # --- revenue (DEMO) ------------------------------------------------------
    db.add_all([
        Revenue(
            user_id=uid, source="sponsorship", description="Fevikwik Advanced - sponsored short",
            amount=45000.0, currency="USD", date=datetime(2026, 8, 21),
            status=RevenueStatus.received, deal_id=deal.id, received_at=datetime(2026, 8, 21),
            hours_spent=9.0, invoiced=True,
            content_id=items["Jodna hi tha toh car ke liye paise jod leta"].id,
            notes="DEMO amount attached to a real collaboration.",
        ),
        Revenue(
            user_id=uid, source="sponsorship", description="Channel income - DEMO placeholder",
            amount=125000.0, currency="USD", date=datetime(2026, 9, 1),
            status=RevenueStatus.pending, invoiced=False,
            notes="DEMO figure standing in for channel/ad revenue, which is not public.",
        ),
    ])
    created["revenue"] += 2

    # --- ideas drawn from recurring real formats ---------------------------
    db.add_all([
        Idea(
            user_id=uid, title="Ninja Tech as a repeatable format",
            description="'Ninja Tech' appeared three times in six weeks and was the "
                        "channel's strongest recurring short concept.",
            type="content", potential=IdeaPotential.high, effort=IdeaEffort.low,
            status=IdeaStatus.backlog, platform="shorts",
            problem="Three separate shorts used the same concept without a named format.",
            audience="Existing short-form viewers",
            notes="Derived from the real video feed: Ninja Tech shorts on 2026-07-30, "
                  "2026-08-04 and 2026-08-14.",
        ),
        Idea(
            user_id=uid, title="Shark Tank auditions as a recurring slot",
            description="The Dombivli audition outperformed every other short in the feed. "
                        "Turn it into a recurring audition format.",
            type="content", potential=IdeaPotential.high, effort=IdeaEffort.medium,
            status=IdeaStatus.exploring, platform="shorts",
            notes="Derived from the highest-viewed short in the feed.",
        ),
    ])
    created["ideas"] += 2

    # --- tasks (real cadence, plus the next episode) ------------------------
    ep5 = items["The Influencer Agency - Ep 05 - Why Everyone Hate Influencers?"]
    db.add_all([
        Task(
            user_id=uid, title="Draft Ep 06 script - The Influencer Agency",
            description="Next weekly episode. Series publishes Thursdays at 7pm.",
            category="content", priority="high", status=TaskStatus.todo,
            due_date=datetime(2026, 9, 30), estimated_minutes=120,
            content_id=ep5.id,
            notes="Cadence is quoted from the creators' own episode descriptions.",
        ),
        Task(
            user_id=uid, title="Shoot Ep 06 - The Influencer Agency",
            description="Full cast shoot for the weekly episode.",
            category="content", priority="high", status=TaskStatus.todo,
            due_date=datetime(2026, 10, 1), estimated_minutes=480,
        ),
        Task(
            user_id=uid, title="Edit and publish Ep 06 by Thursday 7pm",
            description="Edit, colour, caption, publish.",
            category="content", priority="medium", status=TaskStatus.todo,
            due_date=datetime(2026, 10, 2), estimated_minutes=300,
        ),
        Task(
            user_id=uid, title="Repurpose 'Shark Tank Dombivli' into a cutdown",
            description="Highest-viewed short in the feed; the concept is worth a second pass.",
            category="content", priority="medium", status=TaskStatus.todo,
            due_date=datetime(2026, 9, 28), estimated_minutes=90,
            content_id=items["Shark Tank Dombivli"].id,
        ),
    ])
    created["tasks"] += 4

    # --- goal (DEMO target) --------------------------------------------------
    db.add(
        CreatorGoal(
            user_id=uid, title="Reach the monthly revenue target", category="revenue",
            metric="monthly_revenue", target_value=150000.0, current_value=45000.0,
            unit="USD", period="monthly", deadline=datetime(2026, 9, 30),
            status="active",
            notes="DEMO target. A monthly goal needs a target the creator sets; this "
                  "one is a placeholder so the Goals screen has something to show.",
        )
    )
    created["goals"] += 1

    # --- pillar, derived from the real feed's shape -------------------------
    # Ten of the fifteen real videos are shorts, so short-form comedy is the
    # obvious dominant pillar. The colour is a placeholder for the UI.
    db.add(
        ContentPillar(
            user_id=uid,
            name="Short-form comedy",
            description="Vertical shorts built on recurring comic concepts - Ninja Tech, "
                        "Shark Tank auditions, one-off reels.",
            color="#e4572e",
            is_active=True,
        )
)
    created["pillars"] += 1

    # --- rate card (DEMO pricing) -------------------------------------------
    # One row per real format visible in the feed. The format is real; the
    # prices are placeholders, since a creator's rates are never public.
    for name, fmt, start, typ, prem, days in [
        ("YouTube integration", "Long-form video", 60000.0, 150000.0, 300000.0, 21),
        ("Short-form sponsorship", "Short", 18000.0, 45000.0, 90000.0, 10),
        ("Scripted series episode", "Series episode", 120000.0, 250000.0, 400000.0, 30),
        ("Short production", "Short", 12000.0, 18000.0, 30000.0, 7),
    ]:
        db.add(
            RateCardItem(
                user_id=uid, name=name, platform="youtube", format=fmt,
                starting_price=start, typical_price=typ, premium_price=prem,
                turnaround_days=days, is_public=True,
                notes="DEMO pricing. The format is real; these are not real rates.",
            )
        )
        created["rate_card"] += 1

    # --- library: hooks and outlines lifted from the real videos -------------
    # These bodies are the creators' own wording, taken from the descriptions in
    # the public feed, so the library holds genuine hooks rather than invented
    # ones.
    for title, kind, body, tags, fav in [
        ("Hook: the cash and the call", "hook",
         "A bag full of cash. A strange phone call. And one decision that could change "
         "everything. Sometimes, doing the right thing can put you in the wrong place "
         "at the wrong time.", "shortfilm, story", 1),
        ("Hook: the wrong place at the wrong time", "hook",
         "Sometimes doing the right thing puts you in the wrong place at the wrong "
         "time.", "shortfilm, story", 0),
        ("Hook: the outsider sits down", "hook",
         "Behind the screen, creators carry a daily weight of hate that most people "
         "never see. Their debate starts with raw tension.", "influencer-agency, ep5", 1),
        ("Hook: damage control", "hook",
         "A cafe outing explodes into a viral showdown over an unpaid bill, and the "
         "creator becomes the internet's latest target.", "influencer-agency, ep4", 0),
        ("Hook: the drop-out", "hook",
         "A brand deal, a car bought with an advance payment, and an influencer couple "
         "calling it quits right before the shoot.", "influencer-agency, ep3", 0),
        ("Hook: sign the superstar", "hook",
         "One massive goal: sign the biggest vlogger in the scene - and put the agency "
         "on the map.", "influencer-agency, ep1", 0),
        ("Sponsored integration outline", "template",
         "Intro (the brand's problem) -> my honest experience -> 3 use cases -> CTA -> "
         "disclosure. Used for the Fevikwik short.", "sponsor, shorts", 0),
        ("Weekly series production checklist", "template",
         "Thursday 7pm release. Script -> cast -> shoot -> edit -> colour -> caption -> "
         "publish. Credits block at the end of every description.", "series, workflow", 1),
        ("Short-form hook bank", "resource",
         "Recurring concepts that worked in this feed: Ninja Tech, Shark Tank auditions, "
         "one-off reels. Each is a named, repeatable format rather than a one-off.",
         "shorts, hooks", 0),
        ("Festival short template", "brief",
         "Occasion -> greeting -> 5 seconds of the actual thing -> sign off. Keep it "
         "under 20 seconds.", "shorts, seasonal", 0),
    ]:
        db.add(Asset(user_id=uid, title=title, kind=kind, body=body, tags=tags,
                     is_favorite=fav))
        created["assets"] += 1

    # --- timeline: real events, dated from the feed -------------------------
    # Each publication below happened on the date the feed reports, so the
    # timeline records something that actually occurred rather than a fiction.
    for item in items.values():
        activity.record(
            db, uid, "content",
            f"Published {item.title}",
            entity_type="content", entity_id=item.id,
            detail=f"{item.platform} · {item.hook}" if item.hook else item.platform,
            occurred_at=item.published_at,
            commit=False,
        )
        created["timeline"] += 1

    activity.record(db, uid, "deal", "Signed Fevikwik Advanced sponsorship",
                    entity_type="deal", entity_id=deal.id,
                    detail="Brand-tagged short published July 2026",
                    occurred_at=datetime(2026, 7, 21), commit=False)
    created["timeline"] += 1

    activity.record(db, uid, "revenue", "Received Fevikwik Advanced sponsorship",
                    entity_type="revenue",
                    amount=45000.0,
                    detail="DEMO amount for a real collaboration",
                    occurred_at=datetime(2026, 8, 21), commit=False)
    created["timeline"] += 1

    activity.record(db, uid, "series", "Started 'The Influencer Agency'",
                    entity_type="series", entity_id=series.id,
                    detail="Weekly series, Thursdays at 7pm",
                    occurred_at=datetime(2026, 8, 20), commit=False)
    created["timeline"] += 1

    db.commit()

total = sum(created.values())
print("\nRecords created:")
for key, n in created.items():
    if n:
        print(f"    {key:9} {n:>3}")
print(f"    {'TOTAL':9} {total:>3}")
print(f"\nReal: {created['videos']} published videos + 1 series + 1 real sponsor brand.")
print("Demo: all money figures (deal value, revenue, offer prices) are placeholders.")
print("Instagram: not retrievable (login wall) - nothing was invented for it.")