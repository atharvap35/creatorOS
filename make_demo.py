"""Create a fresh demo database with a fully populated creator account."""
import os
import sys

DB = os.path.abspath("demo.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"

from app.database import Base, SessionLocal, engine, _apply_sqlite_migrations  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import seed  # noqa: E402

Base.metadata.create_all(bind=engine)
_apply_sqlite_migrations()

db = SessionLocal()
u = User(email="alex@creator.dev", name="Alex Carter", hashed_password=hash_password("demo-password-123"))
db.add(u)
db.commit()
db.refresh(u)

seed.seed_db(db, u.id)
db.commit()

counts = {}
from app.models import (
    Brand, BrandDeal, ContentItem, CreatorPreference, Idea, MonetizationOpportunity,
    Offer, Revenue, Task,
)
from app.models.business import ContentSeries
from app.models.goal import CreatorGoal

for label, model in [
    ("content", ContentItem), ("tasks", Task), ("deals", BrandDeal), ("brands", Brand),
    ("offers", Offer), ("series", ContentSeries), ("revenue", Revenue), ("ideas", Idea),
    ("opportunities", MonetizationOpportunity), ("goals", CreatorGoal),
]:
    counts[label] = db.query(model).filter(model.user_id == u.id).count()

pref = db.query(CreatorPreference).filter(CreatorPreference.user_id == u.id).first()
print("seeded:", counts)
print("working_days:", pref.working_days, "hours_per_day:", pref.hours_per_day)
db.close()
print("db:", DB)
