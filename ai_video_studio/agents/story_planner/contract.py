from typing import List, Literal, Optional
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

    # Custom Scene Count Override. "default" preserves the existing
    # LLM-judged scene count; "custom" makes scene_count a hard requirement
    # the Story Planner must hit exactly (agents/story_planner/validator.py).
    # Validated as a project-level request at the web_api boundary
    # (web_api/models.py CreateProjectRequest) - trusted as already-valid here.
    scene_count_mode: Literal["default", "custom"] = "default"
    scene_count: Optional[int] = None
