from typing import List, Optional
from pydantic import BaseModel, Field

from shared_core.contracts.production_plan import ProductionPlan

__all__ = ["ProductionPlan", "StoryPlannerInput"]


class StoryPlannerInput(BaseModel):
    story_idea: str
    target_duration_seconds: int = 60
    tone: Optional[str] = None
    audience: Optional[str] = None
    # Flattened from ResearchBrief by the controller, not the ResearchBrief type
    # itself - agents.story_planner must not import agents.research (SS14: "No
    # agent imports another agent").
    research_key_facts: List[str] = Field(default_factory=list)
    research_considerations: List[str] = Field(default_factory=list)
