from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class CreatorPreference(Base):
    """Persistent 'creator memory' that shapes recommendations."""

    __tablename__ = "creator_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    niche = Column(String)
    audience = Column(String)
    tone = Column(String)
    primary_goal = Column(String, default="build_business")
    platforms = Column(String, default="instagram,youtube")
    preferred_formats = Column(String, default="reel,video")
    monetization_methods = Column(String, default="")
    brand_preferences = Column(String)
    working_days = Column(String, default="0,1,2,3,4")  # Monday=0
    hours_per_day = Column(Integer, default=4)
    daily_capacity_hours = Column(Integer, default=4)
    onboarding_step = Column(Integer, default=0)
    onboarding_complete = Column(Boolean, default=False)

    # 3.0: operating rhythm + personalisation
    peak_hour = Column(Integer, default=9)            # best creative hour (0-23)
    monthly_revenue_target = Column(Integer, default=0)
    series_length_default = Column(Integer, default=5)
    timezone = Column(String, default="UTC")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def platform_list(self):
        return [p for p in (self.platforms or "").split(",") if p]

    def format_list(self):
        return [f for f in (self.preferred_formats or "").split(",") if f]

    # weekday indexes (Monday = 0), the order capacity arithmetic expects
    DAY_INDEXES = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

    def working_day_list(self):
        """Weekday indexes from the stored working days.

        Both formats are accepted so rows written before and after the settings
        page existed keep working: legacy rows stored bare indexes ("0,1,2"),
        while the settings form and the demo data store names ("Mon,Tue,Thu").
        """
        raw = (self.working_days or "").replace(" ", "")
        days = []
        for part in raw.split(","):
            if not part:
                continue
            if part.isdigit():
                index = int(part)
            else:
                index = self.DAY_INDEXES.get(part[:3].lower(), -1)
            if 0 <= index <= 6 and index not in days:
                days.append(index)
        return sorted(days)
