from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.opportunity import OpportunityType, OpportunityPotential, OpportunityEffort, OpportunityStatus

class OpportunityBase(BaseModel):
    title: str
    description: Optional[str] = None
    type: OpportunityType = OpportunityType.other
    estimated_value: float = 0.0
    effort: OpportunityEffort = OpportunityEffort.medium
    potential: OpportunityPotential = OpportunityPotential.medium
    status: OpportunityStatus = OpportunityStatus.idea
    source: str = "creator_input"
    next_action: Optional[str] = None

class OpportunityCreate(OpportunityBase):
    pass

class Opportunity(OpportunityBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
