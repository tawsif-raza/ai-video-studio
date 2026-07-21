import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProjectState(str, Enum):
    """
    NOTE: RESEARCHED / SHOTS_COMPLETE / CAMERA_COMPLETE from ARCHITECTURE.md
    SS8's full 14-state machine are intentionally omitted here - no Research,
    Shot Planner, or Camera Planner agent exists yet (roadmap Phases 7-8).
    Add the missing states once those agents exist.
    """

    CREATED = "CREATED"
    STORY_COMPLETE = "STORY_COMPLETE"
    SCENES_COMPLETE = "SCENES_COMPLETE"
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

    source_plan_id: Optional[str] = None
    source_storyboard_id: Optional[str] = None
    source_character_sheet_id: Optional[str] = None
    source_environment_sheet_id: Optional[str] = None
    source_prompt_set_id: Optional[str] = None
    production_package_dir: Optional[str] = None
    image_manifest_path: Optional[str] = None
