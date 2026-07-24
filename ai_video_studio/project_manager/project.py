import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProjectState(str, Enum):
    """
    Implements ARCHITECTURE.md SS8's full 14-state machine. SHOTS_COMPLETE and
    CAMERA_COMPLETE were added once the Shot Planner and Camera Planner agents
    landed (roadmap Phase 7), closing the gap tracked in the Active Technical
    Debt Ledger. RESEARCHED was added once the Research agent (roadmap Phase 8)
    landed.
    """

    CREATED = "CREATED"
    RESEARCHED = "RESEARCHED"
    STORY_COMPLETE = "STORY_COMPLETE"
    SCENES_COMPLETE = "SCENES_COMPLETE"
    SHOTS_COMPLETE = "SHOTS_COMPLETE"
    CAMERA_COMPLETE = "CAMERA_COMPLETE"
    CHARACTERS_COMPLETE = "CHARACTERS_COMPLETE"
    ENVIRONMENTS_COMPLETE = "ENVIRONMENTS_COMPLETE"
    PROMPTS_COMPLETE = "PROMPTS_COMPLETE"
    PACKAGE_READY = "PACKAGE_READY"


class Project(BaseModel):
    """
    The unit of persistent work Project Manager owns end to end (ARCHITECTURE.md
    SS4/SS8). project_id is generated at create_project() time - before Story
    Planner ever runs - so it's available to key the package/project.json
    location from the very start, unlike plan.plan_id, which only exists once
    the first stage completes.
    """

    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: ProjectState = ProjectState.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    source_research_brief_id: Optional[str] = None
    source_plan_id: Optional[str] = None
    source_storyboard_id: Optional[str] = None
    source_shot_plan_id: Optional[str] = None
    source_camera_plan_id: Optional[str] = None
    source_character_sheet_id: Optional[str] = None
    source_environment_sheet_id: Optional[str] = None
    source_prompt_set_id: Optional[str] = None
    source_voice_script_id: Optional[str] = None
    production_package_dir: Optional[str] = None
    image_manifest_path: Optional[str] = None
